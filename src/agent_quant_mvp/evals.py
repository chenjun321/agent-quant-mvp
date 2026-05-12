from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import AccountSnapshot, AgentTrace, MarketBar
from .workflow import AgentWorkflow


@dataclass
class EvalExpectation:
    expected_regime: str | None = None
    expected_action: str | None = None
    expected_target_side: str | None = None
    risk_approved: bool | None = None
    min_confidence: float | None = None


@dataclass
class EvalCase:
    name: str
    symbol: str
    window: list[MarketBar]
    expectation: EvalExpectation
    description: str = ""
    account: AccountSnapshot | None = None


@dataclass
class EvalCheck:
    name: str
    passed: bool
    expected: str
    actual: str


@dataclass
class EvalResult:
    case_name: str
    passed: bool
    score: float
    checks: list[EvalCheck] = field(default_factory=list)
    trace: AgentTrace | None = None


def _make_bars(closes: list[float], symbol: str = "BTCUSDT", interval: str = "1h") -> list[MarketBar]:
    start = datetime(2025, 1, 1, 0, 0, 0)
    bars: list[MarketBar] = []
    previous_close = closes[0]
    for idx, close in enumerate(closes):
        open_price = previous_close if idx > 0 else close
        bars.append(
            MarketBar(
                ts=start + timedelta(hours=idx),
                open=round(open_price, 4),
                high=round(max(open_price, close) * 1.002, 4),
                low=round(min(open_price, close) * 0.998, 4),
                close=round(close, 4),
                volume=1000 + idx * 8,
                symbol=symbol,
                interval=interval,
                source="eval",
            )
        )
        previous_close = close
    return bars


def default_eval_cases() -> list[EvalCase]:
    uptrend: list[float] = []
    price = 100.0
    increments = [1.4, 1.1, -0.9, 1.2, 0.7, -0.4]
    for idx in range(70):
        price += increments[idx % len(increments)]
        uptrend.append(round(price, 4))
    high_vol = [100, 108, 95, 110, 92, 111, 91, 112, 90, 113] * 7
    downtrend = [160 - idx * 0.9 for idx in range(70)]

    latest_down_close = downtrend[-1]
    account = AccountSnapshot(
        ts=datetime(2025, 1, 3, 22, 0, 0),
        quote_asset="USDT",
        cash=5_000.0,
        positions={"BTC": 1.0},
        prices={"BTCUSDT": latest_down_close},
        equity=5_000.0 + latest_down_close,
        exposure_pct=latest_down_close / (5_000.0 + latest_down_close),
    )

    return [
        EvalCase(
            name="bullish_trend_buy",
            symbol="BTCUSDT",
            window=_make_bars(uptrend),
            expectation=EvalExpectation(
                expected_regime="trend_up",
                expected_action="buy",
                expected_target_side="long",
                risk_approved=True,
                min_confidence=0.7,
            ),
            description="A steady uptrend should produce a long-biased buy plan.",
        ),
        EvalCase(
            name="high_volatility_hold",
            symbol="BTCUSDT",
            window=_make_bars(high_vol),
            expectation=EvalExpectation(
                expected_regime="high_volatility",
                expected_action="hold",
                expected_target_side="flat",
                risk_approved=False,
            ),
            description="Highly unstable price action should block new exposure.",
        ),
        EvalCase(
            name="downtrend_exit_inventory",
            symbol="BTCUSDT",
            window=_make_bars(downtrend),
            expectation=EvalExpectation(
                expected_regime="trend_down",
                expected_action="sell",
                expected_target_side="flat",
                risk_approved=True,
                min_confidence=0.7,
            ),
            description="When inventory exists in a downtrend, the agent should reduce spot exposure.",
            account=account,
        ),
    ]


class WorkflowEvaluator:
    def __init__(self, workflow: AgentWorkflow | None = None) -> None:
        self.workflow = workflow or AgentWorkflow()

    def evaluate_case(self, case: EvalCase) -> EvalResult:
        trace = self.workflow.step(symbol=case.symbol, window=case.window, account=case.account)
        checks: list[EvalCheck] = []

        if case.expectation.expected_regime is not None:
            checks.append(
                EvalCheck(
                    name="regime",
                    passed=trace.research.regime == case.expectation.expected_regime,
                    expected=case.expectation.expected_regime,
                    actual=trace.research.regime,
                )
            )

        if case.expectation.expected_action is not None:
            checks.append(
                EvalCheck(
                    name="action",
                    passed=trace.plan is not None and trace.plan.action == case.expectation.expected_action,
                    expected=case.expectation.expected_action,
                    actual=trace.plan.action if trace.plan is not None else "none",
                )
            )

        if case.expectation.expected_target_side is not None:
            checks.append(
                EvalCheck(
                    name="target_side",
                    passed=trace.portfolio.target_side == case.expectation.expected_target_side,
                    expected=case.expectation.expected_target_side,
                    actual=trace.portfolio.target_side,
                )
            )

        if case.expectation.risk_approved is not None:
            checks.append(
                EvalCheck(
                    name="risk_approved",
                    passed=trace.risk.approved == case.expectation.risk_approved,
                    expected=str(case.expectation.risk_approved),
                    actual=str(trace.risk.approved),
                )
            )

        if case.expectation.min_confidence is not None:
            checks.append(
                EvalCheck(
                    name="confidence_floor",
                    passed=trace.research.confidence >= case.expectation.min_confidence,
                    expected=f">={case.expectation.min_confidence:.2f}",
                    actual=f"{trace.research.confidence:.2f}",
                )
            )

        passed_count = sum(1 for check in checks if check.passed)
        score = passed_count / len(checks) if checks else 1.0
        return EvalResult(
            case_name=case.name,
            passed=passed_count == len(checks),
            score=round(score, 4),
            checks=checks,
            trace=trace,
        )

    def evaluate_cases(self, cases: list[EvalCase]) -> list[EvalResult]:
        return [self.evaluate_case(case) for case in cases]
