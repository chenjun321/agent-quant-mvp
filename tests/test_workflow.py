import importlib
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agent_quant_mvp.agents import MarketAnalystAgent, StrategyPlannerAgent
from agent_quant_mvp.backtest import run_backtest
from agent_quant_mvp.backends import ProviderBackedResearchBackend, ProviderBackedStrategyBackend, StaticStructuredModelProvider
from agent_quant_mvp.database import SQLALCHEMY_AVAILABLE, DatabaseRunStore
from agent_quant_mvp.data import generate_mock_bars
from agent_quant_mvp.evals import WorkflowEvaluator, default_eval_cases
from agent_quant_mvp.knowledge import InMemoryKnowledgeBase, KnowledgeNote
from agent_quant_mvp.models import MarketBar
from agent_quant_mvp.paper import PaperBroker
from agent_quant_mvp.runner import PaperTradingEngine
from agent_quant_mvp.tools import DEFAULT_AGENT_TOOLS
from agent_quant_mvp.workflow import AgentWorkflow


class AgentWorkflowTest(unittest.TestCase):
    def test_generate_mock_bars_count(self) -> None:
        bars = generate_mock_bars(symbol="BTCUSDT", periods=30)
        self.assertEqual(len(bars), 30)
        self.assertGreater(bars[0].close, 0)
        self.assertEqual(bars[0].symbol, "BTCUSDT")

    def test_workflow_returns_structured_agent_trace(self) -> None:
        bars = generate_mock_bars(symbol="BTCUSDT", periods=80)
        broker = PaperBroker()
        account = broker.account_snapshot(bars[-1])
        workflow = AgentWorkflow()
        trace = workflow.step(symbol="BTCUSDT", window=bars[-60:], account=account)

        self.assertEqual(trace.symbol, "BTCUSDT")
        self.assertIsNotNone(trace.plan)
        self.assertIn(trace.plan.action, {"buy", "sell", "hold"})
        self.assertGreaterEqual(trace.risk.max_position_pct, 0)
        self.assertLessEqual(trace.risk.max_position_pct, 1)
        self.assertTrue(trace.research.thesis)

    def test_paper_broker_never_executes_rejected_order(self) -> None:
        bars = generate_mock_bars(symbol="BTCUSDT", periods=80)
        broker = PaperBroker()
        workflow = AgentWorkflow()
        account = broker.account_snapshot(bars[-1])
        trace = workflow.step(symbol="BTCUSDT", window=bars[-60:], account=account)
        trace.risk.approved = False

        fill = broker.execute(trace.plan, trace.risk, bars[-1])
        self.assertIsNone(fill)
        if trace.plan and trace.plan.action != "hold":
            self.assertTrue(broker.rejected_orders)

    def test_backtest_runs_paper_session(self) -> None:
        result = run_backtest(source="mock", limit=180, lookback=60)
        self.assertGreater(result.end_equity, 0)
        self.assertGreaterEqual(result.stats.total_trades, 0)
        self.assertGreater(len(result.traces), 0)
        self.assertGreater(len(result.equity_curve), 0)

    def test_market_endpoint_reports_actual_source_after_fallback(self) -> None:
        fallback_bars = generate_mock_bars(symbol="BTCUSDT", periods=20)
        dummy_fastapi = types.ModuleType("fastapi")
        dummy_pydantic = types.ModuleType("pydantic")

        class DummyFastAPI:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def get(self, *args, **kwargs):
                return lambda func: func

            def post(self, *args, **kwargs):
                return lambda func: func

        class DummyBaseModel:
            pass

        dummy_fastapi.FastAPI = DummyFastAPI
        dummy_pydantic.BaseModel = DummyBaseModel
        dummy_pydantic.Field = lambda default=None, **kwargs: default

        with patch.dict(sys.modules, {"fastapi": dummy_fastapi, "pydantic": dummy_pydantic}):
            sys.modules.pop("agent_quant_mvp.api", None)
            api_module = importlib.import_module("agent_quant_mvp.api")

        with patch("agent_quant_mvp.api.load_market_bars", return_value=fallback_bars):
            payload = api_module.market_klines(symbol="BTCUSDT", source="binance")

        self.assertEqual(payload["requested_source"], "binance")
        self.assertEqual(payload["actual_source"], "mock")
        self.assertTrue(payload["fallback_used"])

    def test_eval_endpoint_returns_default_eval_summary(self) -> None:
        dummy_fastapi = types.ModuleType("fastapi")
        dummy_pydantic = types.ModuleType("pydantic")

        class DummyFastAPI:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def get(self, *args, **kwargs):
                return lambda func: func

            def post(self, *args, **kwargs):
                return lambda func: func

        class DummyBaseModel:
            pass

        dummy_fastapi.FastAPI = DummyFastAPI
        dummy_pydantic.BaseModel = DummyBaseModel
        dummy_pydantic.Field = lambda default=None, **kwargs: default

        with patch.dict(sys.modules, {"fastapi": dummy_fastapi, "pydantic": dummy_pydantic}):
            sys.modules.pop("agent_quant_mvp.api", None)
            api_module = importlib.import_module("agent_quant_mvp.api")

        payload = api_module.default_evals()

        self.assertEqual(payload["total_cases"], 3)
        self.assertEqual(payload["passed_cases"], 3)

    def test_engine_halts_and_flattens_position_when_loss_limit_breaches(self) -> None:
        start = datetime(2025, 1, 1, 0, 0, 0)
        bars = []
        for idx in range(60):
            bars.append(
                MarketBar(
                    ts=start + timedelta(hours=idx),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.0,
                    volume=1000.0,
                    symbol="BTCUSDT",
                    interval="1h",
                    source="mock",
                )
            )
        bars.append(
            MarketBar(
                ts=start + timedelta(hours=60),
                open=100.0,
                high=100.0,
                low=79.0,
                close=80.0,
                volume=1500.0,
                symbol="BTCUSDT",
                interval="1h",
                source="mock",
            )
        )

        broker = PaperBroker(initial_cash=0.0)
        broker.positions["BTC"] = 1.0
        engine = PaperTradingEngine(
            broker=broker,
            lookback=60,
            max_loss_pct=10.0,
            max_drawdown_pct=None,
            flatten_on_halt=True,
        )

        result = engine.run(symbol="BTCUSDT", bars=bars, requested_source="mock")

        self.assertIsNotNone(result.halt_reason)
        self.assertIn("loss limit breached", result.halt_reason or "")
        self.assertEqual(result.halted_at, bars[-1].ts)
        self.assertEqual(result.stats.forced_liquidations, 1)
        self.assertEqual(result.stats.skipped_steps, 0)
        self.assertEqual(broker.positions.get("BTC", 0.0), 0.0)
        self.assertEqual(result.fills[-1].action, "sell")
        self.assertEqual(result.fills[-1].reason, result.halt_reason)

    def test_database_run_store_persists_backtest_result(self) -> None:
        if not SQLALCHEMY_AVAILABLE:
            self.skipTest("sqlalchemy is not installed in this environment")

        result = run_backtest(source="mock", limit=180, lookback=60)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agent_quant_mvp.db"
            store = DatabaseRunStore(database_url=f"sqlite:///{db_path}")
            store.write_run("test-run-1", result)

            with sqlite3.connect(db_path) as conn:
                run_count = conn.execute("select count(*) from runs").fetchone()[0]
                fill_count = conn.execute("select count(*) from fills").fetchone()[0]
                trace_count = conn.execute("select count(*) from traces").fetchone()[0]

        self.assertEqual(run_count, 1)
        self.assertEqual(fill_count, len(result.fills))
        self.assertEqual(trace_count, len(result.traces))

    def test_market_agent_uses_knowledge_and_tool_context(self) -> None:
        bars = generate_mock_bars(symbol="BTCUSDT", periods=80)
        broker = PaperBroker()
        snapshot_account = broker.account_snapshot(bars[-1])
        knowledge_base = InMemoryKnowledgeBase(
            notes=[
                KnowledgeNote(
                    note_id="btc-1",
                    title="BTC momentum regimes deserve explicit confirmation.",
                    content="Use knowledge context to influence market analysis explanations.",
                    symbols=["BTCUSDT"],
                    tags=["trend"],
                )
            ]
        )
        market_agent = MarketAnalystAgent(knowledge_base=knowledge_base, tools=DEFAULT_AGENT_TOOLS)
        workflow = AgentWorkflow(market_agent=market_agent)

        trace = workflow.step(symbol="BTCUSDT", window=bars[-60:], account=snapshot_account)
        joined_observations = " ".join(trace.research.observations)

        self.assertIn("Knowledge note:", joined_observations)
        self.assertIn("Tool", joined_observations)

    def test_provider_backed_agents_can_override_rule_outputs(self) -> None:
        bars = generate_mock_bars(symbol="BTCUSDT", periods=80)
        broker = PaperBroker()
        account = broker.account_snapshot(bars[-1])
        provider = StaticStructuredModelProvider(
            responses={
                "market_analysis": {
                    "regime": "trend_up",
                    "side_bias": "long",
                    "confidence": 0.91,
                    "thesis": "Provider-backed research expects continuation.",
                    "observations": ["Provider saw a favorable setup."],
                    "risk_factors": [],
                },
                "strategy_plan": {
                    "action": "buy",
                    "quote_amount_pct": 0.25,
                    "confidence": 0.91,
                    "rationale": "Provider-backed strategy wants to add spot exposure.",
                    "entry_price": bars[-1].close,
                    "stop_loss": bars[-1].close * 0.96,
                    "take_profit": bars[-1].close * 1.05,
                    "max_holding_bars": 18,
                    "evidence": ["Provider-backed evidence."],
                },
            }
        )
        workflow = AgentWorkflow(
            market_agent=MarketAnalystAgent(backend=ProviderBackedResearchBackend(provider)),
            strategy_agent=StrategyPlannerAgent(backend=ProviderBackedStrategyBackend(provider)),
        )

        trace = workflow.step(symbol="BTCUSDT", window=bars[-60:], account=account)

        self.assertEqual(trace.research.thesis, "Provider-backed research expects continuation.")
        self.assertEqual(trace.plan.action, "buy")
        self.assertAlmostEqual(trace.plan.quote_amount_pct, 0.25)

    def test_default_eval_cases_pass(self) -> None:
        evaluator = WorkflowEvaluator()
        results = evaluator.evaluate_cases(default_eval_cases())

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result.passed for result in results))


if __name__ == "__main__":
    unittest.main()
