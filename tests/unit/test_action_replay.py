"""Tests for ActionExecutor, simulation, ledger, and policy replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from olist_ml.actions.executor import ActionExecutor
from olist_ml.actions.schemas import ActionRequest
from olist_ml.decisions.economics import clear_policy_cache, load_policy_economics
from olist_ml.decisions.replay import ReplayRow, replay_policies
from olist_ml.decisions.schemas import ActionType
from olist_ml.decisions.service import DecisionService
from olist_ml.monitoring.metrics import get_metrics
from olist_ml.outcomes.ledger import DecisionLedger
from olist_ml.simulation.intervention import derive_seed, simulate_intervention

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "policy_economics.yaml"


@pytest.fixture()
def cfg():
    clear_policy_cache()
    return load_policy_economics(CONFIG)


def test_simulation_reproducible(cfg) -> None:
    econ = cfg.actions[ActionType.REMAINING_LEG_UPGRADE]
    a = simulate_intervention(
        action=econ,
        observed_promise_miss=True,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=123,
        cost_override=12.0,
    )
    b = simulate_intervention(
        action=econ,
        observed_promise_miss=True,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=123,
        cost_override=12.0,
    )
    assert a == b


def test_upgrade_can_flip_miss_to_on_time(cfg) -> None:
    econ = cfg.actions[ActionType.REMAINING_LEG_UPGRADE]
    successes = 0
    for seed in range(80):
        out = simulate_intervention(
            action=econ,
            observed_promise_miss=True,
            basket_value=100.0,
            loss_cfg=cfg.business_loss,
            seed=seed,
            cost_override=10.0,
        )
        if out["intervention_success"]:
            successes += 1
            assert out["simulated_promise_miss"] is False
            assert out["simulated_gross_avoided_loss"] > 0
            assert out["simulated_days_late"] == 0.0
            assert out["simulated_delay_days_avoided"] == pytest.approx(6.0)
    assert successes > 0


def test_notice_keeps_lateness_but_reduces_impact(cfg) -> None:
    econ = cfg.actions[ActionType.AT_RISK_NOTICE]
    out = simulate_intervention(
        action=econ,
        observed_promise_miss=True,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=1,
        observed_days_late=4.0,
    )
    assert out["simulated_promise_miss"] is True
    assert out["simulated_days_late"] == pytest.approx(4.0)
    assert out["simulated_delay_days_avoided"] == 0.0
    assert out["simulated_impact_loss_reduction"] == pytest.approx(20.0 * 0.20)
    assert out["simulated_net_value"] == pytest.approx(4.0 - 1.0)


def test_upgrade_credits_observed_overrun_on_success(cfg) -> None:
    econ = cfg.actions[ActionType.REMAINING_LEG_UPGRADE]
    out = simulate_intervention(
        action=econ,
        observed_promise_miss=True,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=0,
        cost_override=10.0,
        observed_days_late=9.0,
    )
    if out["intervention_success"]:
        assert out["simulated_days_late"] == 0.0
        assert out["simulated_delay_days_avoided"] == pytest.approx(9.0)
    else:
        assert out["simulated_days_late"] == pytest.approx(9.0)
        assert out["simulated_delay_days_avoided"] == 0.0


def test_on_time_order_has_zero_delay_days(cfg) -> None:
    econ = cfg.actions[ActionType.REMAINING_LEG_UPGRADE]
    out = simulate_intervention(
        action=econ,
        observed_promise_miss=False,
        basket_value=100.0,
        loss_cfg=cfg.business_loss,
        seed=1,
        cost_override=10.0,
    )
    assert out["observed_days_late"] == 0.0
    assert out["simulated_days_late"] == 0.0
    assert out["simulated_delay_days_avoided"] == 0.0


def test_executor_records_process_metrics(cfg) -> None:
    metrics = get_metrics()
    metrics.reset()
    ex = ActionExecutor(config=cfg, base_seed=1)
    ex.execute(
        ActionRequest(
            order_id="o-metrics",
            prediction_id="p",
            decision_id="d",
            action_type=ActionType.NO_ACTION,
            model_version="m",
            policy_version="v",
            observed_promise_miss=False,
            basket_value=10.0,
        )
    )
    snap = metrics.snapshot()["decision"]
    assert snap["executed_action_distribution"]["NO_ACTION"] == 1
    metrics.reset()


def test_executor_rejects_unknown_action(cfg) -> None:
    cfg.actions[ActionType.LATE_NOTICE].eligible = False
    ex = ActionExecutor(config=cfg, base_seed=1)
    with pytest.raises(ValueError, match="not approved"):
        ex.execute(
            ActionRequest(
                order_id="o",
                prediction_id="p",
                decision_id="d",
                action_type=ActionType.LATE_NOTICE,
                model_version="m",
                policy_version="v",
                observed_promise_miss=True,
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
        promise_miss_probability=0.8,
        risk_band="high",
        model_version="m",
        prediction_timestamp=datetime(2018, 1, 1, tzinfo=UTC),
        p1_score_threshold=0.4,
        p2_score_threshold=0.2,
    )
    decision = svc.decide_from_prediction(
        pred,
        basket_value=150.0,
        remaining_to_promise_days=3.0,
        geo_distance_km=200.0,
        same_state=0.0,
        freight_value=25.0,
    )
    ledger.append_prediction(pred)
    ledger.append_decision(decision)
    rows = ledger.for_order("o1")
    assert len(rows) == 2
    assert {r["record_type"] for r in rows} == {"prediction", "decision"}


def test_policy_replay_ranks_noc_vs_no_action(cfg) -> None:
    rows = [
        ReplayRow("o1", "p1", "m", 0.9, 200.0, True, remaining_to_promise_days=3.0),
        ReplayRow("o2", "p2", "m", 0.1, 50.0, False, remaining_to_promise_days=4.0),
        ReplayRow("o3", "p3", "m", 0.8, 180.0, True, remaining_to_promise_days=3.0),
        ReplayRow("o4", "p4", "m", 0.2, 40.0, False, remaining_to_promise_days=11.0),
        ReplayRow("o5", "p5", "m", 0.75, 220.0, True, remaining_to_promise_days=2.0),
    ]
    report = replay_policies(rows, config=cfg, threshold=0.70, base_seed=7)
    assert report["n_orders"] == 5
    na = report["policies"]["no_action"]
    noc = report["policies"]["noc"]
    assert na["interventions"] == 0
    assert na["net_simulated_value"] == 0.0
    assert noc["interventions"] >= 1
    assert "net_simulated_value" in noc
    assert "roi_simulated" in noc
    assert "simulated_delay_days_avoided" in noc
    assert noc["simulated_delay_days_avoided"] >= 0.0
    assert "headline" in report["business_sim"]
    assert report["business_sim"]["n_actions"] == 5


def test_derive_seed_stable() -> None:
    assert derive_seed("a", "b", base_seed=1) == derive_seed("a", "b", base_seed=1)
    assert derive_seed("a", "b", base_seed=1) != derive_seed("a", "c", base_seed=1)


def test_noc_replay_reproducible_across_runs(cfg) -> None:
    """Same rows + base_seed must give identical NOC results — the executor seed
    derives from decision_id, so replay must not mint a fresh uuid per run."""
    rows = [
        ReplayRow("o1", "p1", "m", 0.9, 200.0, True, remaining_to_promise_days=3.0),
        ReplayRow("o2", "p2", "m", 0.85, 180.0, True, remaining_to_promise_days=2.0),
        ReplayRow("o3", "p3", "m", 0.8, 220.0, False, remaining_to_promise_days=3.0),
        ReplayRow("o4", "p4", "m", 0.75, 150.0, True, remaining_to_promise_days=1.0),
    ]
    first = replay_policies(rows, config=cfg, threshold=0.70, base_seed=7)
    second = replay_policies(rows, config=cfg, threshold=0.70, base_seed=7)
    for key in (
        "net_simulated_value",
        "simulated_misses_prevented",
        "simulated_delay_days_avoided",
        "roi_simulated",
        "intervention_spend",
    ):
        assert first["policies"]["noc"][key] == second["policies"]["noc"][key], key
