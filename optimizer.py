import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize

import stats
import track

METHODS = {
    "Equal weight": "Same amount in every stock. Simple and hard to beat.",
    "Lowest risk": "Mix with the smallest expected ups and downs (minimum variance).",
    "Best return per risk": "Mix with the highest past return per unit of risk (maximum Sharpe). Most sensitive to "
                            "the past, so treat with care.",
    "Equal risk": "Each stock contributes the same amount of risk (risk parity), so calmer stocks get more money.",
}
COV_SHRINK = 0.3
RETURN_SHRINK = 0.5


def load_returns(symbols: list[str], years: int) -> tuple[pd.DataFrame, pd.Series]:
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years) - pd.Timedelta(days=10)
    raw = yf.download([*symbols, track.BENCHMARK], start=start.strftime("%Y-%m-%d"), interval="1d",
                      group_by="ticker", threads=True, progress=False, auto_adjust=True)
    closes = {s: raw[s]["Close"] for s in [*symbols, track.BENCHMARK] if s in raw.columns.get_level_values(0)}
    px = pd.DataFrame(closes)
    if px.index.tz is not None:
        px.index = px.index.tz_localize(None)
    bench = px.pop(track.BENCHMARK).dropna() if track.BENCHMARK in px else pd.Series(dtype=float)
    px = px.dropna(axis=1, thresh=int(len(px) * 0.8)).ffill().dropna()
    return px.pct_change().dropna(), bench


def _cov(returns: pd.DataFrame) -> np.ndarray:
    cov = returns.cov().to_numpy() * stats.TRADING_DAYS
    return (1 - COV_SHRINK) * cov + COV_SHRINK * np.diag(np.diag(cov))


def _mu(returns: pd.DataFrame) -> np.ndarray:
    mu = returns.mean().to_numpy() * stats.TRADING_DAYS
    return (1 - RETURN_SHRINK) * mu + RETURN_SHRINK * mu.mean()


def weights(returns: pd.DataFrame, method: str, max_weight: float = 0.3, risk_free: float = stats.RISK_FREE) -> pd.Series:
    n = returns.shape[1]
    cap = max(max_weight, 1 / n)
    if method == "Equal weight" or n == 1:
        return pd.Series(1 / n, index=returns.columns)
    cov, mu = _cov(returns), _mu(returns)
    start = np.full(n, 1 / n)
    bounds = [(0, cap)] * n
    budget = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    if method == "Lowest risk":
        target = lambda w: w @ cov @ w
    elif method == "Best return per risk":
        target = lambda w: -(w @ mu - risk_free) / np.sqrt(w @ cov @ w)
    else:
        def target(w):
            contribution = w * (cov @ w)
            return ((contribution - contribution.mean()) ** 2).sum() * 1e4
    result = minimize(target, start, method="SLSQP", bounds=bounds, constraints=budget,
                      options={"maxiter": 500, "ftol": 1e-10})
    w = np.clip(result.x if result.success else start, 0, None)
    return pd.Series(w / w.sum(), index=returns.columns)


def profile(returns: pd.DataFrame, w: pd.Series) -> dict:
    cov = returns.cov().to_numpy() * stats.TRADING_DAYS
    mu = returns.mean().to_numpy() * stats.TRADING_DAYS
    vol = float(np.sqrt(w.to_numpy() @ cov @ w.to_numpy()))
    ret = float(w.to_numpy() @ mu)
    return {"return": ret * 100, "volatility": vol * 100,
            "sharpe": (ret - stats.RISK_FREE) / vol if vol else float("nan")}


def curve(returns: pd.DataFrame, w: pd.Series, rebalance: int = 21) -> pd.Series:
    values, holding = [1.0], w.copy()
    for i, (_, day) in enumerate(returns.iterrows()):
        if i % rebalance == 0:
            holding = w * values[-1]
        holding = holding * (1 + day)
        values.append(float(holding.sum()))
    return pd.Series(values[1:], index=returns.index)


def walk_forward(returns: pd.DataFrame, bench: pd.Series, method: str, max_weight: float, train_share: float = 0.67):
    split = int(len(returns) * train_share)
    train, test = returns.iloc[:split], returns.iloc[split:]
    if len(train) < 120 or len(test) < 40:
        return None
    w = weights(train, method, max_weight)
    curves = pd.DataFrame({
        f"{method} (fitted on earlier data)": curve(test, w),
        "Equal weight": curve(test, weights(train, "Equal weight")),
    })
    b = bench.reindex(test.index).ffill()
    curves["NIFTY 50"] = b / b.iloc[0]
    curves = curves * 100
    return {"train": (train.index[0], train.index[-1]), "test": (test.index[0], test.index[-1]),
            "curves": curves, "stats": stats.stats_table(curves)}


def allocate(w: pd.Series, capital: float, prices: dict) -> pd.DataFrame:
    rows = []
    for symbol, weight in w.sort_values(ascending=False).items():
        price = prices.get(symbol)
        shares = int(capital * weight // price) if price and capital else 0
        rows.append({"Stock": symbol, "Weight": weight * 100, "Amount (₹)": capital * weight if capital else None,
                     "Price (₹)": price, "Shares": shares, "Invested (₹)": shares * price if price else None})
    return pd.DataFrame(rows)
