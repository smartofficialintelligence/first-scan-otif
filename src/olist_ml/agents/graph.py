"""Compile LangGraph agent-review workflow."""

from __future__ import annotations

from typing import Any, Literal

from olist_ml.agents.nodes import (
    node_choose_action,
    node_execute,
    node_human_gate,
    node_list_actions,
    node_load_context,
    node_score_actions,
)
from olist_ml.agents.state import AgentReviewState


def _route_after_load(state: AgentReviewState) -> Literal["continue", "end_fail"]:
    if state.get("status") == "failed":
        return "end_fail"
    return "continue"


def _route_after_human(state: AgentReviewState) -> Literal["execute", "end_wait", "end_reject"]:
    status = state.get("status")
    if status == "waiting_approval":
        return "end_wait"
    if status == "rejected":
        return "end_reject"
    return "execute"


def build_agent_review_graph():
    """Build StateGraph: context → actions → score → choose → human → execute."""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentReviewState)
    graph.add_node("load_context", node_load_context)
    graph.add_node("list_actions", node_list_actions)
    graph.add_node("score_actions", node_score_actions)
    graph.add_node("choose_action", node_choose_action)
    graph.add_node("human_gate", node_human_gate)
    graph.add_node("execute", node_execute)

    graph.set_entry_point("load_context")
    graph.add_conditional_edges(
        "load_context",
        _route_after_load,
        {"continue": "list_actions", "end_fail": END},
    )
    graph.add_edge("list_actions", "score_actions")
    graph.add_edge("score_actions", "choose_action")
    graph.add_edge("choose_action", "human_gate")
    graph.add_conditional_edges(
        "human_gate",
        _route_after_human,
        {
            "execute": "execute",
            "end_wait": END,
            "end_reject": END,
        },
    )
    graph.add_edge("execute", END)
    return graph.compile()


def run_agent_review(initial: dict[str, Any]) -> dict[str, Any]:
    """Execute the agent-review graph and return final state as a dict."""
    app = build_agent_review_graph()
    result = app.invoke(initial)
    return dict(result)
