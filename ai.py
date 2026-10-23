import json
import re
from concurrent.futures import ThreadPoolExecutor

PROVIDERS = {
    "Gemini (Google)": {
        "env": "GEMINI_API_KEY",
        "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"],
        "key_url": "https://aistudio.google.com/apikey",
        "note": "Free tier available. No card needed.",
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

SYSTEM = (
    "You are a member of an equity research team covering Indian-listed stocks and indices on NSE and BSE. "
    "All prices are in Indian rupees (₹). Work only from the data you are given; when something is missing, say so "
    "instead of guessing, and never invent numbers. Write in plain, simple English that a beginner can follow, "
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
        return f"{provider} says you hit a usage or quota limit. Wait a minute, or check your plan/billing."
    if status == 404 or "NotFound" in name:
        return f"{provider} does not recognise that model name. Pick another model."
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
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt,
                                              config=types.GenerateContentConfig(system_instruction=SYSTEM))
    return response.text or ""


def _ask_openai(model, api_key, prompt):
    from openai import OpenAI

    client = OpenAI(api_key=api_key, max_retries=3)
    response = client.responses.create(model=model, instructions=SYSTEM, input=prompt)
    return response.output_text or ""


ASKERS = {
    "Claude (Anthropic)": _ask_claude,
    "Gemini (Google)": _ask_gemini,
    "ChatGPT (OpenAI)": _ask_openai,
}


def ask(provider: str, model: str, api_key: str, prompt: str) -> str:
    try:
        text = ASKERS[provider](model, api_key, prompt)
    except AIError:
        raise
    except Exception as exc:
        raise AIError(_friendly(provider, exc)) from None
    if not text.strip():
        raise AIError(f"{provider} returned an empty answer. Try again or pick another model.")
    return text.strip()


def _technical_data(data: dict) -> str:
    table = data["recent"].round(2).to_csv()
    return (
        f"Instrument: {data['name']} ({data['symbol']})\n"
        f"Latest snapshot:\n{json.dumps(data['snapshot'], indent=1, default=str)}\n\n"
        f"Rule-based signals:\n{json.dumps(data['signals'], indent=1, ensure_ascii=False)}\n\n"
        f"Last 30 trading days:\n{table}"
    )


def _fundamental_data(data: dict) -> str:
    if not data["fundamentals"]:
        return "No fundamental data is available (this may be an index)."
    return json.dumps(data["fundamentals"], indent=1, default=str, ensure_ascii=False)


def _news_data(data: dict) -> str:
    if not data["news"]:
        return "No recent news headlines were found."
    return "\n".join(f"- [{n['date']}] {n['title']} ({n['publisher']}) {n['summary'][:300]}" for n in data["news"])


VERDICT_FORMAT = (
    "Start your answer with exactly these three lines:\n"
    "OUTLOOK: Bullish or Neutral or Bearish\n"
    "CONFIDENCE: Low or Medium or High\n"
    "HORIZON: the time frame this view is for (for example 2-6 weeks)\n\n"
    "Then write these sections:\n"
    "## Summary (3-4 sentences)\n"
    "## Key price levels (support, resistance, and an ATR-based stop-loss level someone could consider, with numbers)\n"
    "## Why (the strongest 3-5 reasons)\n"
    "## Main risks\n"
    "## What would change this view\n"
)


def _steps(data: dict) -> dict:
    tech, fund, news = _technical_data(data), _fundamental_data(data), _news_data(data)
    return {
        "Technical Analyst": (
            "Act as the Technical Analyst. Analyse trend, momentum, volatility, volume and key support/resistance "
            f"levels from this data. End with a one-line technical bias.\n\n{tech}"
        ),
        "Fundamentals Analyst": (
            f"Act as the Fundamentals Analyst for {data['name']} ({data['symbol']}). Judge valuation, profitability, "
            "growth, balance-sheet strength and ownership from this data, comparing with what is typical for its "
            f"sector in India where you can. End with a one-line fundamental bias.\n\n{fund}"
        ),
        "News Analyst": (
            f"Act as the News & Sentiment Analyst for {data['name']} ({data['symbol']}). From these headlines, "
            "identify the events that matter for the price, whether sentiment is positive or negative, and any "
            f"upcoming catalysts. End with a one-line sentiment bias.\n\n{news}"
        ),
    }


def run_team(provider: str, model: str, api_key: str, data: dict, quick: bool, on_step=None) -> dict:
    notify = on_step or (lambda _msg: None)
    reports = {}

    if quick:
        notify("Research Manager is reviewing all the data")
        prompt = (
            "Act as the Research Manager. Review the technical data, fundamentals and news below and give a "
            f"balanced view.\n\n{VERDICT_FORMAT}\n\n=== TECHNICAL DATA ===\n{_technical_data(data)}\n\n"
            f"=== FUNDAMENTALS ===\n{_fundamental_data(data)}\n\n=== NEWS ===\n{_news_data(data)}"
        )
        reports["Final Verdict"] = ask(provider, model, api_key, prompt)
        return reports

    notify("Technical, Fundamentals and News analysts are working")
    steps = _steps(data)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {name: pool.submit(ask, provider, model, api_key, prompt) for name, prompt in steps.items()}
        for name, future in futures.items():
            reports[name] = future.result()

    analyst_notes = "\n\n".join(f"=== {name} ===\n{text}" for name, text in reports.items())
    notify("Bull and Bear researchers are debating")
    debate = {
        "Bull Researcher": (
            "Act as the Bull Researcher. Using the analyst reports below, make the strongest honest case for the "
            f"price going UP. Use specific numbers from the reports.\n\n{analyst_notes}"
        ),
        "Bear Researcher": (
            "Act as the Bear Researcher. Using the analyst reports below, make the strongest honest case for the "
            f"price going DOWN. Use specific numbers from the reports.\n\n{analyst_notes}"
        ),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {name: pool.submit(ask, provider, model, api_key, prompt) for name, prompt in debate.items()}
        for name, future in futures.items():
            reports[name] = future.result()

    notify("Risk Manager is writing the final verdict")
    everything = "\n\n".join(f"=== {name} ===\n{text}" for name, text in reports.items())
    prompt = (
        "Act as the Risk Manager who makes the final call. Weigh the analyst reports and the bull vs bear debate "
        f"below. Be balanced and cautious.\n\n{VERDICT_FORMAT}\n\n{everything}\n\n"
        f"Latest close: ₹{data['snapshot'].get('Close')}, ATR(14): ₹{data['snapshot'].get('ATR')}"
    )
    reports["Final Verdict"] = ask(provider, model, api_key, prompt)
    return reports


def parse_verdict(text: str) -> dict:
    found = {}
    for key in ("OUTLOOK", "CONFIDENCE", "HORIZON"):
        match = re.search(rf"^\W*{key}\W*:\s*\**\s*(.+?)\**\s*$", text, re.IGNORECASE | re.MULTILINE)
        found[key.lower()] = match.group(1).strip() if match else None
    outlook = (found["outlook"] or "").lower()
    found["outlook"] = next((label for label in ("Bullish", "Bearish", "Neutral") if label.lower() in outlook), None)
    body = re.sub(r"^\W*(OUTLOOK|CONFIDENCE|HORIZON)\W*:.*$\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    found["body"] = body.strip()
    return found
