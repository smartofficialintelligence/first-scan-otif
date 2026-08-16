"""LangGraph node implementations — call domain tools only."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from olist_ml.agents.state import AgentReviewState
from olist_ml.decisions.schemas import ActionType
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
        "long_delivery_probability",
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
    proba = float(state["long_delivery_probability"])
    basket = float(state["basket_value"])
    values = []
    for row in state.get("available_actions") or []:
        scored = dtools.calculate_action_value(
            action=row["action"],
            long_delivery_probability=proba,
            basket_value=basket,
        )
        values.append(scored["candidate"])
    # Also capture deterministic policy recommendation for comparison.
    svc = DecisionService()
    from olist_ml.decisions.schemas import DecisionContext

    policy = svc.decide(
        DecisionContext(
            order_id=str(state["order_id"]),
            prediction_id=str(state["prediction_id"]),
            model_version=str(state["model_version"]),
            long_delivery_probability=proba,
            basket_value=basket,
            seller_id=state.get("seller_id"),
        )
    )
    return {
        "action_values": values,
        "policy_recommendation": {
            "recommended_action": policy.recommended_action.value,
            "expected_net_value": policy.expected_net_value,
            "decision_id": policy.decision_id,
            "policy_version": policy.policy_version,
            "requires_agent_review": policy.requires_agent_review,
        },
        "decision_id": policy.decision_id,
        "policy_version": policy.policy_version,
        "tool_trace": _trace(state, "calculate_action_value+recommend_policy_action"),
    }


def node_choose_action(state: AgentReviewState) -> dict[str, Any]:
    """
    Bounded agent choice: only approved actions; prefer max EV;
    if top-two EV within $1, prefer lower cost (cautious agent).
    """
    values = list(state.get("action_values") or [])
    if not values:
        return {
            "selected_action": ActionType.NO_ACTION.value,
            "agent_rationale": "No scored actions; defaulting to NO_ACTION.",
            "tool_trace": _trace(state, "choose_action:empty"),
        }

    approved = {a["action"] for a in (state.get("available_actions") or [])}
    candidates = [v for v in values if v["action"] in approved and v["expected_net_value"] > 0]
    if not candidates:
        return {
            "selected_action": ActionType.NO_ACTION.value,
            "agent_rationale": "No positive-EV approved action; selecting NO_ACTION.",
            "tool_trace": _trace(state, "choose_action:no_positive_ev"),
        }

    candidates.sort(
        key=lambda v: (v["expected_net_value"], -v["expected_intervention_cost"]),
        reverse=True,
    )
    best = candidates[0]
    if len(candidates) > 1:
        second = candidates[1]
        if best["expected_net_value"] - second["expected_net_value"] <= 1.0:
            # Prefer cheaper when nearly tied.
            tied = [best, second]
            chosen = min(tied, key=lambda v: v["expected_intervention_cost"])
            rationale = (
                f"Top actions close in EV ({best['action']}={best['expected_net_value']:.2f} vs "
                f"{second['action']}={second['expected_net_value']:.2f}); "
                f"agent selected lower-cost {chosen['action']}."
            )
            best = chosen
        else:
            rationale = (
                f"Selected {best['action']} with highest expected_net_value="
                f"{best['expected_net_value']:.2f} from tool-scored candidates."
            )
    else:
        rationale = (
            f"Selected sole positive-EV action {best['action']} "
            f"(EV={best['expected_net_value']:.2f})."
        )

    policy = state.get("policy_recommendation") or {}
    if policy.get("recommended_action") and policy["recommended_action"] != best["action"]:
        rationale += (
            f" Differs from deterministic policy ({policy['recommended_action']}) "
            "due to near-tie cost preference."
        )

    if best["action"] not in approved:
        return {
            "selected_action": ActionType.NO_ACTION.value,
            "agent_rationale": "Rejected invalid action outside approved set.",
            "status": "failed",
            "error": "invalid_action",
            "tool_trace": _trace(state, "choose_action:invalid"),
        }

    return {
        "selected_action": best["action"],
        "agent_rationale": rationale,
        "tool_trace": _trace(state, f"choose_action:{best['action']}"),
    }


def node_human_gate(state: AgentReviewState) -> dict[str, Any]:
    """D10: require explicit approval for high-value / high-cost selections when flagged."""
    if not state.get("require_human_approval"):
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
    # Pending — graph interrupt path sets status waiting_approval
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
    if state.get("observed_long_delivery") is None:
        return {
            "status": "failed",
            "error": "observed_long_delivery required when run_simulation=true",
            "tool_trace": _trace(state, "execute:missing_label"),
        }

    action = state.get("selected_action") or ActionType.NO_ACTION.value
    result = dtools.execute_simulated_action(
        order_id=str(state["order_id"]),
        prediction_id=str(state["prediction_id"]),
        decision_id=str(state.get("decision_id") or uuid4()),
        action=action,
        model_version=str(state["model_version"]),
        policy_version=str(state.get("policy_version") or "expected-value-policy-v1"),
        observed_long_delivery=bool(state["observed_long_delivery"]),
        basket_value=float(state["basket_value"]),
        persist_ledger=True,
    )
    return {
        "action_result": result,
        "status": "completed",
        "tool_trace": _trace(state, "execute_simulated_action"),
    }
