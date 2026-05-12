from __future__ import annotations

import json
from dataclasses import asdict

from agent_quant_mvp.evals import WorkflowEvaluator, default_eval_cases


def main() -> None:
    evaluator = WorkflowEvaluator()
    results = evaluator.evaluate_cases(default_eval_cases())
    payload = {
        "passed_cases": sum(1 for result in results if result.passed),
        "total_cases": len(results),
        "results": [asdict(result) for result in results],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
