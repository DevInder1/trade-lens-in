import pandas as pd

SWING_N = 2
TURN_LOOKBACK = 12
EQUAL_TOLERANCE = 0.0008
AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def to_5min(bars_1m: pd.DataFrame, live: bool) -> pd.DataFrame:
    if bars_1m.empty:
        return bars_1m
    out = bars_1m.resample("5min", label="left", closed="left").agg(AGG).dropna(subset=["Close"])
    if live and len(out) and bars_1m.index[-1] < out.index[-1] + pd.Timedelta(minutes=4):
        out = out.iloc[:-1]
    return out


def swing_points(df: pd.DataFrame, n: int = SWING_N) -> tuple[list[int], list[int]]:
    h, l = df["High"].to_numpy(), df["Low"].to_numpy()
    highs, lows = [], []
    for i in range(n, len(df) - n):
        if h[i] > h[i - n:i].max() and h[i] > h[i + 1:i + n + 1].max():
            highs.append(i)
        if l[i] < l[i - n:i].min() and l[i] < l[i + 1:i + n + 1].min():
            lows.append(i)
    return highs, lows


def _turn(o, c, j, bullish) -> int | None:
    for t in range(j - 1, max(-1, j - 1 - TURN_LOOKBACK), -1):
        if (bullish and c[t] < o[t]) or (not bullish and c[t] > o[t]):
            return t
    return None


def order_blocks(df: pd.DataFrame) -> list[dict]:
    if len(df) < 2 * SWING_N + 4:
        return []
    o, h, l, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    idx = df.index
    avg = (df["High"] - df["Low"]).rolling(20, min_periods=5).mean().bfill().to_numpy()
    highs, lows = swing_points(df)
    zones, used = [], set()

    for j in range(1, len(df)):
        for bullish, swings in ((True, highs), (False, lows)):
            ready = [i for i in swings if i + SWING_N < j and (bullish, i) not in used]
            if not ready:
                continue
            i = ready[-1]
            level = h[i] if bullish else l[i]
            crossed = c[j] > level >= c[j - 1] if bullish else c[j] < level <= c[j - 1]
            if not crossed:
                continue
            used.add((bullish, i))
            k = _turn(o, c, j, bullish)
            kind = "bull" if bullish else "bear"
            if k is None or any(z["kind"] == kind and z["start"] == idx[k] for z in zones):
                continue
            if bullish:
                gap = any(l[t] > h[t - 2] for t in range(max(k + 2, 2), j + 1))
                fast = gap or c[j] - h[k] >= avg[j]
            else:
                gap = any(h[t] < l[t - 2] for t in range(max(k + 2, 2), j + 1))
                fast = gap or l[k] - c[j] >= avg[j]
            if fast:
                zones.append({"kind": kind, "top": float(h[k]), "bottom": float(l[k]),
                              "start": idx[k], "formed": idx[j], "swing": float(level), "gap": gap,
                              "broken": None, "tested": None})

    for z in zones:
        after = df[df.index > z["formed"]]
        if z["kind"] == "bull":
            broke, touch = after[after["Close"] < z["bottom"]], after[after["Low"] <= z["top"]]
        else:
            broke, touch = after[after["Close"] > z["top"]], after[after["High"] >= z["bottom"]]
        z["broken"] = broke.index[0] if len(broke) else None
        touch = touch[touch.index < z["broken"]] if z["broken"] is not None else touch
        z["tested"] = touch.index[0] if len(touch) else None
    return zones


def liquidity(df: pd.DataFrame) -> list[dict]:
    if len(df) < 2 * SWING_N + 1:
        return []
    highs, lows = swing_points(df)
    h, l = df["High"].to_numpy(), df["Low"].to_numpy()
    idx = df.index
    levels = []
    for kind, points, values in (("BSL", highs, h), ("SSL", lows, l)):
        for i in points:
            later = values[i + 1:]
            hit = (later > values[i]) if kind == "BSL" else (later < values[i])
            swept = idx[i + 1 + int(hit.argmax())] if hit.any() else None
            levels.append({"kind": kind, "price": float(values[i]), "start": idx[i], "swept": swept})
    for lv in levels:
        lv["equal"] = any(o is not lv and o["kind"] == lv["kind"] and
                          abs(o["price"] - lv["price"]) <= EQUAL_TOLERANCE * lv["price"] for o in levels)
    return levels


def htf_levels(daily: pd.DataFrame, day) -> list[dict]:
    done = daily[daily.index.date < day]
    if done.empty:
        return []
    last = done.iloc[-1]
    levels = [{"label": "Prev day high", "price": float(last["High"])},
              {"label": "Prev day low", "price": float(last["Low"])}]
    week_start = pd.Timestamp(day) - pd.Timedelta(days=pd.Timestamp(day).weekday())
    prev_week = done[(done.index >= week_start - pd.Timedelta(days=7)) & (done.index < week_start)]
    if len(prev_week):
        levels += [{"label": "Prev week high", "price": float(prev_week["High"].max())},
                   {"label": "Prev week low", "price": float(prev_week["Low"].min())}]
    for z in order_blocks(done.tail(80)):
        if z["broken"] is None:
            label = "Daily bullish OB" if z["kind"] == "bull" else "Daily bearish OB"
            edge = z["top"] if z["kind"] == "bull" else z["bottom"]
            levels.append({"label": label, "price": edge, "zone": (z["bottom"], z["top"])})
    return levels


def setup(zones: list[dict], liq: list[dict], htf: list[dict], direction: str, last: float, adr: float) -> dict | None:
    bullish = direction == "Bullish"
    live = [z for z in zones if z["kind"] == ("bull" if bullish else "bear") and z["broken"] is None]
    if not live:
        return None
    z = live[-1]
    if bullish:
        ahead = sorted(lv["price"] for lv in liq if lv["kind"] == "BSL" and lv["swept"] is None and lv["price"] > last)
        behind = sorted((x for x in htf if x["price"] < z["bottom"]), key=lambda x: -x["price"])[:3]
        resting = [lv for lv in liq if lv["kind"] == "SSL" and lv["swept"] is None and lv["price"] < z["bottom"]]
        sweep = max(resting, key=lambda lv: lv["price"]) if resting else None
        invalid = z["bottom"]
    else:
        ahead = sorted((lv["price"] for lv in liq if lv["kind"] == "SSL" and lv["swept"] is None and lv["price"] < last),
                       reverse=True)
        behind = sorted((x for x in htf if x["price"] > z["top"]), key=lambda x: x["price"])[:3]
        resting = [lv for lv in liq if lv["kind"] == "BSL" and lv["swept"] is None and lv["price"] > z["top"]]
        sweep = min(resting, key=lambda lv: lv["price"]) if resting else None
        invalid = z["top"]
    step = 1 if bullish else -1
    targets = [{"price": p, "source": "liquidity"} for p in ahead[:2]]
    while len(targets) < 2:
        base = targets[-1]["price"] if targets else last
        targets.append({"price": base + step * adr * 0.5, "source": "½ daily range"})
    return {"direction": direction, "zone": z, "invalid": invalid, "targets": targets, "behind": behind,
            "sweep": sweep, "risk": abs(last - invalid)}


def analyse(bars_1m: pd.DataFrame, daily: pd.DataFrame, day, direction: str, last: float, adr: float,
            live: bool) -> dict:
    five = to_5min(bars_1m, live)
    zones = order_blocks(five)
    liq = liquidity(five)
    htf = htf_levels(daily, day) if daily is not None else []
    session = five[five.index.date == day]
    in_session = [z for z in zones if z["formed"].date() == day]
    return {
        "adr": adr,
        "five": session,
        "zones": in_session,
        "liquidity": [lv for lv in liq if lv["start"].date() == day],
        "htf": htf,
        "setup": setup(in_session, liq, htf, direction, last, adr) if direction in ("Bullish", "Bearish") else None,
    }
