import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

UP = "#16a34a"
DOWN = "#dc2626"


def zone_chart(analysis: dict, title: str, height: int = 520) -> go.Figure:
    five = analysis["five"]
    fig = go.Figure(go.Candlestick(x=five.index, open=five["Open"], high=five["High"], low=five["Low"],
                                   close=five["Close"], increasing_line_color=UP, decreasing_line_color=DOWN,
                                   name="5-min"))
    if five.empty:
        return fig
    first, last = five.index[0], five.index[-1] + pd.Timedelta(minutes=5)
    current = (analysis.get("setup") or {}).get("zone")

    for z in analysis["zones"]:
        bull = z["kind"] == "bull"
        alive = z["broken"] is None
        end = z["broken"] if not alive else last
        color = UP if bull else DOWN
        fig.add_shape(type="rect", x0=max(z["start"], first), x1=end, y0=z["bottom"], y1=z["top"],
                      line=dict(color=color if alive else "#94a3b8", width=1, dash="solid" if alive else "dot"),
                      fillcolor=color if alive else "#94a3b8", opacity=0.22 if alive else 0.08, layer="below")
        if z is current:
            fig.add_annotation(x=last, y=z["top"] if bull else z["bottom"], xanchor="right",
                               yanchor="bottom" if bull else "top", showarrow=False,
                               text=f"{'Bullish' if bull else 'Bearish'} zone {z['bottom']:,.1f}–{z['top']:,.1f}",
                               font=dict(size=11, color=color))

    for lv in analysis["liquidity"]:
        end = lv["swept"] if lv["swept"] is not None else last
        color = "#0ea5e9" if lv["kind"] == "BSL" else "#a855f7"
        fig.add_shape(type="line", x0=lv["start"], x1=end, y0=lv["price"], y1=lv["price"],
                      line=dict(color=color, width=1.2 if lv["equal"] else 0.8,
                                dash="dot" if lv["swept"] is not None else "dash"))

    s = analysis.get("setup")
    low, high = float(five["Low"].min()), float(five["High"].max())
    reach = analysis.get("adr", 0) * 1.5
    shown = [low, high]
    if s:
        fig.add_hline(y=s["invalid"], line=dict(color="#f97316", width=1.2, dash="dashdot"),
                      annotation_text=f"Invalid beyond {s['invalid']:,.1f}", annotation_position="bottom left",
                      annotation_font_size=10)
        shown.append(s["invalid"])
        for n, t in enumerate(s["targets"], 1):
            fig.add_hline(y=t["price"], line=dict(color="#64748b", width=1, dash="dot"),
                          annotation_text=f"L{n} {t['price']:,.1f}", annotation_position="top left",
                          annotation_font_size=10)
            shown.append(t["price"])
        for b in s["behind"]:
            if low - reach <= b["price"] <= high + reach:
                fig.add_hline(y=b["price"], line=dict(color="#eab308", width=1, dash="longdash"),
                              annotation_text=f"{b['label']} {b['price']:,.1f}", annotation_position="bottom right",
                              annotation_font_size=10)
                shown.append(b["price"])

    pad = (max(shown) - min(shown)) * 0.04
    fig.update_layout(title=dict(text=title, font=dict(size=14)), height=height, margin=dict(l=10, r=10, t=40, b=10),
                      xaxis_rangeslider_visible=False, showlegend=False, hovermode="x unified")
    fig.update_xaxes(tickformat="%H:%M", nticks=8)
    fig.update_yaxes(range=[min(shown) - pad, max(shown) + pad], side="right")
    return fig


def xray_chart(table: pd.DataFrame, order: list[str]) -> go.Figure:
    fig = go.Figure()
    for state, color in (("Bullish", UP), ("Bearish", DOWN), ("Choppy", "#94a3b8")):
        part = table[table["state"] == state]
        fig.add_trace(go.Box(x=part["sector"], y=part["change_pct"], boxpoints="all", jitter=0.6, pointpos=0,
                             fillcolor="rgba(0,0,0,0)", line=dict(color="rgba(0,0,0,0)"),
                             marker=dict(color=color, size=7, opacity=0.85), name=state,
                             customdata=part[["symbol", "strength"]],
                             hovertemplate="%{customdata[0]}: %{y:+.2f}% · strength %{customdata[1]:+.2f}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#64748b", width=1))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), boxmode="overlay",
                      yaxis_title="Day move %", legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(categoryorder="array", categoryarray=order, tickangle=-45, tickfont=dict(size=10),
                     automargin=True)
    return fig


def breadth_bar(up: int, flat: int, down: int) -> go.Figure:
    fig = go.Figure()
    for value, color, label in ((up, UP, "Up"), (flat, "#94a3b8", "Flat"), (down, DOWN, "Down")):
        if value:
            fig.add_trace(go.Bar(x=[value], y=[""], orientation="h", marker_color=color, name=label,
                                 text=f"{label} {value}", textposition="inside", insidetextanchor="middle",
                                 hovertemplate=f"{label}: {value}<extra></extra>"))
    fig.update_layout(barmode="stack", height=70, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def pnl_calendar(daily: pd.Series, year: int, month: int) -> go.Figure:
    first = pd.Timestamp(year=year, month=month, day=1)
    days = pd.date_range(first, first + pd.offsets.MonthEnd(0))
    weeks = sorted({(d - pd.Timedelta(days=d.weekday())).strftime("%d %b") for d in days},
                   key=lambda s: pd.Timestamp(f"{s} {year}"))
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    z = [[None] * len(weeks) for _ in names]
    text = [[""] * len(weeks) for _ in names]
    for d in days:
        col = weeks.index((d - pd.Timedelta(days=d.weekday())).strftime("%d %b"))
        value = daily.get(d)
        z[d.weekday()][col] = value
        text[d.weekday()][col] = f"{d.day}<br>{'' if value is None else f'₹{value:,.0f}'}"
    peak = max([abs(v) for v in daily.values] + [1])
    fig = go.Figure(go.Heatmap(z=z, x=weeks, y=names, text=text, texttemplate="%{text}", zmin=-peak, zmax=peak,
                               colorscale=[[0, DOWN], [0.5, "#f1f5f9"], [1, UP]], showscale=False,
                               hovertemplate="%{text}<extra></extra>", xgap=3, ygap=3))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="Week starting", side="top")
    return fig


def equity_chart(curves: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    colors = {"Signals strategy": "#2563eb", "Buy and hold": "#f59e0b", "NIFTY 50": "#94a3b8"}
    for col in curves.columns:
        fig.add_trace(go.Scatter(x=curves.index, y=curves[col], name=col,
                                 line=dict(color=colors.get(col), width=2 if col == "Signals strategy" else 1.4)))
    fig.add_hline(y=100, line=dict(color="#64748b", width=1, dash="dot"))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      yaxis_title="Value of ₹100 invested", legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig


def price_chart(df: pd.DataFrame, title: str) -> go.Figure:
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.55, 0.13, 0.16, 0.16],
                        subplot_titles=(title, "Volume", "RSI (14)", "MACD (12, 26, 9)"))

    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                 name="Price", increasing_line_color=UP, decreasing_line_color=DOWN), row=1, col=1)
    for col, color in (("SMA20", "#f59e0b"), ("SMA50", "#2563eb"), ("SMA200", "#9333ea")):
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col.replace("SMA", "") + "-day avg",
                                 line=dict(color=color, width=1.4)), row=1, col=1)
    for col in ("BB_upper", "BB_lower"):
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name="Bollinger band", showlegend=col == "BB_upper",
                                 legendgroup="bb", line=dict(color="#94a3b8", width=1, dash="dot")), row=1, col=1)

    colors = [UP if c >= o else DOWN for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=colors, name="Volume", showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["VolAvg20"], name="20-day avg volume", showlegend=False,
                             line=dict(color="#64748b", width=1)), row=2, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI", showlegend=False,
                             line=dict(color="#0ea5e9", width=1.4)), row=3, col=1)
    for level, color in ((70, DOWN), (30, UP)):
        fig.add_hline(y=level, line=dict(color=color, width=1, dash="dash"), row=3, col=1)

    hist_colors = [UP if v >= 0 else DOWN for v in df["MACD_hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_hist"], marker_color=hist_colors, name="Histogram", showlegend=False),
                  row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD", showlegend=False,
                             line=dict(color="#2563eb", width=1.3)), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD_signal"], name="Signal", showlegend=False,
                             line=dict(color="#f59e0b", width=1.3)), row=4, col=1)

    fig.update_layout(height=860, margin=dict(l=10, r=10, t=40, b=10), xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified")
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    return fig
