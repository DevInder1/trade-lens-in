# Trade Lens IN

A private research app for Indian stocks (NSE / BSE), modelled on the TradingAgents multi-agent framework.
Type a symbol, see the chart, signals, news, social sentiment and market mood, and optionally ask a team of
AI agents (analysts, researchers, a trader, a risk team and a portfolio manager) for a decision that fits your position.

**It is read-only.** It never connects to a broker, never places trades, and runs only on your Mac
(`http://localhost:8501`). For education and research, not financial advice.

## Start it

Double-click **`Start Trading Assistant.command`** in this folder.
The first time, it installs what it needs (about a minute), then opens the app in your browser.
Close the Terminal window to stop it.

If macOS says it can't open the file: right-click it → **Open** → **Open**.

Or from Terminal:

```bash
cd ~/claude/trading-assistant && .venv/bin/streamlit run app.py
```

## What you get

| Tab | What it shows | Needs AI key? |
|---|---|---|
| 📊 Chart | Candles, 20/50/200-day averages, Bollinger Bands, volume, RSI, MACD | No |
| 🚦 Signals | 7 rule checks (trend, cross, RSI, MACD, bands, volume), support/resistance, ATR | No |
| 🏢 Fundamentals | P/E, P/B, ROE, debt, margins, growth, holdings, analyst target | No |
| 📰 News | Company headlines (Yahoo Finance + Google News India) | No |
| 💬 Sentiment | StockTwits messages (bullish/bearish labels) and Reddit posts from Indian investing communities | No |
| 🌏 Market | NIFTY, Bank NIFTY, India VIX, USD/INR, crude, gold, S&P 500, US 10-year yield; stock vs NIFTY; market headlines | No |
| 💼 Position | Your holding and P&L; rule-based position size and stop-loss from your capital and risk limit | No |
| 🤖 AI Team | The full multi-agent decision (below), downloadable as a report | Yes |

Symbols: `RELIANCE`, `TCS`, `HDFCBANK`, `INFY`, `SBIN`, … and indices `NIFTY 50`, `BANK NIFTY`, `SENSEX`, `NIFTY IT`.

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

- Pick which analysts to use and how many debate rounds in the sidebar. The sidebar shows how many AI calls a run
  will make (11 with all analysts and 1 round; 16 with 2 rounds).
- **Quick mode** makes a single call: one Portfolio Manager reviews everything.
- Tell the app in the sidebar whether you own the stock, how many shares and at what price, plus your trading capital
  and risk per trade. The trader and portfolio manager then tailor the plan (add, trim, hold) and keep the quantity
  within your risk limit.

## About AI keys (important)

Your **Claude.ai, Gemini and ChatGPT subscriptions don't work in apps**. Apps use a separate **API key**:

| Provider | Where to get a key | Cost |
|---|---|---|
| **Gemini** (easiest) | https://aistudio.google.com/apikey → *Create API key* | Free tier, no card |
| Claude | https://console.anthropic.com/settings/keys | Pay per use (add credit first) |
| ChatGPT | https://platform.openai.com/api-keys | Pay per use (add credit first) |

Paste the key in the sidebar. With **Remember on this computer** ticked it is saved to `.env` in this folder,
readable only by your Mac user. **Remove saved key** deletes it. On the free Gemini tier, a full team run may pause
briefly when it hits the per-minute limit; the app waits and retries.

## Safety and privacy

- Sent to the AI you choose: market data, headlines, public social posts, and the position/capital you entered.
  Nothing else about you.
- Your position and capital are saved only in `portfolio.json` in this folder (owner-only). `.env` and
  `portfolio.json` are excluded from git.
- The server listens only on `localhost`, so other devices on your Wi-Fi can't open it.
- Streamlit's usage statistics are turned off.
- Prices come from Yahoo Finance and can be delayed. Social posts are noisy. AI can be wrong. Check before you act.

## Files

- `app.py`: the web page
- `market.py`: prices, fundamentals, company and market news
- `indicators.py`: indicators and rule-based signals
- `macro.py`: market and macro dashboard, India VIX mood, relative strength
- `social.py`: StockTwits and Reddit sentiment
- `portfolio.py`: your position, P&L and position sizing
- `charts.py`: the chart
- `ai.py`: the multi-agent AI team (Gemini, Claude and OpenAI)
