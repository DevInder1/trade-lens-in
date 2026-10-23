import pandas as pd
import streamlit as st

import ai
import settings
import track
import ui

HORIZONS = [10, 20, 40, 60]

prefs = settings.load()
with st.sidebar:
    st.subheader("How calls are judged")
    horizon = st.selectbox("Judge new calls after (trading days)", HORIZONS,
                           index=HORIZONS.index(prefs["horizon_days"]) if prefs["horizon_days"] in HORIZONS else 1,
                           help="20 trading days is about one month.")
    settings.update(horizon_days=horizon)
cfg = ui.ai_sidebar(team_options=False, title="AI lessons (optional)")
st.sidebar.divider()
st.sidebar.caption(ui.DISCLAIMER)

st.title("🎯 Track record")
st.caption(
    "Every AI decision, and each day's signal view for your watchlist, is saved here and judged automatically. "
    "**Buy / Overweight / Bullish** is right if the stock beats NIFTY 50; **Sell / Underweight / Bearish** is right "
    f"if it lags NIFTY; **Hold / Neutral** is right if it stays within ±{track.HOLD_BAND:g}% of NIFTY. Judged lessons "
    "are fed back to the AI team as memory."
)

with st.spinner("Checking prices for open calls…"):
    settled, progress = ui.refresh_track(pd.Timestamp.now().strftime("%Y-%m-%d %H"))
if st.button("🔄 Re-check now"):
    ui.refresh_track.clear()
    st.rerun()

rows = track.decisions()
if not rows:
    st.info("No decisions yet. Open the Watchlist page (saves today's signal views) or run the AI team on the "
            "Analyse page. Each call is judged after the chosen number of trading days.")
    st.stop()

summary = track.stats(rows)
judged = [r for r in rows if r["outcome"]]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Calls saved", len(rows))
c2.metric("Judged", len(judged))
right = sum(1 for r in judged if r["outcome"] == "Right")
c3.metric("Right", f"{right}/{len(judged)}" if judged else "–",
          f"{right / len(judged) * 100:.0f}% hit rate" if judged else None, delta_color="off")
c4.metric("Avg vs NIFTY", ui.pct(sum(r["alpha_pct"] for r in judged) / len(judged)) if judged else "–")
st.dataframe(summary, width="stretch", hide_index=True)

st.subheader("All calls")
sources = st.multiselect("Show", list(track.SOURCES.values()), default=list(track.SOURCES.values()))
stocks = sorted({r["name"] or r["symbol"] for r in rows})
stock = st.selectbox("Stock", ["All stocks", *stocks])
shown = [r for r in rows if track.SOURCES.get(r["source"]) in sources
         and (stock == "All stocks" or (r["name"] or r["symbol"]) == stock)]
ui.decisions_table(shown, progress)

lessons = [r for r in judged if r["lesson"]][:15]
if lessons:
    st.subheader("🧠 Lessons (memory)")
    for r in lessons:
        st.markdown(f"{ui.OUTCOME_BADGE.get(r['outcome'], '')} **{r['name'] or r['symbol']}** "
                    f"({track.SOURCES.get(r['source'])}): {r['lesson']}")

pending_lessons = track.needs_ai_lesson(50)
if pending_lessons:
    st.divider()
    st.markdown(f"**{len(pending_lessons)} judged AI calls** don't have an AI-written lesson yet.")
    if cfg["provider"] == ui.NO_AI:
        st.caption("Choose an AI provider in the sidebar to have the AI reflect on what it got right or wrong.")
    elif st.button(f"✍️ Write AI lessons ({min(len(pending_lessons), 10)} AI calls)", disabled=not cfg["ready"]):
        with st.spinner("Reflecting on past calls…"):
            try:
                done = track.add_ai_lessons(ai.asker(cfg["provider"], cfg["model"], cfg["api_key"]), limit=10)
            except ai.AIError as exc:
                st.error(str(exc))
            else:
                st.success(f"Added {done} lessons.")
                st.rerun()

with st.expander("Danger zone"):
    sure = st.checkbox("I want to delete every saved call and lesson")
    if st.button("Delete track record", disabled=not sure):
        track.clear()
        ui.refresh_track.clear()
        st.rerun()
