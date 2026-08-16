#!/usr/bin/env python3
"""
Demo harness for prediction → decision → agent review → simulated action (D13).

Runs without an LLM API key. Optional agent extra: uv sync --extra agent
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from olist_ml.actions.executor import ActionExecutor
from olist_ml.decisions.replay import ReplayRow, replay_policies
from olist_ml.decisions.schemas import DecisionContext
from olist_ml.decisions.service import DecisionService
from olist_ml.schemas import PredictResponse


def demo_b_deterministic() -> dict:
    svc = DecisionService()
    # High risk, mid basket → positive EV intervention
    decision = svc.decide(
        DecisionContext(
            order_id="demo-b",
            prediction_id="pred-demo-b",
            model_version="demo",
            long_delivery_probability=0.82,
            basket_value=160.0,
        )
    )
    return {
        "scenario": "B_deterministic_decision",
        "probability": 0.82,
        "recommended_action": decision.recommended_action.value,
        "expected_net_value": decision.expected_net_value,
        "alternatives": [
            {
                "action": a.action.value,
                "expected_net_value": a.expected_net_value,
                "cost": a.expected_intervention_cost,
            }
            for a in decision.alternative_actions
        ],
        "rationale": decision.rationale,
    }


def demo_c_simulate() -> dict:
    decision = DecisionService().decide(
        DecisionContext(
            order_id="demo-c",
            prediction_id="pred-demo-c",
            model_version="demo",
            long_delivery_probability=0.8,
            basket_value=200.0,
        )
    )
    action = ActionExecutor().execute_decision(
        decision_id=decision.decision_id,
        prediction_id="pred-demo-c",
        order_id="demo-c",
        action_type=decision.recommended_action,
        model_version="demo",
        policy_version=decision.policy_version,
        observed_long_delivery=True,
        basket_value=200.0,
        expected_net_value=decision.expected_net_value,
    )
    return {
        "scenario": "C_simulated_execution",
        "action": action.action_type.value,
        "cost": action.simulated_cost,
        "intervention_success": action.intervention_success,
        "observed_long_delivery": action.observed_long_delivery,
        "simulated_long_delivery": action.simulated_long_delivery,
        "simulated_net_value": action.simulated_net_value,
        "assumptions": action.assumptions_disclaimer[:120] + "...",
    }


def demo_d_policy_replay() -> dict:
    rows = [
        ReplayRow("r1", "p1", "demo", 0.9, 200.0, True),
        ReplayRow("r2", "p2", "demo", 0.15, 40.0, False),
        ReplayRow("r3", "p3", "demo", 0.78, 180.0, True),
        ReplayRow("r4", "p4", "demo", 0.25, 60.0, False),
        ReplayRow("r5", "p5", "demo", 0.85, 250.0, True),
    ]
    report = replay_policies(rows, threshold=0.70, base_seed=11)
    return {"scenario": "D_policy_value", "policies": report["policies"]}


def demo_e_agent_review() -> dict:
    from olist_ml.agents.graph import run_agent_review

    # Near-tie / high-value style case
    result = run_agent_review(
        {
            "order_id": "demo-e",
            "prediction_id": "pred-demo-e",
            "model_version": "demo",
            "long_delivery_probability": 0.81,
            "basket_value": 300.0,
            "seller_id": "s-demo",
            "observed_long_delivery": True,
            "run_simulation": True,
            "require_human_approval": True,
            "human_approved": True,
            "tool_trace": [],
        }
    )
    return {
        "scenario": "E_agent_review",
        "status": result.get("status"),
        "selected_action": result.get("selected_action"),
        "agent_rationale": result.get("agent_rationale"),
        "policy_recommendation": result.get("policy_recommendation"),
        "tool_trace": result.get("tool_trace"),
        "action_result": {
            "cost": (result.get("action_result") or {}).get("simulated_cost"),
            "simulated_net_value": (result.get("action_result") or {}).get("simulated_net_value"),
        },
    }


def demo_g_lineage() -> dict:
    pred = PredictResponse(
        order_id="demo-g",
        prediction_id="pred-demo-g",
        long_delivery_probability=0.77,
        risk_band="high",
        model_version="demo",
        prediction_timestamp=datetime(2018, 6, 1, tzinfo=UTC),
    )
    decision = DecisionService().decide_from_prediction(pred, basket_value=175.0)
    return {
        "scenario": "G_lineage",
        "prediction_id": pred.prediction_id,
        "model_version": pred.model_version,
        "probability": pred.long_delivery_probability,
        "decision_id": decision.decision_id,
        "policy_version": decision.policy_version,
        "recommended_action": decision.recommended_action.value,
        "expected_net_value": decision.expected_net_value,
    }


def main() -> None:
    out = {
        "B": demo_b_deterministic(),
        "C": demo_c_simulate(),
        "D": demo_d_policy_replay(),
        "E": demo_e_agent_review(),
        "G": demo_g_lineage(),
    }
    path = Path("artifacts/demo_decision_chain.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "alternatives"} for k, v in out.items() if k != "D"}, indent=2, default=str))
    print("D policies net_simulated_value:", {p: out["D"]["policies"][p]["net_simulated_value"] for p in out["D"]["policies"]})
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
