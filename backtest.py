import pandas as pd

import indicators
import market
import stats
import track

COST_PCT = 0.1


def signal_backtest(symbol: str, years: int, horizon: int, turbulence_filter: bool = False) -> dict:
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years) - pd.Timedelta(days=420)
    df = indicators.add_indicators(market.load_history(symbol, start, end))
    bench = market.load_history(track.BENCHMARK, start, end)["Close"].reindex(df.index).ffill()

    first = df["SMA200"].first_valid_index()
    if first is None:
        raise ValueError("Not enough price history for a backtest (needs at least 200 trading days).")
    df = df.loc[max(first, end - pd.DateOffset(years=years)):]
    bench = bench.loc[df.index]
    views = indicators.view_series(df)
    close = df["Close"]

    fwd = (close.shift(-horizon) / close - 1) * 100
    bench_fwd = (bench.shift(-horizon) / bench - 1) * 100
    alpha = fwd if symbol == track.BENCHMARK else fwd - bench_fwd
    table = []
    for view in ("Bullish", "Neutral", "Bearish"):
        mask = (views["view"] == view) & fwd.notna()
        if not mask.any():
            continue
        outcomes = [track.judge(track.DIRECTION[view], a) for a in alpha[mask]]
        table.append({
            "Signal view": view,
            "Days": int(mask.sum()),
            f"Avg return next {horizon}d": f"{fwd[mask].mean():+.2f}%",
            "Avg vs NIFTY": f"{alpha[mask].mean():+.2f}%",
            "Hit rate": f"{outcomes.count('Right') / len(outcomes) * 100:.0f}%",
        })

    daily = close.pct_change().fillna(0)

    def run(position):
        trades = position.diff().abs().fillna(position.iloc[0])
        return (1 + position.shift(1).fillna(0) * daily - trades * COST_PCT / 100).cumprod()

    position = (views["view"] == "Bullish").astype(float)
    curves = {"Signals strategy": run(position)}
    risk_off_days = None
    if turbulence_filter:
        turb = stats.turbulence(stats.basket_closes(start, end))
        risk_off = stats.risk_off_mask(turb).reindex(df.index).fillna(False).astype(bool)
        risk_off_days = float(risk_off.mean() * 100)
        curves["Signals + turbulence filter"] = run(position.where(~risk_off, 0.0))
    curves["Buy and hold"] = close / close.iloc[0]
    curves["NIFTY 50"] = bench / bench.iloc[0]
    curves = pd.DataFrame(curves) * 100

    def drawdown(series):
        return float((series / series.cummax() - 1).min() * 100)

    summary = {
        "start": df.index[0].strftime("%Y-%m-%d"),
        "end": df.index[-1].strftime("%Y-%m-%d"),
        "strategy_return": float(curves["Signals strategy"].iloc[-1] - 100),
        "hold_return": float(curves["Buy and hold"].iloc[-1] - 100),
        "nifty_return": float(curves["NIFTY 50"].iloc[-1] - 100),
        "strategy_drawdown": drawdown(curves["Signals strategy"]),
        "hold_drawdown": drawdown(curves["Buy and hold"]),
        "time_in_market": float(position.mean() * 100),
        "entries": int((position.diff() > 0).sum() + (position.iloc[0] > 0)),
        "risk_off_days": risk_off_days,
    }
    return {"table": table, "curves": curves, "summary": summary, "views": views, "stats": stats.stats_table(curves)}


def past_dates(symbol: str, count: int, horizon: int, spacing: int = 21) -> list[str]:
    df = market.load_prices(symbol, "2y")
    idx = df.index
    last_judgeable = len(idx) - 1 - horizon
    picks = [idx[last_judgeable - i * spacing] for i in range(count) if last_judgeable - i * spacing >= 260]
    return [d.strftime("%Y-%m-%d") for d in sorted(picks)]
