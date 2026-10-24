import pandas as pd
import streamlit as st

import charts
import intraday
import portfolio
import zones
import ui

BADGE = {"Bullish": "🟢", "Bearish": "🔴", "Choppy": "⚪"}

with st.sidebar:
    st.subheader("Terminal")
    size = st.select_slider("Stocks per board", [10, 20, 30], value=20)
    auto = st.toggle("Auto-refresh every minute", value=True)
    st.caption("Prices from Yahoo Finance, refreshed about once a minute during market hours. "
               "They may lag the exchange by a minute or two.")
    st.sidebar.divider()
    st.caption("A market analytics view: strength, zones and levels are calculations, not recommendations.")

st.title("📡 Terminal")
st.caption("Every F&O stock ranked by how far it has moved since the open, measured in its normal daily range "
           "(average of the last 20 sessions), and counted only when the move is clean: mostly one-sided and on "
           "the right side of VWAP. Click a stock on a board to open its chart with order-block zones and liquidity.")


def analysis_for(snap: dict, row) -> dict:
    t = row["ticker"]
    return zones.analyse(snap["minutes"][t], snap["daily"].get(t), snap["day"], row["state"], row["last"],
                         row["adr"], snap["status"]["live"])


def levels_text(a: dict) -> tuple[str, str]:
    s = a["setup"]
    if not s:
        return "–", "–"
    z = s["zone"]
    return f"{z['bottom']:,.1f}–{z['top']:,.1f}", f"{s['targets'][0]['price']:,.1f}"


def close_popup():
    st.session_state.pop("popup", None)


def leave(target):
    close_popup()
    target()


@st.dialog("Chart", width="large", on_dismiss=close_popup)
def popup(rows: list[dict], snap_key: str):
    snap = ui.get_terminal()
    pos = st.session_state.get("popup_pos", 0) % len(rows)
    row = rows[pos]
    a = analysis_for(snap, row)
    st.markdown(f"### {BADGE[row['state']]} {row['name']} ({row['symbol']})")
    st.caption(f"{row['sector']} · {row['state']} · strength {row['strength']:+.2f}× ADR · "
               f"session {snap['day']:%d %b %Y} · {pos + 1} of {len(rows)}")
    pairs = [("Price", ui.rupees(row["last"]), "Day move", ui.pct(row["change_pct"])),
             ("From open", ui.pct(row["from_open_pct"]), "Strength", f"{row['strength']:+.2f}× ADR"),
             ("VWAP", ui.rupees(row["vwap"]), "Clean move", f"{row['clean_pct']:.0f}%"),
             ("Day high", ui.rupees(row["high"]), "Day low", ui.rupees(row["low"])),
             ("Normal daily range", ui.rupees(row["adr"]), "Volume vs usual",
              f"{row['rel_volume']:.1f}×" if row["rel_volume"] else "–")]
    st.markdown("  \n".join(f"**{l1}:** {v1} · **{l2}:** {v2}" for l1, v1, l2, v2 in pairs))
    st.plotly_chart(charts.zone_chart(a, f"{row['symbol']} · 5-minute"), width="stretch", key=f"chart_{snap_key}_{pos}")
    s = a["setup"]
    if s:
        z = s["zone"]
        bull = s["direction"] == "Bullish"
        st.markdown(
            f"**{'Bullish' if bull else 'Bearish'} zone:** ₹{z['bottom']:,.2f} – ₹{z['top']:,.2f} "
            f"(formed {z['formed']:%H:%M}{', tested' if z['tested'] is not None else ', not yet tested'})  \n"
            f"**Setup is invalid if a 5-min candle closes {'below' if bull else 'above'}:** ₹{s['invalid']:,.2f}  \n"
            + "  \n".join(f"**Level {n}:** ₹{t['price']:,.2f} ({t['source']})" for n, t in enumerate(s["targets"], 1))
            + (f"  \n**Liquidity that may be taken first:** ₹{s['sweep']['price']:,.2f}" if s["sweep"] else "")
            + ("  \n**Levels behind the zone:** " + ", ".join(f"{b['label']} ₹{b['price']:,.2f}" for b in s["behind"])
               if s["behind"] else ""))
    else:
        st.info("No unbroken zone in the direction of the move yet.")
    st.caption("Boxes: order-block zones where they formed (grey dotted = broken). Dashed lines: liquidity resting at "
               "untaken swing highs (blue) and lows (purple); thicker = equal highs/lows. Yellow: higher-timeframe levels.")
    b1, b2, b3, b4 = st.columns(4)
    b1.button("‹ Previous", on_click=lambda: st.session_state.update(popup_pos=pos - 1), width="stretch")
    b2.button("Next ›", on_click=lambda: st.session_state.update(popup_pos=pos + 1), width="stretch")
    if b3.button("⭐ Watchlist", width="stretch"):
        portfolio.add_to_watchlist([row["ticker"]])
        st.toast(f"{row['symbol']} added to your watchlist")
    if b4.button("📒 Journal", width="stretch"):
        st.session_state["journal_prefill"] = {"symbol": row["symbol"],
                                               "side": "Short" if row["state"] == "Bearish" else "Long",
                                               "entry": round(row["last"], 2)}
        leave(lambda: st.switch_page("views/page_journal.py"))
    if st.button("Open full analysis →"):
        leave(lambda: ui.go_analyse(row["ticker"]))


def board_table(board: pd.DataFrame, marks: list[str], analyses: dict) -> pd.DataFrame:
    rows = []
    for (i, r), mark in zip(board.iterrows(), marks):
        zone, nxt = levels_text(analyses[r["ticker"]])
        rows.append({"#": i + 1, "Stock": r["symbol"], "Day %": round(r["change_pct"], 2),
                     "Strength": round(r["strength"], 2), "Δ": mark, "Price": round(r["last"], 2),
                     "Clean %": round(r["clean_pct"]), "Zone": zone, "Next level": nxt})
    return pd.DataFrame(rows)


def show_board(title: str, board: pd.DataFrame, marks: list[str], analyses: dict, key: str):
    st.markdown(f"#### {title} ({len(board)})")
    if board.empty:
        st.caption("No stock qualifies right now.")
        return
    nonce = st.session_state.get("board_nonce", 0)
    event = st.dataframe(board_table(board, marks, analyses), hide_index=True, width="stretch",
                         on_select="rerun", selection_mode="single-row", key=f"{key}_{nonce}",
                         column_config={"Day %": st.column_config.NumberColumn(format="%+.2f%%"),
                                        "Strength": st.column_config.NumberColumn(format="%+.2f×"),
                                        "Price": st.column_config.NumberColumn(format="₹%.2f")})
    picked = event.selection.rows if event and event.selection else []
    if picked:
        st.session_state["board_nonce"] = nonce + 1
        st.session_state["popup_pos"] = picked[0]
        st.session_state["popup"] = key


@st.fragment(run_every=60 if auto else None)
def terminal():
    top = st.columns([4, 1])
    force = top[1].button("🔄 Refresh", width="stretch")
    with st.spinner("Loading every F&O stock…"):
        snap = ui.get_terminal(force)
    table = snap["table"]
    status = snap["status"]
    top[0].markdown(f"**{status['label']}** · updated {snap['fetched']} IST · {len(table)} of {snap['universe']} "
                    "F&O stocks")
    if table.empty:
        st.warning("No intraday data available right now. Try Refresh in a minute.")
        return

    b = intraday.breadth(table)
    st.plotly_chart(charts.breadth_bar(b["up"], b["flat"], b["down"]), width="stretch", key="breadth",
                    config={"displayModeBar": False})
    st.markdown(f"**Breadth:** {b['up']} up · {b['down']} down  ·  **Clean moves:** 🟢 {b['bullish']} bullish · "
                f"🔴 {b['bearish']} bearish · ⚪ {b['choppy']} choppy")

    flow = intraday.sector_flow(table)
    order = flow.sort_values("avg_change", ascending=False)["sector"].tolist()
    lead, lag = flow.sort_values("avg_change").iloc[-1], flow.sort_values("avg_change").iloc[0]
    st.markdown(f"**Market X-Ray** · leading: **{lead['sector']}** ({lead['avg_change']:+.2f}%) · "
                f"lagging: **{lag['sector']}** ({lag['avg_change']:+.2f}%)")
    st.plotly_chart(charts.xray_chart(table, order), width="stretch", key="xray")

    bull, bear = intraday.boards(table, size)
    snap_key = f"{snap['day']}_{snap['fetched']}"
    memory = st.session_state.get("rank_memory", {})
    if memory.get("at") != snap_key:
        memory = {"at": snap_key,
                  "marks": {"bull": intraday.rank_changes(bull, memory.get("ranks", {}).get("bull")),
                            "bear": intraday.rank_changes(bear, memory.get("ranks", {}).get("bear"))},
                  "ranks": {"bull": {s: i for i, s in enumerate(bull["symbol"], 1)},
                            "bear": {s: i for i, s in enumerate(bear["symbol"], 1)}}}
        st.session_state["rank_memory"] = memory
    analyses = {r["ticker"]: analysis_for(snap, r) for _, r in pd.concat([bull, bear]).iterrows()}

    left, right = st.columns(2)
    with left:
        show_board("🟢 Bullish board", bull, memory["marks"]["bull"], analyses, "bull")
    with right:
        show_board("🔴 Bearish board", bear, memory["marks"]["bear"], analyses, "bear")
    st.caption("Δ = places moved since the previous refresh (🆕 = new in the top 10). Strength = move from the open "
               "in multiples of the stock's normal daily range. Clean % = share of the day's range on the side of "
               "the move.")

    with st.expander("🧭 Sector flow", expanded=False):
        st.dataframe(flow.rename(columns={"sector": "Sector", "stocks": "Stocks", "avg_strength": "Avg strength",
                                          "avg_change": "Avg day %", "up": "Up", "down": "Down"}).round(2),
                     hide_index=True, width="stretch")

    ordered = table.sort_values("symbol").reset_index(drop=True)
    names = {f"{r['symbol']} · {r['name']}": i for i, r in ordered.iterrows()}
    c1, c2 = st.columns([4, 1])
    pick = c1.selectbox("Open any F&O stock", list(names), index=None, placeholder="Search any F&O stock…",
                        label_visibility="collapsed")
    if c2.button("Open chart", width="stretch", disabled=pick is None):
        st.session_state["popup_pos"] = names[pick]
        st.session_state["popup"] = "all"

    sources = {"bull": bull, "bear": bear, "all": ordered}
    open_on = st.session_state.get("popup")
    if open_on in sources and not sources[open_on].empty:
        popup(sources[open_on].to_dict("records"), snap_key)


terminal()
