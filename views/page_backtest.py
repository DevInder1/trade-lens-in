from datetime import date, timedelta

import streamlit as st

import ai
import backtest
import charts
import market
import research
import settings
import track
import ui

prefs = settings.load()
with st.sidebar:
    st.subheader("Backtest settings")
    exchange = st.radio("Exchange", ["NSE", "BSE"], horizontal=True, key="bt_exchange")
    query = st.text_input("Symbol or index", value=prefs["last_query"], key="bt_query")
    years = st.selectbox("Years of history", [1, 2, 5], index=1)
    horizon = st.selectbox("Judge each call after (trading days)", [10, 20, 40, 60],
                           index=[10, 20, 40, 60].index(prefs["horizon_days"]) if prefs["horizon_days"] in
                           (10, 20, 40, 60) else 1)
cfg = ui.ai_sidebar(title="AI backtest (optional)")
st.sidebar.divider()
st.sidebar.caption(ui.DISCLAIMER)

symbol = market.normalize_symbol(query, exchange)
st.title("⏪ Backtest")
if not symbol:
    st.info("Type a symbol in the sidebar.")
    st.stop()

st.subheader(f"1. Rule-based signals on {symbol} (no AI)")
st.caption(f"For every trading day in the last {years} year(s), the app works out what the signals said using only "
           f"data up to that day, then checks the next {horizon} trading days. The strategy line buys when signals are "
           "Bullish and holds cash otherwise, with 0.1% cost per trade.")
try:
    with st.spinner("Running backtest…"):
        bt = ui.get_backtest(symbol, years, horizon)
except Exception as exc:
    st.error(f"Backtest failed: {exc}")
    st.stop()

s = bt["summary"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Signals strategy", ui.pct(s["strategy_return"]), f"worst fall {s['strategy_drawdown']:.1f}%",
          delta_color="off")
c2.metric("Buy and hold", ui.pct(s["hold_return"]), f"worst fall {s['hold_drawdown']:.1f}%", delta_color="off")
c3.metric("NIFTY 50", ui.pct(s["nifty_return"]))
c4.metric("Time invested", f"{s['time_in_market']:.0f}%", f"{s['entries']} entries", delta_color="off")
st.plotly_chart(charts.equity_chart(bt["curves"]), width="stretch")
st.markdown(f"**How reliable each signal view was** ({s['start']} to {s['end']}):")
st.dataframe(bt["table"], width="stretch", hide_index=True)
st.caption("Past results don't guarantee future results. A hit rate near 50% means the signal adds little on this stock.")

st.divider()
st.subheader("2. AI team on past dates")
st.caption("The AI team is run as if it were a past date, using only prices, macro data and news headlines from up "
           "to that date (fundamentals and social posts are left out because only today's versions exist). Each call "
           "is judged straight away because the future is already known. Calls are saved as *AI backtest* in your "
           "track record. Note: the AI model itself may remember some later events, so treat results as indicative.")
if cfg["provider"] == ui.NO_AI:
    st.info("Choose an AI provider in the sidebar to run the AI team on past dates.")
    st.stop()

mode = st.radio("Which dates?", ["Several past dates (about monthly)", "One specific date"], horizontal=True)
if mode.startswith("Several"):
    count = st.slider("Number of dates", 2, 10, 4)
    dates = backtest.past_dates(symbol, count, horizon)
    per_run = 1 if cfg["quick"] else ai.call_count(ai.team_analysts(cfg["analysts"], True), cfg["rounds"], False)
    st.caption(f"Dates: {', '.join(dates)} · about **{per_run * len(dates)} AI calls** "
               f"({'Quick' if cfg['quick'] else 'Full team'} mode, set in the sidebar).")
else:
    latest = date.today() - timedelta(days=int(horizon * 1.5) + 3)
    picked = st.date_input("Analyse as of", value=latest - timedelta(days=60), max_value=date.today() - timedelta(days=1),
                           min_value=date.today() - timedelta(days=365 * 3))
    dates = [picked.strftime("%Y-%m-%d")]
    if picked > latest:
        st.caption(f"Calls after about {latest:%d %b %Y} can't be judged yet; they will be judged later automatically.")

if st.button("▶ Run AI backtest", type="primary", disabled=not cfg["ready"] or not dates):
    results = []
    for i, day in enumerate(dates, 1):
        with st.spinner(f"Collecting data as of {day} ({i}/{len(dates)})…"):
            data = research.build(symbol, as_of=day)
        result = ui.run_ai(cfg, data, label=f"AI team as of {data['as_of']} ({i}/{len(dates)})…")
        if not result:
            break
        row_id, d = research.record_ai(data, result, cfg["provider"], cfg["model"], horizon, "ai-backtest")
        results.append({"id": row_id, "result": result, "as_of": data["as_of"]})
    track.refresh()
    ui.refresh_track.clear()
    st.session_state[f"bt_ai::{symbol}"] = results

results = st.session_state.get(f"bt_ai::{symbol}")
if results:
    saved = {r["id"]: r for r in track.decisions(symbol)}
    rows = [saved[r["id"]] for r in results if r["id"] in saved]
    judged = [r for r in rows if r["outcome"]]
    if judged:
        right = sum(1 for r in judged if r["outcome"] == "Right")
        st.metric("AI hit rate on these dates", f"{right}/{len(judged)} right",
                  f"avg vs NIFTY {ui.pct(sum(r['alpha_pct'] for r in judged) / len(judged))}", delta_color="off")
    ui.decisions_table(rows, show_symbol=False)
    if len(results) == 1:
        ui.decision_card(results[0]["result"])
