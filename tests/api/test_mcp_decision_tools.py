"""MCP decision tool handler tests (D7) — domain services only, no duplicated logic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from olist_ml.actions.executor import ActionExecutor
from olist_ml.api import mcp_server
from olist_ml.config import Settings
from olist_ml.decisions.service import DecisionService
from olist_ml.inference.predictor import PredictionService
from olist_ml.outcomes.ledger import DecisionLedger
from olist_ml.tools import decision_tools
from olist_ml.training.pipeline import run_training
from olist_ml.training.promote import promote_candidate

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
CONFIG = Path(__file__).resolve().parents[2] / "config" / "policy_economics.yaml"


@pytest.fixture(scope="module")
def trained_stack(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("mcp-decision-artifacts")
    settings = Settings(
        data_dir=FIXTURES,
        artifact_dir=root,
        model_path=root / "model.joblib",
        model_meta_path=root / "model_meta.json",
        decision_ledger_path=root / "decision_ledger.jsonl",
        policy_economics_path=CONFIG,
        n_optuna_trials=2,
        cv_folds=2,
        auth_mode="off",
    )
    meta = run_training(settings, data_dir=FIXTURES)
    promote_candidate(settings, meta.model_version, approved_by="pytest")
    pred = PredictionService(settings)
    pred.load()
    decision = DecisionService(config_path=CONFIG)
    executor = ActionExecutor(config_path=CONFIG, base_seed=7)
    ledger = DecisionLedger(settings.decision_ledger_path)
    return pred, decision, executor, ledger


@pytest.fixture(autouse=True)
def _inject(trained_stack):
    pred, decision, executor, ledger = trained_stack
    mcp_server.set_service(pred)
    decision_tools.set_decision_deps(
        prediction_service=pred,
        decision_service=decision,
        executor=executor,
        ledger=ledger,
    )
    yield


def _payload(order_id: str = "mcp-dec") -> dict:
    ts = datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat()
    return {
        "order_id": order_id,
        "seller_id": "s000",
        "purchase_timestamp": ts,
        "prediction_timestamp": ts,
        "item_count": 2,
        "basket_value": 180.0,
        "freight_value": 15.0,
        "estimated_delivery_horizon_days": 5.0,
        "seller_late_rate_30d": 0.5,
        "geo_distance_km": 400.0,
    }


def test_list_and_policy_metrics(trained_stack) -> None:
    actions = decision_tools.list_available_actions(decision_service=trained_stack[1])
    assert actions["policy_version"] == "noc-handoff-policy-v1"
    names = {a["action"] for a in actions["actions"]}
    assert "REMAINING_LEG_UPGRADE" in names
    assert "AT_RISK_NOTICE" in names
    assert "NO_ACTION" in names
    assert decision_tools.get_policy_metrics(decision_service=trained_stack[1])["actions"]


def test_calculate_action_value(trained_stack) -> None:
    out = decision_tools.calculate_action_value(
        action="REMAINING_LEG_UPGRADE",
        probability=0.8,
        basket_value=200.0,
        decision_service=trained_stack[1],
    )
    assert out["candidate"]["action"] == "REMAINING_LEG_UPGRADE"
    assert "expected_net_value" in out["candidate"]


def test_recommend_p0_late_notice(trained_stack) -> None:
    body = decision_tools.recommend_policy_action(
        service=trained_stack[0],
        decision_service=trained_stack[1],
        ledger=trained_stack[3],
        remaining_to_promise_days=-0.5,
        handling_days=12.0,
        **_payload("mcp-p0"),
    )
    assert body["decision"]["recommended_action"] == "LATE_NOTICE"
    assert body["decision"]["policy_band"] == "P0"


def test_recommend_and_history(trained_stack) -> None:
    body = decision_tools.recommend_policy_action(
        service=trained_stack[0],
        decision_service=trained_stack[1],
        ledger=trained_stack[3],
        remaining_to_promise_days=4.0,
        handling_days=2.0,
        **_payload("mcp-rec"),
    )
    assert "prediction" in body and "decision" in body
    assert body["decision"]["recommended_action"]
    hist = decision_tools.get_decision_history("mcp-rec", ledger=trained_stack[3])
    assert len(hist["records"]) >= 2


def test_execute_simulated_action_and_outcome(trained_stack) -> None:
    rec = decision_tools.recommend_policy_action(
        service=trained_stack[0],
        decision_service=trained_stack[1],
        ledger=trained_stack[3],
        **_payload("mcp-act"),
    )
    d = rec["decision"]
    p = rec["prediction"]
    action = decision_tools.execute_simulated_action(
        order_id=p["order_id"],
        prediction_id=p["prediction_id"],
        decision_id=d["decision_id"],
        action=d["recommended_action"],
        model_version=p["model_version"],
        policy_version=d["policy_version"],
        observed_promise_miss=True,
        basket_value=180.0,
        expected_net_value=d["expected_net_value"],
        executor=trained_stack[2],
        ledger=trained_stack[3],
    )
    assert action["status"] == "simulated"
    assert "simulated_delay_days_avoided" in action
    assert "observed_days_late" in action
    out = decision_tools.get_action_outcome(action["action_id"], ledger=trained_stack[3])
    assert len(out["records"]) >= 1


def test_execute_uses_ledgered_upgrade_cost_when_caller_omits_it(trained_stack) -> None:
    """MCP execute passes no cost context; the frozen decision's priced
    upgrade_cost must be used instead of the freight-0 $5 minimum fallback."""
    ledger = trained_stack[3]
    ledger.append_decision(
        {
            "decision_id": "mcp-cost-1",
            "order_id": "mcp-cost",
            "prediction_id": "pred-cost",
            "recommended_action": "REMAINING_LEG_UPGRADE",
            "upgrade_cost": 42.5,
        }
    )
    action = decision_tools.execute_simulated_action(
        order_id="mcp-cost",
        prediction_id="pred-cost",
        decision_id="mcp-cost-1",
        action="REMAINING_LEG_UPGRADE",
        model_version="m",
        policy_version="noc-handoff-policy-v1",
        observed_promise_miss=True,
        basket_value=800.0,
        executor=trained_stack[2],
        ledger=ledger,
    )
    assert action["simulated_cost"] == pytest.approx(42.5)


def test_execute_rejects_action_not_in_policy(trained_stack) -> None:
    rec = decision_tools.recommend_policy_action(
        service=trained_stack[0],
        decision_service=trained_stack[1],
        ledger=trained_stack[3],
        remaining_to_promise_days=4.0,
        handling_days=2.0,
        **_payload("mcp-bind"),
    )
    d = rec["decision"]
    p = rec["prediction"]
    cheaper = (
        "AT_RISK_NOTICE"
        if d["recommended_action"] == "REMAINING_LEG_UPGRADE"
        else "REMAINING_LEG_UPGRADE"
    )
    if cheaper == d["recommended_action"]:
        cheaper = "NO_ACTION"
    with pytest.raises(ValueError, match="frozen policy"):
        decision_tools.execute_simulated_action(
            order_id=p["order_id"],
            prediction_id=p["prediction_id"],
            decision_id=d["decision_id"],
            action=cheaper,
            model_version=p["model_version"],
            policy_version=d["policy_version"],
            observed_promise_miss=True,
            basket_value=180.0,
            executor=trained_stack[2],
            ledger=trained_stack[3],
        )
