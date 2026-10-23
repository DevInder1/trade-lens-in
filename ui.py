import json
import os
from datetime import datetime

import streamlit as st
from dotenv import set_key, unset_key

import ai
import backtest
import indicators
import macro
import market
import portfolio
import scanner
import settings
import social
import track
from storage import ENV_PATH

NO_AI = "None (charts and signals only)"
BADGE = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}
RATING_BADGE = {"Buy": "🟢", "Overweight": "🟢", "Hold": "🟡", "Underweight": "🟠", "Sell": "🔴",
                "Bullish": "🟢", "Neutral": "🟡", "Bearish": "🔴"}
OUTCOME_BADGE = {"Right": "✅", "Wrong": "❌"}
DISCLAIMER = ("For education and research only. Not financial advice. "
              "This app never places trades or touches your broker account.")


@st.cache_data(ttl=900, show_spinner=False)
def get_prices(symbol, period):
    return indicators.add_indicators(market.load_prices(symbol, period))


@st.cache_data(ttl=3600, show_spinner=False)
def get_fundamentals(symbol):
    return market.load_fundamentals(symbol)


@st.cache_data(ttl=900, show_spinner=False)
def get_news(symbol, company):
    return market.load_news(symbol, company)


@st.cache_data(ttl=1800, show_spinner=False)
def get_market_news():
    return market.market_headlines()


@st.cache_data(ttl=3600, show_spinner=False)
def get_macro():
    return macro.load_macro()


@st.cache_data(ttl=3600, show_spinner=False)
def get_social(symbol, company):
    return social.load_social(symbol, company)


@st.cache_data(ttl=900, show_spinner=False)
def get_scan(symbols: tuple, positions_json: str):
    return scanner.scan(list(symbols), portfolio.load(), get_macro())


@st.cache_data(ttl=900, show_spinner=False)
def refresh_track(_stamp: str):
    return track.refresh()


@st.cache_data(ttl=3600, show_spinner=False)
def get_backtest(symbol, years, horizon):
    return backtest.signal_backtest(symbol, years, horizon)


def scan_watchlist(book: dict):
    return get_scan(tuple(book["watchlist"]), json.dumps(book["positions"], sort_keys=True))


def pct(value):
    return "–" if value is None else f"{value:+.2f}%"


def rupees(value, decimals=2):
    if value is None:
        return "–"
    return f"{'-' if value < 0 else ''}₹{abs(value):,.{decimals}f}"


def nice(value):
    if isinstance(value, float):
        if abs(value) >= 1e7:
            return f"{value / 1e7:,.2f} Cr"
        return f"{value:,.4g}" if abs(value) < 1 else f"{value:,.2f}"
    if isinstance(value, int) and abs(value) >= 1e7:
        return f"{value / 1e7:,.2f} Cr"
    return str(value)


def save_key(env_name, key):
    if not ENV_PATH.exists():
        os.close(os.open(ENV_PATH, os.O_CREAT | os.O_WRONLY, 0o600))
    os.chmod(ENV_PATH, 0o600)
    set_key(str(ENV_PATH), env_name, key)
    os.environ[env_name] = key


def forget_key(env_name):
    if ENV_PATH.exists():
        unset_key(str(ENV_PATH), env_name)
    os.environ.pop(env_name, None)


def ai_sidebar(team_options: bool = True, title: str = "AI team (optional)") -> dict:
    prefs = settings.load()
    st.sidebar.subheader(title)
    providers = [NO_AI, *ai.PROVIDERS]
    provider = st.sidebar.selectbox("AI provider", providers,
                                    index=providers.index(prefs["provider"]) if prefs["provider"] in providers else 0,
                                    key="ai_provider")
    cfg = {"provider": provider, "model": None, "api_key": None, "quick": True,
           "analysts": prefs["analysts"], "rounds": prefs["rounds"], "ready": False}
    if provider not in ai.PROVIDERS:
        settings.update(provider=provider)
        st.sidebar.caption("Without AI, everything except the written AI analysis still works.")
        return cfg

    spec = ai.PROVIDERS[provider]
    options = [*spec["models"], "Other (type a name)"]
    saved_model = prefs["model"] if prefs["provider"] == provider else ""
    custom = bool(saved_model) and saved_model not in spec["models"]
    choice = st.sidebar.selectbox("Model", options,
                                  index=len(options) - 1 if custom else
                                  (options.index(saved_model) if saved_model in options else 0),
                                  key=f"ai_model::{provider}")
    model = (st.sidebar.text_input("Model name", value=saved_model if custom else "", key=f"ai_custom::{provider}")
             if choice.startswith("Other") else choice)

    key = os.environ.get(spec["env"], "")
    if key:
        st.sidebar.success("API key saved on this computer ✓")
        if st.sidebar.button("Remove saved key", key=f"forget::{provider}"):
            forget_key(spec["env"])
            st.rerun()
    else:
        st.sidebar.markdown(f"[Get a {provider.split(' ')[0]} API key]({spec['key_url']}) · {spec['note']}")
        entered = st.sidebar.text_input("Paste API key", type="password", key=f"ai_key::{provider}")
        remember = st.sidebar.checkbox("Remember on this computer", value=True, key=f"ai_remember::{provider}",
                                       help="Saved to .env in the app folder, readable only by your Mac user.")
        if entered:
            key = entered.strip()
            if remember:
                save_key(spec["env"], key)

    quick, analysts, rounds = prefs["quick"], prefs["analysts"], prefs["rounds"]
    if team_options:
        mode = st.sidebar.radio("Analysis depth", ["Full team", "Quick (1 AI call)"], horizontal=True,
                                index=1 if quick else 0, key="ai_mode")
        quick = mode.startswith("Quick")
        if not quick:
            analysts = st.sidebar.multiselect("Analysts", ai.ANALYSTS,
                                              default=[a for a in analysts if a in ai.ANALYSTS] or ai.ANALYSTS,
                                              key="ai_analysts") or ai.ANALYSTS
            rounds = st.sidebar.slider("Debate rounds", 1, 3, int(rounds), key="ai_rounds",
                                       help="How many times the Bull/Bear and risk analysts reply to each other.")
        st.sidebar.caption(f"One run makes about **{ai.call_count(analysts, rounds, quick)} AI calls**.")
    settings.update(provider=provider, model=model or "", quick=quick, analysts=analysts, rounds=rounds)
    cfg.update(model=model, api_key=key or None, quick=quick if team_options else True, analysts=analysts,
               rounds=rounds, ready=bool(key and model))
    return cfg


def run_ai(cfg: dict, data: dict, quick: bool | None = None, label: str = "AI team at work…"):
    quick = cfg["quick"] if quick is None else quick
    with st.status(label, expanded=True) as status:
        try:
            result = ai.run_team(cfg["provider"], cfg["model"], cfg["api_key"], data, cfg["analysts"],
                                 cfg["rounds"], quick, on_step=status.write)
        except ai.AIError as exc:
            status.update(label="AI analysis failed", state="error")
            st.error(str(exc))
            return None
        status.update(label=f"Done · {result['calls']} AI calls", state="complete", expanded=False)
    result["time"] = datetime.now().strftime("%d %b %Y %H:%M")
    result["provider"], result["model"] = cfg["provider"], cfg["model"]
    return result


def show_debate(entries):
    for e in entries:
        st.markdown(f"**{e['speaker']}** · round {e['round']}")
        st.markdown(e["text"])
        st.divider()


def decision_card(result: dict):
    d = ai.parse_decision(result["final"])
    rating = d["rating"] or "Unclear"
    st.subheader(f"{RATING_BADGE.get(rating, '⚪')} Final rating: {rating}")
    st.caption(f"{result.get('provider', '')} {result.get('model', '')} · {result.get('time', '')}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Decision on trader's plan", d["decision"] or ("–" if result.get("trader") else "Quick mode"))
    c2.metric("Confidence", d["confidence"] or "–")
    c3.metric("Time horizon", d["horizon"] or "–")
    if d["action"]:
        st.success(f"**Action:** {d['action']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Entry", d["entry"] or "–")
    c2.metric("Stop-loss", d["stop-loss"] or "–")
    c3.metric("Target", d["target"] or "–")
    st.markdown(d["body"])
    if result.get("trader"):
        trader = ai.parse_decision(result["trader"])
        proposal = f" — proposed: {trader['proposal']}" if trader["proposal"] else ""
        with st.expander(f"📋 Trader's plan{proposal}"):
            st.markdown(trader["body"])
        with st.expander("⚖️ Risk team debate (Aggressive · Conservative · Neutral)"):
            show_debate(result["risk_debate"])
        with st.expander("🐂🐻 Bull vs Bear debate"):
            show_debate(result["research_debate"])
        for analyst, text in result["analysts"].items():
            with st.expander(f"🔬 {analyst} Analyst"):
                st.markdown(text)
    return d


def decisions_table(rows: list[dict], progress: dict | None = None, show_symbol: bool = True):
    progress = progress or {}
    table = []
    for r in rows:
        if r["outcome"]:
            status = f"{OUTCOME_BADGE.get(r['outcome'], '')} {r['outcome']}"
            ret, alpha = r["return_pct"], r["alpha_pct"]
        else:
            p = progress.get(r["id"], {})
            status = f"⏳ {p.get('days', 0)}/{r['horizon_days']} days"
            ret, alpha = p.get("return_pct"), p.get("alpha_pct")
        row = {"Date": r["as_of"], "Source": track.SOURCES.get(r["source"], r["source"]),
               "Call": f"{RATING_BADGE.get(r['rating'], '')} {r['rating']}", "Price": rupees(r["price"]),
               "Status": status, "Return": pct(ret), "vs NIFTY": pct(alpha), "Action": r["action"] or ""}
        if show_symbol:
            row = {"Stock": r["name"] or r["symbol"], **row}
        table.append(row)
    st.dataframe(table, width="stretch", hide_index=True)


def go_analyse(symbol: str):
    st.session_state["goto_symbol"] = symbol
    st.switch_page("views/page_analyse.py")
