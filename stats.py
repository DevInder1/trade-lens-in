import math

import numpy as np
import pandas as pd
import yfinance as yf

import fno

TRADING_DAYS = 252
RISK_FREE = 0.065
TURBULENCE_WINDOW = 252


def performance(values: pd.Series, risk_free: float = RISK_FREE) -> dict:
    values = values.dropna()
    returns = values.pct_change().dropna()
    if len(returns) < 2:
        return {}
    years = len(returns) / TRADING_DAYS
    total = values.iloc[-1] / values.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else float("nan")
    vol = returns.std() * math.sqrt(TRADING_DAYS)
    excess = returns - risk_free / TRADING_DAYS
    downside = returns[returns < 0].std() * math.sqrt(TRADING_DAYS)
    drawdown = values / values.cummax() - 1
    max_dd = drawdown.min()
    return {
        "Total return": total * 100,
        "Yearly return (CAGR)": cagr * 100,
        "Yearly volatility": vol * 100,
        "Sharpe ratio": excess.mean() / returns.std() * math.sqrt(TRADING_DAYS) if returns.std() else float("nan"),
        "Sortino ratio": (returns.mean() * TRADING_DAYS - risk_free) / downside if downside else float("nan"),
        "Max drawdown": max_dd * 100,
        "Calmar ratio": cagr / abs(max_dd) if max_dd else float("nan"),
        "Up days": (returns > 0).mean() * 100,
        "Best day": returns.max() * 100,
        "Worst day": returns.min() * 100,
        "Daily VaR (95%)": np.percentile(returns, 5) * 100,
    }


PERCENT_KEYS = {"Total return", "Yearly return (CAGR)", "Yearly volatility", "Max drawdown", "Up days", "Best day",
                "Worst day", "Daily VaR (95%)"}


def stats_table(curves: pd.DataFrame) -> pd.DataFrame:
    table = pd.DataFrame({name: performance(curves[name]) for name in curves.columns})
    formatted = table.copy().astype(object)
    for key in table.index:
        for col in table.columns:
            v = table.loc[key, col]
            formatted.loc[key, col] = "–" if pd.isna(v) else (f"{v:+.2f}%" if key in PERCENT_KEYS else f"{v:.2f}")
    return formatted


def basket_closes(start, end=None) -> pd.DataFrame:
    tickers = [fno.ticker(s) for s in fno.FALLBACK]
    raw = yf.download(tickers, start=pd.Timestamp(start).strftime("%Y-%m-%d"),
                      end=(pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") if end is not None else None,
                      interval="1d", group_by="ticker", threads=True, progress=False, auto_adjust=False)
    closes = {t: raw[t]["Close"] for t in tickers if t in raw.columns.get_level_values(0)}
    px = pd.DataFrame(closes).dropna(how="all")
    if px.index.tz is not None:
        px.index = px.index.tz_localize(None)
    px.index = px.index.normalize()
    return px


def turbulence(px: pd.DataFrame, window: int = TURBULENCE_WINDOW) -> pd.Series:
    returns = px.pct_change().iloc[1:]
    values, dates = [], []
    for i in range(window, len(returns)):
        hist = returns.iloc[i - window:i].dropna(axis=1, thresh=int(window * 0.9))
        hist = hist.fillna(hist.mean())
        today = returns.iloc[i][hist.columns]
        if today.isna().sum() > len(today) * 0.2:
            continue
        today = today.fillna(hist.mean())
        diff = (today - hist.mean()).to_numpy()
        values.append(float(diff @ np.linalg.pinv(hist.cov().to_numpy()) @ diff))
        dates.append(returns.index[i])
    return pd.Series(values, index=dates, name="turbulence")


def turbulence_level(series: pd.Series, lookback: int = 2 * TRADING_DAYS) -> dict | None:
    if series.empty:
        return None
    recent = series.tail(lookback)
    value = float(series.iloc[-1])
    pct = float((recent < value).mean() * 100)
    smooth = float(series.tail(5).mean())
    smooth_pct = float((recent < smooth).mean() * 100)
    if smooth_pct >= 95:
        label, note = "Extreme", "markets are moving in a very unusual way; FinRL-style rules would stop buying"
    elif smooth_pct >= 80:
        label, note = "Elevated", "more unusual moves than normal; size positions smaller"
    elif smooth_pct >= 40:
        label, note = "Normal", "typical market behaviour"
    else:
        label, note = "Calm", "quieter than usual"
    return {"value": value, "percentile": pct, "five_day": smooth, "five_day_percentile": smooth_pct,
            "label": label, "note": note, "date": series.index[-1].strftime("%Y-%m-%d")}


def risk_off_mask(series: pd.Series, quantile: float = 0.9, window: int = TRADING_DAYS) -> pd.Series:
    threshold = series.rolling(window, min_periods=60).quantile(quantile).shift(1)
    return series >= threshold


def ordinal(value: float) -> str:
    n = int(round(value))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def momentum_12_1(close: pd.Series, bench: pd.Series) -> float | None:
    close, bench = close.dropna(), bench.reindex(close.index).ffill()
    if len(close) < 253:
        return None
    stock = close.iloc[-22] / close.iloc[-253] - 1
    index = bench.iloc[-22] / bench.iloc[-253] - 1
    return float((stock - index) * 100)
