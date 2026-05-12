from __future__ import annotations

from typing import Protocol

from .models import MarketSnapshot


class AgentTool(Protocol):
    name: str

    def run(self, snapshot: MarketSnapshot) -> list[str]:
        ...


class TrendSignalTool:
    name = "trend_signal"

    def run(self, snapshot: MarketSnapshot) -> list[str]:
        trend_score = snapshot.factors.trend_score
        if trend_score >= 0.65:
            return [f"Tool trend_signal: trend score is strongly positive at {trend_score:.2f}."]
        if trend_score <= -0.65:
            return [f"Tool trend_signal: trend score is strongly negative at {trend_score:.2f}."]
        return [f"Tool trend_signal: trend score is mixed at {trend_score:.2f}."]


class VolatilityGuardTool:
    name = "volatility_guard"

    def run(self, snapshot: MarketSnapshot) -> list[str]:
        volatility = snapshot.factors.volatility_10
        if volatility > 0.035:
            return [f"Tool volatility_guard: realized volatility is elevated at {volatility:.4f}."]
        return [f"Tool volatility_guard: realized volatility remains contained at {volatility:.4f}."]


class AccountStateTool:
    name = "account_state"

    def run(self, snapshot: MarketSnapshot) -> list[str]:
        if snapshot.account is None:
            return []
        return [
            (
                "Tool account_state: equity="
                f"{snapshot.account.equity:.2f}, cash={snapshot.account.cash:.2f}, "
                f"exposure={snapshot.account.exposure_pct:.2%}."
            )
        ]


DEFAULT_AGENT_TOOLS: tuple[AgentTool, ...] = (
    TrendSignalTool(),
    VolatilityGuardTool(),
    AccountStateTool(),
)
