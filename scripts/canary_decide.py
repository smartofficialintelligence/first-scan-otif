#!/usr/bin/env python3
"""Compare champion vs challenger prediction logs; recommend rollback (never auto-promote)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)

DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")


def _read_logs(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise SystemExit(f"Prediction log not found: {path}")
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _bucket_metrics(rows: list[dict[str, Any]], bucket: str) -> dict[str, Any]:
    subset = [r for r in rows if r.get("traffic_bucket") == bucket]
    n = len(subset)
    if n == 0:
        return {
            "n": 0,
            "error_rate": None,
            "brier": None,
            "mean_abs_error": None,
            "p95_latency_ms": None,
            "http_error_rate": None,
        }

    http_errors = sum(1 for r in subset if (r.get("http_status") or 0) >= 400 or r.get("error_class"))
    latencies = [float(r["latency_ms"]) for r in subset if r.get("latency_ms") is not None]
    p95 = float(np.percentile(latencies, 95)) if latencies else None

    labeled = [
        r
        for r in subset
        if r.get("label_long_delivery") is not None and r.get("proba") is not None
    ]
    brier = None
    mae = None
    error_rate = None
    if labeled:
        y = np.array([int(r["label_long_delivery"]) for r in labeled], dtype=float)
        p = np.array([float(r["proba"]) for r in labeled], dtype=float)
        brier = float(np.mean((p - y) ** 2))
        mae = float(np.mean(np.abs(p - y)))
        preds = (p >= 0.5).astype(int)
        error_rate = float(np.mean(preds != y.astype(int)))

    return {
        "n": n,
        "error_rate": error_rate,
        "brier": brier,
        "mean_abs_error": mae,
        "p95_latency_ms": p95,
        "http_error_rate": http_errors / n,
        "model_versions": sorted({str(r.get("model_version")) for r in subset if r.get("model_version")}),
    }


def decide(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compare error proxies. If challenger is worse → ROLLBACK (100% champion).
    Never auto-promote.
    """
    champion = _bucket_metrics(rows, "champion")
    challenger = _bucket_metrics(rows, "challenger")

    recommendation = "HOLD"
    reasons: list[str] = []
    auto_promote = False

    if challenger["n"] == 0:
        reasons.append("no challenger traffic observed")
        recommendation = "HOLD"
    else:
        # Primary proxy: Brier (or MAE / classification error) when labels present.
        champ_brier = champion.get("brier")
        chal_brier = challenger.get("brier")
        if champ_brier is not None and chal_brier is not None:
            if chal_brier > champ_brier:
                recommendation = "ROLLBACK"
                reasons.append(
                    f"challenger brier {chal_brier:.4f} > champion {champ_brier:.4f}"
                )
            else:
                reasons.append(
                    f"challenger brier {chal_brier:.4f} <= champion {champ_brier:.4f} "
                    "(still requires H4 for promote)"
                )
                recommendation = "HOLD"
        else:
            # Fallback without labels: HTTP error rate + high-risk concentration as proxies.
            champ_http = champion.get("http_error_rate") or 0.0
            chal_http = challenger.get("http_error_rate") or 0.0
            if chal_http > champ_http + 0.01:
                recommendation = "ROLLBACK"
                reasons.append(
                    f"challenger http_error_rate {chal_http:.4f} > champion {champ_http:.4f} + 1pp"
                )
            else:
                # Compare mean |proba - 0.5| inverted quality: worse if closer to random after degrade
                chal_rows = [r for r in rows if r.get("traffic_bucket") == "challenger"]
                champ_rows = [r for r in rows if r.get("traffic_bucket") == "champion"]
                chal_probas = [
                    float(r["proba"]) for r in chal_rows if r.get("proba") is not None
                ]
                champ_probas = [
                    float(r["proba"]) for r in champ_rows if r.get("proba") is not None
                ]
                if chal_probas and champ_probas:
                    # Proxy: challenger with inverted scores tends toward higher mean abs error vs label;
                    # without labels, flag if challenger mean proba is wildly different (drift).
                    chal_mean = float(np.mean(chal_probas))
                    champ_mean = float(np.mean(champ_probas))
                    if abs(chal_mean - champ_mean) > 0.15:
                        recommendation = "ROLLBACK"
                        reasons.append(
                            f"challenger mean_proba {chal_mean:.3f} vs champion {champ_mean:.3f} "
                            "(proxy drift > 0.15); recommend 100% champion"
                        )
                    else:
                        reasons.append("insufficient label signal; HOLD pending H4")
                        recommendation = "HOLD"
                else:
                    reasons.append("no probabilities to compare; HOLD")
                    recommendation = "HOLD"

        # Latency gate (gate-defaults: challenger ≤ champion × 1.25); skip on tiny samples.
        c_lat = champion.get("p95_latency_ms")
        x_lat = challenger.get("p95_latency_ms")
        if (
            champion.get("n", 0) >= 5
            and challenger.get("n", 0) >= 5
            and c_lat
            and x_lat
            and x_lat > c_lat * 1.25
        ):
            recommendation = "ROLLBACK"
            reasons.append(
                f"challenger p95 latency {x_lat:.1f}ms > champion×1.25 ({c_lat * 1.25:.1f})"
            )

    summary = {
        "recommendation": recommendation,
        "traffic_split_recommended": "100% champion" if recommendation == "ROLLBACK" else "90/10 hold",
        "auto_promote": auto_promote,
        "reasons": reasons,
        "champion": champion,
        "challenger": challenger,
        "n_events": len(rows),
        "note": "Never auto-promote. ROLLBACK → set traffic to 100% champion. Promote requires H4.",
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canary decision from prediction logs")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/canary_decision.json"),
        help="Write JSON summary path",
    )
    args = parser.parse_args(argv)
    setup_logging()
    rows = _read_logs(args.log_path)
    summary = decide(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if summary["recommendation"] == "ROLLBACK":
        print("ROLLBACK recommendation: set traffic to 100% champion (no auto-promote).", file=sys.stderr)
    else:
        print(
            "HOLD: do not promote without H4 human approval (never auto-promote).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
