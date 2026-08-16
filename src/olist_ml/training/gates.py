"""Offline promotion gates (candidate vs champion). See docs/gate-defaults.md."""

from __future__ import annotations

from typing import Any

PR_AUC_TOLERANCE = 0.01
BRIER_TOLERANCE = 0.02
ECE_ABSOLUTE_MAX = 0.08
ECE_TOLERANCE = 0.02


def _get_metric(metrics: dict[str, Any], *keys: str) -> float | None:
    """Resolve metric by preferred key order (e.g. pr_auc, test_pr_auc)."""
    for key in keys:
        if key in metrics and metrics[key] is not None:
            return float(metrics[key])
    # Allow prefixed lookup: any key ending with _pr_auc etc.
    suffixes = keys
    for k, v in metrics.items():
        for suffix in suffixes:
            if k == suffix or k.endswith(f"_{suffix}"):
                if v is not None:
                    return float(v)
    return None


def offline_promotion_checks(
    candidate_metrics: dict[str, Any],
    champion_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Offline H3-style checks before APPROVED_FOR_CANARY.

    Primary rule (M4): PR-AUC within 0.01 of champion if champion exists;
    else pass if pr_auc is present. Additional Brier/ECE checks from
    gate-defaults.md apply when those metrics are available.
    """
    reasons: list[str] = []
    passed = True

    cand_pr = _get_metric(candidate_metrics, "pr_auc", "test_pr_auc")
    if cand_pr is None:
        return {"passed": False, "reasons": ["missing candidate pr_auc"]}

    if champion_metrics is None:
        reasons.append("no champion; pr_auc present — pass")
    else:
        champ_pr = _get_metric(champion_metrics, "pr_auc", "test_pr_auc")
        if champ_pr is None:
            reasons.append("champion missing pr_auc; candidate pr_auc present — pass")
        elif cand_pr < champ_pr - PR_AUC_TOLERANCE:
            passed = False
            reasons.append(
                f"PR-AUC {cand_pr:.4f} < champion {champ_pr:.4f} − {PR_AUC_TOLERANCE}"
            )
        else:
            reasons.append(
                f"PR-AUC {cand_pr:.4f} within {PR_AUC_TOLERANCE} of champion {champ_pr:.4f}"
            )

        cand_brier = _get_metric(candidate_metrics, "brier", "test_brier")
        champ_brier = _get_metric(champion_metrics, "brier", "test_brier")
        if cand_brier is not None and champ_brier is not None:
            if cand_brier > champ_brier + BRIER_TOLERANCE:
                passed = False
                reasons.append(
                    f"Brier {cand_brier:.4f} > champion {champ_brier:.4f} + {BRIER_TOLERANCE}"
                )
            else:
                reasons.append(
                    f"Brier {cand_brier:.4f} within {BRIER_TOLERANCE} of champion"
                )

        cand_ece = _get_metric(candidate_metrics, "ece", "test_ece")
        champ_ece = _get_metric(champion_metrics, "ece", "test_ece")
        if cand_ece is not None:
            ece_ok = cand_ece <= ECE_ABSOLUTE_MAX
            if champ_ece is not None:
                ece_ok = ece_ok or cand_ece <= champ_ece + ECE_TOLERANCE
            if not ece_ok:
                passed = False
                reasons.append(
                    f"ECE {cand_ece:.4f} exceeds {ECE_ABSOLUTE_MAX} "
                    f"(and champion+{ECE_TOLERANCE} if available)"
                )
            else:
                reasons.append(f"ECE {cand_ece:.4f} within gate defaults")

    return {"passed": passed, "reasons": reasons}
