from __future__ import annotations

from .data import load_market_bars
from .models import BacktestResult
from .paper import PaperBroker
from .runner import PaperTradingEngine


def run_backtest(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 240,
    lookback: int = 60,
    start_equity: float = 10_000.0,
    source: str = "mock",
    max_drawdown_pct: float | None = 12.0,
    max_loss_pct: float | None = 8.0,
    flatten_on_halt: bool = True,
) -> BacktestResult:
    bars = load_market_bars(symbol=symbol, interval=interval, limit=limit, source=source)
    engine = PaperTradingEngine(
        broker=PaperBroker(initial_cash=start_equity),
        lookback=lookback,
        max_drawdown_pct=max_drawdown_pct,
        max_loss_pct=max_loss_pct,
        flatten_on_halt=flatten_on_halt,
    )
    return engine.run(symbol=symbol, bars=bars, requested_source=source)
