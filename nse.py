import io
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd

import fno
from storage import DATA_DIR, ensure_dirs, read_json, write_json

CACHE_DIR = DATA_DIR / "nse"
BASE = "https://nsearchives.nseindia.com"
URLS = {
    "equity": BASE + "/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv",
    "fo": BASE + "/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip",
    "participants": BASE + "/content/nsccl/fao_participant_oi_{d:%d%m%Y}.csv",
}
MISSING_TTL = 6 * 3600
_missing: dict[tuple, float] = {}


def _fetch(kind: str, day: date) -> bytes | None:
    ensure_dirs()
    CACHE_DIR.mkdir(mode=0o700, exist_ok=True)
    path = CACHE_DIR / f"{kind}_{day:%Y%m%d}.csv"
    if path.exists():
        return path.read_bytes()
    if time.time() - _missing.get((kind, day), 0) < MISSING_TTL:
        return None
    try:
        raw = urlopen(Request(URLS[kind].format(d=day), headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
    except HTTPError as exc:
        if exc.code == 404:
            _missing[(kind, day)] = time.time()
        return None
    except Exception:
        return None
    if URLS[kind].endswith(".zip"):
        archive = zipfile.ZipFile(io.BytesIO(raw))
        raw = archive.read(archive.namelist()[0])
    if day < fno.now_ist().date():
        path.write_bytes(raw)
    return raw


def session_date(kind: str, raw: bytes) -> date | None:
    text = raw[:4000].decode("utf-8", "ignore").splitlines()
    try:
        if kind == "equity":
            return pd.to_datetime(text[1].split(",")[2].strip(), format="%d-%b-%Y").date()
        if kind == "fo":
            return pd.to_datetime(text[1].split(",")[0].strip()).date()
        title = text[0].split("as on")[-1].strip().strip('",')
        return pd.to_datetime(title, format="%b %d, %Y").date()
    except (IndexError, ValueError):
        return None


def recent_days(kind: str, count: int = 1, max_back: int = 45) -> list[tuple[date, bytes]]:
    today = fno.now_ist().date()
    days = [today - timedelta(days=i) for i in range(max_back)]
    batch = 1 if count == 1 else min(max_back, int(count * 1.5) + 6)
    out, seen = [], set()
    for start in range(0, max_back, batch):
        chunk = days[start:start + batch]
        with ThreadPoolExecutor(max_workers=min(6, len(chunk))) as pool:
            fetched = list(pool.map(lambda d: _fetch(kind, d), chunk))
        for raw in fetched:
            actual = session_date(kind, raw) if raw else None
            if actual and actual not in seen:
                seen.add(actual)
                out.append((actual, raw))
        if len(out) >= count:
            break
    return sorted(out, key=lambda item: item[0], reverse=True)[:count]


LISTED_URL = BASE + "/content/equities/EQUITY_L.csv"
LISTED_PATH = DATA_DIR / "nse_listed.json"


def listed_stocks() -> dict[str, str]:
    saved = read_json(LISTED_PATH, {})
    if saved.get("stocks") and time.time() - saved.get("saved", 0) < 7 * 24 * 3600:
        return saved["stocks"]
    try:
        raw = urlopen(Request(LISTED_URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = [c.strip() for c in df.columns]
        stocks = {str(s).strip(): str(n).strip() for s, n in zip(df["SYMBOL"], df["NAME OF COMPANY"])}
    except Exception:
        return saved.get("stocks") or {s["symbol"]: s["name"] for s in fno.universe()}
    write_json(LISTED_PATH, {"saved": time.time(), "stocks": stocks})
    return stocks


def _equity_frame(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    df = df[df["SERIES"].astype(str).str.strip().isin(["EQ", "BE", "BZ"])].copy()
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    for col in ("CLOSE_PRICE", "PREV_CLOSE", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER", "TURNOVER_LACS"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.set_index("SYMBOL")


def official_close(symbol: str) -> dict | None:
    base = symbol.removesuffix(".NS").removesuffix(".BO")
    for day, raw in recent_days("equity", 1):
        df = _equity_frame(raw)
        if base in df.index:
            row = df.loc[base]
            row = row.iloc[0] if isinstance(row, pd.DataFrame) else row
            return {"date": day, "close": float(row["CLOSE_PRICE"]), "prev_close": float(row["PREV_CLOSE"])}
    return None


def verify(symbol: str, yahoo_close: float, yahoo_date: str) -> dict:
    if symbol.startswith("^") or symbol.endswith(".BO"):
        return {"status": "skipped", "text": "Official NSE check covers NSE-listed stocks only."}
    found = official_close(symbol)
    if not found:
        return {"status": "unknown", "text": "Couldn't reach NSE's official end-of-day file to cross-check."}
    official_day = found["date"].strftime("%Y-%m-%d")
    if official_day != yahoo_date:
        newer = "Yahoo has a newer session" if yahoo_date > official_day else "Yahoo looks out of date"
        return {"status": "warn" if yahoo_date < official_day else "ok",
                "text": f"{newer}: Yahoo {yahoo_date}, NSE official file {official_day} "
                        f"(official close ₹{found['close']:,.2f})."}
    gap = abs(yahoo_close / found["close"] - 1) * 100
    if gap <= 0.3:
        return {"status": "ok", "text": f"Matches NSE's official close for {official_day} (₹{found['close']:,.2f})."}
    return {"status": "warn", "text": f"Yahoo close ₹{yahoo_close:,.2f} differs from NSE's official close "
                                      f"₹{found['close']:,.2f} by {gap:.2f}% on {official_day}. Trust the NSE figure."}


def delivery(symbol: str, sessions: int = 20) -> pd.DataFrame:
    base = symbol.removesuffix(".NS")
    rows = []
    for day, raw in recent_days("equity", sessions):
        df = _equity_frame(raw)
        if base in df.index:
            row = df.loc[base]
            row = row.iloc[0] if isinstance(row, pd.DataFrame) else row
            rows.append({"date": pd.Timestamp(day), "close": row["CLOSE_PRICE"], "prev_close": row["PREV_CLOSE"],
                         "volume": row["TTL_TRD_QNTY"], "delivery_qty": row["DELIV_QTY"],
                         "delivery_pct": row["DELIV_PER"]})
    return pd.DataFrame(rows).sort_values("date").set_index("date") if rows else pd.DataFrame()


def delivery_summary(symbol: str) -> dict | None:
    df = delivery(symbol)
    if df.empty or df["delivery_pct"].isna().all():
        return None
    last = df.iloc[-1]
    avg = float(df["delivery_pct"].iloc[:-1].mean()) if len(df) > 1 else float(last["delivery_pct"])
    up = last["close"] >= last["prev_close"]
    high = last["delivery_pct"] >= avg * 1.2
    if high and up:
        read = "Bullish", "High delivery on an up day: buyers are taking shares home (accumulation)."
    elif high and not up:
        read = "Bearish", "High delivery on a down day: genuine selling, not just intraday trading (distribution)."
    else:
        read = "Neutral", "Delivery is around its usual level."
    return {"date": df.index[-1].strftime("%Y-%m-%d"), "delivery_pct": float(last["delivery_pct"]), "avg_pct": avg,
            "sessions": len(df), "verdict": read[0], "detail": read[1], "history": df}


def _fo_frame(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw))
    for col in ("ClsPric", "PrvsClsgPric", "OpnIntrst", "ChngInOpnIntrst", "UndrlygPric", "TtlTradgVol"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


BUILDUP = {
    (True, True): ("Long build-up", "Price up with rising open interest: new buying."),
    (False, True): ("Short build-up", "Price down with rising open interest: new selling."),
    (True, False): ("Short covering", "Price up with falling open interest: sellers exiting."),
    (False, False): ("Long unwinding", "Price down with falling open interest: buyers exiting."),
}


def positioning(fo: pd.DataFrame) -> pd.DataFrame:
    futures = fo[fo["FinInstrmTp"].isin(["STF", "IDF"])].copy()
    options = fo[fo["FinInstrmTp"].isin(["STO", "IDO"])]
    near = futures.sort_values("XpryDt").groupby("TckrSymb").first()
    totals = futures.groupby("TckrSymb").agg(oi=("OpnIntrst", "sum"), oi_change=("ChngInOpnIntrst", "sum"))
    puts = options[options["OptnTp"] == "PE"].groupby("TckrSymb")["OpnIntrst"].sum()
    calls = options[options["OptnTp"] == "CE"].groupby("TckrSymb")["OpnIntrst"].sum()
    out = totals.join(near[["ClsPric", "PrvsClsgPric", "UndrlygPric"]])
    out["price_change_pct"] = (out["ClsPric"] / out["PrvsClsgPric"] - 1) * 100
    out["oi_change_pct"] = out["oi_change"] / (out["oi"] - out["oi_change"]) * 100
    out["pcr"] = (puts / calls).reindex(out.index)
    labels = [BUILDUP[(p >= 0, c >= 0)] for p, c in zip(out["price_change_pct"].fillna(0), out["oi_change"].fillna(0))]
    out["buildup"] = [label for label, _ in labels]
    out["buildup_detail"] = [detail for _, detail in labels]
    return out


_FO_CACHE: dict = {}
INDEX_NAMES = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY", "^CNXFIN": "FINNIFTY"}


def fo_positioning() -> tuple[date | None, pd.DataFrame]:
    found = recent_days("fo", 1)
    if not found:
        return None, pd.DataFrame()
    day, raw = found[0]
    if day not in _FO_CACHE:
        _FO_CACHE.clear()
        _FO_CACHE[day] = positioning(_fo_frame(raw))
    return day, _FO_CACHE[day]


def fo_for(symbol: str) -> dict | None:
    day, table = fo_positioning()
    key = INDEX_NAMES.get(symbol, symbol.removesuffix(".NS"))
    if table.empty or key not in table.index:
        return None
    row = table.loc[key]
    return {"date": day.strftime("%Y-%m-%d"), "buildup": row["buildup"], "detail": row["buildup_detail"],
            "price_change_pct": float(row["price_change_pct"]), "oi_change_pct": float(row["oi_change_pct"]),
            "pcr": None if pd.isna(row["pcr"]) else float(row["pcr"]), "oi": int(row["oi"])}


def participants() -> dict | None:
    found = recent_days("participants", 2)
    if not found:
        return None

    def parse(raw):
        lines = raw.decode("utf-8", "ignore").splitlines()[1:]
        df = pd.read_csv(io.StringIO("\n".join(lines)))
        df.columns = [c.strip() for c in df.columns]
        df["Client Type"] = df["Client Type"].astype(str).str.strip()
        return df.set_index("Client Type")

    day, raw = found[0]
    today = parse(raw)
    before = parse(found[1][1]) if len(found) > 1 else None
    rows = []
    for who in ("FII", "DII", "Pro", "Client"):
        if who not in today.index:
            continue
        long_, short = float(today.loc[who, "Future Index Long"]), float(today.loc[who, "Future Index Short"])
        row = {"Participant": {"FII": "FII / FPI (foreign)", "DII": "DII (domestic funds)", "Pro": "Pro (brokers' own)",
                               "Client": "Clients (retail & others)"}[who],
               "Index futures long": int(long_), "Index futures short": int(short), "Net": int(long_ - short),
               "Long %": long_ / (long_ + short) * 100 if long_ + short else None}
        if before is not None and who in before.index:
            prev_net = float(before.loc[who, "Future Index Long"]) - float(before.loc[who, "Future Index Short"])
            row["Net change"] = int(long_ - short - prev_net)
        rows.append(row)
    return {"date": day, "rows": rows}
