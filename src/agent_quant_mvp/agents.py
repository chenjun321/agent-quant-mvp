from __future__ import annotations

from .models import (
    AccountSnapshot,
    FactorSnapshot,
    MarketSnapshot,
    PortfolioDecision,
    ResearchView,
    RiskDecision,
    StrategyPlan,
)


class MarketAnalystAgent:
    """Interprets market state from deterministic indicators.

    The class is rule-based now so the system is testable and safe. It is shaped
    like an LLM agent: structured input, structured output, thesis, evidence,
    and risk factors.
    """

    def analyze(self, snapshot: MarketSnapshot) -> ResearchView:
        factors = snapshot.factors
        observations: list[str] = []
        risk_factors: list[str] = []

        if factors.momentum_20 > 0:
            observations.append("20-bar momentum is positive.")
        else:
            observations.append("20-bar momentum is negative or flat.")

        if factors.rsi_14 >= 70:
            risk_factors.append("RSI is overheated.")
        elif factors.rsi_14 <= 30:
            observations.append("RSI is near oversold territory.")

        if factors.volume_zscore > 1.5:
            observations.append("Latest volume is materially above its recent baseline.")

        if factors.volatility_10 > 0.035:
            return ResearchView(
                regime="high_volatility",
                side_bias="flat",
                confidence=0.38,
                thesis="Realized volatility is elevated, so the system should avoid opening new spot exposure.",
                observations=observations,
                risk_factors=risk_factors + ["Volatility filter is active."],
            )

        if factors.trend_score >= 0.65 and factors.rsi_14 < 95:
            return ResearchView(
                regime="trend_up",
                side_bias="long",
                confidence=0.76,
                thesis="Trend, moving-average position, and MACD are aligned to the upside.",
                observations=observations,
                risk_factors=risk_factors,
            )

        if factors.trend_score <= -0.65:
            return ResearchView(
                regime="trend_down",
                side_bias="flat",
                confidence=0.73,
                thesis="Downside trend evidence is strong; spot mode should avoid long exposure.",
                observations=observations,
                risk_factors=risk_factors + ["Spot mode cannot express a short without derivatives."],
            )

        return ResearchView(
            regime="range",
            side_bias="flat",
            confidence=0.48,
            thesis="Signals are mixed, suggesting a ranging market without a strong directional edge.",
            observations=observations,
            risk_factors=risk_factors,
        )


class StrategyPlannerAgent:
    def plan(self, snapshot: MarketSnapshot, research: ResearchView) -> StrategyPlan:
        price = snapshot.latest_bar.close
        atr = snapshot.factors.atr_14

        if research.side_bias == "long" and research.confidence >= 0.7:
            quote_pct = 0.2 if research.confidence < 0.8 else 0.3
            return StrategyPlan(
                action="buy",
                quote_amount_pct=quote_pct,
                confidence=research.confidence,
                rationale="Open spot exposure because trend evidence is aligned and volatility is acceptable.",
                entry_price=price,
                stop_loss=round(max(price - atr * 2, price * 0.96), 4),
                take_profit=round(price + atr * 3, 4),
                evidence=research.observations,
            )

        if research.regime == "trend_down" and snapshot.account and snapshot.account.exposure_pct > 0:
            return StrategyPlan(
                action="sell",
                quote_amount_pct=1.0,
                confidence=research.confidence,
                rationale="Reduce spot exposure because downside trend evidence is strong.",
                entry_price=price,
                evidence=research.observations + research.risk_factors,
            )

        if research.regime == "trend_down":
            return StrategyPlan(
                action="hold",
                quote_amount_pct=0.0,
                confidence=research.confidence,
                rationale="Hold because spot inventory is empty and spot mode does not open short positions.",
                entry_price=price,
                evidence=research.observations + research.risk_factors,
            )

        return StrategyPlan(
            action="hold",
            quote_amount_pct=0.0,
            confidence=research.confidence,
            rationale="Hold because the agent does not have enough directional edge.",
            entry_price=price,
            evidence=research.observations + research.risk_factors,
        )


class RiskManagerAgent:
    def __init__(
        self,
        max_position_pct: float = 0.6,
        max_order_pct: float = 0.25,
        min_confidence: float = 0.65,
        max_volatility: float = 0.04,
        max_rsi: float = 95.0,
    ) -> None:
        self.max_position_pct = max_position_pct
        self.max_order_pct = max_order_pct
        self.min_confidence = min_confidence
        self.max_volatility = max_volatility
        self.max_rsi = max_rsi

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        research: ResearchView,
        plan: StrategyPlan,
    ) -> RiskDecision:
        account = snapshot.account
        factors = snapshot.factors
        violations: list[str] = []

        if plan.action == "hold":
            return RiskDecision(
                approved=False,
                max_position_pct=self.max_position_pct,
                adjusted_quote_amount_pct=0.0,
                reason="No order is needed for a hold plan.",
            )

        if factors.volatility_10 > self.max_volatility:
            violations.append("realized volatility exceeds the configured cap")

        if plan.action == "buy" and factors.rsi_14 > self.max_rsi:
            violations.append("RSI is too extended for a new spot buy")

        if plan.action == "buy" and plan.confidence < self.min_confidence:
            violations.append("strategy confidence is below the minimum threshold")

        if plan.action == "buy" and account and account.exposure_pct >= self.max_position_pct:
            violations.append("current exposure already reached the maximum allocation")

        if plan.action == "sell" and account and account.exposure_pct <= 0:
            violations.append("no spot inventory is available to sell")

        if violations:
            return RiskDecision(
                approved=False,
                max_position_pct=self.max_position_pct,
                adjusted_quote_amount_pct=0.0,
                reason="Order blocked by deterministic risk rules.",
                violations=violations,
            )

        adjusted_pct = min(plan.quote_amount_pct, self.max_order_pct)
        if plan.action == "buy" and account:
            room = max(self.max_position_pct - account.exposure_pct, 0.0)
            adjusted_pct = min(adjusted_pct, room)

        if adjusted_pct <= 0:
            return RiskDecision(
                approved=False,
                max_position_pct=self.max_position_pct,
                adjusted_quote_amount_pct=0.0,
                reason="No allocation room remains after exposure checks.",
            )

        return RiskDecision(
            approved=True,
            max_position_pct=self.max_position_pct,
            adjusted_quote_amount_pct=round(adjusted_pct, 6),
            reason="Plan passed confidence, volatility, inventory, and exposure checks.",
        )


class PortfolioAgent:
    def decide(self, research: ResearchView, risk: RiskDecision, plan: StrategyPlan | None = None) -> PortfolioDecision:
        if not risk.approved:
            return PortfolioDecision(
                target_side="flat",
                target_position_pct=0.0,
                reason=risk.reason,
            )

        if plan and plan.action == "sell":
            return PortfolioDecision(
                target_side="flat",
                target_position_pct=0.0,
                reason="Approved sell plan reduces spot inventory.",
            )

        if plan and plan.action == "buy":
            return PortfolioDecision(
                target_side="long",
                target_position_pct=risk.adjusted_quote_amount_pct,
                reason="Approved buy plan opens risk-capped spot exposure.",
            )

        if research.side_bias == "long":
            return PortfolioDecision(
                target_side="long",
                target_position_pct=risk.adjusted_quote_amount_pct,
                reason="Long bias survives risk checks.",
            )

        return PortfolioDecision(
            target_side="flat",
            target_position_pct=0.0,
            reason="No directional position is opened after research and risk synthesis.",
        )


# Backwards-compatible aliases for the original MVP naming.
ResearchAgent = MarketAnalystAgent
RiskAgent = RiskManagerAgent
