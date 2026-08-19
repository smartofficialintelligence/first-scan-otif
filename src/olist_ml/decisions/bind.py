"""Bind simulated execution to a frozen policy decision."""

from __future__ import annotations

from olist_ml.outcomes.ledger import DecisionLedger


class PolicyActionMismatch(ValueError):
    """Caller asked to execute an action other than the frozen policy decision."""


def latest_decision(ledger: DecisionLedger, decision_id: str) -> dict | None:
    rows = [
        r
        for r in ledger.read_all()
        if r.get("record_type") == "decision" and r.get("decision_id") == decision_id
    ]
    return rows[-1] if rows else None


def latest_prediction(ledger: DecisionLedger, prediction_id: str) -> dict | None:
    rows = [
        r
        for r in ledger.read_all()
        if r.get("record_type") == "prediction" and r.get("prediction_id") == prediction_id
    ]
    return rows[-1] if rows else None


def assert_action_matches_policy(
    ledger: DecisionLedger,
    *,
    decision_id: str,
    action: str,
) -> dict:
    """Return the decision row, or raise if the action is not the frozen policy."""
    row = latest_decision(ledger, decision_id)
    if row is None:
        raise PolicyActionMismatch(
            f"No policy decision for decision_id={decision_id}; "
            "call recommend_policy_action / POST /v1/decision first"
        )
    recommended = str(row.get("recommended_action") or "")
    if recommended != action:
        raise PolicyActionMismatch(
            f"Action {action} is not the frozen policy action {recommended} "
            f"for decision_id={decision_id}"
        )
    return row
