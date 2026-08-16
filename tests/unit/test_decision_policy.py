"""Unit tests for expected-value decision policy (D1–D2)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from olist_ml.decisions.economics import clear_policy_cache, load_policy_economics
from olist_ml.decisions.policy import run_expected_value_policy, select_recommended_action
from olist_ml.decisions.routing import requires_agent_review
from olist_ml.decisions.schemas import ActionCandidate, ActionType, DecisionContext
from olist_ml.decisions.service import DecisionService
from olist_ml.decisions.value import business_loss_if_long, score_action
from olist_ml.schemas import PredictResponse

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "policy_economics.yaml"


@pytest.fixture()
def policy_cfg():
    clear_policy_cache()
    return load_policy_economics(CONFIG)


def test_business_loss_flat(policy_cfg) -> None:
    loss = business_loss_if_long(100.0, policy_cfg.business_loss)
    assert loss == pytest.approx(10.0 + 0.10 * 100.0)


def test_no_action_when_low_risk(policy_cfg) -> None:
    loss, recommended, alts = run_expected_value_policy(
        probability=0.01,
        basket_value=50.0,
        config=policy_cfg,
    )
    assert loss > 0
    assert recommended.action == ActionType.NO_ACTION
    assert recommended.expected_net_value == 0.0
    assert len(alts) >= 5


def test_high_risk_selects_positive_ev_action(policy_cfg) -> None:
    _, recommended, alts = run_expected_value_policy(
        probability=0.85,
        basket_value=200.0,
        config=policy_cfg,
    )
    assert recommended.action != ActionType.NO_ACTION
    assert recommended.expected_net_value > 0
    positive = [c for c in alts if c.expected_net_value > 0]
    assert recommended.expected_net_value == max(c.expected_net_value for c in positive)


def test_customer_notification_uses_impact_formula(policy_cfg) -> None:
    econ = policy_cfg.actions[ActionType.CUSTOMER_NOTIFICATION]
    cand = score_action(action=econ, probability=0.5, loss_if_long=40.0)
    assert cand.expected_avoided_loss == pytest.approx(4.0)
    assert cand.expected_net_value == pytest.approx(3.0)
    assert "customer_impact_reduction" in cand.formula


def test_negative_ev_yields_no_action(policy_cfg) -> None:
    _, recommended, _ = run_expected_value_policy(
        probability=0.15,
        basket_value=5.0,
        config=policy_cfg,
    )
    assert recommended.action == ActionType.NO_ACTION


def test_select_recommended_prefers_highest_positive() -> None:
    cands = [
        ActionCandidate(
            action=ActionType.EXPEDITE,
            expected_intervention_cost=8,
            expected_avoided_loss=10,
            expected_net_value=2,
            formula="x",
        ),
        ActionCandidate(
            action=ActionType.SELLER_ESCALATION,
            expected_intervention_cost=4,
            expected_avoided_loss=9,
            expected_net_value=5,
            formula="x",
        ),
        ActionCandidate(
            action=ActionType.NO_ACTION,
            expected_intervention_cost=0,
            expected_avoided_loss=0,
            expected_net_value=0,
            formula="x",
        ),
    ]
    assert select_recommended_action(cands).action == ActionType.SELLER_ESCALATION


def test_agent_review_flag_high_value(policy_cfg) -> None:
    _, recommended, alts = run_expected_value_policy(
        probability=0.9,
        basket_value=500.0,
        config=policy_cfg,
    )
    assert requires_agent_review(
        recommended=recommended,
        alternatives=alts,
        basket_value=500.0,
        routing=policy_cfg.routing,
    )


def test_decision_service_from_prediction(policy_cfg) -> None:
    svc = DecisionService(config=policy_cfg)
    pred = PredictResponse(
        order_id="o1",
        prediction_id="pred-1",
        long_delivery_probability=0.8,
        risk_band="high",
        model_version="m1",
        prediction_timestamp=datetime(2018, 1, 1, tzinfo=UTC),
    )
    result = svc.decide_from_prediction(pred, basket_value=180.0, seller_id="s1")
    assert result.prediction_id == "pred-1"
    assert result.order_id == "o1"
    assert result.policy_version == "expected-value-policy-v1"
    assert result.policy_config_version == "econ-sim-v2"
    assert result.recommended_action in set(ActionType)
    assert len(result.alternative_actions) >= 1
    assert len(result.assumptions_disclaimer) > 0
    assert result.decision_source in {"deterministic_policy", "agent_review_pending"}


def test_decision_context_decide(policy_cfg) -> None:
    svc = DecisionService(config=policy_cfg)
    result = svc.decide(
        DecisionContext(
            order_id="o2",
            prediction_id="pred-2",
            model_version="m1",
            long_delivery_probability=0.02,
            basket_value=40.0,
        )
    )
    assert result.recommended_action == ActionType.NO_ACTION
    assert result.expected_net_value == 0.0
