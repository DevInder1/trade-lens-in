import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

import yfinance as yf

from storage import DATA_DIR, read_json, write_json

LOTS_URL = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"
UNIVERSE_PATH = DATA_DIR / "fno_universe.json"
SECTORS_PATH = DATA_DIR / "fno_sectors.json"
MAX_AGE = 7 * 24 * 3600
IST = timezone(timedelta(hours=5, minutes=30))
OPEN, CLOSE = (9, 15), (15, 30)

FALLBACK = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "BHARTIARTL", "ITC", "LT", "SBIN", "KOTAKBANK", "AXISBANK",
    "HINDUNILVR", "BAJFINANCE", "MARUTI", "SUNPHARMA", "HCLTECH", "TITAN", "ULTRACEMCO", "NTPC", "ASIANPAINT",
    "M&M", "POWERGRID", "TATASTEEL", "ONGC", "WIPRO", "NESTLEIND", "JSWSTEEL", "ADANIENT", "ADANIPORTS", "COALINDIA",
    "BAJAJFINSV", "TECHM", "GRASIM", "HINDALCO", "CIPLA", "DRREDDY", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO",
    "BRITANNIA", "APOLLOHOSP", "INDUSINDBK", "TATACONSUM", "SBILIFE", "HDFCLIFE", "BPCL", "SHRIRAMFIN", "TRENT",
    "BEL", "HAL",
]


def now_ist() -> datetime:
    return datetime.now(IST)


def _fresh(path, key="saved") -> dict | None:
    data = read_json(path, {})
    return data if data and time.time() - data.get(key, 0) < MAX_AGE else None


def _download_lots() -> list[dict]:
    raw = urlopen(Request(LOTS_URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "ignore")
    out = []
    for line in raw.splitlines()[1:]:
        cells = [c.strip() for c in line.split(",")]
        if len(cells) < 3 or not cells[1] or cells[1].upper() == "SYMBOL" or "NIFTY" in cells[1].upper():
            continue
        lot = next((c for c in cells[2:] if c.isdigit()), "")
        out.append({"symbol": cells[1], "name": cells[0].title(), "lot": int(lot) if lot else None})
    return out


def universe() -> list[dict]:
    cached = _fresh(UNIVERSE_PATH)
    if cached:
        return cached["stocks"]
    try:
        stocks = _download_lots()
    except Exception:
        stale = read_json(UNIVERSE_PATH, {})
        return stale.get("stocks") or [{"symbol": s, "name": s, "lot": None} for s in FALLBACK]
    if stocks:
        write_json(UNIVERSE_PATH, {"saved": time.time(), "stocks": stocks})
    return stocks


def ticker(symbol: str) -> str:
    return f"{symbol}.NS"


def _sector(symbol: str) -> str:
    try:
        info = yf.Ticker(ticker(symbol)).info or {}
    except Exception:
        return ""
    return info.get("sector") or ""


SHORT_SECTOR = {
    "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Disc.",
    "Consumer Defensive": "Consumer Staples",
    "Communication Services": "Telecom & Media",
    "Basic Materials": "Materials",
}


def sectors(symbols: list[str]) -> dict:
    data = read_json(SECTORS_PATH, {})
    known = data.get("map", {}) if time.time() - data.get("saved", 0) < 4 * MAX_AGE else {}
    missing = [s for s in symbols if not known.get(s)]
    if missing:
        with ThreadPoolExecutor(max_workers=16) as pool:
            found = dict(zip(missing, pool.map(_sector, missing)))
        known.update({s: v for s, v in found.items() if v})
        write_json(SECTORS_PATH, {"saved": data.get("saved") or time.time(), "map": known})
    return {s: SHORT_SECTOR.get(known.get(s), known.get(s)) or "Other" for s in symbols}


def market_status(session_date, now: datetime | None = None) -> dict:
    now = now or now_ist()
    today = now.date()
    minutes = now.hour * 60 + now.minute
    open_min, close_min = OPEN[0] * 60 + OPEN[1], CLOSE[0] * 60 + CLOSE[1]
    live_today = session_date == today
    if live_today and open_min <= minutes < close_min:
        return {"state": "live", "label": "🟢 Market open · live", "live": True}
    if live_today and minutes >= close_min:
        return {"state": "closed", "label": f"Market closed · today's closing board ({today:%d %b})", "live": False}
    if live_today:
        return {"state": "special", "label": "🟣 Special session", "live": True}
    if today.weekday() >= 5:
        reason = "Weekend"
    elif minutes < open_min:
        reason = "Pre-open"
    elif minutes >= open_min + 15:
        reason = "Market holiday"
    else:
        reason = "Waiting for the open"
    last = session_date.strftime("%a %d %b") if session_date else "–"
    return {"state": "closed", "label": f"{reason} · showing last session ({last})", "live": False}
