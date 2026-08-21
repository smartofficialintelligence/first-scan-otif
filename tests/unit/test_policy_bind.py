"""Simulated execute is bound to the frozen policy decision, not a caller-chosen action."""

from __future__ import annotations

import pytest

from olist_ml.decisions.bind import PolicyActionMismatch, assert_action_matches_policy
from olist_ml.outcomes.ledger import DecisionLedger


def test_bind_requires_an_existing_decision(tmp_path) -> None:
    ledger = DecisionLedger(tmp_path / "ledger.jsonl")
    with pytest.raises(PolicyActionMismatch, match="No policy decision"):
        assert_action_matches_policy(
            ledger, decision_id="missing", action="NO_ACTION"
        )


def test_bind_rejects_action_other_than_frozen_policy(tmp_path) -> None:
    ledger = DecisionLedger(tmp_path / "ledger.jsonl")
    ledger.append_decision({"decision_id": "d1", "recommended_action": "NO_ACTION"})
    with pytest.raises(PolicyActionMismatch, match="not the frozen policy"):
        assert_action_matches_policy(
            ledger, decision_id="d1", action="REMAINING_LEG_UPGRADE"
        )
    row = assert_action_matches_policy(ledger, decision_id="d1", action="NO_ACTION")
    assert row["decision_id"] == "d1"


def test_bind_uses_the_latest_decision_row(tmp_path) -> None:
    """A superseded recommend must not leave execute bound to the first write."""
    ledger = DecisionLedger(tmp_path / "ledger.jsonl")
    ledger.append_decision({"decision_id": "d1", "recommended_action": "NO_ACTION"})
    ledger.append_decision({"decision_id": "d1", "recommended_action": "AT_RISK_NOTICE"})
    row = assert_action_matches_policy(
        ledger, decision_id="d1", action="AT_RISK_NOTICE"
    )
    assert row["recommended_action"] == "AT_RISK_NOTICE"
    with pytest.raises(PolicyActionMismatch):
        assert_action_matches_policy(ledger, decision_id="d1", action="NO_ACTION")
