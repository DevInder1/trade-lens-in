import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import ai
import macro
import market
import portfolio
import research
import scanner
import settings
import track
from storage import ENV_PATH, REPORTS_DIR, write_private_text


def _pct(value):
    return "–" if value is None else f"{value:+.2f}%"


def _money(value):
    return "–" if value is None else f"{'-' if value < 0 else ''}₹{abs(value):,.0f}"


def _previous_view(symbol: str, today: str) -> str | None:
    for row in track.decisions(symbol):
        if row["source"] == "signals" and row["as_of"] < today:
            return row["rating"]
    return None


def _ai_ready(prefs: dict) -> tuple[str, str, str] | None:
    provider = prefs["provider"]
    if provider not in ai.PROVIDERS or not prefs["model"]:
        return None
    key = os.environ.get(ai.PROVIDERS[provider]["env"], "")
    return (provider, prefs["model"], key) if key else None


def generate(include_ai: bool | None = None, log=print) -> Path:
    load_dotenv(ENV_PATH)
    prefs = settings.load()
    book = portfolio.load()
    horizon = prefs["horizon_days"]
    include_ai = prefs["report_ai"] if include_ai is None else include_ai
    now = datetime.now()

    log("Loading market data")
    macro_rows = macro.load_macro()
    market_news = market.market_headlines(8)
    log(f"Scanning {len(book['watchlist'])} watchlist stocks")
    rows = scanner.scan(book["watchlist"], book, macro_rows) if book["watchlist"] else []
    good = [r for r in rows if not r["error"]]
    today = good[0]["date"] if good else now.strftime("%Y-%m-%d")

    changes = []
    for r in good:
        before = _previous_view(r["symbol"], r["date"])
        if before and before != r["view"]:
            changes.append(f"- **{r['name']}** ({r['symbol']}): signals turned **{r['view']}** (was {before})")
        research.record_signals(r["symbol"], r["name"], r["tech"], horizon)

    log("Updating the track record")
    settled, _ = track.refresh()

    ai_sections, ai_note = [], ""
    ready = _ai_ready(prefs) if include_ai else None
    if include_ai and not ready:
        ai_note = "AI takes were switched on, but no AI provider, model or saved key was found. Skipped."
    if ready:
        provider, model, key = ready
        for r in good:
            log(f"AI quick take: {r['symbol']}")
            try:
                data = research.build(r["symbol"], name=r["name"], macro_rows=macro_rows,
                                      market_news=market_news, book=book)
                result = ai.run_team(provider, model, key, data, ai.ANALYSTS, 1, True)
                _, d = research.record_ai(data, result, provider, model, horizon, "ai-quick")
            except Exception as exc:
                ai_sections.append(f"### {r['name']} ({r['symbol']})\nAI take failed: {exc}")
                continue
            ai_sections.append(
                f"### {r['name']} ({r['symbol']}): {d['rating'] or 'unclear'}\n"
                f"**Action:** {d['action'] or '–'}  \n**Entry:** {d['entry'] or '–'} · **Stop-loss:** "
                f"{d['stop-loss'] or '–'} · **Target:** {d['target'] or '–'} · **Confidence:** "
                f"{d['confidence'] or '–'} · **Horizon:** {d['horizon'] or '–'}\n\n"
                f"{re.sub(r'^#{1,3} ', '#### ', d['body'][:1500], flags=re.MULTILINE)}")
        try:
            track.add_ai_lessons(ai.asker(provider, model, key), limit=10)
        except Exception as exc:
            log(f"AI lessons skipped: {exc}")

    lines = [f"# Trade Lens IN — daily report, {now:%a %d %b %Y}", ""]
    nifty = next((m for m in macro_rows if m["symbol"] == "^NSEI"), None)
    lines.append("## Market")
    if nifty:
        lines.append(f"- **NIFTY 50** {nifty['last']:,.2f} (1 week {_pct(nifty['change_1w'])}, 1 month "
                     f"{_pct(nifty['change_1m'])}) · {nifty['trend'] or ''}")
    if macro.vix_reading(macro_rows):
        lines.append(f"- {macro.vix_reading(macro_rows)}")
    for m in macro_rows:
        if m["symbol"] in ("INR=X", "BZ=F", "GC=F", "^GSPC"):
            lines.append(f"- {m['name']}: {m['last']:,.2f} (1 week {_pct(m['change_1w'])})")
    if market_news:
        lines += ["", "**Headlines**"] + [f"- [{n['title']}]({n['url']}) — {n['publisher']}, {n['date']}"
                                          for n in market_news[:6]]

    lines += ["", "## Your watchlist (strongest signals first)"]
    if good:
        lines += ["| Stock | Close | 1 day | 1 month | vs NIFTY (1m) | RSI | Signals | Your P&L |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in good:
            lines.append(
                f"| {r['name']} ({r['symbol']}) | ₹{r['price']:,.2f} | {_pct(r['change_1d'])} | "
                f"{_pct(r['change_1m'])} | {_pct(r['vs_nifty_1m'])} | {r['rsi']:.0f} | {r['view']} ({r['score']:+d}) | "
                f"{_money(r['pnl'])} {'' if r['pnl_pct'] is None else _pct(r['pnl_pct'])} |")
    else:
        lines.append("Your watchlist is empty. Add stocks on the Watchlist page.")
    bad = [r for r in rows if r["error"]]
    if bad:
        lines.append("\nCould not load: " + ", ".join(r["symbol"] for r in bad))

    lines += ["", "## Signal changes since last report"]
    lines += changes or ["No changes."]

    if ai_sections or ai_note:
        lines += ["", "## AI quick takes"] + ([ai_note] if ai_note else []) + ai_sections

    lines += ["", "## Track record"]
    if settled:
        lines += [f"- {s['symbol']}: {s['lesson']}" for s in settled]
    else:
        lines.append("No decisions were judged today.")
    record = track.stats(track.decisions())
    if record:
        lines.append("")
        lines += [f"- {s['Source']}: {s['Right']}/{s['Judged']} right ({s['Hit rate']}), avg vs NIFTY {s['Avg alpha']}"
                  if s["Judged"] else f"- {s['Source']}: {s['Decisions']} calls, none judged yet"
                  for s in record]

    lines += ["", "---", "For education and research only. Not financial advice."]
    path = REPORTS_DIR / f"{today}.md"
    write_private_text(path, "\n".join(lines))
    log(f"Report saved: {path}")
    return path


def notify_mac(title: str, message: str) -> None:
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


if __name__ == "__main__":
    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M}] daily report starting", flush=True)
    try:
        report = generate(log=lambda m: print(f"  {m}", flush=True))
    except Exception as exc:
        print(f"  failed: {exc}", flush=True)
        notify_mac("Trade Lens IN", "Daily report failed. Open the app for details.")
        sys.exit(1)
    notify_mac("Trade Lens IN", f"Daily report ready: {report.stem}")
