from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import pandas as pd
import yfinance as yf

INDICES = {
    "NIFTY 50": "^NSEI",
    "NIFTY": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTY IT": "^CNXIT",
    "NIFTY AUTO": "^CNXAUTO",
    "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY METAL": "^CNXMETAL",
}

SUFFIX = {"NSE": ".NS", "BSE": ".BO"}

FUNDAMENTAL_FIELDS = {
    "longName": "Company",
    "sector": "Sector",
    "industry": "Industry",
    "marketCap": "Market cap (₹)",
    "currentPrice": "Current price (₹)",
    "trailingPE": "P/E (trailing)",
    "forwardPE": "P/E (forward)",
    "priceToBook": "Price / Book",
    "trailingEps": "EPS (trailing)",
    "dividendYield": "Dividend yield (%)",
    "returnOnEquity": "Return on equity",
    "returnOnAssets": "Return on assets",
    "debtToEquity": "Debt / Equity",
    "profitMargins": "Profit margin",
    "operatingMargins": "Operating margin",
    "revenueGrowth": "Revenue growth (YoY)",
    "earningsGrowth": "Earnings growth (YoY)",
    "totalRevenue": "Total revenue (₹)",
    "freeCashflow": "Free cash flow (₹)",
    "fiftyTwoWeekHigh": "52-week high (₹)",
    "fiftyTwoWeekLow": "52-week low (₹)",
    "beta": "Beta",
    "heldPercentInsiders": "Held by promoters/insiders",
    "heldPercentInstitutions": "Held by institutions",
    "targetMeanPrice": "Analyst target (mean, ₹)",
    "recommendationKey": "Analyst consensus",
    "numberOfAnalystOpinions": "Number of analysts",
}


def normalize_symbol(text: str, exchange: str) -> str:
    raw = " ".join(text.strip().upper().split())
    if not raw:
        return ""
    if raw in INDICES:
        return INDICES[raw]
    if raw.startswith("^") or "." in raw:
        return raw
    return raw.replace(" ", "") + SUFFIX.get(exchange, ".NS")


def is_index(symbol: str) -> bool:
    return symbol.startswith("^")


def load_prices(symbol: str, period: str) -> pd.DataFrame:
    df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
    if df is None or df.empty:
        raise ValueError(f"No price data found for {symbol}. Check the symbol and exchange.")
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "Date"
    return df


def load_fundamentals(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return {}
    return {label: info[key] for key, label in FUNDAMENTAL_FIELDS.items() if info.get(key) not in (None, "")}


def load_news(symbol: str, company: str = "", limit: int = 15) -> list[dict]:
    news = _yahoo_news(symbol, company, limit)
    seen = {n["title"].lower() for n in news}
    if len(news) < limit:
        for n in _google_news(company or symbol.split(".")[0], limit):
            if n["title"].lower() not in seen:
                seen.add(n["title"].lower())
                news.append(n)
    news.sort(key=lambda n: n["date"], reverse=True)
    return news[:limit]


def _google_news(query: str, limit: int) -> list[dict]:
    url = "https://news.google.com/rss/search?" + urlencode(
        {"q": f"{query} share price when:30d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as resp:
            root = ElementTree.fromstring(resp.read())
    except Exception:
        return []
    news = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            date = ""
        if title:
            news.append({"title": title, "publisher": source, "date": date,
                         "url": item.findtext("link") or "", "summary": ""})
        if len(news) >= limit:
            break
    return news


def _yahoo_news(symbol: str, company: str, limit: int) -> list[dict]:
    items = []
    try:
        items = list(yf.Ticker(symbol).news or [])
    except Exception:
        pass
    if company:
        try:
            items += list(yf.Search(company, news_count=limit, max_results=1).news or [])
        except Exception:
            pass
    news = []
    for item in items[:limit]:
        content = item.get("content") if isinstance(item.get("content"), dict) else item
        title = content.get("title")
        if not title:
            continue
        provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher")
        link = content.get("canonicalUrl") or content.get("clickThroughUrl")
        url = link.get("url") if isinstance(link, dict) else content.get("link")
        date = content.get("pubDate") or content.get("providerPublishTime")
        if isinstance(date, (int, float)):
            date = pd.Timestamp(date, unit="s").strftime("%Y-%m-%d")
        elif isinstance(date, str):
            date = date[:10]
        news.append({
            "title": title,
            "publisher": publisher or "",
            "date": date or "",
            "url": url or "",
            "summary": content.get("summary") or "",
        })
    return news
