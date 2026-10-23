import os
import sqlite3
from datetime import date, datetime

import pandas as pd

import market
from storage import DATA_DIR, ensure_dirs

DB = DATA_DIR / "track_record.db"
BENCHMARK = "^NSEI"
HOLD_BAND = 3.0
DIRECTION = {"Buy": 1, "Overweight": 1, "Bullish": 1, "Hold": 0, "Neutral": 0,
             "Underweight": -1, "Sell": -1, "Bearish": -1}
SOURCES = {"signals": "Rule-based signals", "ai": "AI team", "ai-quick": "AI quick", "ai-backtest": "AI backtest"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    as_of TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT,
    source TEXT NOT NULL,
    rating TEXT NOT NULL,
    direction INTEGER NOT NULL,
    price REAL NOT NULL,
    horizon_days INTEGER NOT NULL,
    action TEXT,
    entry TEXT,
    stop TEXT,
    target TEXT,
    provider TEXT,
    model TEXT,
    summary TEXT,
    settled_on TEXT,
    exit_price REAL,
    return_pct REAL,
    benchmark_pct REAL,
    alpha_pct REAL,
    outcome TEXT,
    lesson TEXT,
    ai_lesson INTEGER DEFAULT 0
)
"""


def connect() -> sqlite3.Connection:
    ensure_dirs()
    fresh = not DB.exists()
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    if fresh:
        os.chmod(DB, 0o600)
    return conn


def record(symbol: str, name: str, as_of, source: str, rating: str, price: float, horizon_days: int,
           decision: dict | None = None, provider: str = "", model: str = "", summary: str = "") -> int | None:
    if rating not in DIRECTION or not price:
        return None
    as_of = pd.Timestamp(as_of).strftime("%Y-%m-%d")
    decision = decision or {}
    with connect() as conn:
        if source == "signals":
            exists = conn.execute("SELECT 1 FROM decisions WHERE symbol=? AND as_of=? AND source='signals'",
                                  (symbol, as_of)).fetchone()
            if exists:
                return None
        cur = conn.execute(
            "INSERT INTO decisions (created, as_of, symbol, name, source, rating, direction, price, horizon_days, "
            "action, entry, stop, target, provider, model, summary) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), as_of, symbol, name, source, rating, DIRECTION[rating],
             float(price), int(horizon_days), decision.get("action"), decision.get("entry"),
             decision.get("stop-loss"), decision.get("target"), provider, model, (summary or "")[:2000]))
        return cur.lastrowid


def decisions(symbol: str | None = None, limit: int = 1000) -> list[dict]:
    query = "SELECT * FROM decisions"
    args: tuple = ()
    if symbol:
        query += " WHERE symbol=?"
        args = (symbol,)
    query += " ORDER BY as_of DESC, id DESC LIMIT ?"
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, (*args, limit))]


def clear() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM decisions")


def judge(direction: int, alpha: float) -> str:
    if direction > 0:
        return "Right" if alpha > 0 else "Wrong"
    if direction < 0:
        return "Right" if alpha < 0 else "Wrong"
    return "Right" if abs(alpha) <= HOLD_BAND else "Wrong"


def _close_on_or_before(closes: pd.Series, when) -> float | None:
    before = closes[closes.index <= pd.Timestamp(when)]
    return float(before.iloc[-1]) if not before.empty else None


def _lesson(row: dict, ret: float, bench: float, alpha: float, outcome: str) -> str:
    vs = "" if row["symbol"] == BENCHMARK else f" vs NIFTY {bench:+.2f}% (alpha {alpha:+.2f}%)"
    return (f"{row['rating']} call on {row['as_of']} at ₹{row['price']:,.2f}: over the next {row['horizon_days']} "
            f"trading days the stock moved {ret:+.2f}%{vs}, so the call was {outcome.lower()}.")


def refresh() -> tuple[list[dict], dict]:
    with connect() as conn:
        open_rows = [dict(r) for r in conn.execute("SELECT * FROM decisions WHERE outcome IS NULL")]
    if not open_rows:
        return [], {}
    earliest = min(pd.Timestamp(r["as_of"]) for r in open_rows) - pd.Timedelta(days=7)
    try:
        bench = market.load_history(BENCHMARK, earliest)["Close"]
    except Exception:
        return [], {}
    histories = {}
    for symbol in {r["symbol"] for r in open_rows}:
        try:
            histories[symbol] = market.load_history(symbol, earliest)["Close"]
        except Exception:
            continue

    settled, progress = [], {}
    with connect() as conn:
        for row in open_rows:
            closes = histories.get(row["symbol"])
            if closes is None:
                continue
            as_of = pd.Timestamp(row["as_of"])
            after = closes[closes.index > as_of]
            b_entry = _close_on_or_before(bench, as_of)
            is_bench = row["symbol"] == BENCHMARK
            if len(after) >= row["horizon_days"]:
                exit_date = after.index[row["horizon_days"] - 1]
                exit_price = float(after.iloc[row["horizon_days"] - 1])
                b_exit = _close_on_or_before(bench, exit_date)
            elif len(after):
                exit_date, exit_price = after.index[-1], float(after.iloc[-1])
                b_exit = _close_on_or_before(bench, exit_date)
                ret = (exit_price / row["price"] - 1) * 100
                b_ret = (b_exit / b_entry - 1) * 100 if b_entry and b_exit else 0.0
                progress[row["id"]] = {"days": len(after), "return_pct": ret,
                                       "alpha_pct": ret if is_bench else ret - b_ret}
                continue
            else:
                progress[row["id"]] = {"days": 0, "return_pct": 0.0, "alpha_pct": 0.0}
                continue
            ret = (exit_price / row["price"] - 1) * 100
            b_ret = (b_exit / b_entry - 1) * 100 if b_entry and b_exit else 0.0
            alpha = ret if is_bench else ret - b_ret
            outcome = judge(row["direction"], alpha)
            lesson = _lesson(row, ret, b_ret, alpha, outcome)
            conn.execute(
                "UPDATE decisions SET settled_on=?, exit_price=?, return_pct=?, benchmark_pct=?, alpha_pct=?, "
                "outcome=?, lesson=? WHERE id=?",
                (exit_date.strftime("%Y-%m-%d"), exit_price, ret, b_ret, alpha, outcome, lesson, row["id"]))
            settled.append({**row, "return_pct": ret, "alpha_pct": alpha, "outcome": outcome, "lesson": lesson})
    return settled, progress


def stats(rows: list[dict]) -> list[dict]:
    out = []
    for source, label in SOURCES.items():
        done = [r for r in rows if r["source"] == source and r["outcome"]]
        pending = [r for r in rows if r["source"] == source and not r["outcome"]]
        if not done and not pending:
            continue
        right = sum(1 for r in done if r["outcome"] == "Right")
        out.append({
            "Source": label,
            "Decisions": len(done) + len(pending),
            "Judged": len(done),
            "Right": right,
            "Hit rate": f"{right / len(done) * 100:.0f}%" if done else "–",
            "Avg alpha": f"{sum(r['alpha_pct'] for r in done) / len(done):+.2f}%" if done else "–",
        })
    return out


def needs_ai_lesson(limit: int = 10) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM decisions WHERE outcome IS NOT NULL AND source LIKE 'ai%' AND ai_lesson=0 "
            "ORDER BY settled_on DESC LIMIT ?", (limit,))]


def add_ai_lessons(ask, limit: int = 10) -> int:
    done = 0
    for row in needs_ai_lesson(limit):
        prompt = (
            f"Earlier, our team analysed {row['name']} ({row['symbol']}) on {row['as_of']} at ₹{row['price']:,.2f} "
            f"and rated it {row['rating']}. Action: {row['action'] or 'n/a'}. Entry {row['entry'] or 'n/a'}, "
            f"stop-loss {row['stop'] or 'n/a'}, target {row['target'] or 'n/a'}.\nOur reasoning at the time:\n"
            f"{row['summary'] or 'not saved'}\n\nWhat happened: {row['lesson']}\n\n"
            "In 2-3 sentences, write the lesson our team should remember for future decisions on this stock or "
            "similar setups: what we got right or missed, and what to weigh differently next time. "
            "Write only the lesson."
        )
        text = ask(prompt).strip()
        if not text:
            continue
        with connect() as conn:
            conn.execute("UPDATE decisions SET lesson=?, ai_lesson=1 WHERE id=?",
                         (f"{row['lesson']} Lesson: {text}", row["id"]))
        done += 1
    return done


def memory_text(symbol: str, before: str | None = None) -> str:
    rows = decisions()
    if before:
        rows = [r for r in rows if r["settled_on"] and r["settled_on"] <= before]
    mine = [r for r in rows if r["symbol"] == symbol and r["outcome"]][:5]
    pending = [] if before else [r for r in rows if r["symbol"] == symbol and not r["outcome"]][:3]
    others = [r for r in rows if r["symbol"] != symbol and r["outcome"] and r["ai_lesson"]][:3]
    lines = []
    if mine:
        lines.append("Past calls on this stock (most recent first):")
        lines += [f"- [{r['source']}] {r['lesson']}" for r in mine]
    if pending:
        lines.append("Calls on this stock still being tracked:")
        lines += [f"- {r['as_of']}: {r['rating']} at ₹{r['price']:,.2f} ({r['source']})" for r in pending]
    if others:
        lines.append("Recent lessons from other stocks:")
        lines += [f"- {r['symbol']}: {r['lesson']}" for r in others]
    record_rows = [s for s in stats([r for r in rows if r["outcome"]]) if s["Judged"]]
    if record_rows:
        lines.append("Team track record so far: " + "; ".join(
            f"{s['Source']} {s['Right']}/{s['Judged']} right ({s['Hit rate']}, avg alpha {s['Avg alpha']})"
            for s in record_rows))
    return "\n".join(lines)


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")
