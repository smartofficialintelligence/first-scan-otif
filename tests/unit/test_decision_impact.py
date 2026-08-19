"""Tests for simulated policy-impact rollup copy."""

from __future__ import annotations

import json
from pathlib import Path

from olist_ml.monitoring.export import export_monitoring_snapshot
from olist_ml.outcomes.impact import (
    format_action_mix,
    render_impact_markdown,
    summarize_from_replay_policy,
    summarize_simulated_impact,
)


def test_empty_ledger_has_explicit_headline() -> None:
    report = summarize_simulated_impact([])
    assert report["n_actions"] == 0
    assert report["moved_late_to_on_time"] == 0
    assert report["causal_roi_claim_allowed"] is False
    assert report["source"] == "decision_ledger"
    assert "No simulated actions" in report["headline"]


def test_rollup_counts_actions_spend_and_late_to_ontime() -> None:
    rows = [
        {"record_type": "decision", "recommended_action": "REMAINING_LEG_UPGRADE"},
        {
            "record_type": "action",
            "action_type": "REMAINING_LEG_UPGRADE",
            "simulated_cost": 12.5,
            "simulated_net_value": 8.0,
            "observed_promise_miss": True,
            "simulated_promise_miss": False,
            "simulated_delay_days_avoided": 6.0,
        },
        {
            "record_type": "action",
            "action_type": "AT_RISK_NOTICE",
            "simulated_cost": 1.0,
            "simulated_net_value": -1.0,
            "observed_promise_miss": True,
            "simulated_promise_miss": True,
            "simulated_delay_days_avoided": 0.0,
        },
        {
            "record_type": "action",
            "action_type": "NO_ACTION",
            "simulated_cost": 0.0,
            "simulated_net_value": 0.0,
            "observed_promise_miss": False,
            "simulated_promise_miss": False,
            "simulated_delay_days_avoided": 0.0,
        },
        {
            "record_type": "action",
            "action_type": "LATE_NOTICE",
            "simulated_cost": 1.0,
            "simulated_net_value": 0.5,
            "observed_promise_miss": True,
            "simulated_promise_miss": True,
            "simulated_delay_days_avoided": 0.0,
        },
    ]
    report = summarize_simulated_impact(rows)
    assert report["n_actions"] == 4
    assert report["interventions"] == 3
    assert report["action_distribution"]["REMAINING_LEG_UPGRADE"] == 1
    assert report["action_distribution"]["AT_RISK_NOTICE"] == 1
    assert report["action_distribution"]["LATE_NOTICE"] == 1
    assert report["action_distribution"]["NO_ACTION"] == 1
    assert report["observed_late_deliveries"] == 3
    assert report["simulated_still_late"] == 2
    assert report["moved_late_to_on_time"] == 1
    assert report["simulated_delay_days_avoided"] == 6.0
    assert report["intervention_spend_simulated"] == 14.5
    assert report["net_value_simulated"] == 7.5
    assert "1 remaining-leg upgrade" in report["headline"]
    assert "moved 1 delivery from late to on-time" in report["headline"]
    assert "$14.50" in report["headline"]

    md = render_impact_markdown(report)
    assert "Moved late → on-time: **1**" in md
    assert "econ-sim-v3" in md


def test_summarize_from_replay_policy_uses_holdout_scope() -> None:
    report = summarize_from_replay_policy(
        {
            "action_distribution": {
                "REMAINING_LEG_UPGRADE": 12,
                "AT_RISK_NOTICE": 40,
                "LATE_NOTICE": 3,
                "NO_ACTION": 100,
            },
            "observed_promise_misses": 20,
            "simulated_promise_misses": 16,
            "simulated_misses_prevented": 4,
            "intervention_spend": 87.5,
            "net_simulated_value": 12.3,
            "simulated_delay_days_avoided": 24.0,
        },
        n_orders=155,
    )
    assert report["source"] == "policy_replay:noc"
    assert report["moved_late_to_on_time"] == 4
    assert "155-order holdout replay" in report["narrative"]
    assert "spent $87.50 to do it" in report["headline"]


def test_format_action_mix_order_and_plurals() -> None:
    text = format_action_mix(
        {
            "NO_ACTION": 100,
            "REMAINING_LEG_UPGRADE": 12,
            "AT_RISK_NOTICE": 40,
            "LATE_NOTICE": 3,
        }
    )
    assert text == (
        "3 late notices, 40 at-risk notices, 12 remaining-leg upgrades, and 100 no-action"
    )


def test_export_monitoring_includes_ledger_business_sim(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "record_type": "action",
                "action_type": "REMAINING_LEG_UPGRADE",
                "simulated_cost": 10.0,
                "simulated_net_value": 5.0,
                "observed_promise_miss": True,
                "simulated_promise_miss": False,
                "simulated_delay_days_avoided": 4.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    snap = export_monitoring_snapshot(
        log_path=tmp_path / "missing_logs.jsonl",
        alarm_path=tmp_path / "missing_alarm.json",
        delayed_path=tmp_path / "missing_delayed.json",
        ledger_path=ledger,
        out_path=tmp_path / "dash.json",
    )
    assert snap["business_sim"]["moved_late_to_on_time"] == 1
    assert snap["business_sim"]["intervention_spend_simulated"] == 10.0
    assert "Performed" in snap["business_sim"]["headline"]
