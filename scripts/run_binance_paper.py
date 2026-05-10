from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime

from agent_quant_mvp.backtest import run_backtest
from agent_quant_mvp.database import DEFAULT_DATABASE_URL, DatabaseRunStore
from agent_quant_mvp.storage import JsonlRunStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Binance Spot paper-trading session.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--limit", type=int, default=240)
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--source", choices=["mock", "binance"], default="binance")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--persist-db", action="store_true")
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    args = parser.parse_args()

    result = run_backtest(
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
        lookback=args.lookback,
        start_equity=args.equity,
        source=args.source,
    )

    payload = asdict(result)
    payload["equity_curve"] = payload["equity_curve"][-50:]
    payload["traces"] = payload["traces"][-10:]
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))

    run_id = f"{args.symbol.upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    if args.persist:
        store = JsonlRunStore()
        store.write_json(run_id, "summary", payload)
        store.write_jsonl(run_id, "traces", result.traces)
        store.write_jsonl(run_id, "fills", result.fills)

    if args.persist_db:
        store = DatabaseRunStore(database_url=args.database_url)
        store.write_run(run_id, result)
        print(f"persisted run to database: {args.database_url} run_id={run_id}")


if __name__ == "__main__":
    main()
