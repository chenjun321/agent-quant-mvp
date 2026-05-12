from __future__ import annotations

from .models import BacktestResult, BacktestStats, MarketBar, Trade
from .paper import PaperBroker
from .workflow import AgentWorkflow


def compute_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak else 0.0
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


class PaperTradingEngine:
    def __init__(
        self,
        workflow: AgentWorkflow | None = None,
        broker: PaperBroker | None = None,
        lookback: int = 60,
        max_drawdown_pct: float | None = 12.0,
        max_loss_pct: float | None = 8.0,
        flatten_on_halt: bool = True,
    ) -> None:
        self.workflow = workflow or AgentWorkflow()
        self.broker = broker or PaperBroker()
        self.lookback = lookback
        self.max_drawdown_pct = max_drawdown_pct
        self.max_loss_pct = max_loss_pct
        self.flatten_on_halt = flatten_on_halt

    def run(self, symbol: str, bars: list[MarketBar], requested_source: str | None = None) -> BacktestResult:
        if len(bars) <= self.lookback:
            raise ValueError("not enough bars for the configured lookback")

        start_equity = self.broker.account_snapshot(bars[self.lookback - 1]).equity
        equity_curve = [start_equity]
        trades: list[Trade] = []
        traces = []
        peak_equity = start_equity
        halt_reason: str | None = None
        halted_at = None
        skipped_steps = 0
        forced_liquidations = 0

        for idx in range(self.lookback, len(bars)):
            bar = bars[idx]
            account = self.broker.account_snapshot(bar)
            peak_equity = max(peak_equity, account.equity)

            if halt_reason:
                skipped_steps += 1
                equity_curve.append(account.equity)
                continue

            halt_reason = self._session_halt_reason(
                equity=account.equity,
                start_equity=start_equity,
                peak_equity=peak_equity,
            )
            if halt_reason:
                halted_at = bar.ts
                forced_fill = self.broker.flatten_all(bar, reason=halt_reason) if self.flatten_on_halt else None
                if forced_fill:
                    forced_liquidations += 1
                    trades.append(
                        Trade(
                            ts=forced_fill.ts,
                            symbol=forced_fill.symbol,
                            side="flat",
                            price=forced_fill.price,
                            position_pct=0.0,
                            equity_after_trade=forced_fill.equity_after,
                        )
                    )
                equity_curve.append(self.broker.account_snapshot(bar).equity)
                continue

            trace = self.workflow.step(symbol=symbol, window=bars[idx - self.lookback + 1 : idx + 1], account=account)
            traces.append(trace)

            fill = self.broker.execute(trace.plan, trace.risk, bar)
            if fill:
                side = "long" if fill.action == "buy" else "flat"
                trades.append(
                    Trade(
                        ts=fill.ts,
                        symbol=fill.symbol,
                        side=side,
                        price=fill.price,
                        position_pct=trace.risk.adjusted_quote_amount_pct,
                        equity_after_trade=fill.equity_after,
                    )
                )

            equity_curve.append(self.broker.account_snapshot(bar).equity)

        end_equity = equity_curve[-1]
        total_fees = sum(fill.fee for fill in self.broker.fills)
        wins = 0
        closed_sells = [fill for fill in self.broker.fills if fill.action == "sell"]
        # In this platform, win rate is intentionally conservative and only counts
        # completed sell events as closed trades.
        for fill in closed_sells:
            previous_buy = next((item for item in reversed(self.broker.fills) if item.ts <= fill.ts and item.action == "buy"), None)
            if previous_buy and fill.price > previous_buy.price:
                wins += 1
        win_rate = wins / len(closed_sells) if closed_sells else 0.0

        return BacktestResult(
            symbol=symbol.upper(),
            data_source=bars[0].source if bars else "unknown",
            start_equity=round(start_equity, 6),
            end_equity=round(end_equity, 6),
            stats=BacktestStats(
                total_return_pct=round(((end_equity / start_equity) - 1) * 100, 4),
                max_drawdown_pct=round(compute_drawdown(equity_curve) * 100, 4),
                win_rate_pct=round(win_rate * 100, 2),
                total_trades=len(trades),
                total_fees=round(total_fees, 6),
                rejected_orders=len(self.broker.rejected_orders),
                skipped_steps=skipped_steps,
                forced_liquidations=forced_liquidations,
            ),
            requested_source=requested_source or (bars[0].source if bars else "unknown"),
            halt_reason=halt_reason,
            halted_at=halted_at,
            equity_curve=[round(value, 6) for value in equity_curve],
            trades=trades,
            traces=traces,
            fills=self.broker.fills,
            rejected_orders=self.broker.rejected_orders,
        )

    def _session_halt_reason(self, equity: float, start_equity: float, peak_equity: float) -> str | None:
        if self.max_loss_pct is not None and start_equity > 0:
            loss_pct = ((start_equity - equity) / start_equity) * 100
            if loss_pct >= self.max_loss_pct:
                return f"session loss limit breached: {loss_pct:.2f}% >= {self.max_loss_pct:.2f}%"

        if self.max_drawdown_pct is not None and peak_equity > 0:
            drawdown_pct = ((peak_equity - equity) / peak_equity) * 100
            if drawdown_pct >= self.max_drawdown_pct:
                return f"session drawdown limit breached: {drawdown_pct:.2f}% >= {self.max_drawdown_pct:.2f}%"

        return None
