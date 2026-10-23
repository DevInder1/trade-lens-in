import json
import os
from pathlib import Path

PATH = Path(__file__).with_name("portfolio.json")
DEFAULT = {"capital": 0.0, "risk_pct": 1.0, "positions": {}}
STOP_ATR_MULTIPLE = 2.0


def load() -> dict:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT))
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT))
    return {
        "capital": float(data.get("capital") or 0),
        "risk_pct": float(data.get("risk_pct") or 1.0),
        "positions": data.get("positions") if isinstance(data.get("positions"), dict) else {},
    }


def save(data: dict) -> None:
    temp = PATH.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    os.replace(temp, PATH)


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
