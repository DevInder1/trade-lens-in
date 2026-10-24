from storage import DATA_DIR, read_json, write_json

PATH = DATA_DIR / "settings.json"
DEFAULTS = {
    "provider": "None (charts and signals only)",
    "model": "",
    "quick": False,
    "analysts": ["Technical", "Fundamentals", "News & Macro", "Sentiment"],
    "rounds": 1,
    "horizon_days": 20,
    "report_ai": False,
    "report_hour": 16,
    "report_minute": 30,
    "last_query": "RELIANCE",
    "last_exchange": "NSE",
    "recent": [],
}


def remember_recent(symbol: str, limit: int = 8) -> None:
    recent = [s for s in load()["recent"] if s != symbol]
    update(recent=[symbol, *recent][:limit])


def load() -> dict:
    data = read_json(PATH, {})
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def update(**changes) -> dict:
    data = load()
    if any(data.get(k) != v for k, v in changes.items()):
        data.update(changes)
        write_json(PATH, data)
    return data
