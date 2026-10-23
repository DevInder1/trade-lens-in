import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv, set_key, unset_key

import ai
import charts
import indicators
import macro
import market
import portfolio
import social

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH)

st.set_page_config(page_title="Trade Lens IN", page_icon="📈", layout="wide")

PERIODS = {"3 months": 3, "6 months": 6, "1 year": 12, "2 years": 24, "5 years": 60}
BADGE = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}
RATING_BADGE = {"Buy": "🟢", "Overweight": "🟢", "Hold": "🟡", "Underweight": "🟠", "Sell": "🔴"}
OWNERSHIP = ["Not saying", "No", "Yes"]


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


def show_debate(entries):
    for e in entries:
        st.markdown(f"**{e['speaker']}** · round {e['round']}")
        st.markdown(e["text"])
        st.divider()


book = portfolio.load()

with st.sidebar:
    st.title("📈 Trade Lens IN")
    st.caption("Indian stocks · NSE / BSE · read-only research")

    st.subheader("1. Pick a stock")
    exchange = st.radio("Exchange", ["NSE", "BSE"], horizontal=True)
    query = st.text_input("Symbol or index", value="RELIANCE",
                          help="Examples: RELIANCE, TCS, HDFCBANK, INFY, TATAMOTORS, NIFTY 50, BANK NIFTY, SENSEX")
    period_label = st.selectbox("Chart period", list(PERIODS), index=2)
    symbol = market.normalize_symbol(query, exchange)

    st.subheader("2. Your position (optional)")
    saved_pos = book["positions"].get(symbol, {})
    owned = st.radio("Do you own this stock?", OWNERSHIP, horizontal=True,
                     index=OWNERSHIP.index(saved_pos.get("owned", "Not saying")), key=f"owned::{symbol}")
    qty, avg = 0.0, 0.0
    if owned == "Yes":
        qty = st.number_input("Shares held", min_value=0.0, step=1.0, value=float(saved_pos.get("qty", 0)),
                              key=f"qty::{symbol}")
        avg = st.number_input("Average buy price (₹)", min_value=0.0, step=1.0,
                              value=float(saved_pos.get("avg", 0)), key=f"avg::{symbol}")
    capital = st.number_input("Trading capital (₹)", min_value=0.0, step=10000.0, value=book["capital"],
                              help="Money you would use for trading. Used to size positions. Leave 0 to skip.")
    risk_pct = st.slider("Max risk per trade (% of capital)", 0.25, 3.0, value=min(max(book["risk_pct"], 0.25), 3.0),
                         step=0.25, help="How much you accept to lose if the stop-loss is hit. 1% is a common rule.")
    new_pos = {"owned": owned, "qty": qty, "avg": avg} if owned == "Yes" else {"owned": owned}
    if symbol and (new_pos != saved_pos or capital != book["capital"] or risk_pct != book["risk_pct"]):
        if owned == "Not saying":
            book["positions"].pop(symbol, None)
        else:
            book["positions"][symbol] = new_pos
        book["capital"], book["risk_pct"] = capital, risk_pct
        portfolio.save(book)
    st.caption("Saved only on this computer (portfolio.json). Never sent anywhere except to the AI you choose.")

    st.subheader("3. AI team (optional)")
    provider = st.selectbox("AI provider", ["None (charts and signals only)", *ai.PROVIDERS])
    api_key, model, quick, analysts, rounds = None, None, True, ai.ANALYSTS, 1
    if provider in ai.PROVIDERS:
        spec = ai.PROVIDERS[provider]
        choice = st.selectbox("Model", [*spec["models"], "Other (type a name)"])
        model = st.text_input("Model name") if choice.startswith("Other") else choice
        saved_key = os.environ.get(spec["env"], "")
        if saved_key:
            st.success("API key saved on this computer ✓")
            if st.button("Remove saved key"):
                forget_key(spec["env"])
                st.rerun()
            api_key = saved_key
        else:
            st.markdown(f"[Get a {provider.split(' ')[0]} API key]({spec['key_url']}) · {spec['note']}")
            entered = st.text_input("Paste API key", type="password")
            remember = st.checkbox("Remember on this computer", value=True,
                                   help=f"Saved to {ENV_PATH.name} in the app folder, readable only by your Mac user.")
            if entered:
                api_key = entered.strip()
                if remember:
                    save_key(spec["env"], api_key)
        mode = st.radio("Analysis depth", ["Full team", "Quick (1 AI call)"], horizontal=True)
        quick = mode.startswith("Quick")
        if not quick:
            analysts = st.multiselect("Analysts", ai.ANALYSTS, default=ai.ANALYSTS)
            rounds = st.slider("Debate rounds", 1, 3, 1,
                               help="How many times the Bull/Bear and risk analysts reply to each other.")
        st.caption(f"This run makes about **{ai.call_count(analysts or ai.ANALYSTS, rounds, quick)} AI calls**.")

    st.divider()
    st.caption("For education and research only. Not financial advice. "
               "This app never places trades or touches your broker account.")

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

with st.spinner("Loading fundamentals, news, sentiment and market data…"):
    fundamentals = {} if market.is_index(symbol) else get_fundamentals(symbol)
    name = fundamentals.get("Company") or query.strip().upper()
    news = get_news(symbol, name)
    market_news = get_market_news()
    macro_rows = get_macro()
    chatter = get_social(symbol, name)

snap = indicators.snapshot(df)
sigs = indicators.signals(snap)
tech_view, tech_score = indicators.overall(sigs)
relative = macro.relative_strength(snap, macro_rows)
vix = macro.vix_reading(macro_rows)
holding = portfolio.position_summary(qty, avg, snap["Close"]) if owned == "Yes" and qty and avg else None
size = portfolio.sizing(capital, risk_pct, snap["Close"], snap["ATR"])
position_text = portfolio.describe(owned, holding, capital, risk_pct, size)
liquidity = (snap["VolAvg20"] or 0) * (snap["Close"] or 0)

st.title(name)
st.caption(f"{symbol} · last close {snap['date']} · data from Yahoo Finance (may be delayed)")

cols = st.columns(3)
cols[0].metric("Last close", rupees(snap["Close"]), pct(snap["change_1d"]))
cols[1].metric("1 month", pct(snap["change_1m"]),
               None if "vs_nifty_1m" not in relative else f"{relative['vs_nifty_1m']:+.2f} pts vs NIFTY")
cols[2].metric("1 year", pct(snap["change_1y"]))
cols = st.columns(3)
cols[0].metric("52-week low / high", f"{snap['low_52w']:,.0f} / {snap['high_52w']:,.0f}")
cols[1].metric("Technical signals", f"{BADGE[tech_view]} {tech_view}", f"score {tech_score:+d}", delta_color="off")
if holding:
    cols[2].metric("Your P&L", rupees(holding["pnl"], 0), pct(holding["pnl_pct"]))
else:
    cols[2].metric("Market mood (India VIX)", macro.vix_mood(macro_rows) or "–")
chart_df = df[df.index >= df.index[-1] - pd.DateOffset(months=PERIODS[period_label])]

tabs = st.tabs(["📊 Chart", "🚦 Signals", "🏢 Fundamentals", "📰 News", "💬 Sentiment", "🌏 Market",
                "💼 Position", "🤖 AI Team"])
tab_chart, tab_signals, tab_fund, tab_news, tab_social, tab_market, tab_position, tab_ai = tabs

with tab_chart:
    st.plotly_chart(charts.price_chart(chart_df, f"{name} ({symbol})"), width="stretch")
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
        st.dataframe([{"Metric": k, "Value": nice(v)} for k, v in fundamentals.items()],
                     width="stretch", hide_index=True)
    else:
        st.info("No fundamental data for this symbol (indices have none).")

with tab_news:
    if news:
        for n in news:
            title = f"[{n['title']}]({n['url']})" if n["url"] else n["title"]
            st.markdown(f"**{title}**  \n{n['publisher']} · {n['date']}")
    else:
        st.info("No recent news found for this symbol.")

with tab_social:
    st.caption("What retail investors are saying. Social chatter is noisy: treat it as a mood check, not a signal.")
    stw = chatter["stocktwits"]
    rd = chatter["reddit"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("StockTwits messages", len(stw["messages"]))
    c2.metric("Labelled bullish", stw["bullish"])
    c3.metric("Labelled bearish", stw["bearish"])
    c4.metric("Reddit posts (30 days)", len(rd["posts"]))
    left, right = st.columns(2)
    with left:
        st.markdown("#### StockTwits")
        if stw["messages"]:
            for m in stw["messages"][:15]:
                mood = {"Bullish": "🟢", "Bearish": "🔴"}.get(m["sentiment"], "⚪")
                st.markdown(f"{mood} {m['body']}")
                st.caption(f"{m['date']} · {m['likes']} likes")
        else:
            st.info("No StockTwits messages for this symbol.")
    with right:
        st.markdown("#### Reddit (Indian investing communities)")
        if rd["posts"]:
            for p in rd["posts"][:15]:
                st.markdown(f"**[{p['title']}]({p['url']})**  \nr/{p['subreddit']} · {p['date']}")
        elif rd.get("error"):
            st.warning(rd["error"])
            if st.button("Retry Reddit"):
                get_social.clear()
                st.rerun()
        else:
            st.info("No Reddit posts mentioning this stock in the last 30 days.")

with tab_market:
    if vix:
        st.subheader(f"🌡️ {vix}")
    if macro_rows:
        st.dataframe([{
            "Indicator": r["name"], "Last": f"{r['last']:,.2f}", "1 week": pct(r["change_1w"]),
            "1 month": pct(r["change_1m"]), "3 months": pct(r["change_3m"]), "Trend": r["trend"] or "–",
        } for r in macro_rows], width="stretch", hide_index=True)
    if relative:
        parts = [f"{v:+.2f} pts over {k.split('_')[-1]}" for k, v in relative.items()]
        st.markdown(f"**{name} vs NIFTY 50:** " + ", ".join(parts) +
                    " (positive = beating the market)")
    st.markdown("#### Market headlines (last 7 days)")
    for n in market_news:
        title = f"[{n['title']}]({n['url']})" if n["url"] else n["title"]
        st.markdown(f"**{title}**  \n{n['publisher']} · {n['date']}")

with tab_position:
    if holding:
        st.subheader("Your holding")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Shares", f"{holding['qty']:g}")
        c2.metric("Average price", rupees(holding["avg"]))
        c3.metric("Current value", rupees(holding["value"], 0))
        c4.metric("Unrealised P&L", rupees(holding["pnl"], 0), pct(holding["pnl_pct"]))
    elif owned == "Yes":
        st.info("Enter your shares and average price in the sidebar.")
    else:
        st.info("Tell the app in the sidebar whether you own this stock so the AI team can tailor its plan.")
    st.subheader("Position sizing (rule-based, no AI)")
    if size:
        st.caption(f"Stop-loss placed {portfolio.STOP_ATR_MULTIPLE:g}× the average daily move (ATR) below the price; "
                   f"if it is hit you lose at most {risk_pct:g}% of your capital.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Suggested stop-loss", rupees(size["stop"]))
        c2.metric("Risk per share", rupees(size["risk_per_share"]))
        c3.metric("Max shares to buy", f"{size['max_qty']:,}")
        c4.metric("Max position value", rupees(size["max_value"], 0), f"{size['pct_of_capital']:.1f}% of capital",
                  delta_color="off")
    else:
        st.info("Enter your trading capital in the sidebar to see how many shares you could buy safely.")
    if liquidity:
        st.caption(f"Liquidity: about ₹{liquidity / 1e7:,.2f} Cr traded per day (20-day average).")

with tab_ai:
    if provider not in ai.PROVIDERS:
        st.info("Choose an AI provider in the sidebar to get a decision from a team of AI analysts.")
        st.markdown(
            "**Which one should I use?** Your Claude, Gemini or ChatGPT *subscriptions* don't work here — apps need "
            "a separate **API key**. The easiest is a free Gemini key from "
            "[Google AI Studio](https://aistudio.google.com/apikey): sign in, click *Create API key*, paste it in the sidebar."
        )
    else:
        if quick:
            st.markdown("**Quick mode:** one Portfolio Manager reviews everything in a single AI call.")
        else:
            st.markdown(
                f"**How it works:** {', '.join(analysts or ai.ANALYSTS)} analysts write reports → Bull vs Bear debate "
                f"({rounds} round{'s' if rounds > 1 else ''}) → the Trader drafts a plan → the Aggressive, "
                "Conservative and Neutral risk analysts challenge it → the Portfolio Manager approves, modifies or "
                "rejects it. Only market data and the position you entered are sent to the AI."
            )
        state_key = f"result::{symbol}::{provider}::{model}"
        if st.button("▶ Run AI analysis", type="primary", disabled=not (api_key and model)):
            data = {
                "symbol": symbol, "name": name, "snapshot": snap, "signals": sigs, "relative": relative,
                "recent": df.tail(30)[["Open", "High", "Low", "Close", "Volume", "RSI", "MACD", "ATR"]],
                "fundamentals": fundamentals, "news": news, "market_news": market_news,
                "macro": [{k: r[k] for k in ("name", "last", "change_1w", "change_1m", "change_3m", "trend")}
                          for r in macro_rows],
                "vix": vix, "social": chatter, "position_text": position_text, "liquidity": liquidity,
            }
            with st.status("AI team at work…", expanded=True) as status:
                try:
                    result = ai.run_team(provider, model, api_key, data, analysts, rounds, quick,
                                         on_step=status.write)
                except ai.AIError as exc:
                    status.update(label="AI analysis failed", state="error")
                    st.error(str(exc))
                    result = None
                else:
                    status.update(label=f"Done · {result['calls']} AI calls", state="complete", expanded=False)
            if result:
                result["time"] = datetime.now().strftime("%d %b %Y %H:%M")
                st.session_state[state_key] = result
        if not api_key:
            st.warning("Paste an API key in the sidebar to run the AI team.")

        result = st.session_state.get(state_key)
        if result:
            d = ai.parse_decision(result["final"])
            rating = d["rating"] or "Unclear"
            st.subheader(f"{RATING_BADGE.get(rating, '⚪')} Final rating: {rating}")
            st.caption(f"{provider} {model} · {result['time']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Decision on trader's plan", d["decision"] or "–")
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
                proposal = ai.parse_decision(result["trader"])["proposal"]
                with st.expander(f"📋 Trader's plan{f' — proposed: {proposal}' if proposal else ''}"):
                    st.markdown(ai.parse_decision(result["trader"])["body"])
                with st.expander("⚖️ Risk team debate (Aggressive · Conservative · Neutral)"):
                    show_debate(result["risk_debate"])
                with st.expander("🐂🐻 Bull vs Bear debate"):
                    show_debate(result["research_debate"])
                for analyst, text in result["analysts"].items():
                    with st.expander(f"🔬 {analyst} Analyst"):
                        st.markdown(text)

            report = ai.to_markdown(result, f"{name} ({symbol}) — Trade Lens IN report, {result['time']}")
            st.download_button("⬇ Download full report", report,
                               file_name=f"{symbol}-{datetime.now():%Y%m%d-%H%M}.md", mime="text/markdown")
            st.caption("AI can be wrong or out of date. Always check the numbers and decide for yourself.")
