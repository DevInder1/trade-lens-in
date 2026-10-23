import math

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close, high, low = out["Close"], out["High"], out["Low"]

    for n in (20, 50, 200):
        out[f"SMA{n}"] = close.rolling(n).mean()
    out["EMA20"] = close.ewm(span=20, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    out["RSI"] = 100 - 100 / (1 + gain / loss)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["MACD"] = ema12 - ema26
    out["MACD_signal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["MACD_hist"] = out["MACD"] - out["MACD_signal"]

    std20 = close.rolling(20).std()
    out["BB_upper"] = out["SMA20"] + 2 * std20
    out["BB_lower"] = out["SMA20"] - 2 * std20

    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    out["ATR"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()

    out["VolAvg20"] = out["Volume"].rolling(20).mean()
    return out


def _value(x):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _change(close: pd.Series, bars: int):
    if len(close) <= bars:
        return None
    return _value((close.iloc[-1] / close.iloc[-1 - bars] - 1) * 100)


def snapshot(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    close = df["Close"]
    year = df.tail(252)
    recent = df.tail(20)
    keys = ["Close", "SMA20", "SMA50", "SMA200", "EMA20", "RSI", "MACD", "MACD_signal",
            "MACD_hist", "BB_upper", "BB_lower", "ATR", "Volume", "VolAvg20"]
    snap = {k: _value(last.get(k)) for k in keys}
    snap.update({
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "change_1d": _change(close, 1),
        "change_1w": _change(close, 5),
        "change_1m": _change(close, 21),
        "change_3m": _change(close, 63),
        "change_1y": _change(close, 252),
        "high_52w": _value(year["High"].max()),
        "low_52w": _value(year["Low"].min()),
        "support_20d": _value(recent["Low"].min()),
        "resistance_20d": _value(recent["High"].max()),
    })
    if snap["Volume"] and snap["VolAvg20"]:
        snap["volume_ratio"] = snap["Volume"] / snap["VolAvg20"]
    else:
        snap["volume_ratio"] = None
    if snap["ATR"] and snap["Close"]:
        snap["atr_pct"] = snap["ATR"] / snap["Close"] * 100
    else:
        snap["atr_pct"] = None
    return snap


def _signal(name, verdict, detail):
    return {"name": name, "verdict": verdict, "detail": detail}


def signals(s: dict) -> list[dict]:
    out = []
    price = s["Close"]

    if price and s["SMA50"]:
        above = price > s["SMA50"]
        out.append(_signal("Medium-term trend (50-day average)", "Bullish" if above else "Bearish",
                           f"Price ₹{price:,.2f} is {'above' if above else 'below'} the 50-day average ₹{s['SMA50']:,.2f}"))
    if price and s["SMA200"]:
        above = price > s["SMA200"]
        out.append(_signal("Long-term trend (200-day average)", "Bullish" if above else "Bearish",
                           f"Price is {'above' if above else 'below'} the 200-day average ₹{s['SMA200']:,.2f}"))
    if s["SMA50"] and s["SMA200"]:
        golden = s["SMA50"] > s["SMA200"]
        out.append(_signal("Golden / death cross", "Bullish" if golden else "Bearish",
                           "50-day average is above the 200-day (golden cross zone)" if golden
                           else "50-day average is below the 200-day (death cross zone)"))
    if s["RSI"] is not None:
        rsi = s["RSI"]
        if rsi >= 70:
            out.append(_signal("RSI momentum", "Bearish", f"RSI {rsi:.1f}: overbought, a pullback is more likely"))
        elif rsi <= 30:
            out.append(_signal("RSI momentum", "Bullish", f"RSI {rsi:.1f}: oversold, a bounce is more likely"))
        elif rsi >= 55:
            out.append(_signal("RSI momentum", "Bullish", f"RSI {rsi:.1f}: healthy upward momentum"))
        elif rsi <= 45:
            out.append(_signal("RSI momentum", "Bearish", f"RSI {rsi:.1f}: weak momentum"))
        else:
            out.append(_signal("RSI momentum", "Neutral", f"RSI {rsi:.1f}: no clear momentum"))
    if s["MACD"] is not None and s["MACD_signal"] is not None:
        up = s["MACD"] > s["MACD_signal"]
        out.append(_signal("MACD", "Bullish" if up else "Bearish",
                           f"MACD {s['MACD']:.2f} is {'above' if up else 'below'} its signal line {s['MACD_signal']:.2f}"))
    if price and s["BB_upper"] and s["BB_lower"]:
        if price > s["BB_upper"]:
            out.append(_signal("Bollinger Bands", "Bearish", "Price is above the upper band: stretched, may cool off"))
        elif price < s["BB_lower"]:
            out.append(_signal("Bollinger Bands", "Bullish", "Price is below the lower band: stretched down, may rebound"))
        else:
            out.append(_signal("Bollinger Bands", "Neutral", "Price is inside the bands"))
    if s["volume_ratio"] and s["change_1d"] is not None and s["volume_ratio"] >= 1.5:
        up = s["change_1d"] >= 0
        out.append(_signal("Volume", "Bullish" if up else "Bearish",
                           f"Volume is {s['volume_ratio']:.1f}× its 20-day average on a {'rising' if up else 'falling'} day"))
    elif s["volume_ratio"]:
        out.append(_signal("Volume", "Neutral", f"Volume is {s['volume_ratio']:.1f}× its 20-day average"))
    return out


ROW_KEYS = ["Close", "SMA50", "SMA200", "RSI", "MACD", "MACD_signal", "BB_upper", "BB_lower"]


def view_series(df: pd.DataFrame) -> pd.DataFrame:
    prev_close = df["Close"].shift(1)
    rows = []
    for (ts, row), prev in zip(df.iterrows(), prev_close):
        s = {k: _value(row.get(k)) for k in ROW_KEYS}
        s["change_1d"] = _value((row["Close"] / prev - 1) * 100) if prev else None
        vol, avg = _value(row.get("Volume")), _value(row.get("VolAvg20"))
        s["volume_ratio"] = vol / avg if vol and avg else None
        view, score = overall(signals(s))
        rows.append((ts, view, score))
    return pd.DataFrame(rows, columns=["Date", "view", "score"]).set_index("Date")


def overall(sigs: list[dict]) -> tuple[str, int]:
    score = sum(1 if x["verdict"] == "Bullish" else -1 if x["verdict"] == "Bearish" else 0 for x in sigs)
    if score >= 2:
        return "Bullish", score
    if score <= -2:
        return "Bearish", score
    return "Neutral", score
