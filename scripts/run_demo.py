from __future__ import annotations

import json
from dataclasses import asdict

from agent_quant_mvp.backtest import run_backtest


def main() -> None:
    result = run_backtest(source="mock")
    payload = asdict(result)
    payload["equity_curve"] = payload["equity_curve"][-20:]
    payload["traces"] = payload["traces"][-5:]
    payload["fills"] = payload["fills"][-10:]
    payload["rejected_orders"] = payload["rejected_orders"][-10:]
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
