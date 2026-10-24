import pandas as pd
import streamlit as st

import charts
import fno
import ideas
import intraday
import journal
import macro
import portfolio
import track
import ui
import zones
from storage import REPORTS_DIR

book = portfolio.load()
now = fno.now_ist()
greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"

st.title(f"{greeting} 👋")
macro_rows = ui.get_macro()
nifty = next((r for r in macro_rows if r["symbol"] == "^NSEI"), None)
session = pd.Timestamp(nifty["date"]).date() if nifty else None
status = fno.market_status(session, now)
st.caption(f"{now:%A %d %B %Y, %H:%M} IST · {status['label']}")

turbulence_series, turbulence = ui.get_turbulence()
flows = ui.get_participants()
fii = next((r for r in (flows or {}).get("rows", []) if r["Participant"].startswith("FII")), None)

c = st.columns(4)
if nifty:
    c[0].metric("NIFTY 50", f"{nifty['last']:,.0f}", f"{ui.pct(nifty['change_1w'])} this week")
c[1].metric("Fear gauge (India VIX)", macro.vix_mood(macro_rows) or "–")
if turbulence:
    c[2].metric("Market turbulence", turbulence["label"], f"{turbulence['five_day_percentile']:.0f}th percentile",
                delta_color="off", help="How unusual recent market moves are vs the past year (FinRL's risk switch).")
if fii:
    c[3].metric("FII index futures long", f"{fii['Long %']:.0f}%",
                f"net {fii['Net change']:+,} contracts" if fii.get("Net change") is not None else None,
                help="Share of foreign investors' index-futures positions that are long (NSE official). "
                     "Below 30% = heavily bearish positioning.")

if nifty and nifty.get("trend"):
    tone = "⚠️" if turbulence and turbulence["label"] in ("Elevated", "Extreme") else "ℹ️"
    st.markdown(f"{tone} **Market read:** NIFTY is in a {nifty['trend'].split(' (')[0].lower()}; turbulence is "
                f"{turbulence['label'].lower() if turbulence else 'unknown'} — {turbulence['note'] if turbulence else ''}.")

live_hours = now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) < (15, 31)


def flow_card(row, side: str, snap: dict):
    analysis = zones.analyse(snap["minutes"][row["ticker"]], snap["daily"].get(row["ticker"]), snap["day"],
                             row["state"], row["last"], row["adr"], snap["status"]["live"])
    plan = ideas.idea(row, analysis, side)
    with st.container(border=True):
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        word = "in" if side == "in" else "out"
        c1.markdown(f"**{row['symbol']}** · {ui.pct(row['change_pct'])}  \n"
                    f"₹{abs(row['flow_cr']):,.0f} Cr {word} ({abs(row['flow_pct']):.0f}% of ₹{row['turnover_cr']:,.0f} Cr "
                    "traded)")
        path = intraday.intraday_path(snap["minutes"][row["ticker"]], snap["day"])
        if not path.empty:
            c2.plotly_chart(charts.sparkline(path, row["open"]), width="stretch", config={"displayModeBar": False},
                            key=f"spark_{side}_{row['symbol']}")
        icon = {"Buy idea": "🟢", "Sell idea": "🔴"}.get(plan["bias"], "⏸️")
        st.markdown(f"{icon} **{plan['bias']}** · confidence {plan['confidence']}  \n{plan['text']}")
        b1, b2 = st.columns(2)
        if b1.button("Analyse →", key=f"go_{side}_{row['symbol']}", width="stretch"):
            ui.go_analyse(row["ticker"])
        if b2.button("⭐ Watchlist", key=f"wl_{side}_{row['symbol']}", width="stretch"):
            portfolio.add_to_watchlist([row["ticker"]])
            st.toast(f"{row['symbol']} added to your watchlist")


@st.fragment(run_every=60 if live_hours else None)
def money_flow_section():
    st.subheader("💸 Where money is moving (F&O stocks)")
    with st.spinner("Loading minute data for every F&O stock…"):
        snap = ui.get_terminal()
    if snap["table"].empty:
        st.info("Live data isn't available right now. Try again in a minute.")
        return
    inflow, outflow = intraday.money_flow(snap["table"])
    status = snap["status"]
    when = "live, refreshes every minute" if status["live"] else "ideas are for the next session"
    st.caption(f"{status['label']} · {when} · updated {snap['fetched']} IST. Money in = value traded on up-ticks minus "
               "value on down-ticks, from 1-minute data (matches NSE's official turnover within a few %). Ideas are "
               "rule-based (VWAP, order-block zones, liquidity), not advice.")
    count = st.session_state.get("flow_count", 10)
    left, right = st.columns(2)
    with left:
        st.markdown(f"#### 🟢 Money coming in ({len(inflow)})")
        for _, row in inflow.head(count).iterrows():
            flow_card(row.to_dict(), "in", snap)
    with right:
        st.markdown(f"#### 🔴 Money going out ({len(outflow)})")
        for _, row in outflow.head(count).iterrows():
            flow_card(row.to_dict(), "out", snap)
    if count < max(len(inflow), len(outflow)):
        st.button("⬇ Load 10 more", width="stretch",
                  on_click=lambda: st.session_state.update(flow_count=count + 10))


money_flow_section()

if not book["watchlist"]:
    st.info("**Start here (3 steps):** 1) Open **Watchlist** and click *Add NIFTY top 10* or add your stocks. "
            "2) Open **Terminal** during market hours to see live movers. 3) Pick a stock in **Analyse**; for the AI "
            "team choose *Ollama* in the sidebar (free, runs on your Mac).")

left, right = st.columns(2)
with left:
    st.subheader("⭐ Your watchlist")
    if book["watchlist"]:
        with st.spinner("Scanning your watchlist…"):
            rows = [r for r in ui.scan_watchlist(book) if not r["error"]]
        ranked = sorted(rows, key=lambda r: -(r.get("momentum") if r.get("momentum") is not None else -1e9))
        st.dataframe([{"Stock": r["symbol"].removesuffix(".NS"), "Close": ui.rupees(r["price"]),
                       "Day": ui.pct(r["change_1d"]),
                       "Momentum 12m": f"{r['momentum']:+.1f}" if r.get("momentum") is not None else "–",
                       "F&O": r.get("buildup") or "–", "Signals": f"{ui.BADGE[r['view']]} {r['view']}"}
                      for r in ranked], hide_index=True, width="stretch")
        if st.button("Open watchlist →"):
            st.switch_page("views/page_watchlist.py")
    else:
        st.caption("Empty for now.")

with right:
    st.subheader("🚀 Momentum leaders (F&O stocks)")
    with st.spinner("Ranking F&O stocks…"):
        leaders = ui.get_momentum_leaders()
    if not leaders.empty:
        top = leaders.head(8)
        st.dataframe(top.assign(**{"Momentum vs NIFTY": top["Momentum vs NIFTY"].map(lambda v: f"{v:+.1f} pts")})
                     [["Symbol", "Sector", "Momentum vs NIFTY"]], hide_index=True, width="stretch")
        st.caption("12-month return (skipping the last month) minus NIFTY's. In our tests the top 20% beat NIFTY over "
                   "the next 3 months 54% of the time. These are large stocks today, so history flatters it a little.")

left, right = st.columns(2)
with left:
    st.subheader("📒 Journal")
    trades = journal.trades()
    month = trades[(trades["status"] == "Closed") & (pd.to_datetime(trades["to_date"]).dt.to_period("M")
                                                       == pd.Timestamp(now.date()).to_period("M"))] \
        if not trades.empty else trades
    if trades.empty:
        st.caption("No trades logged yet.")
    else:
        st.metric("This month's realised P&L", ui.rupees(float(month["pnl"].sum()) if not month.empty else 0.0, 0),
                  f"{len(month)} closed trades · {int((trades['status'] == 'Open').sum())} open", delta_color="off")
with right:
    st.subheader("🎯 Track record")
    rows = track.decisions()
    judged = [r for r in rows if r["outcome"]]
    if judged:
        right_calls = sum(1 for r in judged if r["outcome"] == "Right")
        st.metric("Calls judged right", f"{right_calls}/{len(judged)}", f"{right_calls / len(judged) * 100:.0f}%",
                  delta_color="off")
    else:
        st.caption(f"{len(rows)} calls saved, none judged yet (judged after ~1 month).")
    reports = sorted(REPORTS_DIR.glob("*.md"), reverse=True) if REPORTS_DIR.exists() else []
    if reports:
        st.caption(f"Latest daily report: {reports[0].stem}")

with st.expander("📖 Glossary: what the terms mean"):
    st.markdown("""
- **Strength** (Terminal): how far a stock moved since the open, in multiples of its normal daily range, counted only if the move was clean.
- **Order block / zone**: the last opposite candle before a strong move; price often reacts when it comes back to it.
- **Liquidity**: untaken highs and lows where stop-loss orders cluster; price often reaches for them.
- **Momentum 12m**: 12-month return (skipping the last month) minus NIFTY's. Our most reliable measure, still modest.
- **Delivery %**: share of traded shares actually taken home (not intraday). High on an up day = accumulation.
- **Long build-up / Short build-up / Short covering / Long unwinding**: what the futures price and open interest did together.
- **Put-call ratio (PCR)**: put open interest ÷ call open interest. Very high or low values show crowded positioning.
- **Turbulence**: how unusual the market's moves are vs the past year. High = risky conditions.
- **Sharpe ratio**: return per unit of risk above a fixed deposit (6.5%). Above 1 is good.
- **Max drawdown**: the worst fall from a peak.
""")
