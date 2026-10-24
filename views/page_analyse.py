import pandas as pd
import streamlit as st

import ai
import charts
import macro
import market
import portfolio
import research
import settings
import track
import ui

PERIODS = {"3 months": 3, "6 months": 6, "1 year": 12, "2 years": 24, "5 years": 60}
OWNERSHIP = ["Not saying", "No", "Yes"]

prefs = settings.load()
if "goto_symbol" in st.session_state:
    target = st.session_state.pop("goto_symbol")
    st.session_state["symbol_query"] = target
    st.session_state["symbol_exchange"] = "BSE" if target.endswith(".BO") else "NSE"
st.session_state.setdefault("symbol_query", prefs["last_query"])
st.session_state.setdefault("symbol_exchange", prefs["last_exchange"])

book = portfolio.load()

with st.sidebar:
    st.subheader("1. Pick a stock")
    exchange = st.radio("Exchange", ["NSE", "BSE"], horizontal=True, key="symbol_exchange")
    query = st.text_input("Symbol or index", key="symbol_query",
                          help="Examples: RELIANCE, TCS, HDFCBANK, INFY, TATAMOTORS, NIFTY 50, BANK NIFTY, SENSEX")
    period_label = st.selectbox("Chart period", list(PERIODS), index=2)
    symbol = market.normalize_symbol(query, exchange)
    settings.update(last_query=query, last_exchange=exchange)
    if symbol:
        if symbol in book["watchlist"]:
            if st.button("☆ Remove from watchlist"):
                portfolio.remove_from_watchlist([symbol])
                st.rerun()
        elif st.button("⭐ Add to watchlist"):
            portfolio.add_to_watchlist([symbol])
            st.rerun()

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
    st.caption("Saved only on this computer. Sent only to the AI you choose.")

cfg = ui.ai_sidebar()
st.sidebar.divider()
st.sidebar.caption(ui.DISCLAIMER)

if not symbol:
    st.info("Type a stock symbol in the sidebar to begin.")
    st.stop()

try:
    with st.spinner(f"Loading {symbol}…"):
        df = ui.get_prices(symbol, "5y" if PERIODS[period_label] > 24 else "2y")
except Exception as exc:
    st.error(f"Could not load prices for **{symbol}**: {exc}")
    st.caption("Tip: use the NSE code (e.g. HDFCBANK, not HDFC Bank). Switch to BSE if the stock is only listed there.")
    st.stop()

with st.spinner("Loading fundamentals, news, sentiment, official NSE data and market data…"):
    fundamentals = {} if market.is_index(symbol) else ui.get_fundamentals(symbol)
    name = fundamentals.get("Company") or query.strip().upper()
    extras = ui.get_extras(symbol, float(df["Close"].iloc[-1]), df.index[-1].strftime("%Y-%m-%d"))
    turbulence_series, turbulence = ui.get_turbulence()
    data = research.build(symbol, df=df, name=name, fundamentals=fundamentals, news=ui.get_news(symbol, name),
                          market_news=ui.get_market_news(), macro_rows=ui.get_macro(),
                          chatter=ui.get_social(symbol, name), book=book, turbulence=turbulence, extras=extras)

snap, sigs = data["snapshot"], data["signals"]
tech_view, tech_score = data["view"], data["score"]
relative, vix = data["relative"], data["vix"]
holding = portfolio.holding_for(book, symbol, snap["Close"])
size = portfolio.sizing(capital, risk_pct, snap["Close"], snap["ATR"])

st.title(name)
st.caption(f"{symbol} · last close {snap['date']} · prices from Yahoo Finance"
           + (" · ⭐ on your watchlist" if symbol in book["watchlist"] else ""))
check = extras.get("verify")
if check and check["status"] == "ok":
    st.caption(f"✅ Verified: {check['text']}")
elif check and check["status"] == "warn":
    st.warning(f"⚠️ Data check: {check['text']}")

cols = st.columns(3)
cols[0].metric("Last close", ui.rupees(snap["Close"]), ui.pct(snap["change_1d"]))
cols[1].metric("1 month", ui.pct(snap["change_1m"]),
               None if "vs_nifty_1m" not in relative else f"{relative['vs_nifty_1m']:+.2f} pts vs NIFTY")
cols[2].metric("1 year", ui.pct(snap["change_1y"]))
cols = st.columns(3)
cols[0].metric("52-week low / high", f"{snap['low_52w']:,.0f} / {snap['high_52w']:,.0f}")
cols[1].metric("Technical signals", f"{ui.BADGE[tech_view]} {tech_view}", f"score {tech_score:+d}", delta_color="off")
if holding:
    cols[2].metric("Your P&L", ui.rupees(holding["pnl"], 0), ui.pct(holding["pnl_pct"]))
else:
    cols[2].metric("Market mood (India VIX)", macro.vix_mood(data["macro_rows"]) or "–")
chart_df = df[df.index >= df.index[-1] - pd.DateOffset(months=PERIODS[period_label])]

tabs = st.tabs(["📊 Chart", "🚦 Signals", "🏢 Fundamentals", "📰 News", "💬 Sentiment", "🌏 Market",
                "💼 Position", "🤖 AI Team"])
tab_chart, tab_signals, tab_fund, tab_news, tab_social, tab_market, tab_position, tab_ai = tabs

with tab_chart:
    st.plotly_chart(charts.price_chart(chart_df, f"{name} ({symbol})"), width="stretch")
    st.caption("Lines: orange = 20-day average, blue = 50-day, purple = 200-day, dotted = Bollinger Bands. "
               "RSI above 70 = overbought, below 30 = oversold.")

with tab_signals:
    st.subheader("📐 Evidence-based measures")
    st.caption("These come from official NSE files or have held up in our tests on Indian large caps.")
    momentum = extras.get("momentum")
    if momentum is not None:
        leaders = ui.get_momentum_leaders()
        mine = leaders[leaders["Symbol"] == symbol.removesuffix(".NS")]
        rank = f" · ranks {mine.index[0] + 1} of {len(leaders)} F&O stocks" if not mine.empty else ""
        verdict = "🟢" if momentum > 0 else "🔴"
        st.markdown(f"{verdict} **12-month momentum vs NIFTY** (skipping the last month): **{momentum:+.1f} pts**{rank}  \n"
                    "Most reliable measure in our tests: the top 20% beat NIFTY over the next 3 months 54% of the "
                    "time (bottom 20%: 49%). A modest edge, not a guarantee.")
    delivery = extras.get("delivery")
    if delivery:
        st.markdown(f"{ui.BADGE[delivery['verdict']]} **Delivery % (NSE official, {delivery['date']}):** "
                    f"{delivery['delivery_pct']:.1f}% vs {delivery['avg_pct']:.1f}% usual  \n{delivery['detail']}")
        history = ui.get_delivery_history(symbol)
        if not history.empty:
            st.bar_chart(history["delivery_pct"].rename("Delivery %"), height=160)
    fo = extras.get("fo")
    if fo:
        mood = {"Long build-up": "🟢", "Short covering": "🟢", "Short build-up": "🔴", "Long unwinding": "🔴"}[fo["buildup"]]
        pcr = f" · put-call ratio {fo['pcr']:.2f}" if fo["pcr"] is not None else ""
        st.markdown(f"{mood} **F&O positioning (NSE official, {fo['date']}): {fo['buildup']}**  \n"
                    f"Futures price {fo['price_change_pct']:+.2f}%, open interest {fo['oi_change_pct']:+.2f}%{pcr}. "
                    f"{fo['detail']}")
    row = df.iloc[-1]
    if not pd.isna(row.get("ADX")):
        strength = "strong trend" if row["ADX"] >= 25 else "weak or no trend" if row["ADX"] < 20 else "building trend"
        direction = "up" if row["DI_plus"] > row["DI_minus"] else "down"
        st.markdown(f"⚪ **Trend strength (ADX):** {row['ADX']:.0f}, {strength}, pointing {direction} · "
                    f"**CCI:** {row['CCI']:.0f}  \nInformation only: adding these to the score didn't improve "
                    "accuracy in our tests.")

    st.divider()
    st.subheader(f"{ui.BADGE[tech_view]} Rule checks: {tech_view} (score {tech_score:+d})")
    st.caption("Simple rule-based checks (trend, momentum, bands, volume). Honest note: across 25 large stocks over "
               "5 years, Bullish readings were right 52% of the time and Bearish 48% — close to a coin flip. Use them "
               "to describe the chart, not to predict it. Check this stock on the Backtest page.")
    for s in sigs:
        st.markdown(f"{ui.BADGE[s['verdict']]} **{s['name']}** — {s['verdict']}  \n{s['detail']}")
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Support (20-day low)", ui.rupees(snap["support_20d"]))
    c2.metric("Resistance (20-day high)", ui.rupees(snap["resistance_20d"]))
    c3.metric("Average daily move (ATR)", ui.rupees(snap["ATR"]),
              None if snap["atr_pct"] is None else f"{snap['atr_pct']:.2f}% of price", delta_color="off")

with tab_fund:
    if fundamentals:
        st.dataframe([{"Metric": k, "Value": ui.nice(v)} for k, v in fundamentals.items()],
                     width="stretch", hide_index=True)
    else:
        st.info("No fundamental data for this symbol (indices have none).")

with tab_news:
    if data["news"]:
        for n in data["news"]:
            title = f"[{n['title']}]({n['url']})" if n["url"] else n["title"]
            st.markdown(f"**{title}**  \n{n['publisher']} · {n['date']}")
    else:
        st.info("No recent news found for this symbol.")

with tab_social:
    st.caption("What retail investors are saying. Social chatter is noisy: treat it as a mood check, not a signal.")
    stw = data["social"]["stocktwits"]
    rd = data["social"]["reddit"]
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
                ui.get_social.clear()
                st.rerun()
        else:
            st.info("No Reddit posts mentioning this stock in the last 30 days.")

with tab_market:
    if vix:
        st.subheader(f"🌡️ {vix}")
    if turbulence:
        st.markdown(f"**Market turbulence: {turbulence['label']}** — {turbulence['note']} (5-day average at the "
                    f"{turbulence['five_day_percentile']:.0f}th percentile of the last 2 years, from 50 large stocks).")
        st.line_chart(turbulence_series.tail(500).rename("Turbulence index"), height=160)
        st.caption("Turbulence measures how unusual the market's moves are compared with the past year "
                   "(the FinRL framework's risk switch). Spikes match events like the June 2024 election result day.")
    flows = ui.get_participants()
    if flows:
        st.markdown(f"**Who is positioned how in index futures** (NSE official, {flows['date']:%d %b %Y})")
        st.dataframe([{**r, "Long %": f"{r['Long %']:.0f}%" if r.get("Long %") is not None else "–"}
                      for r in flows["rows"]], width="stretch", hide_index=True)
        st.caption("FII = foreign investors. A low FII long % means foreigners are betting on a fall in the index; "
                   "retail clients are often on the other side.")
    if data["macro_rows"]:
        st.dataframe([{
            "Indicator": r["name"], "Last": f"{r['last']:,.2f}", "1 week": ui.pct(r["change_1w"]),
            "1 month": ui.pct(r["change_1m"]), "3 months": ui.pct(r["change_3m"]), "Trend": r["trend"] or "–",
        } for r in data["macro_rows"]], width="stretch", hide_index=True)
    if relative:
        parts = [f"{v:+.2f} pts over {k.split('_')[-1]}" for k, v in relative.items()]
        st.markdown(f"**{name} vs NIFTY 50:** " + ", ".join(parts) + " (positive = beating the market)")
    st.markdown("#### Market headlines (last 7 days)")
    for n in data["market_news"]:
        title = f"[{n['title']}]({n['url']})" if n["url"] else n["title"]
        st.markdown(f"**{title}**  \n{n['publisher']} · {n['date']}")

with tab_position:
    if holding:
        st.subheader("Your holding")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Shares", f"{holding['qty']:g}")
        c2.metric("Average price", ui.rupees(holding["avg"]))
        c3.metric("Current value", ui.rupees(holding["value"], 0))
        c4.metric("Unrealised P&L", ui.rupees(holding["pnl"], 0), ui.pct(holding["pnl_pct"]))
    elif owned == "Yes":
        st.info("Enter your shares and average price in the sidebar.")
    else:
        st.info("Tell the app in the sidebar whether you own this stock so the AI team can tailor its plan.")
    st.subheader("Position sizing (rule-based, no AI)")
    if size:
        st.caption(f"Stop-loss placed {portfolio.STOP_ATR_MULTIPLE:g}× the average daily move (ATR) below the price; "
                   f"if it is hit you lose at most {risk_pct:g}% of your capital.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Suggested stop-loss", ui.rupees(size["stop"]))
        c2.metric("Risk per share", ui.rupees(size["risk_per_share"]))
        c3.metric("Max shares to buy", f"{size['max_qty']:,}")
        c4.metric("Max position value", ui.rupees(size["max_value"], 0), f"{size['pct_of_capital']:.1f}% of capital",
                  delta_color="off")
    else:
        st.info("Enter your trading capital in the sidebar to see how many shares you could buy safely.")
    if data["liquidity"]:
        st.caption(f"Liquidity: about ₹{data['liquidity'] / 1e7:,.2f} Cr traded per day (20-day average).")

with tab_ai:
    if cfg["provider"] == ui.NO_AI:
        st.info("Choose an AI provider in the sidebar to get a decision from a team of AI analysts.")
        st.markdown(
            "**Which one should I use?** Your Claude, Gemini or ChatGPT *subscriptions* don't work here — apps need "
            "a separate **API key**. The easiest is a free Gemini key from "
            "[Google AI Studio](https://aistudio.google.com/apikey): sign in, click *Create API key*, paste it in the sidebar."
        )
    else:
        if cfg["quick"]:
            st.markdown("**Quick mode:** one Portfolio Manager reviews everything in a single AI call.")
        else:
            st.markdown(
                f"**How it works:** {', '.join(cfg['analysts'])} analysts write reports → Bull vs Bear debate "
                f"({cfg['rounds']} round{'s' if cfg['rounds'] > 1 else ''}) → the Trader drafts a plan → the "
                "Aggressive, Conservative and Neutral risk analysts challenge it → the Portfolio Manager approves, "
                "modifies or rejects it. Only market data and the position you entered are sent to the AI."
            )
        if data["memory"]:
            st.caption("🧠 The team will be reminded of its past calls and lessons (see Track record).")
        state_key = f"result::{symbol}::{cfg['provider']}::{cfg['model']}"
        if st.button("▶ Run AI analysis", type="primary", disabled=not cfg["ready"]):
            result = ui.run_ai(cfg, data)
            if result:
                research.record_ai(data, result, cfg["provider"], cfg["model"], prefs["horizon_days"],
                                   "ai-quick" if cfg["quick"] else "ai")
                st.session_state[state_key] = result
        if not cfg["ready"]:
            st.warning("Finish the AI setup in the sidebar (model and, for cloud AI, an API key).")

        result = st.session_state.get(state_key)
        if result:
            ui.decision_card(result)
            report = ai.to_markdown(result, f"{name} ({symbol}) — Trade Lens IN report, {result['time']}")
            st.download_button("⬇ Download full report", report,
                               file_name=f"{symbol}-{pd.Timestamp.now():%Y%m%d-%H%M}.md", mime="text/markdown")
            st.caption(f"Saved to your track record. It will be judged after {prefs['horizon_days']} trading days.")

    past = track.decisions(symbol)
    if past:
        st.divider()
        st.markdown("#### 🎯 Track record for this stock")
        _, progress = ui.refresh_track(pd.Timestamp.now().strftime("%Y-%m-%d %H"))
        ui.decisions_table(past[:10], progress, show_symbol=False)
