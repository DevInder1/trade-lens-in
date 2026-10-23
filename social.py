import html
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

UA = "trade-lens-in/0.2 (personal stock research app)"
SUBREDDITS = "IndianStockMarket+IndiaInvestments+DalalStreetTalks+StockMarketIndia+IndianStreetBets"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
NAME_NOISE = re.compile(r"\b(limited|ltd\.?|corporation|corp\.?|company|co\.?|india|industries)\b", re.IGNORECASE)


def _get(url: str, accept: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": UA, "Accept": accept}), timeout=12) as resp:
        return resp.read()


def _plain(text: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def short_name(company: str, symbol: str) -> str:
    base = symbol.split(".")[0].lstrip("^")
    name = " ".join(NAME_NOISE.sub(" ", company or "").split())
    return name or base


def stocktwits(symbol: str, limit: int = 30) -> dict:
    empty = {"messages": [], "bullish": 0, "bearish": 0, "available": False}
    if symbol.startswith("^"):
        return empty
    ticker = symbol.split(".")[0] + ".NSE"
    try:
        payload = json.loads(_get(f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json", "application/json"))
    except Exception:
        return empty
    messages = []
    for m in (payload.get("messages") or [])[:limit]:
        sentiment = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        messages.append({
            "date": (m.get("created_at") or "")[:10],
            "body": _plain(m.get("body"), 400),
            "sentiment": sentiment or "",
            "likes": (m.get("likes") or {}).get("total", 0),
        })
    return {
        "messages": messages,
        "bullish": sum(1 for m in messages if m["sentiment"] == "Bullish"),
        "bearish": sum(1 for m in messages if m["sentiment"] == "Bearish"),
        "available": True,
    }


def reddit(symbol: str, company: str, limit: int = 25, days: int = 30) -> dict:
    base = symbol.split(".")[0].lstrip("^")
    name = short_name(company, symbol)
    query = f'"{name}" OR {base}' if name.upper() != base.upper() else f'"{name}"'
    url = f"https://www.reddit.com/r/{SUBREDDITS}/search.rss?" + urlencode(
        {"q": query, "restrict_sr": "on", "sort": "new", "t": "month", "limit": limit})
    try:
        root = ElementTree.fromstring(_get(url, "application/atom+xml"))
    except HTTPError as exc:
        busy = exc.code == 429
        return {"posts": [], "error": "Reddit is limiting requests right now; try again in a few minutes."
                if busy else f"Reddit returned HTTP {exc.code}."}
    except Exception:
        return {"posts": [], "error": "Could not reach Reddit."}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    terms = {re.escape(t) for t in (name, base) if t}
    mentions = re.compile(rf"\b({'|'.join(terms)})\b", re.IGNORECASE)
    posts = []
    for entry in root.findall("a:entry", ATOM):
        updated = entry.findtext("a:updated", "", ATOM) or entry.findtext("a:published", "", ATOM)
        try:
            when = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            continue
        title = _plain(entry.findtext("a:title", "", ATOM), 300)
        body = _plain(entry.findtext("a:content", "", ATOM), 5000)
        if not mentions.search(f"{title} {body}"):
            continue
        link = entry.find("a:link", ATOM)
        category = entry.find("a:category", ATOM)
        posts.append({
            "date": when.strftime("%Y-%m-%d"),
            "title": title,
            "text": _plain(body, 500),
            "url": link.get("href", "") if link is not None else "",
            "subreddit": category.get("term", "") if category is not None else "",
        })
    return {"posts": posts[:limit], "error": None}


def load_social(symbol: str, company: str) -> dict:
    return {"stocktwits": stocktwits(symbol), "reddit": reddit(symbol, company)}
