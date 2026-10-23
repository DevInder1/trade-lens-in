from concurrent.futures import ThreadPoolExecutor

import indicators
import market
import portfolio
import research


def _scan_one(symbol: str, book: dict, nifty: dict | None) -> dict:
    try:
        df = indicators.add_indicators(market.load_prices(symbol, "2y"))
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc)}
    try:
        name = research.company_name(symbol)
    except Exception:
        name = symbol.split(".")[0].lstrip("^")
    tech = research.technicals(df)
    snap = tech["snapshot"]
    holding = portfolio.holding_for(book, symbol, snap["Close"])
    vs_nifty = None
    if nifty and snap["change_1m"] is not None and nifty.get("change_1m") is not None:
        vs_nifty = snap["change_1m"] - nifty["change_1m"]
    return {
        "symbol": symbol,
        "name": name,
        "date": snap["date"],
        "price": snap["Close"],
        "change_1d": snap["change_1d"],
        "change_1m": snap["change_1m"],
        "vs_nifty_1m": vs_nifty,
        "rsi": snap["RSI"],
        "view": tech["view"],
        "score": tech["score"],
        "signals": tech["signals"],
        "tech": tech,
        "pnl": holding["pnl"] if holding else None,
        "pnl_pct": holding["pnl_pct"] if holding else None,
        "error": None,
    }


def scan(symbols: list[str], book: dict | None = None, macro_rows: list[dict] | None = None) -> list[dict]:
    book = book or portfolio.load()
    nifty = next((r for r in (macro_rows or []) if r["symbol"] == "^NSEI"), None)
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda s: _scan_one(s, book, nifty), symbols))
    return sorted(rows, key=lambda r: (r["error"] is not None, -(r.get("score") or 0)))
