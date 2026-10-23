from datetime import time

import streamlit as st

import daily_report
import portfolio
import scheduler
import settings
import ui
from storage import REPORTS_DIR

prefs = settings.load()
book = portfolio.load()
cfg = ui.ai_sidebar(team_options=False, title="AI for reports (optional)")
st.sidebar.divider()
st.sidebar.caption(ui.DISCLAIMER)

st.title("🗞️ Daily report")
st.caption("After market close, the app scans your watchlist, saves each stock's signal view to the track record, "
           "judges older calls, and writes a short report: market mood, your watchlist sorted by signal strength, "
           "signals that changed, your P&L and (optionally) an AI quick take per stock.")

state = scheduler.status()
st.subheader("Schedule")
c1, c2 = st.columns(2)
when = c1.time_input("Run every weekday at", value=time(prefs["report_hour"], prefs["report_minute"]), step=900)
include_ai = c2.checkbox("Include AI quick take for each stock", value=prefs["report_ai"],
                         disabled=cfg["provider"] == ui.NO_AI,
                         help="Uses the AI provider, model and saved key from the sidebar. One AI call per stock.")
if cfg["provider"] == ui.NO_AI:
    include_ai = False
settings.update(report_hour=when.hour, report_minute=when.minute, report_ai=include_ai)
if include_ai:
    st.caption(f"About **{len(book['watchlist'])} AI calls** per report, plus up to 10 for lessons. "
               + ("" if cfg["api_key"] else "⚠️ The key must be saved (Remember ticked) for scheduled reports."))

if state["enabled"]:
    st.success(f"✅ Scheduled: every weekday at {state['hour']:02d}:{state['minute']:02d}. "
               "If your Mac is asleep then, it runs when it wakes up.")
    b1, b2 = st.columns(2)
    if b1.button("Update schedule", disabled=(state["hour"], state["minute"]) == (when.hour, when.minute)):
        scheduler.enable(when.hour, when.minute)
        st.rerun()
    if b2.button("Turn off daily report"):
        scheduler.disable()
        st.rerun()
else:
    st.info("Daily report is off.")
    if st.button("Turn on daily report", type="primary", disabled=not book["watchlist"]):
        try:
            scheduler.enable(when.hour, when.minute)
        except RuntimeError as exc:
            st.error(f"Could not schedule it: {exc}")
        else:
            st.rerun()
    if not book["watchlist"]:
        st.caption("Add stocks to your watchlist first.")

if st.button("▶ Create a report now", disabled=not book["watchlist"]):
    with st.status("Creating report…", expanded=True) as status:
        try:
            path = daily_report.generate(include_ai=include_ai, log=status.write)
        except Exception as exc:
            status.update(label="Report failed", state="error")
            st.error(str(exc))
        else:
            status.update(label="Report ready", state="complete", expanded=False)
            ui.refresh_track.clear()
            ui.get_scan.clear()
            st.session_state["report_pick"] = path.name

st.divider()
reports = sorted(REPORTS_DIR.glob("*.md"), reverse=True) if REPORTS_DIR.exists() else []
if not reports:
    st.info("No reports yet. Click **Create a report now** or turn on the daily schedule.")
else:
    names = [p.name for p in reports]
    default = names.index(st.session_state["report_pick"]) if st.session_state.get("report_pick") in names else 0
    pick = st.selectbox("Report", names, index=default, format_func=lambda n: n.removesuffix(".md"))
    text = (REPORTS_DIR / pick).read_text(encoding="utf-8")
    st.download_button("⬇ Download", text, file_name=pick, mime="text/markdown")
    st.markdown(text)

log = scheduler.last_log_lines()
if log:
    with st.expander("Scheduled run log"):
        st.code(log, language=None)
