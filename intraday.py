from datetime import datetime

import pandas as pd
import yfinance as yf

import fno

ADR_SESSIONS = 20
CLEAN_SHARE = 0.7
SESSION_MINUTES = 375
COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _download(tickers: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    raw = yf.download(tickers, period=period, interval=interval, group_by="ticker", threads=True,
                      progress=False, auto_adjust=False)
    out = {}
    if raw is None or raw.empty:
        return out
    for t in tickers:
        if t not in raw.columns.get_level_values(0):
            continue
        df = raw[t][COLUMNS].dropna(subset=["Close"])
        if df.empty:
            continue
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
        out[t] = df
    return out


def load_daily(tickers: list[str]) -> dict[str, pd.DataFrame]:
    return _download(tickers, "6mo", "1d")


def load_minutes(tickers: list[str], period: str = "2d") -> dict[str, pd.DataFrame]:
    return _download(tickers, period, "1m")


def session_date(minutes: dict[str, pd.DataFrame]):
    dates = [df.index[-1].date() for df in minutes.values() if not df.empty]
    return max(dates) if dates else None


def session_bars(df: pd.DataFrame, day) -> pd.DataFrame:
    bars = df[df.index.date == day]
    return bars[(bars.index.time >= datetime.strptime("09:15", "%H:%M").time())]


def daily_stats(daily: pd.DataFrame, day) -> dict | None:
    done = daily[daily.index.date < day]
    if len(done) < 5:
        return None
    recent = done.tail(ADR_SESSIONS)
    last = done.iloc[-1]
    return {
        "adr": float((recent["High"] - recent["Low"]).mean()),
        "avg_volume": float(recent["Volume"].mean()),
        "prev_close": float(last["Close"]),
        "pdh": float(last["High"]),
        "pdl": float(last["Low"]),
    }


def score(bars: pd.DataFrame, stats: dict) -> dict | None:
    if bars.empty or not stats or not stats["adr"]:
        return None
    open_ = float(bars["Open"].iloc[0])
    last = float(bars["Close"].iloc[-1])
    high, low = float(bars["High"].max()), float(bars["Low"].min())
    volume = bars["Volume"].fillna(0)
    typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3
    vwap = float((typical * volume).sum() / volume.sum()) if volume.sum() else last
    move = last - open_
    up, down = high - open_, open_ - low
    favourable, adverse = (up, down) if move >= 0 else (down, up)
    clean = favourable / (favourable + adverse) if favourable + adverse > 0 else 0.0
    path = bars["Close"].diff().abs().sum()
    efficiency = abs(move) / path if path else 0.0
    one_sided = clean >= CLEAN_SHARE and ((move > 0 and last >= vwap) or (move < 0 and last <= vwap))
    strength = move / stats["adr"] if one_sided else 0.0
    elapsed = min(max(len(bars), 1), SESSION_MINUTES) / SESSION_MINUTES
    return {
        "open": open_,
        "last": last,
        "high": high,
        "low": low,
        "vwap": vwap,
        "change_pct": (last / stats["prev_close"] - 1) * 100,
        "from_open_pct": (last / open_ - 1) * 100,
        "strength": strength,
        "state": "Bullish" if strength > 0 else "Bearish" if strength < 0 else "Choppy",
        "clean_pct": clean * 100,
        "efficiency_pct": efficiency * 100,
        "rel_volume": float(volume.sum()) / (stats["avg_volume"] * elapsed) if stats["avg_volume"] else None,
        "adr": stats["adr"],
        "updated": bars.index[-1],
    }


def tickers() -> list[str]:
    return [fno.ticker(s["symbol"]) for s in fno.universe()]


def snapshot(minutes: dict | None = None, daily: dict | None = None, period: str = "2d") -> dict:
    stocks = fno.universe()
    names = {fno.ticker(s["symbol"]): s["name"] for s in stocks}
    lots = {fno.ticker(s["symbol"]): s["lot"] for s in stocks}
    minutes = load_minutes(tickers(), period) if minutes is None else minutes
    day = session_date(minutes)
    daily = load_daily(tickers()) if daily is None else daily
    sector_map = fno.sectors([s["symbol"] for s in stocks])
    rows = []
    for t, df in minutes.items():
        stats = daily_stats(daily[t], day) if t in daily else None
        result = score(session_bars(df, day), stats) if stats else None
        if not result:
            continue
        rows.append({"ticker": t, "symbol": t.removesuffix(".NS"), "name": names.get(t, t),
                     "sector": sector_map.get(t.removesuffix(".NS"), "Other"), "lot": lots.get(t), **result})
    table = pd.DataFrame(rows)
    return {
        "day": day,
        "status": fno.market_status(day),
        "table": table,
        "minutes": minutes,
        "daily": daily,
        "fetched": fno.now_ist().strftime("%H:%M:%S"),
        "universe": len(stocks),
    }


def boards(table: pd.DataFrame, size: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    if table.empty:
        return table, table
    bull = table[table["strength"] > 0].sort_values("strength", ascending=False).head(size)
    bear = table[table["strength"] < 0].sort_values("strength").head(size)
    return bull.reset_index(drop=True), bear.reset_index(drop=True)


def breadth(table: pd.DataFrame) -> dict:
    if table.empty:
        return {"up": 0, "down": 0, "flat": 0, "bullish": 0, "bearish": 0, "choppy": 0}
    return {
        "up": int((table["change_pct"] > 0).sum()),
        "down": int((table["change_pct"] < 0).sum()),
        "flat": int((table["change_pct"] == 0).sum()),
        "bullish": int((table["state"] == "Bullish").sum()),
        "bearish": int((table["state"] == "Bearish").sum()),
        "choppy": int((table["state"] == "Choppy").sum()),
    }


def sector_flow(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    grouped = table.groupby("sector").agg(
        stocks=("symbol", "count"),
        avg_strength=("strength", "mean"),
        avg_change=("change_pct", "mean"),
        up=("change_pct", lambda s: int((s > 0).sum())),
        down=("change_pct", lambda s: int((s < 0).sum())),
    )
    return grouped.sort_values("avg_strength", ascending=False).reset_index()


def rank_changes(board: pd.DataFrame, previous: dict | None) -> list[str]:
    marks = []
    for rank, symbol in enumerate(board["symbol"] if not board.empty else [], 1):
        if previous is None:
            marks.append("")
        elif symbol not in previous:
            marks.append("🆕" if rank <= 10 else "NEW")
        else:
            moved = previous[symbol] - rank
            marks.append(f"▲{moved}" if moved > 0 else f"▼{-moved}" if moved < 0 else "•")
    return marks
