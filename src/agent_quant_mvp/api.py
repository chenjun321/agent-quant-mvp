from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .backtest import run_backtest
from .data import load_market_bars

app = FastAPI(title="Crypto AI Trading Agent Paper MVP", version="0.2.0")


class PaperRunRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", examples=["BTCUSDT"])
    interval: str = Field(default="1h", examples=["1h"])
    limit: int = Field(default=240, ge=80, le=1000)
    lookback: int = Field(default=60, ge=30, le=240)
    start_equity: float = Field(default=10_000.0, gt=0)
    source: str = Field(default="mock", pattern="^(mock|binance)$")
    max_drawdown_pct: float | None = Field(default=12.0, gt=0, le=100)
    max_loss_pct: float | None = Field(default=8.0, gt=0, le=100)
    flatten_on_halt: bool = True


def _compact_result(result) -> dict:
    payload = asdict(result)
    payload["equity_curve"] = payload["equity_curve"][-50:]
    payload["traces"] = payload["traces"][-10:]
    payload["fills"] = payload["fills"][-20:]
    payload["rejected_orders"] = payload["rejected_orders"][-20:]
    return payload


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "paper-trading"}


@app.get("/market/klines")
def market_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 120, source: str = "mock") -> dict:
    bars = load_market_bars(symbol=symbol, interval=interval, limit=limit, source=source)
    actual_source = bars[-1].source if bars else "unknown"
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "requested_source": source,
        "actual_source": actual_source,
        "fallback_used": source != actual_source,
        "count": len(bars),
        "bars": [asdict(bar) for bar in bars[-20:]],
    }


@app.post("/paper/run")
def paper_run(request: PaperRunRequest) -> dict:
    result = run_backtest(
        symbol=request.symbol,
        interval=request.interval,
        limit=request.limit,
        lookback=request.lookback,
        start_equity=request.start_equity,
        source=request.source,
        max_drawdown_pct=request.max_drawdown_pct,
        max_loss_pct=request.max_loss_pct,
        flatten_on_halt=request.flatten_on_halt,
    )
    return _compact_result(result)


@app.get("/demo/backtest")
def demo_backtest(symbol: str = "BTCUSDT", source: str = "mock") -> dict:
    result = run_backtest(symbol=symbol, source=source)
    return _compact_result(result)
