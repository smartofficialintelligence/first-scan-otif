#!/usr/bin/env python3
"""Lightweight deterministic agent-review eval (no LangSmith required)."""

from __future__ import annotations

import json
from pathlib import Path

from olist_ml.agents.graph import run_agent_review

DATASET = Path(__file__).resolve().parent / "datasets" / "agent_review_cases.jsonl"


def main() -> None:
    cases = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    results = []
    failures = 0
    for case in cases:
        out = run_agent_review(
            {
                "order_id": case["case_id"],
                "prediction_id": f"pred-{case['case_id']}",
                "model_version": "eval",
                "long_delivery_probability": case["long_delivery_probability"],
                "basket_value": case["basket_value"],
                "observed_long_delivery": True,
                "run_simulation": False,
                "require_human_approval": bool(case.get("require_human_approval", False)),
                "human_approved": case.get("human_approved", True),
                "tool_trace": [],
            }
        )
        ok = True
        if "expected_status" in case and out.get("status") != case["expected_status"]:
            ok = False
        if "expected_action" in case and out.get("selected_action") != case["expected_action"]:
            ok = False
        # Policy compliance: selected action must be in scored list or NO_ACTION
        allowed = {v["action"] for v in (out.get("action_values") or [])} | {"NO_ACTION"}
        if out.get("selected_action") not in allowed:
            ok = False
        if not ok:
            failures += 1
        results.append(
            {
                "case_id": case["case_id"],
                "ok": ok,
                "status": out.get("status"),
                "action": out.get("selected_action"),
            }
        )

    n = max(len(cases), 1)
    summary = {
        "n": len(cases),
        "failures": failures,
        "policy_compliance_pct": 100.0 * (1 - failures / n),
        "results": results,
    }
    out_path = Path("artifacts/agent_eval_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
