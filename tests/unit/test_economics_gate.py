"""Tests for H9/H10 economics gate + optional LangSmith status."""

from __future__ import annotations

from olist_ml.agents.tracing import configure_tracing, tracing_enabled
from olist_ml.decisions.economics import clear_policy_cache, load_policy_economics


def test_economics_gate_defaults_pending() -> None:
    clear_policy_cache()
    cfg = load_policy_economics()
    assert cfg.economics_gate.status == "pending_approval"
    assert not cfg.economics_gate.is_approved
    assert cfg.routing.real_external_execution_enabled is False


def test_tracing_disabled_without_key(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    assert tracing_enabled() is False
    status = configure_tracing()
    assert status["enabled"] is False


def test_tracing_respects_explicit_disable(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    assert tracing_enabled() is False
