# Trading Assistant

A simple, private research app for Indian stocks (NSE / BSE), inspired by TradingAgents.
Type a symbol, see the chart and signals, and optionally ask a team of AI analysts for a written view.

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
| 🚦 Signals | 7 simple rule checks (trend, cross, RSI, MACD, bands, volume), support/resistance, ATR | No |
| 🏢 Fundamentals | P/E, P/B, ROE, debt, margins, growth, holdings, analyst target | No |
| 📰 News | Latest headlines (Yahoo Finance + Google News India) | No |
| 🤖 AI Team | Technical, Fundamentals and News analysts → Bull vs Bear debate → Risk Manager verdict, downloadable | Yes |

Symbols: `RELIANCE`, `TCS`, `HDFCBANK`, `INFY`, `SBIN`, … and indices `NIFTY 50`, `BANK NIFTY`, `SENSEX`, `NIFTY IT`.

## About AI keys (important)

Your **Claude.ai, Gemini and ChatGPT subscriptions don't work in apps**. Apps use a separate **API key**:

| Provider | Where to get a key | Cost |
|---|---|---|
| **Gemini** (easiest) | https://aistudio.google.com/apikey → *Create API key* | Free tier, no card |
| Claude | https://console.anthropic.com/settings/keys | Pay per use (add credit first) |
| ChatGPT | https://platform.openai.com/api-keys | Pay per use (add credit first) |

Paste the key in the sidebar. With **Remember on this computer** ticked it is saved to `.env` in this folder,
readable only by your Mac user. **Remove saved key** deletes it.

*Full team* makes 6 AI calls per analysis; *Quick* makes 1. On paid providers, Quick is cheapest.

## Safety and privacy

- Only market data (prices, indicators, fundamentals, headlines) is sent to the AI you choose. Nothing about you.
- The server listens only on `localhost`, so other devices on your Wi-Fi can't open it.
- Streamlit's usage statistics are turned off.
- Your key is never shown on screen and never leaves your Mac except to the AI provider you picked.
- Prices come from Yahoo Finance and can be delayed. AI can be wrong. Check before you act.

## Files

- `app.py`: the web page
- `market.py`: prices, fundamentals and news
- `indicators.py`: indicators and rule-based signals
- `charts.py`: the chart
- `ai.py`: the AI analyst team (Gemini, Claude and OpenAI)
