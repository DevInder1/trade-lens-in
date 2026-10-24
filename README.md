# Trade Lens IN

A private research app for Indian stocks (NSE / BSE). It combines ideas from three projects:
**TradingAgents** (a team of AI analysts that debate), **FinRL** (risk switches, portfolio allocation and proper
backtest statistics) and **OrderBlock** (live F&O strength boards with order-block zones), rebuilt with free and
official Indian data.

**It is read-only.** It never connects to a broker, never places trades, and runs only on your Mac
(`http://localhost:8501`). For education and research, not financial advice.

Everything works **without an AI key**. For the AI team, the easiest option is **Ollama**: free, private and
unlimited, running on your own Mac.

## Start it

Double-click **`Start Trading Assistant.command`** in this folder.
The first time, it installs what it needs (about a minute), then opens the app in your browser.
Close the Terminal window to stop it.

If macOS says it can't open the file: right-click it → **Open** → **Open**.

Or from Terminal:

```bash
cd ~/claude/trading-assistant && .venv/bin/streamlit run app.py
```

The first page you open each day takes 30–40 seconds while market data loads; after that pages open in seconds.

## Pages

The menu is grouped into **Today**, **Research** and **Review**.

### 🏠 Home
One screen for the day: NIFTY, the India VIX fear gauge, **market turbulence**, **FII index-futures positioning**,
your watchlist ranked by momentum, the **momentum leaders** among F&O stocks, this month's journal P&L, your track
record, and a glossary of terms.

### 📡 Terminal (intraday, F&O stocks)
A live board of all ~210 F&O stocks (list downloaded from NSE), refreshed about once a minute during market hours.

- **Strength** = move since the open ÷ the stock's normal daily range (average of the last 20 sessions). It only
  counts when the move is clean: at least 70% of the day's range on the side of the move, with price on the right
  side of VWAP. Otherwise the stock is **Choppy** and scores zero.
- **Bullish and Bearish boards** with rank-change markers (▲▼, 🆕), the current order-block zone and the next level.
- **Breadth bar**, **Market X-Ray** (every F&O stock as a dot at its day's move, by sector) and **Sector flow**.
- **F&O positioning (end of day, NSE official)**: long build-up, short build-up, short covering and long unwinding
  counts, the biggest movers in each, and NIFTY / Bank NIFTY put-call ratio.
- **Popup chart**: click any row for a 5-minute chart with order-block zones drawn where they formed, liquidity lines,
  the level where the setup fails, the next two levels, up to three higher-timeframe levels behind it, and the stock's
  F&O build-up.

How zones are found (our own implementation of standard order-block ideas): an **order block** is the last
opposite-colour candle before a move that *closes* beyond a recent swing high/low, and the move must be fast (it leaves
a fair-value gap or travels at least one average candle beyond the block). Only finished 5-minute candles are used.
**Liquidity** = swing highs/lows no candle has traded through yet.

### 📊 Analyse
One stock in depth. Pick it from a **searchable list of all 2,600+ NSE-listed stocks and the main indices**: start
typing a company name or code (e.g. *tata*), or click one of your **⭐ watchlist** or **🕘 recently viewed** stocks.
Whatever you type works as a search, even if you just press Enter: it handles nicknames (*L&T*, *Zomato*, *SBI*,
*Airtel*) and spelling mistakes (*infosis*, *hdfc bnak*), opens the best match and offers other matches as one-click
buttons.
You can also type any Yahoo symbol, such as a BSE code. The same search is used on the Backtest page, and for adding
stocks on the Watchlist and Portfolio pages (pick several at once). Under the name, a **✅ Verified** line confirms Yahoo's price matches **NSE's official closing
price** (or warns you if it doesn't). Eight tabs: chart; signals with an **evidence** section (12-month momentum and its
rank among F&O stocks, NSE delivery % with a 20-session chart, F&O build-up and put-call ratio, ADX/CCI for
information); fundamentals; news; sentiment (StockTwits and Reddit); market (VIX, turbulence chart, FII/DII/Pro/Client
index-futures positioning, macro, headlines); your position with rule-based sizing; and the AI team.

### ⭐ Watchlist
All your stocks in one table, sortable by **momentum** (most reliable) or signal score, with NSE delivery %, F&O
build-up, RSI, signals, your P&L and the last AI call. With AI, run a quick take on every stock in one click.

### 🧺 Portfolio (from FinRL's portfolio-allocation baselines)
How to split money across several stocks: **Equal weight**, **Lowest risk** (minimum variance), **Best return per
risk** (maximum Sharpe) or **Equal risk** (risk parity), with a cap on any one stock. Shows the weights, how many whole
shares to buy with your capital, and an **honest check**: the weights are fitted on older data and tested on the most
recent third, which the method never saw, against equal weight and NIFTY. Plus a correlation heatmap.

### 📒 Journal
Log trades (Long/Short, quantity, entry, exit, From and To dates, charges, setup tag, note). See realised P&L, win rate,
profit factor, **which setups pay**, a **P&L calendar heatmap** and cumulative P&L. Export to CSV.

### 🎯 Track record (with memory)
Every AI decision, and each day's signal view for your watchlist, is saved and judged after 20 trading days (10–60):
Buy/Overweight/Bullish is right if the stock beats NIFTY; Sell/Underweight/Bearish if it lags; Hold/Neutral if it
stays within ±3% of NIFTY. With AI, the team writes a lesson on each judged call and is reminded of them next time.

### ⏪ Backtest
- **Rule-based (no AI):** what the signals said each day and what happened next, with a full **statistics table**
  (total return, CAGR, volatility, Sharpe, Sortino, Calmar, max drawdown, up days, best/worst day, VaR) for the
  strategy, the strategy with FinRL's **turbulence filter** (cash in the most turbulent 10% of days), buy-and-hold and
  NIFTY.
- **AI on past dates:** runs the AI team as if it were a past date, using only data available then, and judges it.

### 🗞️ Daily report
A report every weekday after market close (default 4:30 PM) with market turbulence, FII positioning, your watchlist
ranked by momentum with delivery % and F&O build-up, signal changes, optional AI quick takes, and the track record.
You get a Mac notification. **Create a report now** runs it immediately.

## How accurate is this? (tested, not assumed)

| Measure | Test | Result |
|---|---|---|
| Rule-based signals (trend, RSI, MACD, bands, volume) | 25 large stocks, 5 years, next 20 trading days | Bullish right **52%**, Bearish right **48%**: close to a coin flip. Shown as chart description, not prediction. |
| Adding FinRL's ADX / CCI indicators to the score | Same test | No meaningful improvement, so they're shown as information only |
| **12-month momentum vs NIFTY** (skipping the last month) | 45 large stocks, 7 years, next 3 months | Top 20% beat NIFTY **54%** of the time (avg **+2.7%**); bottom 20%: 49%. The best measure we found; modest, and flattered slightly because these are today's large companies |
| Signals strategy vs buy-and-hold | Reliance, HDFC Bank, NIFTY, 5 years | The signals strategy **underperformed** buy-and-hold. The turbulence filter helped on HDFC Bank but not the others |
| Yahoo prices | Cross-checked against NSE's official closing prices | Matched for the stocks tested; the app warns you whenever they differ by more than 0.3% or Yahoo is out of date |

## The AI team

```
Technical · Fundamentals · News & Macro · Sentiment analysts
        ↓
Bull researcher  vs  Bear researcher                            (1–3 debate rounds)
        ↓
Trader: proposes Buy / Add / Hold / Trim / Sell / Avoid with entry, stop-loss, targets, quantity
        ↓
Aggressive · Conservative · Neutral risk analysts               (1–3 debate rounds)
        ↓
Portfolio Manager: approves, modifies or rejects → rating Buy / Overweight / Hold / Underweight / Sell
```

- The AI sees the NSE-verified price, delivery %, F&O positioning, momentum, market turbulence, your position and its
  own past calls, and is told how reliable each measure has been.
- A full run is 11 AI calls with all analysts and 1 round. **Quick mode** is 1 call.
- If a model ignores the required answer format, the app makes one short extra call to convert its answer, so the
  rating card always works, even with small local models.

## AI options

Your **Claude.ai, Gemini and ChatGPT subscriptions don't work in apps**. Choose one of these in the sidebar:

| Provider | Cost | Setup | Speed |
|---|---|---|---|
| **Ollama** (on your Mac) | Free, unlimited, private | Install from https://ollama.com and pull a model (e.g. `ollama pull gemma4`). No key | Quick ≈ 1–2 min, full team ≈ 5 min |
| **Gemini** | Free tier | Key from https://aistudio.google.com/apikey | Fast |
| **OpenRouter** | Free models (daily limits) | Free key from https://openrouter.ai/keys; the app lists only free models | Fast |
| **Groq** | Free tier (per-minute limits) | Free key from https://console.groq.com/keys | Very fast |
| Claude | Pay per use | Key from https://console.anthropic.com/settings/keys | Fast |
| ChatGPT | Pay per use | Key from https://platform.openai.com/api-keys | Fast |

Keys are saved to `.env` in this folder (owner-only) when **Remember on this computer** is ticked; **Remove saved key**
deletes it.

## Free data sources

| Source | Used for | Key? |
|---|---|---|
| Yahoo Finance | Prices (daily and 1-minute), fundamentals, company news | No |
| **NSE official archives** | Official closing prices (data check), delivery %, F&O open interest and build-up, put-call ratio, FII/DII/Pro/Client index-futures positioning, the F&O stock list | No |
| Google News (India) | Company and market headlines, including past dates for backtests | No |
| StockTwits, Reddit | Retail sentiment | No |

NSE files are downloaded once per session date and cached in `data/nse/`. NSE also serves weekend and holiday files that
repeat the previous session; the app reads the real session date inside each file and skips duplicates.

## Your data

Everything stays in the `data/` folder on your Mac (owner-only): `portfolio.json` (watchlist, positions, capital),
`settings.json`, `track_record.db`, `journal.db`, `reports/`, `logs/`, and caches (`nse/`, F&O list and sectors).
`data/` and `.env` are excluded from git, so they never go to GitHub.

## Safety and privacy

- Sent to the AI you choose: market data, headlines, public social posts, the position/capital you entered and your
  past calls. With Ollama nothing leaves your Mac.
- The server listens only on `localhost`. Streamlit's usage statistics are turned off.
- Prices can be delayed. AI can be wrong. Backtests don't guarantee the future. Strength, zones and levels are
  calculations, not recommendations. SEBI's studies found about 9 in 10 individual F&O traders made net losses.

## What was taken from FinRL (and what wasn't)

FinRL (MIT licence) is a deep-reinforcement-learning research framework. Re-implemented here: the **turbulence index**
and risk switch, **pyfolio-style statistics**, **portfolio-allocation baselines** (equal weight, minimum variance, mean
variance) with out-of-sample testing, and its extra indicators (tested, kept as information). **Not included:** the
DRL agents (PPO, A2C, SAC…). They need about 2 GB of extra software and hours of training per stock, and FinRL itself
presents them as research, not a trading tool.

## Files

| File | What it does |
|---|---|
| `app.py` | Starts the app and the grouped page menu |
| `views/` | The nine pages |
| `ui.py` | Shared page pieces: AI settings, decision card, tables, caching |
| `research.py` | Gathers everything the AI sees, live or as of a past date |
| `ai.py` | The multi-agent AI team and all AI providers (Ollama, Gemini, OpenRouter, Groq, Claude, OpenAI) |
| `nse.py` | NSE official files: closing prices, delivery %, F&O build-up, participant positioning |
| `stats.py` | Backtest statistics, turbulence index, momentum |
| `optimizer.py` | Portfolio allocation and the out-of-sample check |
| `track.py` | Track record, judging and memory |
| `backtest.py` | Rule-based backtest and past-date selection |
| `scanner.py` | Watchlist scanner |
| `daily_report.py` / `scheduler.py` | Daily report and its Mac schedule |
| `market.py`, `macro.py`, `social.py` | Prices, fundamentals, news, macro and sentiment data |
| `fno.py`, `intraday.py`, `zones.py` | F&O universe and market calendar, intraday strength boards, order blocks and liquidity |
| `journal.py` | Trading journal |
| `indicators.py`, `charts.py` | Indicators, signals and charts |
| `portfolio.py`, `settings.py`, `storage.py` | Your saved data and preferences |
