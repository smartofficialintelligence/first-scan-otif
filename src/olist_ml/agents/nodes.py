"""LangGraph node implementations — call domain tools only."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from olist_ml.agents.state import AgentReviewState
from olist_ml.decisions.schemas import ActionType, DecisionContext
from olist_ml.decisions.service import DecisionService
from olist_ml.tools import decision_tools as dtools


def _trace(state: AgentReviewState, step: str) -> list[str]:
    return list(state.get("tool_trace") or []) + [step]


def node_load_context(state: AgentReviewState) -> dict[str, Any]:
    """Validate required prediction context (prediction already computed upstream)."""
    required = (
        "order_id",
        "prediction_id",
        "model_version",
        "promise_miss_probability",
        "basket_value",
    )
    missing = [k for k in required if state.get(k) is None]
    if missing:
        return {
            "status": "failed",
            "error": f"Missing fields: {missing}",
            "tool_trace": _trace(state, "load_context:fail"),
        }
    return {
        "status": "running",
        "error": None,
        "tool_trace": _trace(state, "load_context:ok"),
        "decision_id": state.get("decision_id") or str(uuid4()),
    }


def node_list_actions(state: AgentReviewState) -> dict[str, Any]:
    listing = dtools.list_available_actions()
    return {
        "available_actions": listing["actions"],
        "policy_version": listing["policy_version"],
        "tool_trace": _trace(state, "list_available_actions"),
    }


def node_score_actions(state: AgentReviewState) -> dict[str, Any]:
    proba = float(state["promise_miss_probability"])
    basket = float(state["basket_value"])
    values = []
    for row in state.get("available_actions") or []:
        scored = dtools.calculate_action_value(
            action=row["action"],
            probability=proba,
            basket_value=basket,
        )
        values.append(scored["candidate"])
    svc = DecisionService()
    policy = svc.decide(
        DecisionContext(
            order_id=str(state["order_id"]),
            prediction_id=str(state["prediction_id"]),
            model_version=str(state["model_version"]),
            promise_miss_probability=proba,
            basket_value=basket,
            seller_id=state.get("seller_id"),
            remaining_to_promise_days=state.get("remaining_to_promise_days"),
            geo_distance_km=state.get("geo_distance_km"),
            same_state=state.get("same_state"),
            freight_value=state.get("freight_value"),
            p1_score_threshold=state.get("p1_score_threshold"),
            p2_score_threshold=state.get("p2_score_threshold"),
        )
    )
    dtools.get_ledger().append_decision(policy)
    return {
        "action_values": values,
        "policy_recommendation": {
            "recommended_action": policy.recommended_action.value,
            "expected_net_value": policy.expected_net_value,
            "decision_id": policy.decision_id,
            "policy_version": policy.policy_version,
            "requires_agent_review": policy.requires_agent_review,
            "requires_human_approval": policy.requires_human_approval,
            "policy_band": policy.policy_band,
            "upgrade_eligible": policy.upgrade_eligible,
            "upgrade_cost": policy.upgrade_cost,
        },
        "decision_id": policy.decision_id,
        "policy_version": policy.policy_version,
        "tool_trace": _trace(state, "calculate_action_value+recommend_policy_action"),
    }


def node_choose_action(state: AgentReviewState) -> dict[str, Any]:
    """Copy the frozen NOC policy action. The agent does not re-select policy."""
    policy = state.get("policy_recommendation") or {}
    action = str(policy.get("recommended_action") or ActionType.NO_ACTION.value)
    approved = {a["action"] for a in (state.get("available_actions") or [])}
    if approved and action not in approved:
        return {
            "selected_action": ActionType.NO_ACTION.value,
            "agent_rationale": "Rejected invalid action outside approved set.",
            "status": "failed",
            "error": "invalid_action",
            "tool_trace": _trace(state, "choose_action:invalid"),
        }
    band = policy.get("policy_band")
    rationale = (
        f"Executing frozen NOC policy action {action}"
        + (f" (band={band})" if band else "")
        + ". Agent does not re-select policy."
    )
    return {
        "selected_action": action,
        "agent_rationale": rationale,
        "tool_trace": _trace(state, f"choose_action:{action}"),
    }


def node_human_gate(state: AgentReviewState) -> dict[str, Any]:
    """Require explicit approval for spend-risk upgrades, or when the caller flags it."""
    selected = state.get("selected_action") or ActionType.NO_ACTION.value
    if selected == ActionType.NO_ACTION.value:
        return {"tool_trace": _trace(state, "human_gate:skipped"), "human_approved": True}

    policy = state.get("policy_recommendation") or {}
    need = bool(state.get("require_human_approval")) or bool(policy.get("requires_human_approval"))
    if not need:
        return {"tool_trace": _trace(state, "human_gate:skipped"), "human_approved": True}

    approved = state.get("human_approved")
    if approved is True:
        return {"tool_trace": _trace(state, "human_gate:approved"), "status": "running"}
    if approved is False:
        return {
            "status": "rejected",
            "selected_action": ActionType.NO_ACTION.value,
            "agent_rationale": (
                (state.get("agent_rationale") or "") + " Human rejected; forcing NO_ACTION."
            ),
            "tool_trace": _trace(state, "human_gate:rejected"),
        }
    return {
        "status": "waiting_approval",
        "tool_trace": _trace(state, "human_gate:waiting"),
    }


def node_execute(state: AgentReviewState) -> dict[str, Any]:
    if state.get("status") == "waiting_approval":
        return {}
    if not state.get("run_simulation"):
        return {
            "action_result": None,
            "status": "completed",
            "tool_trace": _trace(state, "execute:skipped"),
        }
    if state.get("observed_promise_miss") is None:
        return {
            "status": "failed",
            "error": "observed_promise_miss required when run_simulation=true",
            "tool_trace": _trace(state, "execute:missing_label"),
        }

    action = state.get("selected_action") or ActionType.NO_ACTION.value
    policy = state.get("policy_recommendation") or {}
    result = dtools.execute_simulated_action(
        order_id=str(state["order_id"]),
        prediction_id=str(state["prediction_id"]),
        decision_id=str(state.get("decision_id") or uuid4()),
        action=action,
        model_version=str(state["model_version"]),
        policy_version=str(state.get("policy_version") or "noc-handoff-policy-v1"),
        observed_promise_miss=bool(state["observed_promise_miss"]),
        basket_value=float(state["basket_value"]),
        freight_value=state.get("freight_value"),
        intervention_cost=policy.get("upgrade_cost"),
        persist_ledger=True,
    )
    return {
        "action_result": result,
        "status": "completed",
        "tool_trace": _trace(state, "execute_simulated_action"),
    }
