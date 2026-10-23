from storage import DATA_DIR, read_json, write_json

PATH = DATA_DIR / "portfolio.json"
STOP_ATR_MULTIPLE = 2.0


def load() -> dict:
    data = read_json(PATH, {})
    positions = data.get("positions")
    watchlist = data.get("watchlist")
    return {
        "capital": float(data.get("capital") or 0),
        "risk_pct": float(data.get("risk_pct") or 1.0),
        "positions": positions if isinstance(positions, dict) else {},
        "watchlist": [s for s in watchlist if isinstance(s, str)] if isinstance(watchlist, list) else [],
    }


def save(data: dict) -> None:
    write_json(PATH, data)


def add_to_watchlist(symbols: list[str]) -> list[str]:
    book = load()
    added = [s for s in symbols if s and s not in book["watchlist"]]
    if added:
        book["watchlist"] += added
        save(book)
    return added


def remove_from_watchlist(symbols: list[str]) -> None:
    book = load()
    book["watchlist"] = [s for s in book["watchlist"] if s not in symbols]
    save(book)


def position_summary(qty: float, avg: float, price: float) -> dict:
    invested = qty * avg
    value = qty * price
    pnl = value - invested
    return {
        "qty": qty,
        "avg": avg,
        "invested": invested,
        "value": value,
        "pnl": pnl,
        "pnl_pct": (pnl / invested * 100) if invested else None,
    }


def holding_for(book: dict, symbol: str, price: float):
    pos = book["positions"].get(symbol) or {}
    if pos.get("owned") == "Yes" and pos.get("qty") and pos.get("avg"):
        return position_summary(float(pos["qty"]), float(pos["avg"]), price)
    return None


def sizing(capital: float, risk_pct: float, price: float, atr: float | None) -> dict | None:
    if not capital or not price or not atr:
        return None
    stop = price - STOP_ATR_MULTIPLE * atr
    risk_per_share = price - stop
    budget = capital * risk_pct / 100
    max_qty = int(budget // risk_per_share) if risk_per_share > 0 else 0
    max_qty = min(max_qty, int(capital // price))
    return {
        "stop": stop,
        "risk_per_share": risk_per_share,
        "risk_budget": budget,
        "max_qty": max_qty,
        "max_value": max_qty * price,
        "pct_of_capital": max_qty * price / capital * 100 if capital else 0,
    }


def describe(owned: str, summary: dict | None, capital: float, risk_pct: float, size: dict | None) -> str:
    lines = []
    if owned == "Yes" and summary:
        pnl_pct = f"{summary['pnl_pct']:+.2f}%" if summary["pnl_pct"] is not None else "n/a"
        lines.append(
            f"The user HOLDS {summary['qty']:g} shares at an average price of ₹{summary['avg']:,.2f} "
            f"(invested ₹{summary['invested']:,.0f}, now worth ₹{summary['value']:,.0f}, "
            f"unrealised P&L ₹{summary['pnl']:,.0f} / {pnl_pct}).")
    elif owned == "No":
        lines.append("The user does NOT hold this stock (no position). Any buy would be a new position.")
    else:
        lines.append("The user did not say whether they hold this stock. Do not assume a position either way.")
    if capital:
        lines.append(f"Trading capital available: ₹{capital:,.0f}. Maximum risk per trade: {risk_pct:g}% "
                     f"(₹{capital * risk_pct / 100:,.0f}).")
        if summary and owned == "Yes":
            lines.append(f"This holding is {summary['value'] / capital * 100:.1f}% of that capital.")
    else:
        lines.append("The user did not share their capital, so express position size as a % of capital.")
    if size:
        lines.append(
            f"Rule-based sizing (stop-loss {STOP_ATR_MULTIPLE:g}×ATR below price at ₹{size['stop']:,.2f}, "
            f"₹{size['risk_per_share']:,.2f} risk per share): at most {size['max_qty']} shares "
            f"(₹{size['max_value']:,.0f}, {size['pct_of_capital']:.1f}% of capital) for a NEW purchase.")
    return "\n".join(lines)


def describe_for(book: dict, symbol: str, price: float, atr: float | None) -> str:
    owned = (book["positions"].get(symbol) or {}).get("owned", "Not saying")
    holding = holding_for(book, symbol, price)
    size = sizing(book["capital"], book["risk_pct"], price, atr)
    return describe(owned, holding, book["capital"], book["risk_pct"], size)
