from datetime import date

import pandas as pd
import streamlit as st

import charts
import journal
import ui

NEW_TAG = "＋ New tag…"

st.title("📒 Trading journal")
st.caption("Log your trades to see what actually works for you. Saved only on this computer (data/journal.db).")

trades = journal.trades()
prefill = st.session_state.pop("journal_prefill", None) or {}

with st.expander("➕ Log a trade", expanded=bool(prefill) or trades.empty):
    with st.form("add_trade", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        symbol = c1.text_input("Symbol", value=prefill.get("symbol", ""), placeholder="e.g. SBIN")
        side = c2.radio("Side", journal.SIDES, horizontal=True,
                        index=journal.SIDES.index(prefill.get("side", "Long")))
        qty = c3.number_input("Quantity", min_value=0.0, step=1.0)
        c1, c2, c3 = st.columns(3)
        entry = c1.number_input("Entry price (₹)", min_value=0.0, step=0.05, value=float(prefill.get("entry", 0.0)))
        exit_price = c2.number_input("Exit price (₹)", min_value=0.0, step=0.05,
                                     help="Leave 0 if the trade is still open.")
        charges = c3.number_input("Charges (₹)", min_value=0.0, step=1.0, help="Brokerage, STT and other costs.")
        c1, c2 = st.columns(2)
        from_date = c1.date_input("From", value=date.today())
        to_date = c2.date_input("To", value=date.today(), help="For trades held over several days.")
        c1, c2 = st.columns(2)
        tag = c1.selectbox("Setup tag", [NEW_TAG, *journal.setups(trades)])
        new_tag = c2.text_input("New tag", placeholder="e.g. Bullish zone retest",
                                help="Typing a new tag here overrides the list.")
        note = st.text_area("Note", placeholder="Why you took it, what you learned…", height=80)
        if st.form_submit_button("Save trade", type="primary"):
            try:
                journal.add(symbol, side, qty, entry, exit_price or None, from_date, to_date,
                            new_tag.strip() or ("" if tag == NEW_TAG else tag), charges, note)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.toast("Trade saved")
                st.rerun()

if trades.empty:
    st.info("No trades yet. Log your first one above, or click 📒 Journal on any chart in the Terminal.")
    st.stop()

s = journal.stats(trades)
c = st.columns(4)
c[0].metric("Realised P&L", ui.rupees(s.get("pnl"), 0) if s["trades"] else "–")
c[1].metric("Closed trades", s["trades"], f"{s.get('open', 0)} open", delta_color="off")
c[2].metric("Win rate", f"{s['win_rate']:.0f}%" if s["trades"] else "–")
c[3].metric("Profit factor", f"{s['profit_factor']:.2f}" if s.get("profit_factor") else "–",
            help="Total won ÷ total lost. Above 1 means you make more than you lose.")
if s["trades"]:
    c = st.columns(4)
    c[0].metric("Average win", ui.rupees(s["avg_win"], 0))
    c[1].metric("Average loss", ui.rupees(s["avg_loss"], 0))
    c[2].metric("Best trade", ui.rupees(s["best"], 0))
    c[3].metric("Worst trade", ui.rupees(s["worst"], 0))

daily = journal.daily_pnl(trades)
if not daily.empty:
    st.subheader("P&L calendar")
    months = sorted({(d.year, d.month) for d in daily.index}, reverse=True)
    year, month = st.selectbox("Month", months, format_func=lambda ym: pd.Timestamp(year=ym[0], month=ym[1], day=1)
                               .strftime("%B %Y"))
    month_total = daily[(daily.index.year == year) & (daily.index.month == month)].sum()
    st.caption(f"Total for the month: {ui.rupees(month_total, 0)} · trades counted on their exit (To) date")
    st.plotly_chart(charts.pnl_calendar(daily, year, month), width="stretch", config={"displayModeBar": False})
    st.line_chart(daily.cumsum().rename("Cumulative P&L (₹)"), height=220)

setups = journal.by_setup(trades)
if not setups.empty:
    st.subheader("Which setups pay")
    st.dataframe(setups.rename(columns={"setup": "Setup", "trades": "Trades", "pnl": "P&L (₹)",
                                        "win_rate": "Win rate %", "avg": "Avg per trade (₹)"}).round(1),
                 hide_index=True, width="stretch")

open_trades = trades[trades["status"] == "Open"]
if not open_trades.empty:
    st.subheader("Close an open trade")
    labels = {f"#{r['id']} {r['symbol']} {r['side']} {r['qty']:g} @ ₹{r['entry']:,.2f} ({r['from_date']})": r["id"]
              for _, r in open_trades.iterrows()}
    c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 1])
    pick = c1.selectbox("Open trade", list(labels), label_visibility="collapsed")
    price = c2.number_input("Exit ₹", min_value=0.0, step=0.05, label_visibility="collapsed")
    when = c3.date_input("Exit date", value=date.today(), label_visibility="collapsed")
    if c4.button("Close", disabled=not price):
        journal.close(labels[pick], price, when)
        st.rerun()

st.subheader("All trades")
view = trades[["id", "from_date", "to_date", "symbol", "side", "qty", "entry", "exit", "charges", "pnl", "return_pct",
               "setup", "status", "note"]].rename(columns={
    "id": "#", "from_date": "From", "to_date": "To", "symbol": "Symbol", "side": "Side", "qty": "Qty",
    "entry": "Entry", "exit": "Exit", "charges": "Charges", "pnl": "P&L", "return_pct": "Return %", "setup": "Setup",
    "status": "Status", "note": "Note"})
event = st.dataframe(view.round(2), hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row",
                     column_config={"P&L": st.column_config.NumberColumn(format="₹%.0f"),
                                    "Return %": st.column_config.NumberColumn(format="%+.2f%%")})
chosen = [int(view.iloc[i]["#"]) for i in (event.selection.rows if event and event.selection else [])]
c1, c2 = st.columns([1, 3])
if c1.button(f"🗑 Delete {len(chosen)} selected", disabled=not chosen):
    journal.delete(chosen)
    st.rerun()
c2.download_button("⬇ Export CSV", view.to_csv(index=False), file_name="trade-journal.csv", mime="text/csv")
