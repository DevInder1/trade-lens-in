import streamlit as st

import macro
import portfolio
import research
import settings
import track
import ui

NIFTY_TOP = ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "BHARTIARTL", "ITC", "LT", "SBIN", "KOTAKBANK"]

prefs = settings.load()
book = portfolio.load()

with st.sidebar:
    st.subheader("Add stocks")
    exchange = st.radio("Exchange", ["NSE", "BSE"], horizontal=True, key="wl_exchange")
    nonce = st.session_state.get("wl_add_nonce", 0)
    chosen = ui.stocks_multi_picker("Search and pick stocks", f"wl_add_{nonce}", exchange,
                                    "Pick as many as you like, then click Add.")
    if st.button("➕ Add to watchlist", disabled=not chosen):
        added = portfolio.add_to_watchlist(chosen)
        st.toast(f"Added {', '.join(ui.short(s) for s in added)}" if added else "Already on your watchlist")
        st.session_state["wl_add_nonce"] = nonce + 1
        st.rerun()
    if st.button("Add NIFTY top 10"):
        portfolio.add_to_watchlist([f"{s}.NS" for s in NIFTY_TOP])
        st.rerun()
cfg = ui.ai_sidebar(team_options=False, title="AI quick takes (optional)")
st.sidebar.divider()
st.sidebar.caption(ui.DISCLAIMER)

st.title("⭐ Watchlist")
macro_rows = ui.get_macro()
nifty = next((r for r in macro_rows if r["symbol"] == "^NSEI"), None)
c1, c2, c3 = st.columns(3)
if nifty:
    c1.metric("NIFTY 50", f"{nifty['last']:,.2f}", ui.pct(nifty["change_1w"]) + " this week")
c2.metric("Market mood (India VIX)", macro.vix_mood(macro_rows) or "–")
c3.metric("Stocks on watchlist", len(book["watchlist"]))

if not book["watchlist"]:
    st.info("Your watchlist is empty. Add stocks in the sidebar, or click **Add NIFTY top 10** to start.")
    st.stop()

with st.spinner(f"Scanning {len(book['watchlist'])} stocks…"):
    rows = ui.scan_watchlist(book)
good = [r for r in rows if not r["error"]]
for r in good:
    research.record_signals(r["symbol"], r["name"], r["tech"], prefs["horizon_days"])

latest_ai = {}
for d in track.decisions():
    if d["source"].startswith("ai") and d["symbol"] not in latest_ai:
        latest_ai[d["symbol"]] = d

table = []
for r in good:
    last = latest_ai.get(r["symbol"])
    table.append({
        "Stock": r["name"],
        "Symbol": r["symbol"],
        "Close": ui.rupees(r["price"]),
        "1 day": ui.pct(r["change_1d"]),
        "1 month": ui.pct(r["change_1m"]),
        "vs NIFTY (1m)": ui.pct(r["vs_nifty_1m"]),
        "Momentum 12m": ui.pct(r["momentum"]).replace("%", " pts") if r.get("momentum") is not None else "–",
        "Delivery %": (f"{r['delivery_pct']:.0f}% (usual {r['delivery_avg']:.0f}%)"
                       if r.get("delivery_pct") is not None else "–"),
        "F&O": r.get("buildup") or "–",
        "RSI": round(r["rsi"]) if r["rsi"] is not None else None,
        "Signals": f"{ui.BADGE[r['view']]} {r['view']} ({r['score']:+d})",
        "Your P&L": "" if r["pnl"] is None else f"{ui.rupees(r['pnl'], 0)} ({ui.pct(r['pnl_pct'])})",
        "Last AI call": f"{ui.RATING_BADGE.get(last['rating'], '')} {last['rating']} · {last['as_of']}" if last else "",
    })
st.subheader("Scanner")
order = st.radio("Sort by", ["Momentum (most reliable)", "Signal score"], horizontal=True)
if order.startswith("Momentum"):
    table.sort(key=lambda row: -float(row["Momentum 12m"].replace(" pts", "")) if row["Momentum 12m"] != "–" else 1e9)
st.dataframe(table, width="stretch", hide_index=True)
st.caption("Momentum 12m = the stock's return over the last 12 months (skipping the latest month) minus NIFTY's. "
           "Delivery % and F&O build-up come from NSE's official end-of-day files.")
st.caption(f"Data as of {good[0]['date'] if good else '–'}. Today's signal view for each stock is saved to your "
           f"track record and judged after {prefs['horizon_days']} trading days.")
bad = [r for r in rows if r["error"]]
if bad:
    st.warning("Could not load: " + ", ".join(r["symbol"] for r in bad) + ". Check the symbols or remove them.")

labels = {f"{r['name']} ({r['symbol']})": r["symbol"] for r in good}
c1, c2 = st.columns([3, 1])
pick = c1.selectbox("Open a stock in Analyse", list(labels), label_visibility="collapsed")
if c2.button("Analyse →", width="stretch") and pick:
    ui.go_analyse(labels[pick])

with st.expander("Remove stocks"):
    remove = st.multiselect("Remove", book["watchlist"], label_visibility="collapsed")
    if st.button("Remove selected", disabled=not remove):
        portfolio.remove_from_watchlist(remove)
        st.rerun()
    if st.button("🔄 Refresh prices now"):
        ui.get_scan.clear()
        st.rerun()

st.divider()
st.subheader("🤖 AI quick take on every stock")
if cfg["provider"] == ui.NO_AI:
    st.info("Choose an AI provider in the sidebar to get an AI quick take (one AI call per stock).")
else:
    st.caption(f"Runs the Portfolio Manager quick review for all {len(good)} stocks: {len(good)} AI calls. "
               "Each decision is saved to your track record.")
    if st.button(f"▶ Run AI on {len(good)} stocks", type="primary", disabled=not cfg["ready"]):
        results = []
        progress = st.progress(0.0)
        for i, r in enumerate(good, 1):
            progress.progress(i / len(good), text=f"{r['name']} ({i}/{len(good)})")
            data = research.build(r["symbol"], name=r["name"], macro_rows=macro_rows,
                                  market_news=ui.get_market_news(), book=book)
            result = ui.run_ai(cfg, data, quick=True, label=f"{r['name']}…")
            if not result:
                break
            _, d = research.record_ai(data, result, cfg["provider"], cfg["model"], prefs["horizon_days"], "ai-quick")
            results.append({"Stock": r["name"],
                            "Rating": f"{ui.RATING_BADGE.get(d['rating'], '⚪')} {d['rating'] or 'unclear'}",
                            "Action": d["action"] or "", "Entry": d["entry"] or "", "Stop-loss": d["stop-loss"] or "",
                            "Target": d["target"] or "", "Confidence": d["confidence"] or ""})
        progress.empty()
        st.session_state["wl_ai_results"] = results
    if st.session_state.get("wl_ai_results"):
        st.dataframe(st.session_state["wl_ai_results"], width="stretch", hide_index=True)
    if not cfg["ready"]:
        st.warning("Finish the AI setup in the sidebar (model and, for cloud AI, an API key).")
