"""Unit tests for NOC handoff decision policy."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from olist_ml.decisions.economics import clear_policy_cache, load_policy_economics
from olist_ml.decisions.policy import apply_noc_policy
from olist_ml.decisions.routing import requires_agent_review
from olist_ml.decisions.schemas import ActionType, DecisionContext
from olist_ml.decisions.service import DecisionService
from olist_ml.decisions.upgrade_cost import remaining_leg_upgrade_cost, seed_from_order_id
from olist_ml.decisions.value import business_loss_if_miss, score_action
from olist_ml.schemas import PredictResponse

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "policy_economics.yaml"


@pytest.fixture()
def policy_cfg():
    clear_policy_cache()
    return load_policy_economics(CONFIG)


def _ctx(**kwargs) -> DecisionContext:
    base = dict(
        order_id="o1",
        prediction_id="pred-1",
        model_version="m1",
        promise_miss_probability=0.5,
        basket_value=180.0,
        remaining_to_promise_days=4.0,
        geo_distance_km=200.0,
        same_state=0.0,
        freight_value=40.0,
        p1_score_threshold=0.40,
        p2_score_threshold=0.20,
    )
    base.update(kwargs)
    return DecisionContext(**base)


def test_business_loss_flat(policy_cfg) -> None:
    loss = business_loss_if_miss(100.0, policy_cfg.business_loss)
    assert loss == pytest.approx(10.0 + 0.10 * 100.0)


def test_p0_already_late_is_notice_not_ranker(policy_cfg) -> None:
    loss, rec, _alts, meta = apply_noc_policy(
        _ctx(remaining_to_promise_days=-0.5, promise_miss_probability=0.01),
        policy_cfg,
    )
    assert loss > 0
    assert rec.action == ActionType.LATE_NOTICE
    assert meta["policy_band"] == "P0"
    assert meta["upgrade_eligible"] is False


def test_p3_low_score_no_action(policy_cfg) -> None:
    _, rec, _, meta = apply_noc_policy(
        _ctx(promise_miss_probability=0.05, remaining_to_promise_days=4.0),
        policy_cfg,
    )
    assert rec.action == ActionType.NO_ACTION
    assert meta["policy_band"] == "P3"


def test_p1_upgrade_when_eligible(policy_cfg) -> None:
    _, rec, _, meta = apply_noc_policy(
        _ctx(promise_miss_probability=0.90, remaining_to_promise_days=3.0),
        policy_cfg,
    )
    assert meta["policy_band"] == "P1"
    assert meta["upgrade_eligible"] is True
    assert rec.action == ActionType.REMAINING_LEG_UPGRADE
    assert meta["upgrade_cost"] is not None
    assert meta["upgrade_cost"] >= 5.0


def test_p1_ineligible_short_remaining_same_state_close(policy_cfg) -> None:
    _, rec, _, meta = apply_noc_policy(
        _ctx(
            promise_miss_probability=0.90,
            remaining_to_promise_days=12.0,
            geo_distance_km=10.0,
            same_state=1.0,
        ),
        policy_cfg,
    )
    assert meta["policy_band"] == "P1"
    assert meta["upgrade_eligible"] is False
    assert rec.action == ActionType.AT_RISK_NOTICE


def test_p2_notice_only(policy_cfg) -> None:
    _, rec, _, meta = apply_noc_policy(
        _ctx(promise_miss_probability=0.25, remaining_to_promise_days=3.0),
        policy_cfg,
    )
    assert meta["policy_band"] == "P2"
    assert rec.action == ActionType.AT_RISK_NOTICE
    assert meta["upgrade_eligible"] is False


def test_at_risk_notice_uses_impact_formula(policy_cfg) -> None:
    econ = policy_cfg.actions[ActionType.AT_RISK_NOTICE]
    cand = score_action(action=econ, probability=0.5, loss_if_miss=40.0)
    assert cand.expected_avoided_loss == pytest.approx(4.0)
    assert cand.expected_net_value == pytest.approx(3.0)
    assert "customer_impact_reduction" in cand.formula


def test_agent_review_flag_non_no_action(policy_cfg) -> None:
    _loss, recommended, alts, _meta = apply_noc_policy(
        _ctx(promise_miss_probability=0.9, remaining_to_promise_days=3.0),
        policy_cfg,
    )
    assert recommended.action != ActionType.NO_ACTION
    assert requires_agent_review(
        recommended=recommended,
        alternatives=alts,
        basket_value=500.0,
        routing=policy_cfg.routing,
    )


def test_upgrade_cost_stable_not_python_hash(policy_cfg) -> None:
    a = remaining_leg_upgrade_cost(
        "order-stable", 20.0, 200.0, config=policy_cfg.noc_policy.upgrade_cost
    )
    b = remaining_leg_upgrade_cost(
        "order-stable", 20.0, 200.0, config=policy_cfg.noc_policy.upgrade_cost
    )
    assert a == b
    assert seed_from_order_id("order-stable") == seed_from_order_id("order-stable")
    assert seed_from_order_id("a") != seed_from_order_id("b")


def test_decision_service_from_prediction(policy_cfg) -> None:
    svc = DecisionService(config=policy_cfg)
    pred = PredictResponse(
        order_id="o1",
        prediction_id="pred-1",
        promise_miss_probability=0.8,
        risk_band="high",
        model_version="m1",
        prediction_timestamp=datetime(2018, 1, 1, tzinfo=UTC),
        p1_score_threshold=0.4,
        p2_score_threshold=0.2,
    )
    result = svc.decide_from_prediction(
        pred,
        basket_value=180.0,
        seller_id="s1",
        remaining_to_promise_days=3.0,
        geo_distance_km=250.0,
        same_state=0.0,
        freight_value=30.0,
    )
    assert result.prediction_id == "pred-1"
    assert result.order_id == "o1"
    assert result.policy_version == "noc-handoff-policy-v1"
    assert result.policy_config_version == "econ-sim-v3"
    assert result.recommended_action in set(ActionType)
    assert result.policy_band in {"P0", "P1", "P2", "P3"}
    assert len(result.alternative_actions) >= 1
    assert len(result.assumptions_disclaimer) > 0
    assert result.decision_source in {"deterministic_policy", "agent_review_pending"}
    assert result.git_sha is None or (len(result.git_sha) >= 7)


def test_decision_records_shared_git_sha(policy_cfg, monkeypatch) -> None:
    """Decision rows must use the same helper as model meta, not a second lookup."""
    monkeypatch.setattr("olist_ml.decisions.service.current_git_sha", lambda: "abc1234def")
    svc = DecisionService(config=policy_cfg)
    result = svc.decide(_ctx())
    assert result.git_sha == "abc1234def"


def test_decision_context_low_score_no_action(policy_cfg) -> None:
    svc = DecisionService(config=policy_cfg)
    result = svc.decide(
        DecisionContext(
            order_id="o2",
            prediction_id="pred-2",
            model_version="m1",
            promise_miss_probability=0.02,
            basket_value=40.0,
            remaining_to_promise_days=4.0,
            p1_score_threshold=0.4,
            p2_score_threshold=0.2,
        )
    )
    assert result.recommended_action == ActionType.NO_ACTION
    assert result.policy_band == "P3"
    assert result.expected_net_value == 0.0
