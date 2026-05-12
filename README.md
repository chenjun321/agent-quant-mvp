# Agent Quant Platform

一个面向 `Binance Spot` 模拟盘的 `AI Agent + Quant + Execution` 项目原型。

这个仓库不是在演示“让大模型直接拍脑袋下单”，而是在实现一条更接近生产系统的交易闭环：

```text
Market Data
  -> Factor Engine
  -> Market Analyst Agent
  -> Strategy Planner Agent
  -> Risk Manager Agent
  -> Portfolio Agent
  -> Paper Broker
  -> Fill / Equity / Trace / Run Artifacts
```

当前版本聚焦 `现货模拟盘`，不接真实资金，不需要 Binance API Key，但已经把后续走向实盘所需的系统边界拆出来了。

## Why This Project

这个项目适合用来展示以下能力：

- `AI Agent engineering`：把研究、计划、风控、组合决策拆成可组合的多 Agent 工作流
- `Trading system thinking`：不是只算指标，而是覆盖数据、信号、执行、风控、复盘
- `Production awareness`：显式处理 fallback、风控熔断、结构化 trace、可持久化结果
- `Backend engineering`：提供可脚本化运行入口和 FastAPI 服务接口

如果你在找的是下面这类岗位，这个项目方向是对的：

- AI Agent 工程师
- AI 交易系统工程师
- Quant / Trading Infra / Strategy Platform 工程师

## Core Features

- `Binance Spot public market data`
  通过 REST 拉取历史 K 线
- `Mock fallback`
  Binance 请求失败时自动回退到 mock 数据，方便 demo 和离线演示
- `Explicit data-source reporting`
  返回 `requested_source`、`actual_source`、`fallback_used`
- `Factor engine`
  包含 momentum、volatility、MA gap、RSI、EMA、MACD、ATR、volume z-score、trend score
- `Agent workflow`
  市场分析、策略规划、规则风控、组合决策分层执行
- `Pluggable agent backends`
  research / strategy 已抽象成 backend，可切换 rule-based 或 provider-backed 实现
- `Knowledge and tools`
  Agent 可接入 knowledge notes 与 specialized tools，补充决策上下文
- `Paper broker`
  支持现货买卖、手续费、滑点、现金/仓位/权益跟踪
- `Session risk halt`
  支持最大回撤、最大亏损阈值，触发后可强制平仓
- `Structured trace`
  每根 bar 的 research、plan、risk、portfolio 输出都能回放
- `Run persistence`
  支持 JSON / JSONL 调试落盘，以及 `SQLite / PostgreSQL` 数据库存储
- `FastAPI service`
  可通过 HTTP 触发行情拉取与模拟盘运行
- `Built-in evals`
  提供默认 eval cases 和 eval runner，用于回归 agent 行为

## Architecture

```text
Binance REST / Mock Bars
  -> data.py
  -> factors.py
  -> knowledge.py / tools.py
  -> backends.py
  -> workflow.py
      -> MarketAnalystAgent
      -> StrategyPlannerAgent
      -> RiskManagerAgent
      -> PortfolioAgent
  -> paper.py
  -> runner.py
  -> storage.py
  -> api.py / scripts/
```

模块职责：

- `data.py`
  行情读取与 mock fallback
- `factors.py`
  指标与特征计算
- `agents.py`
  多 Agent 决策逻辑与 backend 装配
- `backends.py`
  research / strategy backend 抽象，支持 provider-backed 模式
- `knowledge.py`
  knowledge note 与检索接口
- `tools.py`
  agent tools 注册与上下文补充
- `workflow.py`
  串联一次完整决策链
- `paper.py`
  模拟成交、持仓、费用、滑点
- `runner.py`
  回测/模拟盘 session 引擎与会话级熔断
- `storage.py`
  JSON / JSONL 调试落盘
- `database.py`
  PostgreSQL-ready 数据库持久化层，默认本地使用 SQLite
- `api.py`
  对外 API 服务
- `evals.py`
  eval cases、打分逻辑、eval runner

## Repository Layout

```text
agent-quant-platform/
├── README.md
├── pyproject.toml
├── scripts/
│   ├── run_binance_paper.py
│   ├── run_demo.py
│   └── run_evals.py
├── src/
│   └── agent_quant_platform/
│       ├── agents.py
│       ├── api.py
│       ├── backends.py
│       ├── backtest.py
│       ├── database.py
│       ├── data.py
│       ├── evals.py
│       ├── factors.py
│       ├── knowledge.py
│       ├── models.py
│       ├── paper.py
│       ├── runner.py
│       ├── storage.py
│       ├── tools.py
│       └── workflow.py
└── tests/
    └── test_workflow.py
```

## Quick Start

```bash
git clone <your-repo-url> agent-quant-platform
cd agent-quant-platform
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/run_demo.py
```

如果你只想快速运行源码，不先安装依赖，也可以：

```bash
PYTHONPATH=src python3 scripts/run_demo.py
```

拉取 Binance 公共 K 线并运行模拟盘：

```bash
PYTHONPATH=src python3 scripts/run_binance_paper.py \
  --symbol BTCUSDT \
  --interval 1h \
  --limit 240 \
  --source binance
```

保存结果到 `runs/`：

```bash
PYTHONPATH=src python3 scripts/run_binance_paper.py \
  --symbol BTCUSDT \
  --source binance \
  --persist
```

写入数据库：

```bash
PYTHONPATH=src python3 scripts/run_binance_paper.py \
  --symbol BTCUSDT \
  --source binance \
  --persist-db \
  --database-url postgresql+psycopg://user:password@localhost:5432/agent_quant
```

启动 API：

```bash
uvicorn agent_quant_platform.api:app --reload
```

运行默认 evals：

```bash
PYTHONPATH=src python3 scripts/run_evals.py
```

## API

常用接口：

- `GET /health`
- `GET /market/klines?symbol=BTCUSDT&source=mock`
- `POST /paper/run`
- `GET /demo/backtest?symbol=BTCUSDT&source=mock`
- `GET /evals/default`

`GET /market/klines` 会返回：

- `requested_source`
- `actual_source`
- `fallback_used`

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
  "flatten_on_halt": true,
  "persist_jsonl": false,
  "persist_db": true,
  "database_url": "postgresql+psycopg://user:password@localhost:5432/agent_quant"
}
```

## Agent Design

`MarketAnalystAgent`

基于因子与市场快照输出：

- regime
- side bias
- confidence
- thesis
- observations
- risk factors

当前支持：

- rule-based backend
- provider-backed backend
- knowledge notes 注入
- specialized tools 注入

`StrategyPlannerAgent`

把市场观点转成结构化交易计划：

- buy / sell / hold
- 仓位比例
- entry price
- stop loss
- take profit
- holding bars
- evidence

`RiskManagerAgent`

用确定性规则做最终拦截：

- 最大仓位
- 单笔上限
- 最低置信度
- 波动率阈值
- RSI 过热过滤
- 库存检查

`PortfolioAgent`

把 research + plan + risk 合成为目标组合动作。当前 spot 版本只支持：

- `buy`
- `sell`
- `hold`

## Production-Oriented Decisions

这个仓库虽然当前以 paper-trading prototype 为主，但有几处设计是明确按生产思路做的：

- `LLM-shaped interface, rule-based implementation`
  先用结构化 Agent 接口把系统边界固定住，再用确定性逻辑保证可测试与可回放
- `Backend abstraction`
  research / strategy 已拆成 backend，可平滑切换到真实 LLM provider
- `Tools and knowledge are first-class`
  agent 不只看指标，还能消费工具输出和知识上下文
- `Data fallback is explicit`
  回退到 mock 数据时不会伪装成真实 Binance 数据
- `Risk is layered`
  既有订单级风控，也有 session 级熔断
- `Execution is isolated`
  决策链和 broker 执行层分离，便于以后接真实交易所 API
- `Database-ready persistence`
  运行结果可以落到生产数据库，而不只是停留在本地 JSON 文件
- `Trace first`
  每一步都有结构化输出，方便 badcase 分析和离线评测
- `Evals are runnable`
  默认 case 可直接跑，适合 prompt / backend / risk 逻辑迭代

## Current Scope

当前版本适合：

- GitHub / 简历项目展示
- AI 交易 Agent 原型验证
- Binance 现货模拟盘
- 决策链路回放
- 风控规则验证

当前版本不做：

- 真实下单
- 私有 API key 管理
- 提现或资金权限控制
- 高频交易
- 合约杠杆与空头
- WebSocket 实时执行

## Roadmap To Production

如果要继续把它打磨成更强的 AI 交易系统项目，我建议下一步按这个顺序升级：

1. `Exchange execution abstraction`
   抽象 live / paper adapter，接 Binance 私有 API、签名、幂等单号、订单同步
2. `Persistent state`
   在当前 SQLite / PostgreSQL run store 基础上继续细化 order ledger / position snapshots / audit trail
3. `Realtime market infra`
   接 WebSocket Kline / ticker / user stream，处理断线重连和补偿
4. `Model routing`
   支持 OpenAI / Claude / 开源模型 provider 抽象与 prompt versioning
5. `Evaluation loop`
   建 badcase 数据集、离线评测、参数回放与策略对比
6. `Observability`
   接 Prometheus / Grafana / alerting

## Validation

当前已覆盖的基础验证：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

测试重点包括：

- mock bars 生成
- workflow 结构化输出
- provider-backed backend 覆盖默认决策
- knowledge / tool context 注入
- rejected order 不执行
- data fallback 标记正确
- session 风控触发后自动平仓
- default eval cases 全量通过

## Resume-Friendly Summary

如果你要把这个项目写进简历，可以概括成：

> 设计并实现一个面向 Crypto Spot 模拟盘的 AI Agent 交易系统原型，打通市场数据、因子计算、多 Agent 决策、规则风控、组合动作、模拟执行与结构化复盘链路，并为后续实盘接入预留执行层、模型路由与监控边界。
