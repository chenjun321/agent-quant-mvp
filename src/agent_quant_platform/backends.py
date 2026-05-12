from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .knowledge import KnowledgeNote
from .models import MarketSnapshot, ResearchView, StrategyPlan


@dataclass
class AgentContext:
    tool_observations: list[str] = field(default_factory=list)
    knowledge_notes: list[KnowledgeNote] = field(default_factory=list)

    def knowledge_observations(self) -> list[str]:
        observations: list[str] = []
        for note in self.knowledge_notes:
            observations.append(f"Knowledge note: {note.title}")
        return observations

    def combined_observations(self) -> list[str]:
        return self.tool_observations + self.knowledge_observations()


class StructuredModelProvider(Protocol):
    name: str

    def generate_json(self, task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class StaticStructuredModelProvider:
    def __init__(self, responses: dict[str, Any], name: str = "static_provider") -> None:
        self.responses = responses
        self.name = name

    def generate_json(self, task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.responses[task_name]
        if callable(response):
            return response(payload)
        return response


class RuleBasedResearchBackend:
    def generate(self, snapshot: MarketSnapshot, context: AgentContext) -> ResearchView:
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

        observations.extend(context.knowledge_observations()[:1])
        observations.extend(context.tool_observations[:2])

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


class RuleBasedStrategyBackend:
    def generate(self, snapshot: MarketSnapshot, research: ResearchView, context: AgentContext) -> StrategyPlan:
        price = snapshot.latest_bar.close
        atr = snapshot.factors.atr_14
        evidence = research.observations + research.risk_factors + context.knowledge_observations()[:1] + context.tool_observations[:2]

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
                evidence=evidence,
            )

        if research.regime == "trend_down" and snapshot.account and snapshot.account.exposure_pct > 0:
            return StrategyPlan(
                action="sell",
                quote_amount_pct=1.0,
                confidence=research.confidence,
                rationale="Reduce spot exposure because downside trend evidence is strong.",
                entry_price=price,
                evidence=evidence,
            )

        if research.regime == "trend_down":
            return StrategyPlan(
                action="hold",
                quote_amount_pct=0.0,
                confidence=research.confidence,
                rationale="Hold because spot inventory is empty and spot mode does not open short positions.",
                entry_price=price,
                evidence=evidence,
            )

        return StrategyPlan(
            action="hold",
            quote_amount_pct=0.0,
            confidence=research.confidence,
            rationale="Hold because the agent does not have enough directional edge.",
            entry_price=price,
            evidence=evidence,
        )


class ProviderBackedResearchBackend:
    def __init__(
        self,
        provider: StructuredModelProvider,
        fallback: RuleBasedResearchBackend | None = None,
    ) -> None:
        self.provider = provider
        self.fallback = fallback or RuleBasedResearchBackend()

    def generate(self, snapshot: MarketSnapshot, context: AgentContext) -> ResearchView:
        payload = {
            "symbol": snapshot.symbol,
            "interval": snapshot.interval,
            "close": snapshot.latest_bar.close,
            "factors": snapshot.factors.__dict__,
            "tool_observations": context.tool_observations,
            "knowledge_notes": [note.title for note in context.knowledge_notes],
        }
        try:
            raw = self.provider.generate_json("market_analysis", payload)
            return ResearchView(
                regime=raw["regime"],
                side_bias=raw["side_bias"],
                confidence=float(raw["confidence"]),
                thesis=raw["thesis"],
                observations=list(raw.get("observations", [])),
                risk_factors=list(raw.get("risk_factors", [])),
            )
        except Exception:
            return self.fallback.generate(snapshot, context)


class ProviderBackedStrategyBackend:
    def __init__(
        self,
        provider: StructuredModelProvider,
        fallback: RuleBasedStrategyBackend | None = None,
    ) -> None:
        self.provider = provider
        self.fallback = fallback or RuleBasedStrategyBackend()

    def generate(self, snapshot: MarketSnapshot, research: ResearchView, context: AgentContext) -> StrategyPlan:
        payload = {
            "symbol": snapshot.symbol,
            "interval": snapshot.interval,
            "close": snapshot.latest_bar.close,
            "factors": snapshot.factors.__dict__,
            "research": research.__dict__,
            "tool_observations": context.tool_observations,
            "knowledge_notes": [note.title for note in context.knowledge_notes],
        }
        try:
            raw = self.provider.generate_json("strategy_plan", payload)
            return StrategyPlan(
                action=raw["action"],
                quote_amount_pct=float(raw["quote_amount_pct"]),
                confidence=float(raw["confidence"]),
                rationale=raw["rationale"],
                entry_price=raw.get("entry_price"),
                stop_loss=raw.get("stop_loss"),
                take_profit=raw.get("take_profit"),
                max_holding_bars=int(raw.get("max_holding_bars", 24)),
                evidence=list(raw.get("evidence", [])),
            )
        except Exception:
            return self.fallback.generate(snapshot, research, context)
