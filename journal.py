import os
import sqlite3
from datetime import date, datetime

import pandas as pd

from storage import DATA_DIR, ensure_dirs

DB = DATA_DIR / "journal.db"
SIDES = ["Long", "Short"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    entry REAL NOT NULL,
    exit REAL,
    from_date TEXT NOT NULL,
    to_date TEXT,
    setup TEXT,
    charges REAL DEFAULT 0,
    note TEXT
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


def add(symbol: str, side: str, qty: float, entry: float, exit_price: float | None, from_date: date,
        to_date: date | None, setup: str = "", charges: float = 0.0, note: str = "") -> int:
    if side not in SIDES or qty <= 0 or entry <= 0:
        raise ValueError("Side, quantity and entry price are required.")
    if to_date and to_date < from_date:
        raise ValueError("The To date can't be before the From date.")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO trades (created, symbol, side, qty, entry, exit, from_date, to_date, setup, charges, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), symbol.strip().upper(), side, float(qty), float(entry),
             float(exit_price) if exit_price else None, from_date.isoformat(),
             (to_date or from_date).isoformat() if exit_price else None, setup.strip(), float(charges or 0),
             note.strip()))
        return cur.lastrowid


def close(trade_id: int, exit_price: float, to_date: date) -> None:
    with connect() as conn:
        conn.execute("UPDATE trades SET exit=?, to_date=? WHERE id=?", (float(exit_price), to_date.isoformat(), trade_id))


def delete(ids: list[int]) -> None:
    with connect() as conn:
        conn.executemany("DELETE FROM trades WHERE id=?", [(i,) for i in ids])


def trades() -> pd.DataFrame:
    with connect() as conn:
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY from_date DESC, id DESC", conn)
    if df.empty:
        return df
    sign = df["side"].map({"Long": 1, "Short": -1})
    df["pnl"] = (df["exit"] - df["entry"]) * df["qty"] * sign - df["charges"].fillna(0)
    df["return_pct"] = (df["exit"] / df["entry"] - 1) * 100 * sign
    df["status"] = df["exit"].apply(lambda x: "Closed" if pd.notna(x) else "Open")
    df["days"] = (pd.to_datetime(df["to_date"]) - pd.to_datetime(df["from_date"])).dt.days
    return df


def stats(df: pd.DataFrame) -> dict:
    closed = df[df["status"] == "Closed"] if not df.empty else df
    if closed.empty:
        return {"trades": 0}
    wins, losses = closed[closed["pnl"] > 0], closed[closed["pnl"] <= 0]
    gross_loss = -losses["pnl"].sum()
    return {
        "trades": len(closed),
        "open": int((df["status"] == "Open").sum()),
        "pnl": float(closed["pnl"].sum()),
        "win_rate": len(wins) / len(closed) * 100,
        "avg_win": float(wins["pnl"].mean()) if len(wins) else 0.0,
        "avg_loss": float(losses["pnl"].mean()) if len(losses) else 0.0,
        "profit_factor": float(wins["pnl"].sum() / gross_loss) if gross_loss > 0 else None,
        "best": float(closed["pnl"].max()),
        "worst": float(closed["pnl"].min()),
    }


def by_setup(df: pd.DataFrame) -> pd.DataFrame:
    closed = df[df["status"] == "Closed"].copy() if not df.empty else df
    if closed.empty:
        return closed
    closed["setup"] = closed["setup"].replace("", "Untagged").fillna("Untagged")
    out = closed.groupby("setup").agg(trades=("id", "count"), pnl=("pnl", "sum"),
                                      win_rate=("pnl", lambda s: (s > 0).mean() * 100),
                                      avg=("pnl", "mean"))
    return out.sort_values("pnl", ascending=False).reset_index()


def daily_pnl(df: pd.DataFrame) -> pd.Series:
    closed = df[df["status"] == "Closed"] if not df.empty else df
    if closed.empty:
        return pd.Series(dtype=float)
    return closed.groupby(pd.to_datetime(closed["to_date"]))["pnl"].sum().sort_index()


def setups(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    return sorted({s for s in df["setup"].dropna() if s})
