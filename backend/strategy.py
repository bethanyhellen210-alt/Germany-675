from dataclasses import dataclass

@dataclass
class TradeSignal:
    side: str          # "BUY" or "SELL"
    sl_distance: float
    tp_distance: float
    reason: str

def ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1.0)
    result = [sum(values[:period]) / period]
    for price in values[period:]:
        result.append(price * k + result[-1] * (1.0 - k))
    return result

def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    val = sum(trs[:period]) / period
    for tr in trs[period:]:
        val = (val * (period - 1) + tr) / period
    return val

def evaluate_trend_rsi_atr(
    rates,
    sl_atr_mult: float = 1.5,
    rr_ratio: float = 2.0,
) -> TradeSignal | None:
    if rates is None or len(rates) < 225:
        return None

    closed = rates[:-1]
    highs = [float(r["high"]) for r in closed]
    lows = [float(r["low"]) for r in closed]
    closes = [float(r["close"]) for r in closed]

    ema200_series = ema(closes, 200)
    curr_rsi = rsi(closes, 14)
    prev_rsi = rsi(closes[:-1], 14)
    curr_atr = atr(highs, lows, closes, 14)

    if not ema200_series or curr_rsi is None or prev_rsi is None or curr_atr is None or curr_atr <= 0:
        return None

    last_close = closes[-1]
    last_ema200 = ema200_series[-1]
    sl_dist = curr_atr * sl_atr_mult
    tp_dist = sl_dist * rr_ratio

    if last_close > last_ema200 and prev_rsi < 30.0 and curr_rsi >= 30.0:
        return TradeSignal(
            side="BUY",
            sl_distance=sl_dist,
            tp_distance=tp_dist,
            reason=f"Uptrend (close>EMA200) + RSI rebound ({prev_rsi:.1f}->{curr_rsi:.1f})",
        )

    if last_close < last_ema200 and prev_rsi > 70.0 and curr_rsi <= 70.0:
        return TradeSignal(
            side="SELL",
            sl_distance=sl_dist,
            tp_distance=tp_dist,
            reason=f"Downtrend (close<EMA200) + RSI rejection ({prev_rsi:.1f}->{curr_rsi:.1f})",
        )

    return None