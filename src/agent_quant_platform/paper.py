from __future__ import annotations

from .models import AccountSnapshot, Fill, MarketBar, Order, RiskDecision, StrategyPlan


def base_asset_from_symbol(symbol: str, quote_asset: str = "USDT") -> str:
    if symbol.endswith(quote_asset):
        return symbol[: -len(quote_asset)]
    return symbol


class PaperBroker:
    def __init__(
        self,
        initial_cash: float = 10_000.0,
        quote_asset: str = "USDT",
        fee_bps: float = 10.0,
        slippage_bps: float = 2.0,
    ) -> None:
        self.quote_asset = quote_asset
        self.cash = initial_cash
        self.positions: dict[str, float] = {}
        self.realized_pnl = 0.0
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.fills: list[Fill] = []
        self.rejected_orders: list[Order] = []

    def account_snapshot(self, bar: MarketBar) -> AccountSnapshot:
        base_asset = base_asset_from_symbol(bar.symbol, self.quote_asset)
        base_qty = self.positions.get(base_asset, 0.0)
        base_value = base_qty * bar.close
        equity = self.cash + base_value
        exposure_pct = base_value / equity if equity else 0.0
        return AccountSnapshot(
            ts=bar.ts,
            quote_asset=self.quote_asset,
            cash=round(self.cash, 6),
            positions={asset: round(qty, 10) for asset, qty in self.positions.items() if qty > 0},
            prices={bar.symbol: bar.close},
            equity=round(equity, 6),
            exposure_pct=round(exposure_pct, 6),
            realized_pnl=round(self.realized_pnl, 6),
        )

    def execute(self, plan: StrategyPlan | None, risk: RiskDecision, bar: MarketBar) -> Fill | None:
        if plan is None or plan.action == "hold":
            return None

        if not risk.approved:
            self.rejected_orders.append(
                Order(
                    ts=bar.ts,
                    symbol=bar.symbol,
                    action=plan.action,
                    requested_quote_amount=0.0,
                    status="rejected",
                    reason=risk.reason,
                )
            )
            return None

        base_asset = base_asset_from_symbol(bar.symbol, self.quote_asset)
        account = self.account_snapshot(bar)
        fee_rate = self.fee_bps / 10_000
        slippage_rate = self.slippage_bps / 10_000

        if plan.action == "buy":
            requested_quote = min(account.equity * risk.adjusted_quote_amount_pct, self.cash)
            if requested_quote <= 0:
                self.rejected_orders.append(
                    Order(bar.ts, bar.symbol, plan.action, requested_quote, "rejected", "cash is not available")
                )
                return None

            fill_price = bar.close * (1 + slippage_rate)
            fee = requested_quote * fee_rate
            net_quote = requested_quote - fee
            base_qty = net_quote / fill_price
            self.cash -= requested_quote
            self.positions[base_asset] = self.positions.get(base_asset, 0.0) + base_qty

            fill = Fill(
                ts=bar.ts,
                symbol=bar.symbol,
                action="buy",
                price=round(fill_price, 6),
                base_qty=round(base_qty, 10),
                quote_qty=round(requested_quote, 6),
                fee=round(fee, 6),
                cash_after=round(self.cash, 6),
                base_after=round(self.positions[base_asset], 10),
                equity_after=self.account_snapshot(bar).equity,
                reason="strategy order",
            )
            self.fills.append(fill)
            return fill

        base_qty = self.positions.get(base_asset, 0.0)
        if base_qty <= 0:
            self.rejected_orders.append(
                Order(bar.ts, bar.symbol, plan.action, 0.0, "rejected", "base inventory is not available")
            )
            return None

        sell_qty = base_qty if plan.quote_amount_pct >= 1 else base_qty * plan.quote_amount_pct
        return self._sell_base_qty(bar=bar, base_asset=base_asset, sell_qty=sell_qty, reason="strategy order")

    def flatten_all(self, bar: MarketBar, reason: str) -> Fill | None:
        base_asset = base_asset_from_symbol(bar.symbol, self.quote_asset)
        base_qty = self.positions.get(base_asset, 0.0)
        if base_qty <= 0:
            return None
        return self._sell_base_qty(bar=bar, base_asset=base_asset, sell_qty=base_qty, reason=reason)

    def _sell_base_qty(self, bar: MarketBar, base_asset: str, sell_qty: float, reason: str) -> Fill:
        base_qty = self.positions.get(base_asset, 0.0)
        fee_rate = self.fee_bps / 10_000
        slippage_rate = self.slippage_bps / 10_000
        fill_price = bar.close * (1 - slippage_rate)
        gross_quote = sell_qty * fill_price
        fee = gross_quote * fee_rate
        net_quote = gross_quote - fee
        self.cash += net_quote
        self.positions[base_asset] = max(base_qty - sell_qty, 0.0)

        fill = Fill(
            ts=bar.ts,
            symbol=bar.symbol,
            action="sell",
            price=round(fill_price, 6),
            base_qty=round(sell_qty, 10),
            quote_qty=round(gross_quote, 6),
            fee=round(fee, 6),
            cash_after=round(self.cash, 6),
            base_after=round(self.positions[base_asset], 10),
            equity_after=self.account_snapshot(bar).equity,
            reason=reason,
        )
        self.fills.append(fill)
        return fill
