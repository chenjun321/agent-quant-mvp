from __future__ import annotations

from .models import FactorSnapshot, MarketBar


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    avg = _mean(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return variance**0.5


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = value * alpha + ema * (1 - alpha)
    return ema


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0

    gains: list[float] = []
    losses: list[float] = []
    for idx in range(-period, 0):
        change = closes[idx] - closes[idx - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))

    avg_gain = _mean(gains)
    avg_loss = _mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(bars: list[MarketBar], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0

    true_ranges: list[float] = []
    for idx in range(1, len(bars)):
        current = bars[idx]
        previous = bars[idx - 1]
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return _mean(true_ranges[-period:])


def compute_factors(window: list[MarketBar]) -> FactorSnapshot:
    if len(window) < 2:
        raise ValueError("at least two market bars are required")

    closes = [bar.close for bar in window]
    volumes = [bar.volume for bar in window]
    latest = closes[-1]
    momentum_5 = (latest / closes[-5]) - 1 if len(closes) >= 5 else 0.0
    momentum_20 = (latest / closes[-20]) - 1 if len(closes) >= 20 else (latest / closes[0]) - 1

    returns = [(closes[idx] / closes[idx - 1]) - 1 for idx in range(1, len(closes))]
    volatility_10 = _std(returns[-10:]) if len(returns) >= 10 else _std(returns)

    ma_10 = _mean(closes[-10:]) if len(closes) >= 10 else _mean(closes)
    ma_gap_10 = (latest / ma_10) - 1 if ma_10 else 0.0
    ema_fast = _ema(closes[-30:], 12)
    ema_slow = _ema(closes[-60:], 26)
    macd = ema_fast - ema_slow

    volume_window = volumes[-20:] if len(volumes) >= 20 else volumes
    volume_std = _std(volume_window) if len(volume_window) > 1 else 0.0
    volume_zscore = ((volumes[-1] - _mean(volume_window)) / volume_std) if volume_std else 0.0

    trend_score = 0.0
    trend_score += 1.0 if momentum_20 > 0 else -1.0 if momentum_20 < 0 else 0.0
    trend_score += 1.0 if ma_gap_10 > 0 else -1.0 if ma_gap_10 < 0 else 0.0
    trend_score += 1.0 if macd > 0 else -1.0 if macd < 0 else 0.0
    trend_score /= 3

    return FactorSnapshot(
        momentum_5=round(momentum_5, 6),
        momentum_20=round(momentum_20, 6),
        volatility_10=round(volatility_10, 6),
        ma_gap_10=round(ma_gap_10, 6),
        rsi_14=round(_rsi(closes), 4),
        ema_fast=round(ema_fast, 4),
        ema_slow=round(ema_slow, 4),
        macd=round(macd, 6),
        atr_14=round(_atr(window), 4),
        volume_zscore=round(volume_zscore, 4),
        trend_score=round(trend_score, 4),
    )

