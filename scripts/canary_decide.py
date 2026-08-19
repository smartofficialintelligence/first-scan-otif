#!/usr/bin/env python3
"""Canary gates: latency, HTTP, and delayed-label ranking vs champion.

Quality uses **released** labels only (``label_released`` after
``release_labels``). Instant historical truth in replay logs is ignored
until that job runs. Never auto-promotes (H4 still required).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from olist_ml.monitoring.delayed_eval import DEFAULT_META, run_evaluate_delayed
from olist_ml.monitoring.logs import load_jsonl

DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")


def _champion_run_id_from_meta(meta_path: Path = DEFAULT_META) -> str:
    """Champion identity comes from the baked model_meta, never a hardcoded id."""
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    return str(payload.get("model_version") or "unknown")


def _p95_latency_ms(rows: list[dict]) -> float:
    values = sorted(float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None)
    if not values:
        return 0.0
    idx = min(len(values) - 1, int(0.95 * (len(values) - 1)))
    return values[idx]


def _http_ok_rate(rows: list[dict]) -> float:
    n = len(rows)
    if n == 0:
        return 0.0
    ok = sum(1 for r in rows if int(r.get("http_status", 0)) == 200)
    return ok / n


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--champion-run-id",
        default=None,
        help="Default: model_version from artifacts/model_meta.json",
    )
    parser.add_argument(
        "--champion-pr-auc",
        type=float,
        default=None,
        help="Default: test_pr_auc from artifacts/model_meta.json (never hardcode)",
    )
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out", type=Path, default=Path("artifacts/canary_decision.json"))
    args = parser.parse_args(argv)
    champion_run_id = args.champion_run_id or _champion_run_id_from_meta()

    rows = load_jsonl(args.log_path)
    latency_p95 = _p95_latency_ms(rows)
    http_ok = _http_ok_rate(rows)
    latency_ok = latency_p95 < 200.0
    http_ok_pass = http_ok >= 0.99

    delayed = run_evaluate_delayed(
        log_path=args.log_path,
        champion_pr_auc=args.champion_pr_auc,
        out_path=Path("artifacts/delayed_eval.json"),
    )
    quality_ok = bool(delayed.get("canary_quality_ok"))
    n_released = int(delayed.get("n_released") or 0)
    n_rows = int(delayed.get("n_log_rows") or 0)

    # Recommendation only — H4 required before any traffic change.
    recommend_promote = latency_ok and http_ok_pass and quality_ok
    decision = {
        "promote": recommend_promote,
        "auto_promote": False,
        "h4_required": True,
        "recommendation": "PROMOTE_CANDIDATE" if recommend_promote else "ROLLBACK",
        "traffic": "100% champion" if not recommend_promote else "hold for H4",
        "champion_run_id": champion_run_id,
        "n_rows": n_rows,
        "n_released": n_released,
        "n_unreleased": n_rows - n_released,
        "latency_p95_ms": round(latency_p95, 2),
        "http_ok_rate": round(http_ok, 4),
        "pr_auc_released": delayed.get("pr_auc_released"),
        "champion_pr_auc": delayed.get("champion_pr_auc"),
        "canary_pr_auc_min": delayed.get("canary_pr_auc_min"),
        "quality_alarm": delayed.get("quality_alarm"),
        "canary_delayed_label_gate": delayed.get("canary_delayed_label_gate"),
        "gates": {
            "latency_p95_lt_200ms": latency_ok,
            "http_ok_rate_ge_0.99": http_ok_pass,
            "delayed_pr_auc_ge_champion_minus_0.02": quality_ok,
        },
        "reasons": delayed.get("reasons") or [],
        "reason": (
            "all gates passed (H4 still required to change traffic)"
            if recommend_promote
            else "hold/rollback: "
            + ", ".join(
                k
                for k, v in {
                    "latency": latency_ok,
                    "http": http_ok_pass,
                    "delayed_label_pr_auc": quality_ok,
                }.items()
                if not v
            )
        ),
        "label_window": "released_only_prediction_ts_plus_7d",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(decision, indent=2) + "\n")
    print(json.dumps(decision, indent=2))
    if not recommend_promote:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
