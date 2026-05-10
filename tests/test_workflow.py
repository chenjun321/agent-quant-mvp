import importlib
import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from agent_quant_mvp.backtest import run_backtest
from agent_quant_mvp.data import generate_mock_bars
from agent_quant_mvp.models import MarketBar
from agent_quant_mvp.paper import PaperBroker
from agent_quant_mvp.runner import PaperTradingEngine
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


if __name__ == "__main__":
    unittest.main()
