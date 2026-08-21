"""Canary gates recommend only — they must never auto-promote (H4)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "canary_decide", ROOT / "scripts/canary_decide.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p95_latency_is_not_the_mean() -> None:
    canary = _load_module()
    rows = [{"latency_ms": float(i)} for i in range(100)]
    p95 = canary._p95_latency_ms(rows)
    assert p95 == pytest.approx(94.0)
    assert p95 != pytest.approx(sum(range(100)) / 100.0)
    assert canary._p95_latency_ms([]) == 0.0


def test_http_ok_rate_empty_is_zero() -> None:
    canary = _load_module()
    assert canary._http_ok_rate([]) == 0.0
    ok99 = [{"http_status": 200}] * 99 + [{"http_status": 500}]
    assert canary._http_ok_rate(ok99) == pytest.approx(0.99)
    ok98 = [{"http_status": 200}] * 98 + [{"http_status": 500}] * 2
    assert canary._http_ok_rate(ok98) < 0.99


def test_champion_run_id_comes_from_meta_not_a_hardcoded_id(tmp_path: Path) -> None:
    canary = _load_module()
    meta = tmp_path / "model_meta.json"
    meta.write_text(json.dumps({"model_version": "from-meta-not-hardcoded"}), encoding="utf-8")
    assert canary._champion_run_id_from_meta(meta) == "from-meta-not-hardcoded"
    assert canary._champion_run_id_from_meta(tmp_path / "missing.json") == "unknown"
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert canary._champion_run_id_from_meta(bad) == "unknown"


def test_canary_decision_never_auto_promotes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canary = _load_module()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "model_meta.json").write_text(
        json.dumps({"model_version": "champ-from-meta"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        canary,
        "run_evaluate_delayed",
        lambda **_kwargs: {
            "canary_quality_ok": True,
            "n_released": 10,
            "n_log_rows": 10,
            "pr_auc_released": 0.5,
            "champion_pr_auc": 0.5,
            "canary_pr_auc_min": 0.48,
            "quality_alarm": False,
            "canary_delayed_label_gate": "pass",
            "reasons": [],
        },
    )
    log = tmp_path / "pred.jsonl"
    log.write_text(
        "\n".join(json.dumps({"latency_ms": 10.0, "http_status": 200}) for _ in range(20))
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "canary.json"
    canary.main(["--log-path", str(log), "--out", str(out)])
    decision = json.loads(out.read_text(encoding="utf-8"))
    assert decision["auto_promote"] is False
    assert decision["h4_required"] is True
    assert decision["promote"] is True
    assert decision["traffic"] == "hold for H4"
    assert decision["champion_run_id"] == "champ-from-meta"
    assert decision["recommendation"] == "PROMOTE_CANDIDATE"


def test_canary_rollback_still_never_auto_promotes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canary = _load_module()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    monkeypatch.setattr(
        canary,
        "run_evaluate_delayed",
        lambda **_kwargs: {
            "canary_quality_ok": False,
            "n_released": 4,
            "n_log_rows": 20,
            "pr_auc_released": 0.1,
            "champion_pr_auc": 0.5,
            "canary_pr_auc_min": 0.48,
            "quality_alarm": True,
            "canary_delayed_label_gate": "fail",
            "reasons": ["quality"],
        },
    )
    log = tmp_path / "pred.jsonl"
    log.write_text(
        "\n".join(json.dumps({"latency_ms": 500.0, "http_status": 500}) for _ in range(20))
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "canary.json"
    with pytest.raises(SystemExit) as exc:
        canary.main(["--log-path", str(log), "--out", str(out), "--champion-run-id", "cli-id"])
    assert exc.value.code == 1
    decision = json.loads(out.read_text(encoding="utf-8"))
    assert decision["auto_promote"] is False
    assert decision["promote"] is False
    assert decision["champion_run_id"] == "cli-id"
    assert decision["recommendation"] == "ROLLBACK"
