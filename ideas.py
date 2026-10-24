STOP_BUFFER = 0.05


def _rr(entry: float, stop: float, target: float) -> float | None:
    risk = abs(entry - stop)
    return abs(target - entry) / risk if risk else None


def _money(value: float) -> str:
    return f"₹{value:,.2f}" if value < 1000 else f"₹{value:,.1f}"


def _next_liquidity(analysis: dict | None, above: bool, price: float) -> float | None:
    levels = [lv["price"] for lv in (analysis or {}).get("liquidity", [])
              if lv["swept"] is None and lv["kind"] == ("BSL" if above else "SSL")
              and (lv["price"] > price if above else lv["price"] < price)]
    if not levels:
        return None
    return min(levels) if above else max(levels)


def _confidence(row: dict, setup_used: bool, side: str) -> str:
    trending = row["state"] == ("Bullish" if side == "in" else "Bearish")
    if trending and setup_used:
        return "High"
    if trending or setup_used:
        return "Medium"
    return "Low"


def idea(row: dict, analysis: dict | None, side: str) -> dict:
    last, vwap, adr = row["last"], row["vwap"], row["adr"]
    high, low = row["high"], row["low"]
    setup = (analysis or {}).get("setup")
    buying = side == "in"

    if buying and row["state"] == "Bearish" or not buying and row["state"] == "Bullish":
        return {"bias": "Wait", "confidence": "Low", "rr": None,
                "text": "Money flow and price direction disagree today. Better to wait for them to line up."}

    if buying:
        use_zone = bool(setup and setup["direction"] == "Bullish")
        if use_zone:
            zone = setup["zone"]
            entry, stop = zone["top"], setup["invalid"] - STOP_BUFFER * adr
            basis = f"the bullish zone {_money(zone['bottom'])}–{_money(zone['top'])}"
        elif last >= vwap:
            entry, stop, basis = vwap, vwap - 0.3 * adr, "VWAP"
        else:
            return {"bias": "Wait", "confidence": "Low", "rr": None,
                    "text": f"Money is coming in, but price is still below VWAP ({_money(vwap)}). Wait for a 5-minute "
                            "close above VWAP before buying."}
        target = _next_liquidity(analysis, True, last) or (high if high > last + 0.1 * adr else last + 0.5 * adr)
        source = "next liquidity" if _next_liquidity(analysis, True, last) else "day high" if high > last + 0.1 * adr \
            else "half a normal day's range"
        rr = _rr(entry, stop, target)
        confidence = _confidence(row, use_zone, side)
        text = (f"Buy on a dip towards {_money(entry)} ({basis}). Stop-loss {_money(stop)}, target {_money(target)} "
                f"({source})" + (f", reward:risk {rr:.1f}." if rr else "."))
        if rr is not None and rr < 1:
            text += " Reward is smaller than risk, so better to skip or wait for a deeper dip."
        if confidence == "Low":
            text += " Choppy day, so treat this with caution."
        return {"bias": "Buy idea" if not rr or rr >= 1 else "Wait", "confidence": confidence, "text": text,
                "entry": entry, "stop": stop, "target": target, "rr": rr}

    use_zone = bool(setup and setup["direction"] == "Bearish")
    if use_zone:
        zone = setup["zone"]
        entry, stop = zone["bottom"], setup["invalid"] + STOP_BUFFER * adr
        basis = f"the bearish zone {_money(zone['bottom'])}–{_money(zone['top'])}"
    elif last <= vwap:
        entry, stop, basis = vwap, vwap + 0.3 * adr, "VWAP"
    else:
        return {"bias": "Wait", "confidence": "Low", "rr": None,
                "text": f"Money is going out, but price is still above VWAP ({_money(vwap)}). Avoid fresh buying; wait "
                        "for a close below VWAP before selling."}
    liquidity = _next_liquidity(analysis, False, last)
    target = liquidity or (low if low < last - 0.1 * adr else last - 0.5 * adr)
    source = "next liquidity" if liquidity else "day low" if low < last - 0.1 * adr else "half a normal day's range"
    rr = _rr(entry, stop, target)
    confidence = _confidence(row, use_zone, side)
    text = (f"Sell on a rise towards {_money(entry)} ({basis}); intraday or F&O only. Stop-loss {_money(stop)}, "
            f"target {_money(target)} ({source})" + (f", reward:risk {rr:.1f}." if rr else ".")
            + f" If you hold it: avoid adding, and consider protecting gains with a stop near {_money(stop)}.")
    if rr is not None and rr < 1:
        text += " Reward is smaller than risk, so better to skip."
    if confidence == "Low":
        text += " Choppy day, so treat this with caution."
    return {"bias": "Sell idea" if not rr or rr >= 1 else "Wait", "confidence": confidence, "text": text,
            "entry": entry, "stop": stop, "target": target, "rr": rr}
