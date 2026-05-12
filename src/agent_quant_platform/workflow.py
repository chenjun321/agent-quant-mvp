from __future__ import annotations

from datetime import datetime

from .agents import MarketAnalystAgent, PortfolioAgent, RiskManagerAgent, StrategyPlannerAgent
from .factors import compute_factors
from .models import AccountSnapshot, AgentTrace, MarketBar, MarketSnapshot


def empty_account(ts: datetime, quote_asset: str = "USDT", cash: float = 10_000.0) -> AccountSnapshot:
    return AccountSnapshot(
        ts=ts,
        quote_asset=quote_asset,
        cash=cash,
        positions={},
        prices={},
        equity=cash,
        exposure_pct=0.0,
    )


class AgentWorkflow:
    def __init__(
        self,
        market_agent: MarketAnalystAgent | None = None,
        strategy_agent: StrategyPlannerAgent | None = None,
        risk_agent: RiskManagerAgent | None = None,
        portfolio_agent: PortfolioAgent | None = None,
    ) -> None:
        self.market_agent = market_agent or MarketAnalystAgent()
        self.strategy_agent = strategy_agent or StrategyPlannerAgent()
        self.risk_agent = risk_agent or RiskManagerAgent()
        self.portfolio_agent = portfolio_agent or PortfolioAgent()

    def step(self, symbol: str, window: list[MarketBar], account: AccountSnapshot | None = None) -> AgentTrace:
        if not window:
            raise ValueError("window cannot be empty")

        latest = window[-1]
        factors = compute_factors(window)
        snapshot = MarketSnapshot(
            symbol=symbol.upper(),
            interval=latest.interval,
            latest_bar=latest,
            factors=factors,
            account=account or empty_account(latest.ts),
        )

        research = self.market_agent.analyze(snapshot)
        plan = self.strategy_agent.plan(snapshot, research)
        risk = self.risk_agent.evaluate(snapshot, research, plan)
        portfolio = self.portfolio_agent.decide(research, risk, plan)

        return AgentTrace(
            ts=latest.ts,
            symbol=symbol.upper(),
            close=latest.close,
            factors=factors,
            research=research,
            plan=plan,
            risk=risk,
            portfolio=portfolio,
            account=snapshot.account,
        )

