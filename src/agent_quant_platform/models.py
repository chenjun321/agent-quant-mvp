from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


Action = Literal["buy", "sell", "hold"]
OrderStatus = Literal["filled", "rejected", "skipped"]
Regime = Literal["trend_up", "trend_down", "range", "high_volatility"]
Side = Literal["long", "short", "flat"]


@dataclass
class MarketBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    source: str = "mock"


@dataclass
class FactorSnapshot:
    momentum_5: float
    momentum_20: float
    volatility_10: float
    ma_gap_10: float
    rsi_14: float
    ema_fast: float
    ema_slow: float
    macd: float
    atr_14: float
    volume_zscore: float
    trend_score: float


@dataclass
class AccountSnapshot:
    ts: datetime
    quote_asset: str
    cash: float
    positions: dict[str, float]
    prices: dict[str, float]
    equity: float
    exposure_pct: float
    realized_pnl: float = 0.0


@dataclass
class MarketSnapshot:
    symbol: str
    interval: str
    latest_bar: MarketBar
    factors: FactorSnapshot
    account: AccountSnapshot | None = None


@dataclass
class ResearchView:
    regime: Regime
    side_bias: Side
    confidence: float
    thesis: str
    observations: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)


@dataclass
class StrategyPlan:
    action: Action
    quote_amount_pct: float
    confidence: float
    rationale: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    max_holding_bars: int = 24
    evidence: list[str] = field(default_factory=list)


@dataclass
class RiskDecision:
    approved: bool
    max_position_pct: float
    reason: str
    adjusted_quote_amount_pct: float = 0.0
    violations: list[str] = field(default_factory=list)


@dataclass
class PortfolioDecision:
    target_side: Side
    target_position_pct: float
    reason: str


@dataclass
class AgentTrace:
    ts: datetime
    symbol: str
    close: float
    factors: FactorSnapshot
    research: ResearchView
    risk: RiskDecision
    portfolio: PortfolioDecision
    plan: StrategyPlan | None = None
    account: AccountSnapshot | None = None


@dataclass
class Order:
    ts: datetime
    symbol: str
    action: Action
    requested_quote_amount: float
    status: OrderStatus
    reason: str


@dataclass
class Fill:
    ts: datetime
    symbol: str
    action: Action
    price: float
    base_qty: float
    quote_qty: float
    fee: float
    cash_after: float
    base_after: float
    equity_after: float
    reason: str = ""


@dataclass
class Trade:
    ts: datetime
    symbol: str
    side: Side
    price: float
    position_pct: float
    equity_after_trade: float


@dataclass
class BacktestStats:
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    total_fees: float = 0.0
    rejected_orders: int = 0
    skipped_steps: int = 0
    forced_liquidations: int = 0


@dataclass
class BacktestResult:
    symbol: str
    data_source: str
    start_equity: float
    end_equity: float
    stats: BacktestStats
    requested_source: str = "mock"
    halt_reason: str | None = None
    halted_at: datetime | None = None
    equity_curve: list[float] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    traces: list[AgentTrace] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    rejected_orders: list[Order] = field(default_factory=list)
