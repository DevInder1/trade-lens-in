import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

PROVIDERS = {
    "Ollama (free, runs on this Mac)": {
        "env": None,
        "models": [],
        "base_url": OLLAMA_URL.rstrip("/") + "/v1",
        "key_url": "https://ollama.com/download",
        "note": "Free, private and unlimited. Nothing leaves your Mac. Slower than cloud AI.",
    },
    "Gemini (Google)": {
        "env": "GEMINI_API_KEY",
        "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"],
        "key_url": "https://aistudio.google.com/apikey",
        "note": "Free tier available. No card needed.",
    },
    "OpenRouter (free models)": {
        "env": "OPENROUTER_API_KEY",
        "models": [],
        "base_url": "https://openrouter.ai/api/v1",
        "key_url": "https://openrouter.ai/keys",
        "note": "Free key. The list shows only free models (limited requests per day).",
    },
    "Groq (free tier)": {
        "env": "GROQ_API_KEY",
        "models": [],
        "base_url": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
        "note": "Free key, very fast. Free tier has per-minute limits.",
    },
    "Claude (Anthropic)": {
        "env": "ANTHROPIC_API_KEY",
        "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
        "key_url": "https://console.anthropic.com/settings/keys",
        "note": "Pay as you go, billed separately from a Claude.ai subscription.",
    },
    "ChatGPT (OpenAI)": {
        "env": "OPENAI_API_KEY",
        "models": ["gpt-6-luna", "gpt-6-sol"],
        "key_url": "https://platform.openai.com/api-keys",
        "note": "Pay as you go, billed separately from a ChatGPT Plus subscription.",
    },
}

CLAUDE_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

ANALYSTS = ["Technical", "Fundamentals", "News & Macro", "Sentiment"]
RATINGS = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]
DECISION_KEYS = ["RATING", "DECISION", "CONFIDENCE", "ACTION", "ENTRY", "STOP-LOSS", "TARGET", "HORIZON", "PROPOSAL"]

SYSTEM = (
    "You are a member of an equity research and trading team covering Indian-listed stocks and indices on NSE and "
    "BSE. All prices are in Indian rupees (₹). Work only from the data you are given; when something is missing, say "
    "so instead of guessing, and never invent numbers. Write in plain, simple English that a beginner can follow, "
    "using short headings and bullet points. This is educational research, not personal investment advice."
)


class AIError(Exception):
    pass


def _friendly(provider: str, exc: Exception) -> str:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    name = type(exc).__name__
    text = str(exc).lower()
    key_invalid = "api key not valid" in text or "api_key_invalid" in text
    if status in (401, 403) or key_invalid or "Authentication" in name or "PermissionDenied" in name:
        return f"{provider} rejected the API key. Check that it is correct and active."
    if status == 429 or "RateLimit" in name:
        return f"{provider} says you hit a usage or quota limit. Wait a minute, use Quick mode, or check your plan."
    if status == 404 or "NotFound" in name:
        return f"{provider} does not recognise that model name. Pick another model."
    if ("Connection" in name or "Timeout" in name) and provider.startswith("Ollama"):
        return "Ollama isn't answering. Open the Ollama app on your Mac and try again."
    if "Connection" in name or "Timeout" in name:
        return f"Could not reach {provider}. Check your internet connection."
    message = getattr(exc, "message", None) or str(exc)
    return f"{provider} error: {message[:300]}"


def _ask_claude(model, api_key, prompt):
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, max_retries=3)
    params = dict(model=model, max_tokens=16000, system=SYSTEM, output_config={"effort": "medium"},
                  messages=[{"role": "user", "content": prompt}])
    if model in CLAUDE_FALLBACK_MODELS:
        response = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params)
    else:
        response = client.messages.create(**params)
    if response.stop_reason == "refusal":
        raise AIError("Claude declined to answer this request.")
    return "".join(block.text for block in response.content if block.type == "text")


def _ask_gemini(model, api_key, prompt):
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(system_instruction=SYSTEM)
    for attempt in range(3):
        try:
            return client.models.generate_content(model=model, contents=prompt, config=config).text or ""
        except errors.APIError as exc:
            if exc.code in (429, 500, 503) and attempt < 2:
                time.sleep(15 * (attempt + 1))
                continue
            raise
    return ""


def _ask_openai(model, api_key, prompt):
    from openai import OpenAI

    client = OpenAI(api_key=api_key, max_retries=3)
    response = client.responses.create(model=model, instructions=SYSTEM, input=prompt)
    return response.output_text or ""


def _compatible(provider):
    local = provider.startswith("Ollama")

    def asker(model, api_key, prompt, deep=False):
        from openai import OpenAI

        client = OpenAI(api_key=api_key or "local", base_url=PROVIDERS[provider]["base_url"], max_retries=2,
                        timeout=900 if local else 300)
        options = {} if deep or not local else {"reasoning_effort": "none"}
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        for _ in range(2):
            response = client.chat.completions.create(model=model, messages=messages, **options)
            text = response.choices[0].message.content if response.choices else ""
            text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
            if text.strip():
                return text
            options = {"reasoning_effort": "none"} if local else options
        return ""
    return asker


COMPATIBLE = {name for name, spec in PROVIDERS.items() if "base_url" in spec}
ASKERS = {
    "Claude (Anthropic)": _ask_claude,
    "Gemini (Google)": _ask_gemini,
    "ChatGPT (OpenAI)": _ask_openai,
    **{name: _compatible(name) for name in COMPATIBLE},
}


def _get_json(url: str, key: str | None = None, timeout: float = 5):
    headers = {"User-Agent": "trade-lens-in"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with urlopen(Request(url, headers=headers), timeout=timeout) as resp:
        return json.loads(resp.read())


def live_models(provider: str, api_key: str | None = None) -> list[str]:
    try:
        if provider.startswith("Ollama"):
            return [m["name"] for m in _get_json(OLLAMA_URL.rstrip("/") + "/api/tags", timeout=3).get("models", [])]
        if provider.startswith("OpenRouter"):
            data = _get_json("https://openrouter.ai/api/v1/models").get("data", [])
            return sorted(m["id"] for m in data
                          if str(m.get("pricing", {}).get("prompt")) in ("0", "0.0")
                          and str(m.get("pricing", {}).get("completion")) in ("0", "0.0"))
        if provider.startswith("Groq") and api_key:
            data = _get_json("https://api.groq.com/openai/v1/models", api_key).get("data", [])
            return sorted(m["id"] for m in data if m.get("active", True) and "whisper" not in m["id"]
                          and "tts" not in m["id"] and "guard" not in m["id"])
    except Exception:
        return []
    return PROVIDERS.get(provider, {}).get("models", [])


def needs_key(provider: str) -> bool:
    return bool(PROVIDERS.get(provider, {}).get("env"))


def ask(provider: str, model: str, api_key: str, prompt: str, deep: bool = False) -> str:
    asker = ASKERS[provider]
    try:
        text = asker(model, api_key, prompt, deep=True) if deep and provider in COMPATIBLE else asker(model, api_key, prompt)
    except AIError:
        raise
    except Exception as exc:
        raise AIError(_friendly(provider, exc)) from None
    if not text.strip():
        raise AIError(f"{provider} returned an empty answer. Try again or pick another model.")
    return text.strip()


def _parallel(provider, model, api_key, prompts: dict) -> dict:
    workers = 1 if not needs_key(provider) else min(4, len(prompts))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {name: pool.submit(ask, provider, model, api_key, prompt) for name, prompt in prompts.items()}
        return {name: future.result() for name, future in futures.items()}


def call_count(analysts: list[str], rounds: int, quick: bool) -> int:
    return 1 if quick else len(analysts) + 2 * rounds + 1 + 3 * rounds + 1


def _dump(value) -> str:
    return json.dumps(value, indent=1, default=str, ensure_ascii=False)


def _technical_data(data: dict) -> str:
    return (
        f"Instrument: {data['name']} ({data['symbol']})\n"
        f"Latest snapshot:\n{_dump(data['snapshot'])}\n\n"
        f"Performance vs NIFTY 50 (percentage points): {_dump(data['relative'])}\n\n"
        f"Rule-based signals (historically close to a coin flip, so give them little weight):\n"
        f"{_dump(data['signals'])}\n\n{_evidence(data)}"
        f"Last 30 trading days:\n{data['recent'].round(2).to_csv()}"
    )


def _evidence(data: dict) -> str:
    extras = data.get("extras") or {}
    lines = []
    if extras.get("momentum") is not None:
        lines.append(f"12-month momentum (skipping the last month) vs NIFTY: {extras['momentum']:+.1f} percentage "
                     "points. In our tests on large Indian stocks, the strongest 20% by this measure beat NIFTY over "
                     "the next 3 months 54% of the time; it is the most reliable signal we have, but still modest.")
    if extras.get("delivery"):
        d = extras["delivery"]
        lines.append(f"NSE delivery % on {d['date']}: {d['delivery_pct']:.1f}% vs {d['avg_pct']:.1f}% average of the "
                     f"previous sessions ({d['verdict']}: {d['detail']})")
    if extras.get("fo"):
        f = extras["fo"]
        pcr = f", put-call ratio {f['pcr']:.2f}" if f["pcr"] is not None else ""
        lines.append(f"NSE F&O on {f['date']}: {f['buildup']} (futures price {f['price_change_pct']:+.2f}%, open "
                     f"interest {f['oi_change_pct']:+.2f}%{pcr}). {f['detail']}")
    if extras.get("verify"):
        lines.append(f"Data check: {extras['verify']['text']}")
    return ("Official NSE data and evidence-based measures:\n" + "\n".join(f"- {line}" for line in lines) + "\n\n"
            if lines else "")


def _fundamental_data(data: dict) -> str:
    if data.get("as_of"):
        return "Not used in historical tests: only today's figures exist, which would reveal the future."
    if not data["fundamentals"]:
        return "No fundamental data is available (this may be an index)."
    return _dump(data["fundamentals"])


def _header(data: dict) -> str:
    if not data.get("as_of"):
        return ""
    return (f"IMPORTANT: this is a historical test. Today is {data['as_of']}. Use only the data below and ignore "
            "anything you may know about events after this date.\n\n")


def _memory(data: dict) -> str:
    if not data.get("memory"):
        return ""
    return ("\n\nOUR TEAM'S PAST DECISIONS AND LESSONS (learn from them; do not repeat past mistakes):\n"
            f"{data['memory']}")


def _headlines(items: list[dict]) -> str:
    if not items:
        return "None found."
    return "\n".join(f"- [{n['date']}] {n['title']} ({n['publisher']}) {n.get('summary', '')[:300]}" for n in items)


def _news_data(data: dict) -> str:
    return (
        f"Company headlines:\n{_headlines(data['news'])}\n\n"
        f"Indian market headlines (last 7 days):\n{_headlines(data['market_news'])}\n\n"
        f"Macro dashboard:\n{_dump(data['macro'])}\n{data['vix'] or ''}"
    )


def _sentiment_data(data: dict) -> str:
    social = data["social"]
    st = social["stocktwits"]
    rd = social["reddit"]
    parts = []
    if st["available"] and st["messages"]:
        lines = "\n".join(f"- [{m['date']}] ({m['sentiment'] or 'unlabelled'}, {m['likes']} likes) {m['body'][:200]}"
                          for m in st["messages"][:15])
        parts.append(f"StockTwits: {len(st['messages'])} recent messages, {st['bullish']} labelled Bullish, "
                     f"{st['bearish']} labelled Bearish.\n{lines}")
    else:
        parts.append("StockTwits: no messages available.")
    if rd["posts"]:
        lines = "\n".join(f"- [{p['date']}] r/{p['subreddit']}: {p['title']} — {p['text'][:160]}"
                          for p in rd["posts"][:12])
        parts.append(f"Reddit (Indian investing communities, last 30 days): {len(rd['posts'])} posts.\n{lines}")
    elif rd.get("error"):
        parts.append(f"Reddit: no posts available ({rd['error']}).")
    else:
        parts.append("Reddit: no posts in the last 30 days.")
    return "\n\n".join(parts)


def _risk_facts(data: dict) -> str:
    s = data["snapshot"]
    facts = [
        f"Last close ₹{s.get('Close')}, ATR(14) ₹{s.get('ATR')} ({s.get('atr_pct') and round(s['atr_pct'], 2)}% of price)",
        f"52-week range ₹{s.get('low_52w')} – ₹{s.get('high_52w')}",
        f"Average daily traded value (20 days): ₹{data['liquidity']:,.0f}" if data.get("liquidity") else "",
        data["vix"] or "",
    ]
    t = data.get("turbulence")
    if t:
        facts.append(f"Market turbulence index (how unusual recent market moves are vs the past year): {t['label']} "
                     f"(5-day average at the {t['five_day_percentile']:.0f}th percentile of the last 2 years) — "
                     f"{t['note']}")
    return "\n".join(f for f in facts if f)


ANALYST_PROMPTS = {
    "Technical": lambda d: (
        "Act as the Technical Analyst. Analyse trend, momentum, volatility, volume, relative strength versus NIFTY and "
        f"key support/resistance levels from this data. End with a one-line technical bias.\n\n{_technical_data(d)}"
    ),
    "Fundamentals": lambda d: (
        f"Act as the Fundamentals Analyst for {d['name']} ({d['symbol']}). Judge valuation, profitability, growth, "
        "balance-sheet strength and ownership, comparing with what is typical for its sector in India where you can. "
        f"Flag any red flags. End with a one-line fundamental bias.\n\n{_fundamental_data(d)}"
    ),
    "News & Macro": lambda d: (
        f"Act as the News & Macro Analyst for {d['name']} ({d['symbol']}). Using the company headlines, Indian market "
        "headlines and the macro dashboard (NIFTY trend, India VIX, USD/INR, crude, gold, US markets and yields), "
        "explain which events and macro forces matter most for this stock and why (for example crude for oil "
        "marketers, paints and airlines; USD/INR for IT exporters; rates for banks). Note upcoming catalysts. "
        f"End with a one-line news/macro bias.\n\n{_news_data(d)}"
    ),
    "Sentiment": lambda d: (
        f"Act as the Social Sentiment Analyst for {d['name']} ({d['symbol']}). From the StockTwits and Reddit posts "
        "below, gauge retail investor mood: how much chatter there is, whether it leans bullish or bearish, the "
        "recurring themes, and any sign of hype or panic. Treat social chatter as a weak, noisy signal and say how "
        f"much weight it deserves. End with a one-line sentiment bias.\n\n{_sentiment_data(d)}"
    ),
}

RESEARCH_ROLES = {
    "Bull Researcher": (
        "You are the Bull Researcher. Argue that this stock is likely to go UP over the coming weeks. Use specific "
        "numbers from the analyst reports. Be honest about weak points but explain why the upside outweighs them."
    ),
    "Bear Researcher": (
        "You are the Bear Researcher. Argue that this stock is likely to go DOWN or underperform over the coming "
        "weeks. Use specific numbers from the analyst reports. Be honest about strong points but explain why the "
        "downside outweighs them."
    ),
}

RISK_ROLES = {
    "Aggressive Risk Analyst": (
        "You are the Aggressive Risk Analyst. Champion the high-reward version of the trader's plan: argue where it "
        "is too cautious and where a larger position, earlier entry or wider target is justified. Stay grounded in "
        "the numbers."
    ),
    "Conservative Risk Analyst": (
        "You are the Conservative Risk Analyst. Protect capital first: point out where the trader's plan risks too "
        "much given volatility (ATR, India VIX), liquidity, concentration in the user's portfolio and downside "
        "scenarios. Propose tighter stops, smaller size or waiting where justified."
    ),
    "Neutral Risk Analyst": (
        "You are the Neutral Risk Analyst. Weigh the aggressive and conservative views fairly and propose a balanced "
        "adjustment to the trader's plan."
    ),
}

TRADER_FORMAT = (
    "Start your answer with exactly this line:\n"
    "PROPOSAL: Buy or Add or Hold or Trim or Sell or Avoid\n"
    "(Use Add, Trim or Sell only if the user holds shares; use Buy or Avoid for a new position.)\n\n"
    "Then write these sections:\n"
    "## Who won the debate and why\n"
    "## Plan (entry zone, stop-loss, target 1 and target 2 in ₹, and quantity in shares; never exceed the rule-based "
    "maximum quantity when one is given; if the user holds shares, say exactly what to do with them)\n"
    "## Timing (act now, wait for a price level, or wait for an event)\n"
    "## Reward-to-risk (calculate it from the entry, stop-loss and first target)\n"
)

DECISION_FORMAT = (
    "Start your answer with exactly these lines, one value each:\n"
    "RATING: Buy or Overweight or Hold or Underweight or Sell\n"
    "DECISION: Approve or Modify or Reject (the trader's proposal)\n"
    "CONFIDENCE: Low or Medium or High\n"
    "ACTION: one short sentence saying exactly what to do, with share quantity and ₹ prices where relevant\n"
    "ENTRY: price or range in ₹, or n/a\n"
    "STOP-LOSS: price in ₹, or n/a\n"
    "TARGET: price or prices in ₹, or n/a\n"
    "HORIZON: the time frame (for example 2-6 weeks)\n\n"
    "Rating scale: Buy = strong case to buy or add now; Overweight = lean positive, build gradually; Hold = keep "
    "what you have, no new position; Underweight = lean negative, reduce gradually; Sell = exit or avoid.\n\n"
    "Then write these sections:\n"
    "## Summary (3-4 sentences)\n"
    "## Why (the strongest 3-5 reasons)\n"
    "## Main risks\n"
    "## What would change this decision\n"
)


def _transcript(entries: list[dict]) -> str:
    return "\n\n".join(f"--- {e['speaker']} (round {e['round']}) ---\n{e['text']}" for e in entries)


def _debate(provider, model, api_key, roles: dict, context: str, rounds: int, notify, label: str) -> list[dict]:
    entries = []
    for r in range(1, rounds + 1):
        notify(f"{label}: round {r} of {rounds}")
        if entries:
            ask_for = (f"Debate so far:\n{_transcript(entries)}\n\nThis is round {r} of {rounds}. Rebut the other "
                       "side's latest points directly, then add anything new. Keep it under 250 words.")
        else:
            ask_for = f"This is round 1 of {rounds}. Give your opening argument in under 300 words."
        prompts = {name: f"{role}\n\n{context}\n\n{ask_for}" for name, role in roles.items()}
        answers = _parallel(provider, model, api_key, prompts)
        entries += [{"speaker": name, "round": r, "text": answers[name]} for name in roles]
    return entries


def team_analysts(analysts: list[str], historical: bool) -> list[str]:
    chosen = [a for a in ANALYSTS if a in analysts] or ANALYSTS
    if historical:
        chosen = [a for a in chosen if a not in ("Fundamentals", "Sentiment")] or ["Technical"]
    return chosen


def run_team(provider: str, model: str, api_key: str, data: dict, analysts: list[str], rounds: int,
             quick: bool, on_step=None) -> dict:
    notify = on_step or (lambda _msg: None)
    position = data["position_text"]
    head = _header(data)
    memory = _memory(data)

    focus = _focus(data)
    if quick:
        notify("Portfolio Manager is reviewing all the data")
        prompt = (
            f"{head}Act as the Portfolio Manager doing a quick review on your own. {focus} Weigh the technical "
            "data, fundamentals, news, macro and social sentiment below, and the user's position.\n\n"
            f"=== TECHNICAL DATA ===\n{_technical_data(data)}\n\n=== FUNDAMENTALS ===\n{_fundamental_data(data)}\n\n"
            f"=== NEWS & MACRO ===\n{_news_data(data)}\n\n=== SOCIAL SENTIMENT ===\n{_sentiment_data(data)}\n\n"
            f"=== RISK FACTS ===\n{_risk_facts(data)}\n\n=== USER'S POSITION ===\n{position}{memory}\n\n"
            f"=== YOUR TASK ===\n{focus}\n{DECISION_FORMAT}"
        )
        final, extra = ensure_decision(provider, model, api_key, ask(provider, model, api_key, prompt, deep=True), data)
        return {"final": final, "calls": 1 + extra}

    chosen = team_analysts(analysts, bool(data.get("as_of")))
    notify(f"{', '.join(chosen)} analyst{'s are' if len(chosen) > 1 else ' is'} working")
    reports = _parallel(provider, model, api_key, {name: head + ANALYST_PROMPTS[name](data) for name in chosen})
    analyst_notes = "\n\n".join(f"=== {name} Analyst ===\n{text}" for name, text in reports.items())

    research = _debate(provider, model, api_key, RESEARCH_ROLES, head + analyst_notes, rounds, notify,
                       "Bull vs Bear debate")

    notify("Trader is drafting the trading plan")
    trader = ask(provider, model, api_key, (
        f"{head}You are the Trader. Read the analyst reports and the bull vs bear debate, decide who argued better, "
        f"and turn it into a concrete trading plan for this user. {focus}\n\n{analyst_notes}\n\n"
        f"=== BULL VS BEAR DEBATE ===\n{_transcript(research)}\n\n=== RISK FACTS ===\n{_risk_facts(data)}\n\n"
        f"=== USER'S POSITION ===\n{position}{memory}\n\n=== YOUR TASK ===\n{focus}\n{TRADER_FORMAT}"
    ))

    risk_context = (f"{head}USER'S POSITION:\n{position}\n\nRISK FACTS:\n{_risk_facts(data)}\n\n"
                    f"=== TRADER'S PLAN ===\n{trader}\n\n{analyst_notes}")
    risk = _debate(provider, model, api_key, RISK_ROLES, risk_context, rounds, notify, "Risk team debate")

    notify("Portfolio Manager is making the final decision")
    final = ask(provider, model, api_key, (
        f"{head}You are the Portfolio Manager and you make the final decision. Review the trader's plan and the risk "
        "team's debate, then approve, modify or reject the plan. Protect the user's capital first, and fit the "
        f"decision to their position. {focus}\n\n{analyst_notes}\n\n=== TRADER'S PLAN ===\n{trader}\n\n"
        f"=== RISK TEAM DEBATE ===\n{_transcript(risk)}\n\n=== RISK FACTS ===\n{_risk_facts(data)}\n\n"
        f"=== USER'S POSITION ===\n{position}{memory}\n\n=== YOUR TASK ===\n{focus}\n{DECISION_FORMAT}"
    ), deep=True)
    final, extra = ensure_decision(provider, model, api_key, final, data)

    return {
        "analysts": reports,
        "research_debate": research,
        "trader": trader,
        "risk_debate": risk,
        "final": final,
        "calls": call_count(chosen, rounds, False) + extra,
    }


def _focus(data: dict) -> str:
    return (f"Decide only about {data['name']} ({data['symbol']}) shares themselves, not about any other company, "
            "IPO or subsidiary mentioned in the news.")


def ensure_decision(provider: str, model: str, api_key: str, text: str, data: dict) -> tuple[str, int]:
    if parse_decision(text)["rating"]:
        return text, 0
    fixed = ask(provider, model, api_key, (
        f"Below is our team's analysis of {data['name']} ({data['symbol']}). Turn its conclusion into the exact "
        f"format requested at the end. Do not add new analysis.\n\n=== ANALYSIS ===\n{text[:6000]}\n\n"
        f"=== YOUR TASK ===\n{_focus(data)}\n{DECISION_FORMAT}"
    ))
    parsed = parse_decision(fixed)
    if not parsed["rating"]:
        return text, 1
    header = "\n".join(f"{key}: {parsed[key.lower()]}" for key in DECISION_KEYS[:8] if parsed[key.lower()])
    return f"{header}\n\n{text}", 1


def asker(provider: str, model: str, api_key: str):
    return lambda prompt: ask(provider, model, api_key, prompt)


def _field(text: str, key: str) -> str | None:
    match = re.search(rf"^[\W_]*{re.escape(key)}[\W_]*:\s*\**\s*(.+?)\**\s*$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def parse_decision(text: str) -> dict:
    found = {key.lower(): _field(text, key) for key in DECISION_KEYS}
    rating = (found["rating"] or "").lower()
    found["rating"] = next((r for r in RATINGS if re.search(rf"\b{r.lower()}\b", rating)), None)
    keys = "|".join(re.escape(k) for k in DECISION_KEYS)
    body = re.sub(rf"^[\W_]*({keys})[\W_]*:.*$\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    found["body"] = body.strip()
    return found


def to_markdown(result: dict, title: str) -> str:
    parts = [f"# {title}", "## Final decision (Portfolio Manager)", result["final"]]
    if result.get("trader"):
        parts += ["## Trader's plan", result["trader"]]
    for name, text in (result.get("analysts") or {}).items():
        parts += [f"## {name} Analyst", text]
    for label, key in (("Bull vs Bear debate", "research_debate"), ("Risk team debate", "risk_debate")):
        if result.get(key):
            parts += [f"## {label}", _transcript(result[key])]
    parts.append("---\nFor education and research only. Not financial advice.")
    return "\n\n".join(parts)
