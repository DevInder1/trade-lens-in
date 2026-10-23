from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import indicators
import macro
import market
import portfolio
import social
import track

RECENT_COLUMNS = ["Open", "High", "Low", "Close", "Volume", "RSI", "MACD", "ATR"]
EMPTY_SOCIAL = {"stocktwits": {"messages": [], "bullish": 0, "bearish": 0, "available": False},
                "reddit": {"posts": [], "error": "not used for past dates"}}


def technicals(df: pd.DataFrame) -> dict:
    snap = indicators.snapshot(df)
    sigs = indicators.signals(snap)
    view, score = indicators.overall(sigs)
    return {"snapshot": snap, "signals": sigs, "view": view, "score": score}


def prices_as_of(symbol: str, as_of) -> pd.DataFrame:
    end = pd.Timestamp(as_of)
    return indicators.add_indicators(market.load_history(symbol, end - pd.Timedelta(days=3 * 365), end))


def company_name(symbol: str) -> str:
    return market.load_fundamentals(symbol).get("Company") or symbol.split(".")[0].lstrip("^")


def build(symbol: str, *, as_of=None, df=None, name=None, fundamentals=None, news=None, market_news=None,
          macro_rows=None, chatter=None, book=None, memory=True) -> dict:
    historical = as_of is not None
    if df is None:
        df = prices_as_of(symbol, as_of) if historical else indicators.add_indicators(market.load_prices(symbol, "2y"))
    if historical:
        df = df[df.index <= pd.Timestamp(as_of)]
    tech = technicals(df)
    snap = tech["snapshot"]

    if historical:
        name = name or company_name(symbol)
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_news = pool.submit(market.news_as_of, name, as_of)
            f_market = pool.submit(market.market_headlines, 12, as_of)
            f_macro = pool.submit(macro.load_macro, as_of)
            news, market_news, macro_rows = f_news.result(), f_market.result(), f_macro.result()
        fundamentals, chatter = {}, EMPTY_SOCIAL
        position_text = (f"This is a historical test as of {snap['date']}. Treat the user as having no position "
                         "and express any position size as a % of capital.")
    else:
        if fundamentals is None:
            fundamentals = {} if market.is_index(symbol) else market.load_fundamentals(symbol)
        name = name or fundamentals.get("Company") or symbol.split(".")[0].lstrip("^")
        news = market.load_news(symbol, name) if news is None else news
        market_news = market.market_headlines() if market_news is None else market_news
        macro_rows = macro.load_macro() if macro_rows is None else macro_rows
        chatter = social.load_social(symbol, name) if chatter is None else chatter
        book = book or portfolio.load()
        position_text = portfolio.describe_for(book, symbol, snap["Close"], snap["ATR"])

    return {
        "symbol": symbol,
        "name": name,
        "as_of": snap["date"] if historical else None,
        "df": df,
        "snapshot": snap,
        "signals": tech["signals"],
        "view": tech["view"],
        "score": tech["score"],
        "relative": macro.relative_strength(snap, macro_rows),
        "recent": df.tail(30)[RECENT_COLUMNS],
        "fundamentals": fundamentals,
        "news": news,
        "market_news": market_news,
        "macro": [{k: r[k] for k in ("name", "last", "change_1w", "change_1m", "change_3m", "trend")}
                  for r in macro_rows],
        "macro_rows": macro_rows,
        "vix": macro.vix_reading(macro_rows),
        "social": chatter,
        "position_text": position_text,
        "liquidity": (snap["VolAvg20"] or 0) * (snap["Close"] or 0),
        "memory": (track.memory_text(symbol, before=snap["date"] if historical else None) if memory else ""),
    }


def record_ai(data: dict, result: dict, provider: str, model: str, horizon_days: int, source: str):
    import ai

    decision = ai.parse_decision(result["final"])
    if not decision["rating"]:
        return None, decision
    row_id = track.record(data["symbol"], data["name"], data["snapshot"]["date"], source, decision["rating"],
                          data["snapshot"]["Close"], horizon_days, decision, provider, model, decision["body"])
    return row_id, decision


def record_signals(symbol: str, name: str, tech: dict, horizon_days: int):
    return track.record(symbol, name, tech["snapshot"]["date"], "signals", tech["view"],
                        tech["snapshot"]["Close"], horizon_days,
                        summary="; ".join(f"{s['name']}: {s['verdict']}" for s in tech["signals"]))
