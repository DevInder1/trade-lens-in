import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

import market

MACRO = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "India VIX (fear gauge)": "^INDIAVIX",
    "USD/INR": "INR=X",
    "Brent crude ($)": "BZ=F",
    "Gold ($/oz)": "GC=F",
    "S&P 500 (US)": "^GSPC",
    "US 10-year yield (%)": "^TNX",
}


def _pct(close, bars):
    if len(close) <= bars:
        return None
    value = (close.iloc[-1] / close.iloc[-1 - bars] - 1) * 100
    return None if math.isnan(value) else round(float(value), 2)


def _trend(close):
    if len(close) < 200:
        return None
    last, sma50, sma200 = close.iloc[-1], close.tail(50).mean(), close.tail(200).mean()
    if last > sma50 > sma200:
        return "Uptrend (above 50- and 200-day averages)"
    if last < sma50 < sma200:
        return "Downtrend (below 50- and 200-day averages)"
    return "Mixed (between its 50- and 200-day averages)"


def _history(symbol, as_of=None):
    try:
        if as_of is None:
            return yf.Ticker(symbol).history(period="1y", interval="1d")["Close"].dropna()
        end = pd.Timestamp(as_of)
        return market.load_history(symbol, end - pd.Timedelta(days=400), end)["Close"]
    except Exception:
        return None


def load_macro(as_of=None) -> list[dict]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        closes = dict(zip(MACRO, pool.map(lambda s: _history(s, as_of), MACRO.values())))
    rows = []
    for name, symbol in MACRO.items():
        close = closes[name]
        if close is None or close.empty:
            continue
        rows.append({
            "name": name,
            "symbol": symbol,
            "last": round(float(close.iloc[-1]), 2),
            "date": close.index[-1].strftime("%Y-%m-%d"),
            "change_1w": _pct(close, 5),
            "change_1m": _pct(close, 21),
            "change_3m": _pct(close, 63),
            "trend": _trend(close),
        })
    return rows


VIX_LEVELS = ((13, "Calm", "low fear"), (18, "Normal", "typical volatility"),
              (25, "Nervous", "above-normal volatility"), (float("inf"), "Fearful", "high volatility"))


def _vix(rows: list[dict]):
    vix = next((r for r in rows if r["symbol"] == "^INDIAVIX"), None)
    if not vix:
        return None
    level = vix["last"]
    _, mood, detail = next(v for v in VIX_LEVELS if level < v[0])
    return level, mood, detail


def vix_mood(rows: list[dict]) -> str | None:
    found = _vix(rows)
    return f"{found[1]} ({found[0]:.1f})" if found else None


def vix_reading(rows: list[dict]) -> str | None:
    found = _vix(rows)
    return f"India VIX {found[0]:.1f}: {found[1].lower()}, {found[2]}" if found else None


def relative_strength(stock_snap: dict, rows: list[dict]) -> dict:
    nifty = next((r for r in rows if r["symbol"] == "^NSEI"), None)
    out = {}
    if not nifty:
        return out
    for key, nkey in (("change_1m", "change_1m"), ("change_3m", "change_3m")):
        s, n = stock_snap.get(key), nifty.get(nkey)
        if s is not None and n is not None:
            out[key.replace("change", "vs_nifty")] = round(s - n, 2)
    return out
