# Trade Lens IN

A private research app for Indian stocks (NSE / BSE), modelled on the TradingAgents multi-agent framework.
Analyse a stock, keep a watchlist, let a team of AI agents make decisions that fit your position, keep score of
every call, learn from mistakes, test ideas on past dates, and get a report every evening.

**It is read-only.** It never connects to a broker, never places trades, and runs only on your Mac
(`http://localhost:8501`). For education and research, not financial advice.

Everything works **without an AI key** (charts, signals, scanner, rule-based backtest, track record, daily report).
An AI key from Gemini, Claude or OpenAI adds the written analysis and decisions.

## Start it

Double-click **`Start Trading Assistant.command`** in this folder.
The first time, it installs what it needs (about a minute), then opens the app in your browser.
Close the Terminal window to stop it.

If macOS says it can't open the file: right-click it → **Open** → **Open**.

Or from Terminal:

```bash
cd ~/claude/trading-assistant && .venv/bin/streamlit run app.py
```

## Pages

### 📊 Analyse
One stock in depth, in eight tabs: chart, signals, fundamentals, news, sentiment (StockTwits and Reddit), market
(NIFTY, India VIX, USD/INR, crude, gold, US markets), your position with rule-based position sizing, and the AI team.
Add the stock to your watchlist from the sidebar.

### ⭐ Watchlist
All your stocks in one table, strongest signals first: price, 1-day and 1-month change, performance vs NIFTY, RSI,
signal view, your P&L and the last AI call. **Add NIFTY top 10** gets you started. With AI, run a quick take on every
stock in one click (one AI call per stock).

### 🎯 Track record (with memory)
Every AI decision, and each day's signal view for your watchlist, is saved and judged automatically after 20 trading
days (you can choose 10–60):

- **Buy / Overweight / Bullish** is right if the stock beats NIFTY 50.
- **Sell / Underweight / Bearish** is right if it lags NIFTY.
- **Hold / Neutral** is right if it stays within ±3% of NIFTY.

You see the hit rate and average performance vs NIFTY for each source (signals, AI team, AI quick, AI backtest).
With AI, the team writes a short lesson on each judged call. Past calls and lessons are given to the Trader and
Portfolio Manager on the next run, so the team learns from its record.

### ⏪ Backtest
- **Rule-based (no AI):** for every day in the last 1–5 years, what the signals said and what happened next. Shows the
  hit rate for each view, and a strategy that is in the stock only when signals are Bullish vs buy-and-hold vs NIFTY.
- **AI on past dates:** runs the AI team as if it were a past date, using only prices, macro data and headlines up to
  that date, then judges the call immediately. Pick several monthly dates or one specific date.

### 🗞️ Daily report
Turn on a report every weekday after market close (default 4:30 PM). It scans your watchlist, saves signal views,
judges older calls, lists signals that changed, and can include an AI quick take per stock. You get a Mac notification
when it's ready. If the Mac is asleep at that time, it runs when it wakes. **Create a report now** runs it immediately.
Turning it off removes the scheduled job completely.

## The AI team

```
Technical · Fundamentals · News & Macro · Sentiment analysts   (work in parallel)
        ↓
Bull researcher  vs  Bear researcher                            (1–3 debate rounds)
        ↓
Trader: proposes Buy / Add / Hold / Trim / Sell / Avoid with entry, stop-loss, targets, quantity
        ↓
Aggressive · Conservative · Neutral risk analysts               (1–3 debate rounds)
        ↓
Portfolio Manager: approves, modifies or rejects → rating Buy / Overweight / Hold / Underweight / Sell
```

- A full run is 11 AI calls with all analysts and 1 round (16 with 2 rounds). **Quick mode** is 1 call.
- Your AI choice (provider, model, depth) is remembered between sessions.
- Tell the app whether you own the stock, your shares, average price, capital and risk per trade, and the plan is
  sized to fit.

## About AI keys (important)

Your **Claude.ai, Gemini and ChatGPT subscriptions don't work in apps**. Apps use a separate **API key**:

| Provider | Where to get a key | Cost |
|---|---|---|
| **Gemini** (easiest) | https://aistudio.google.com/apikey → *Create API key* | Free tier, no card |
| Claude | https://console.anthropic.com/settings/keys | Pay per use (add credit first) |
| ChatGPT | https://platform.openai.com/api-keys | Pay per use (add credit first) |

Paste the key in the sidebar with **Remember on this computer** ticked (needed for scheduled reports). It is saved to
`.env` in this folder, readable only by your Mac user. **Remove saved key** deletes it. On the free Gemini tier, a
full team run may pause briefly at the per-minute limit; the app waits and retries.

## Your data

Everything you enter or the app records stays in the `data/` folder on your Mac (owner-only):

| File | What |
|---|---|
| `data/portfolio.json` | Watchlist, positions, capital, risk per trade |
| `data/settings.json` | AI choice, judging horizon, report schedule |
| `data/track_record.db` | Every saved call, its result and lessons |
| `data/reports/` | Daily reports |
| `data/logs/daily.log` | Log of scheduled runs |

`data/` and `.env` are excluded from git, so they never go to GitHub.

## Safety and privacy

- Sent to the AI you choose: market data, headlines, public social posts, the position/capital you entered, and your
  past calls. Nothing else about you.
- The server listens only on `localhost`, so other devices on your Wi-Fi can't open it.
- Streamlit's usage statistics are turned off.
- Prices come from Yahoo Finance and can be delayed. Social posts are noisy. AI can be wrong, and backtests don't
  guarantee the future. Check before you act.

## Files

| File | What it does |
|---|---|
| `app.py` | Starts the app and the page menu |
| `views/` | The five pages |
| `ui.py` | Shared page pieces: AI settings, decision card, tables, caching |
| `research.py` | Gathers everything the AI sees, live or as of a past date |
| `ai.py` | The multi-agent AI team (Gemini, Claude, OpenAI) |
| `track.py` | Track record, judging and memory |
| `backtest.py` | Rule-based backtest and past-date selection |
| `scanner.py` | Watchlist scanner |
| `daily_report.py` / `scheduler.py` | Daily report and its Mac schedule |
| `market.py`, `macro.py`, `social.py` | Prices, fundamentals, news, macro and sentiment data |
| `indicators.py`, `charts.py` | Indicators, signals and charts |
| `portfolio.py`, `settings.py`, `storage.py` | Your saved data and preferences |
