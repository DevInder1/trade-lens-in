import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv, set_key, unset_key

import ai
import charts
import indicators
import market

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH)

st.set_page_config(page_title="Trading Assistant", page_icon="📈", layout="wide")

PERIODS = {"3 months": 3, "6 months": 6, "1 year": 12, "2 years": 24, "5 years": 60}
BADGE = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}


@st.cache_data(ttl=900, show_spinner=False)
def get_prices(symbol, period):
    return indicators.add_indicators(market.load_prices(symbol, period))


@st.cache_data(ttl=3600, show_spinner=False)
def get_fundamentals(symbol):
    return market.load_fundamentals(symbol)


@st.cache_data(ttl=900, show_spinner=False)
def get_news(symbol, company):
    return market.load_news(symbol, company)


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


def pct(value):
    return "–" if value is None else f"{value:+.2f}%"


def rupees(value):
    return "–" if value is None else f"₹{value:,.2f}"


def nice(value):
    if isinstance(value, float):
        if abs(value) >= 1e7:
            return f"{value / 1e7:,.2f} Cr"
        return f"{value:,.4g}" if abs(value) < 1 else f"{value:,.2f}"
    if isinstance(value, int) and abs(value) >= 1e7:
        return f"{value / 1e7:,.2f} Cr"
    return str(value)


with st.sidebar:
    st.title("📈 Trading Assistant")
    st.caption("Indian stocks · NSE / BSE · read-only research")

    st.subheader("1. Pick a stock")
    exchange = st.radio("Exchange", ["NSE", "BSE"], horizontal=True)
    query = st.text_input("Symbol or index", value="RELIANCE",
                          help="Examples: RELIANCE, TCS, HDFCBANK, INFY, TATAMOTORS, NIFTY 50, BANK NIFTY, SENSEX")
    period_label = st.selectbox("Chart period", list(PERIODS), index=2)

    st.subheader("2. AI (optional)")
    provider = st.selectbox("AI provider", ["None (charts and signals only)", *ai.PROVIDERS])
    api_key, model, quick = None, None, True
    if provider in ai.PROVIDERS:
        spec = ai.PROVIDERS[provider]
        choice = st.selectbox("Model", [*spec["models"], "Other (type a name)"])
        model = st.text_input("Model name") if choice.startswith("Other") else choice
        saved = os.environ.get(spec["env"], "")
        if saved:
            st.success("API key saved on this computer ✓")
            if st.button("Remove saved key"):
                forget_key(spec["env"])
                st.rerun()
            api_key = saved
        else:
            st.markdown(f"[Get a {provider.split(' ')[0]} API key]({spec['key_url']}) · {spec['note']}")
            entered = st.text_input("Paste API key", type="password")
            remember = st.checkbox("Remember on this computer", value=True,
                                   help=f"Saved to {ENV_PATH.name} in the app folder, readable only by your Mac user.")
            if entered:
                api_key = entered.strip()
                if remember:
                    save_key(spec["env"], api_key)
        mode = st.radio("Analysis depth", ["Full team (6 AI calls)", "Quick (1 AI call)"])
        quick = mode.startswith("Quick")

    st.divider()
    st.caption("For education and research only. Not financial advice. "
               "This app never places trades or touches your broker account.")

symbol = market.normalize_symbol(query, exchange)
if not symbol:
    st.info("Type a stock symbol in the sidebar to begin.")
    st.stop()

try:
    with st.spinner(f"Loading {symbol}…"):
        df = get_prices(symbol, "5y" if PERIODS[period_label] > 24 else "2y")
except Exception as exc:
    st.error(f"Could not load prices for **{symbol}**: {exc}")
    st.caption("Tip: use the NSE code (e.g. HDFCBANK, not HDFC Bank). Switch to BSE if the stock is only listed there.")
    st.stop()

fundamentals = {} if market.is_index(symbol) else get_fundamentals(symbol)
name = fundamentals.get("Company") or query.strip().upper()
news = get_news(symbol, name)
snap = indicators.snapshot(df)
sigs = indicators.signals(snap)
tech_view, tech_score = indicators.overall(sigs)

st.title(f"{name}")
st.caption(f"{symbol} · last close {snap['date']} · data from Yahoo Finance (may be delayed)")

cols = st.columns(3)
cols[0].metric("Last close", rupees(snap["Close"]), pct(snap["change_1d"]))
cols[1].metric("1 month", pct(snap["change_1m"]))
cols[2].metric("1 year", pct(snap["change_1y"]))
cols = st.columns(3)
cols[0].metric("52-week low / high", f"{snap['low_52w']:,.0f} / {snap['high_52w']:,.0f}")
cols[1].metric("Technical signals", f"{BADGE[tech_view]} {tech_view}", f"score {tech_score:+d}", delta_color="off")
cols[2].metric("News headlines", len(news))
chart_df = df[df.index >= df.index[-1] - pd.DateOffset(months=PERIODS[period_label])]

tab_chart, tab_signals, tab_fund, tab_news, tab_ai = st.tabs(
    ["📊 Chart", "🚦 Signals", "🏢 Fundamentals", "📰 News", "🤖 AI Team"])

with tab_chart:
    st.plotly_chart(charts.price_chart(chart_df, f"{name} ({symbol})"), use_container_width=True)
    st.caption("Lines: orange = 20-day average, blue = 50-day, purple = 200-day, dotted = Bollinger Bands. "
               "RSI above 70 = overbought, below 30 = oversold.")

with tab_signals:
    st.subheader(f"{BADGE[tech_view]} Overall: {tech_view} (score {tech_score:+d})")
    st.caption("Simple rule-based checks. Each bullish signal adds 1, each bearish subtracts 1. No AI used.")
    for s in sigs:
        st.markdown(f"{BADGE[s['verdict']]} **{s['name']}** — {s['verdict']}  \n{s['detail']}")
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Support (20-day low)", rupees(snap["support_20d"]))
    c2.metric("Resistance (20-day high)", rupees(snap["resistance_20d"]))
    c3.metric("Average daily move (ATR)", rupees(snap["ATR"]),
              None if snap["atr_pct"] is None else f"{snap['atr_pct']:.2f}% of price", delta_color="off")

with tab_fund:
    if fundamentals:
        rows = [{"Metric": k, "Value": nice(v)} for k, v in fundamentals.items()]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No fundamental data for this symbol (indices have none).")

with tab_news:
    if news:
        for n in news:
            title = f"[{n['title']}]({n['url']})" if n["url"] else n["title"]
            st.markdown(f"**{title}**  \n{n['publisher']} · {n['date']}")
    else:
        st.info("No recent news found for this symbol.")

with tab_ai:
    if provider not in ai.PROVIDERS:
        st.info("Choose an AI provider in the sidebar to get a written analysis from a team of AI analysts.")
        st.markdown(
            "**Which one should I use?** Your Claude, Gemini or ChatGPT *subscriptions* don't work here — apps need "
            "a separate **API key**. The easiest is a free Gemini key from "
            "[Google AI Studio](https://aistudio.google.com/apikey): sign in, click *Create API key*, paste it in the sidebar."
        )
    else:
        st.markdown(
            "**How it works:** a Technical, Fundamentals and News analyst each write a report, a Bull and a Bear "
            "researcher debate them, and a Risk Manager gives the final verdict. Only market data is sent to the AI — "
            "nothing about you."
        )
        state_key = f"reports::{symbol}::{provider}::{model}"
        if st.button("▶ Run AI analysis", type="primary", disabled=not (api_key and model)):
            data = {
                "symbol": symbol, "name": name, "snapshot": snap, "signals": sigs,
                "recent": df.tail(30)[["Open", "High", "Low", "Close", "Volume", "RSI", "MACD", "ATR"]],
                "fundamentals": fundamentals, "news": news,
            }
            with st.status("AI team at work…", expanded=True) as status:
                try:
                    reports = ai.run_team(provider, model, api_key, data, quick, on_step=status.write)
                except ai.AIError as exc:
                    status.update(label="AI analysis failed", state="error")
                    st.error(str(exc))
                    reports = None
                else:
                    status.update(label="Done", state="complete", expanded=False)
            if reports:
                st.session_state[state_key] = {"reports": reports, "time": datetime.now().strftime("%d %b %Y %H:%M")}
        if not api_key:
            st.warning("Paste an API key in the sidebar to run the AI team.")

        result = st.session_state.get(state_key)
        if result:
            reports = result["reports"]
            verdict = ai.parse_verdict(reports["Final Verdict"])
            outlook = verdict["outlook"] or "Unclear"
            st.subheader(f"{BADGE.get(outlook, '⚪')} AI outlook: {outlook}")
            st.caption(f"Confidence: {verdict['confidence'] or '–'} · Horizon: {verdict['horizon'] or '–'} · "
                       f"{provider} {model} · {result['time']}")
            st.markdown(verdict["body"])
            for title, text in reports.items():
                if title != "Final Verdict":
                    with st.expander(title):
                        st.markdown(text)
            report_md = f"# {name} ({symbol}) — AI research report\n\n{result['time']} · {provider} {model}\n\n"
            report_md += "\n\n".join(f"## {title}\n\n{text}" for title, text in reports.items())
            report_md += "\n\n---\nFor education and research only. Not financial advice."
            st.download_button("⬇ Download report", report_md,
                               file_name=f"{symbol}-{datetime.now():%Y%m%d}.md", mime="text/markdown")
            st.caption("AI can be wrong or out of date. Always check the numbers and decide for yourself.")
