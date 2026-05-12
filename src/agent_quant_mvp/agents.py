from __future__ import annotations

from .backends import (
    AgentContext,
    RuleBasedResearchBackend,
    RuleBasedStrategyBackend,
)
from .knowledge import InMemoryKnowledgeBase, default_market_knowledge_base
from .models import (
    MarketSnapshot,
    PortfolioDecision,
    ResearchView,
    RiskDecision,
    StrategyPlan,
)
from .tools import AgentTool, DEFAULT_AGENT_TOOLS


class MarketAnalystAgent:
    """Interprets market state with pluggable backends, tools, and knowledge."""

    def __init__(
        self,
        backend: RuleBasedResearchBackend | None = None,
        tools: tuple[AgentTool, ...] = DEFAULT_AGENT_TOOLS,
        knowledge_base: InMemoryKnowledgeBase | None = None,
    ) -> None:
        self.backend = backend or RuleBasedResearchBackend()
        self.tools = tools
        self.knowledge_base = knowledge_base or default_market_knowledge_base()

    def analyze(self, snapshot: MarketSnapshot) -> ResearchView:
        context = self._build_context(snapshot=snapshot)
        return self.backend.generate(snapshot, context)

    def _build_context(self, snapshot: MarketSnapshot) -> AgentContext:
        tool_observations: list[str] = []
        for tool in self.tools:
            tool_observations.extend(tool.run(snapshot))
        knowledge_notes = self.knowledge_base.search(symbol=snapshot.symbol, query="", limit=2)
        return AgentContext(tool_observations=tool_observations, knowledge_notes=knowledge_notes)


class StrategyPlannerAgent:
    def __init__(
        self,
        backend: RuleBasedStrategyBackend | None = None,
        tools: tuple[AgentTool, ...] = DEFAULT_AGENT_TOOLS,
        knowledge_base: InMemoryKnowledgeBase | None = None,
    ) -> None:
        self.backend = backend or RuleBasedStrategyBackend()
        self.tools = tools
        self.knowledge_base = knowledge_base or default_market_knowledge_base()

    def plan(self, snapshot: MarketSnapshot, research: ResearchView) -> StrategyPlan:
        context = self._build_context(snapshot=snapshot)
        return self.backend.generate(snapshot, research, context)

    def _build_context(self, snapshot: MarketSnapshot) -> AgentContext:
        tool_observations: list[str] = []
        for tool in self.tools:
            tool_observations.extend(tool.run(snapshot))
        knowledge_notes = self.knowledge_base.search(symbol=snapshot.symbol, query="", limit=2)
        return AgentContext(tool_observations=tool_observations, knowledge_notes=knowledge_notes)


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
