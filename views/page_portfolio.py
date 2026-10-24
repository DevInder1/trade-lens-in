import plotly.express as px
import streamlit as st

import charts
import optimizer
import portfolio
import ui

book = portfolio.load()
held = [s for s, p in book["positions"].items() if p.get("owned") == "Yes"]
default = [s for s in (book["watchlist"] or held) if not s.startswith("^")]

with st.sidebar:
    st.subheader("Portfolio settings")
    years = st.selectbox("History to learn from", [1, 2, 3, 5], index=2, format_func=lambda y: f"{y} years")
    max_weight = st.slider("Most in any one stock", 10, 100, 30, step=5, format="%d%%",
                           help="Caps concentration. 30% means no stock gets more than 30% of the money.") / 100
    capital = st.number_input("Money to invest (₹)", min_value=0.0, step=10000.0, value=book["capital"] or 100000.0)
    st.divider()
    st.caption(ui.DISCLAIMER)


@st.cache_data(ttl=3600, show_spinner=False)
def returns_for(symbols: tuple, years: int):
    return optimizer.load_returns(list(symbols), years)


st.title("🧺 Portfolio")
st.caption("How to split money across several stocks. Based on the portfolio-allocation baselines in the FinRL "
           "research framework: every method is checked on recent data it never saw.")

symbols = st.multiselect("Stocks from your watchlist and holdings", default, default=default, format_func=ui.short)
symbols = sorted(set(symbols) | set(ui.stocks_multi_picker("Add any other stocks", "pf_add")))
symbols = [s for s in symbols if not s.startswith("^")]

if len(symbols) < 2:
    st.info("Pick at least two stocks (your watchlist is used by default).")
    st.stop()

with st.spinner("Loading price history…"):
    returns, bench = returns_for(tuple(sorted(symbols)), years)
if returns.shape[1] < 2:
    st.error("Not enough price history for these stocks. Try fewer years or other stocks.")
    st.stop()
dropped = sorted(set(symbols) - set(returns.columns))
if dropped:
    st.caption(f"Left out (not enough history): {', '.join(dropped)}")

method = st.radio("Method", list(optimizer.METHODS), horizontal=True)
st.caption(optimizer.METHODS[method])

w = optimizer.weights(returns, method, max_weight)
prof = optimizer.profile(returns, w)
c = st.columns(3)
c[0].metric("Past yearly return", f"{prof['return']:+.1f}%")
c[1].metric("Past yearly volatility", f"{prof['volatility']:.1f}%")
c[2].metric("Sharpe ratio", f"{prof['sharpe']:.2f}")

left, right = st.columns([1, 1])
with left:
    shown = w[w > 0.001].sort_values(ascending=False)
    fig = px.pie(values=shown.values, names=[s.removesuffix(".NS") for s in shown.index], hole=0.45)
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    fig.update_traces(textinfo="label+percent")
    st.plotly_chart(fig, width="stretch")
with right:
    prices = {s: float(ui.get_prices(s, "2y")["Close"].iloc[-1]) for s in w.index}
    plan = optimizer.allocate(w, capital, prices)
    st.dataframe(plan.round(2), hide_index=True, width="stretch",
                 column_config={"Weight": st.column_config.NumberColumn(format="%.1f%%"),
                                "Amount (₹)": st.column_config.NumberColumn(format="₹%.0f"),
                                "Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                                "Invested (₹)": st.column_config.NumberColumn(format="₹%.0f")})
    invested = plan["Invested (₹)"].fillna(0).sum()
    st.caption(f"Whole shares only: ₹{invested:,.0f} invested, ₹{capital - invested:,.0f} left as cash.")

st.subheader("🔍 Honest check: would this have worked?")
wf = optimizer.walk_forward(returns, bench, method, max_weight)
if wf:
    st.caption(f"Weights were fitted on {wf['train'][0]:%b %Y}–{wf['train'][1]:%b %Y} only, then tested on "
               f"{wf['test'][0]:%b %Y}–{wf['test'][1]:%b %Y}, which the method never saw. Rebalanced monthly.")
    st.plotly_chart(charts.equity_chart(wf["curves"]), width="stretch")
    st.dataframe(wf["stats"].loc[["Total return", "Yearly volatility", "Sharpe ratio", "Max drawdown"]],
                 width="stretch")
    st.caption("If the method doesn't beat Equal weight here, prefer Equal weight: optimisers often fit the past "
               "too closely.")
else:
    st.info("Need more history for the honest check. Choose more years.")

with st.expander("How related are these stocks? (correlation)"):
    corr = returns.corr().round(2)
    corr.index = corr.columns = [s.removesuffix(".NS") for s in corr.columns]
    fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("1 = always move together, 0 = unrelated. Mixing less related stocks lowers risk.")
