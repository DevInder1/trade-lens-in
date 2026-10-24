import streamlit as st
from dotenv import load_dotenv

from storage import ENV_PATH, ensure_dirs

load_dotenv(ENV_PATH)
ensure_dirs()

st.set_page_config(page_title="Trade Lens IN", page_icon="📈", layout="wide")

pages = {
    "Today": [
        st.Page("views/page_home.py", title="Home", icon="🏠", default=True),
        st.Page("views/page_terminal.py", title="Terminal", icon="📡"),
    ],
    "Research": [
        st.Page("views/page_analyse.py", title="Analyse", icon="📊"),
        st.Page("views/page_watchlist.py", title="Watchlist", icon="⭐"),
        st.Page("views/page_portfolio.py", title="Portfolio", icon="🧺"),
    ],
    "Review": [
        st.Page("views/page_journal.py", title="Journal", icon="📒"),
        st.Page("views/page_track.py", title="Track record", icon="🎯"),
        st.Page("views/page_backtest.py", title="Backtest", icon="⏪"),
        st.Page("views/page_reports.py", title="Daily report", icon="🗞️"),
    ],
}
st.sidebar.title("📈 Trade Lens IN")
st.sidebar.caption("Indian stocks · NSE / BSE · read-only research")
st.navigation(pages).run()
