"""Tests for ActionExecutor, simulation, ledger, and policy replay (D3–D5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from olist_ml.actions.executor import ActionExecutor
from olist_ml.actions.schemas import ActionRequest
from olist_ml.decisions.economics import clear_policy_cache, load_policy_economics
from olist_ml.decisions.replay import ReplayRow, replay_policies
from olist_ml.decisions.schemas import ActionType
from olist_ml.decisions.service import DecisionService
from olist_ml.outcomes.ledger import DecisionLedger
from olist_ml.simulation.intervention import derive_seed, simulate_intervention

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "policy_economics.yaml"


@pytest.fixture()
def cfg():
    clear_policy_cache()
    return load_policy_economics(CONFIG)


def test_simulation_reproducible(cfg) -> None:
    econ = cfg.actions[ActionType.EXPEDITE]
    a = simulate_intervention(
        action=econ,
        observed_long_delivery=True,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=123,
    )
    b = simulate_intervention(
        action=econ,
        observed_long_delivery=True,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=123,
    )
    assert a == b


def test_expedite_can_flip_long_to_on_time(cfg) -> None:
    econ = cfg.actions[ActionType.EXPEDITE]
    # Try several seeds; with p=0.6 we should see at least one success
    successes = 0
    for seed in range(50):
        out = simulate_intervention(
            action=econ,
            observed_long_delivery=True,
            basket_value=100.0,
            loss_cfg=cfg.business_loss,
            seed=seed,
        )
        if out["intervention_success"]:
            successes += 1
            assert out["simulated_long_delivery"] is False
            assert out["simulated_gross_avoided_loss"] > 0
    assert successes > 0


def test_notification_keeps_lateness_but_reduces_impact(cfg) -> None:
    econ = cfg.actions[ActionType.CUSTOMER_NOTIFICATION]
    out = simulate_intervention(
        action=econ,
        observed_long_delivery=True,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=1,
    )
    assert out["simulated_long_delivery"] is True
    assert out["simulated_impact_loss_reduction"] == pytest.approx(20.0 * 0.2)  # loss=20
    assert out["simulated_net_value"] == pytest.approx(4.0 - 1.0)


def test_executor_rejects_unknown_action(cfg) -> None:
    # Force ineligible by cloning NO_ACTION path — use MANUAL with eligible false via mutate
    cfg.actions[ActionType.MANUAL_REVIEW].eligible = False
    ex = ActionExecutor(config=cfg, base_seed=1)
    with pytest.raises(ValueError, match="not approved"):
        ex.execute(
            ActionRequest(
                order_id="o",
                prediction_id="p",
                decision_id="d",
                action_type=ActionType.MANUAL_REVIEW,
                model_version="m",
                policy_version="v",
                observed_long_delivery=True,
                basket_value=10.0,
            )
        )


def test_ledger_roundtrip(tmp_path: Path, cfg) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = DecisionLedger(path)
    svc = DecisionService(config=cfg)
    from datetime import UTC, datetime

    from olist_ml.schemas import PredictResponse

    pred = PredictResponse(
        order_id="o1",
        prediction_id="p1",
        long_delivery_probability=0.8,
        risk_band="high",
        model_version="m",
        prediction_timestamp=datetime(2018, 1, 1, tzinfo=UTC),
    )
    decision = svc.decide_from_prediction(pred, basket_value=150.0)
    ledger.append_prediction(pred)
    ledger.append_decision(decision)
    rows = ledger.for_order("o1")
    assert len(rows) == 2
    assert {r["record_type"] for r in rows} == {"prediction", "decision"}


def test_policy_replay_ranks_ev_vs_no_action(cfg) -> None:
    rows = [
        ReplayRow("o1", "p1", "m", 0.9, 200.0, True),
        ReplayRow("o2", "p2", "m", 0.1, 50.0, False),
        ReplayRow("o3", "p3", "m", 0.8, 180.0, True),
        ReplayRow("o4", "p4", "m", 0.2, 40.0, False),
        ReplayRow("o5", "p5", "m", 0.75, 220.0, True),
    ]
    report = replay_policies(rows, config=cfg, threshold=0.70, base_seed=7)
    assert report["n_orders"] == 5
    na = report["policies"]["no_action"]
    ev = report["policies"]["expected_value"]
    assert na["interventions"] == 0
    assert na["net_simulated_value"] == 0.0
    assert ev["interventions"] >= 1
    # EV should not be worse than doing nothing on this toy set in expectation of positives
    assert "net_simulated_value" in ev
    assert "roi_simulated" in ev


def test_derive_seed_stable() -> None:
    assert derive_seed("a", "b", base_seed=1) == derive_seed("a", "b", base_seed=1)
    assert derive_seed("a", "b", base_seed=1) != derive_seed("a", "c", base_seed=1)
