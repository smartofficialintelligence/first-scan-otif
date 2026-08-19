"""Delayed-label quality eval — joins released labels only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss

from olist_ml.monitoring.logs import read_jsonl, released_rows

DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")
DEFAULT_OUT = Path("artifacts/delayed_eval.json")
DEFAULT_META = Path("artifacts/model_meta.json")
PR_AUC_QUALITY_DROP = 0.03
CANARY_PR_AUC_SLACK = 0.02


def load_offline_pr_auc(meta_path: Path = DEFAULT_META) -> float | None:
    """Champion test PR-AUC from the baked model_meta (quality / canary floor)."""
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metrics = payload.get("metrics") or {}
    value = metrics.get("test_pr_auc")
    if value is None:
        return None
    return float(value)


def _proba(row: dict[str, Any]) -> float:
    v = row.get("proba", row.get("promise_miss_probability"))
    return float(v)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 2:
        return {"n": len(rows), "pr_auc": None, "brier": None}
    y = np.array([int(r["label_promise_miss"]) for r in rows], dtype=float)
    p = np.array([_proba(r) for r in rows], dtype=float)
    pr_auc = None
    if len(np.unique(y)) > 1:
        pr_auc = float(average_precision_score(y, p))
    return {
        "n": len(rows),
        "pr_auc": pr_auc,
        "brier": float(brier_score_loss(y, p)),
        "positive_rate": float(y.mean()),
    }


def evaluate_delayed(
    rows: list[dict[str, Any]],
    *,
    baseline_pr_auc: float | None = None,
    champion_pr_auc: float | None = None,
    quality_drop: float = PR_AUC_QUALITY_DROP,
    canary_slack: float = CANARY_PR_AUC_SLACK,
) -> dict[str, Any]:
    released = released_rows(rows)
    overall = _metrics(released)
    champion = _metrics([r for r in released if r.get("traffic_bucket") == "champion"])
    challenger = _metrics([r for r in released if r.get("traffic_bucket") == "challenger"])

    quality_alarm = False
    canary_quality = "insufficient_released_labels"
    canary_quality_ok = False
    reasons: list[str] = []
    current = overall.get("pr_auc")
    if current is not None and baseline_pr_auc is not None:
        drop = float(baseline_pr_auc) - float(current)
        if drop > quality_drop:
            quality_alarm = True
            reasons.append(
                f"delayed-label PR-AUC drop {drop:.4f} > {quality_drop} vs rolling baseline"
            )
    champ_pr = champion.get("pr_auc")
    chal_pr = challenger.get("pr_auc")
    if champ_pr is not None and chal_pr is not None:
        if chal_pr < champ_pr - canary_slack:
            canary_quality = "fail"
            canary_quality_ok = False
            reasons.append(
                f"challenger delayed PR-AUC {chal_pr:.4f} < "
                f"champion {champ_pr:.4f} - {canary_slack}"
            )
        else:
            canary_quality = "pass"
            canary_quality_ok = True
            reasons.append(
                f"challenger delayed PR-AUC {chal_pr:.4f} >= "
                f"champion {champ_pr:.4f} - {canary_slack}"
            )
    elif current is not None and champion_pr_auc is not None:
        floor = float(champion_pr_auc) - canary_slack
        if current < floor:
            canary_quality = "fail"
            canary_quality_ok = False
            reasons.append(
                f"released PR-AUC {current:.4f} < "
                f"champion {champion_pr_auc:.4f} - {canary_slack}"
            )
        else:
            canary_quality = "pass"
            canary_quality_ok = True
            reasons.append(
                f"released PR-AUC {current:.4f} >= "
                f"champion {champion_pr_auc:.4f} - {canary_slack}"
            )
    else:
        reasons.append("insufficient released labels for delayed-label PR-AUC gate")

    return {
        "n_log_rows": len(rows),
        "n_released": len(released),
        "overall": overall,
        "champion": champion,
        "challenger": challenger,
        "quality_alarm": quality_alarm,
        "canary_delayed_label_gate": canary_quality,
        "canary_quality_ok": canary_quality_ok,
        "baseline_pr_auc": baseline_pr_auc,
        "champion_pr_auc": champion_pr_auc,
        "canary_pr_auc_min": (
            None if champion_pr_auc is None else float(champion_pr_auc) - canary_slack
        ),
        "pr_auc_released": current,
        "quality_drop_threshold": quality_drop,
        "canary_pr_auc_slack": canary_slack,
        "reasons": reasons,
        "deploy": False,
        "auto_promote": False,
        "note": "Quality uses released labels only. Instant ground truth is ignored until release.",
    }


def run_evaluate_delayed(
    *,
    log_path: Path = DEFAULT_LOG,
    out_path: Path = DEFAULT_OUT,
    baseline_pr_auc: float | None = None,
    champion_pr_auc: float | None = None,
    meta_path: Path = DEFAULT_META,
) -> dict[str, Any]:
    offline = load_offline_pr_auc(meta_path)
    if baseline_pr_auc is None:
        baseline_pr_auc = offline
    if champion_pr_auc is None:
        champion_pr_auc = offline
    rows = read_jsonl(log_path)
    report = evaluate_delayed(
        rows,
        baseline_pr_auc=baseline_pr_auc,
        champion_pr_auc=champion_pr_auc,
    )
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["log_path"] = str(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
