import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

UP = "#16a34a"
DOWN = "#dc2626"


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
