from concurrent.futures import ThreadPoolExecutor

import indicators
import market
import nse
import portfolio
import research
import stats
import track


def _evidence(symbol: str, df, nifty_close) -> dict:
    out = {"momentum": None, "delivery_pct": None, "delivery_avg": None, "buildup": None}
    try:
        out["momentum"] = stats.momentum_12_1(df["Close"], nifty_close) if nifty_close is not None else None
    except Exception:
        pass
    if symbol.endswith(".NS"):
        try:
            d = nse.delivery_summary(symbol)
            if d:
                out["delivery_pct"], out["delivery_avg"] = d["delivery_pct"], d["avg_pct"]
        except Exception:
            pass
    try:
        fo = nse.fo_for(symbol)
        out["buildup"] = fo["buildup"] if fo else None
    except Exception:
        pass
    return out


def _scan_one(symbol: str, book: dict, nifty: dict | None, nifty_close=None) -> dict:
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
        **_evidence(symbol, df, nifty_close),
        "error": None,
    }


def scan(symbols: list[str], book: dict | None = None, macro_rows: list[dict] | None = None) -> list[dict]:
    book = book or portfolio.load()
    nifty = next((r for r in (macro_rows or []) if r["symbol"] == "^NSEI"), None)
    try:
        nifty_close = market.load_prices(track.BENCHMARK, "2y")["Close"]
    except Exception:
        nifty_close = None
    try:
        nse.recent_days("equity", 20)
        nse.fo_positioning()
    except Exception:
        pass
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda s: _scan_one(s, book, nifty, nifty_close), symbols))
    return sorted(rows, key=lambda r: (r["error"] is not None, -(r.get("score") or 0)))
