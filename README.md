# Crypto AI Trading Agent Paper MVP

一个面向 `Binance 现货模拟盘` 的 AI Agent 交易系统 MVP。

这个项目的目标不是让大模型直接下单，而是搭建一条可生产演进的闭环：

```text
Binance / Mock K线
  -> 指标计算
  -> Market Analyst Agent
  -> Strategy Planner Agent
  -> Risk Manager Agent
  -> Portfolio Agent
  -> Paper Broker
  -> Trace / Fill / Equity 复盘
```

当前版本只做模拟盘，不接真实交易 API，不需要 Binance API key。

## 核心能力

- `Binance Spot` 公共 K 线接入：通过 REST 拉取历史 K 线。
- `Mock Data` fallback：无网络或演示场景也可以稳定运行。
- `Data Source 标记`：如果 Binance 请求失败并回退到 mock，结果中的 `data_source` 会明确显示实际数据源。
- `指标计算`：momentum、volatility、MA gap、RSI、EMA、MACD、ATR、volume z-score。
- `Agent 决策链`：市场分析、策略计划、规则风控、组合决策。
- `Spot Paper Broker`：模拟买入、卖出、手续费、滑点、现金、持仓、权益曲线。
- `Session 风控熔断`：支持最大回撤、最大亏损阈值，以及触发后强制平仓。
- `结构化 trace`：每一步 Agent 输入输出都可以复盘。
- `FastAPI`：提供行情和模拟盘运行接口。
- `JSON/JSONL 持久化`：可保存 summary、trace、fills，方便后续接评测和监控。

## 目录结构

```text
agent-quant-mvp/
├── README.md
├── pyproject.toml
├── scripts/
│   ├── run_binance_paper.py
│   └── run_demo.py
├── src/
│   └── agent_quant_mvp/
│       ├── agents.py       # Market / Strategy / Risk / Portfolio agents
│       ├── api.py          # FastAPI service
│       ├── backtest.py     # paper session entrypoint
│       ├── data.py         # Binance public data + mock bars
│       ├── factors.py      # quant indicators
│       ├── models.py       # structured domain models
│       ├── paper.py        # spot paper broker
│       ├── runner.py       # session engine
│       ├── storage.py      # JSON/JSONL run artifacts
│       └── workflow.py     # agent orchestration
└── tests/
    └── test_workflow.py
```

## 快速开始

```bash
cd agent-quant-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/run_demo.py
```

如果你只是想先跑核心模拟盘，不想安装依赖，也可以直接使用源码路径：

```bash
PYTHONPATH=src python3 scripts/run_demo.py
```

拉 Binance 公共 K 线并跑现货模拟盘：

```bash
PYTHONPATH=src python3 scripts/run_binance_paper.py --symbol BTCUSDT --interval 1h --limit 240 --source binance
```

保存运行结果到 `runs/`：

```bash
PYTHONPATH=src python3 scripts/run_binance_paper.py --symbol BTCUSDT --source binance --persist
```

启动 API：

```bash
uvicorn agent_quant_mvp.api:app --reload
```

常用接口：

- `GET /health`
- `GET /market/klines?symbol=BTCUSDT&source=mock`
- `POST /paper/run`
- `GET /demo/backtest?symbol=BTCUSDT&source=mock`

`GET /market/klines` 会同时返回：

- `requested_source`：请求的数据源
- `actual_source`：实际使用的数据源
- `fallback_used`：是否发生了回退

`POST /paper/run` 示例：

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "limit": 240,
  "lookback": 60,
  "start_equity": 10000,
  "source": "mock",
  "max_drawdown_pct": 12,
  "max_loss_pct": 8,
  "flatten_on_halt": true
}
```

## Agent 设计

`MarketAnalystAgent`

基于指标判断市场状态，输出 regime、方向倾向、confidence、thesis、observations 和 risk_factors。

`StrategyPlannerAgent`

把市场观点转换成结构化交易计划，包括 action、仓位比例、入场价、止损、止盈、持仓周期和证据。

`RiskManagerAgent`

用确定性规则做最终拦截，包括最大仓位、单笔上限、最低置信度、波动率上限、RSI 过热、库存检查。

`PortfolioAgent`

把通过风控的计划转换为目标组合动作。当前 spot 版本只支持 `buy / sell / hold`，不做合约空头。

## 生产边界

当前版本适合：

- 简历项目展示
- Agent 交易系统原型
- Binance 现货模拟盘
- 策略链路回放
- 风控规则验证

当前版本不做：

- 真实下单
- API key 管理
- 提现或资金权限
- 高频交易
- 合约杠杆

后续进入真实生产前，建议增加：

- 交易所私有 API 签名与权限隔离
- 实盘全局开关与人工确认
- 最大日亏损熔断
- 订单状态同步与补偿任务
- SQLite / PostgreSQL / ClickHouse 落库
- WebSocket 实时行情
- LLM provider、模型路由、Prompt 版本管理
- badcase 回放与离线评测集
- Grafana / Prometheus 监控
