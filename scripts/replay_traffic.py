#!/usr/bin/env python3
"""Replay holdout traffic through PredictionService (in-process) or HTTP API."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from olist_ml.canary.split import traffic_bucket_for_order
from olist_ml.config import Settings, get_settings
from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.build import build_feature_table
from olist_ml.inference.predictor import PredictionService
from olist_ml.logging import get_logger, setup_logging
from olist_ml.schemas import PredictRequest

logger = get_logger(__name__)

DEFAULT_HOLDOUT = Path("artifacts/replay_holdout.csv")
DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")


def _build_holdout_from_fixtures(data_dir: Path, settings: Settings) -> pd.DataFrame:
    tables = load_olist_tables(data_dir)
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)
    splits = temporal_split(
        features,
        time_col="handoff_ts",
        valid_fraction=settings.valid_fraction,
        test_fraction=settings.test_fraction,
        replay_fraction=settings.replay_fraction,
    )
    return splits.replay_holdout


def load_replay_frame(
    holdout_path: Path,
    *,
    data_dir: Path,
    settings: Settings,
) -> pd.DataFrame:
    if holdout_path.exists():
        logger.info("Loading holdout from %s", holdout_path)
        return pd.read_csv(holdout_path)
    logger.info("Holdout missing; building from fixtures at %s", data_dir)
    frame = _build_holdout_from_fixtures(data_dir, settings)
    holdout_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(holdout_path, index=False)
    return frame


def row_to_request(row: pd.Series) -> PredictRequest:
    purchase = pd.Timestamp(row.get("order_purchase_timestamp") or row.get("prediction_ts"))
    if purchase.tzinfo is None:
        purchase = purchase.tz_localize("UTC")
    pred_ts = pd.Timestamp(row.get("prediction_ts") or purchase)
    if pred_ts.tzinfo is None:
        pred_ts = pred_ts.tz_localize("UTC")

    seller_id = str(row.get("seller_id") or row.get("primary_seller_id") or "unknown")
    payload: dict[str, Any] = {
        "order_id": str(row["order_id"]),
        "seller_id": seller_id,
        "purchase_timestamp": purchase.to_pydatetime(),
        "prediction_timestamp": pred_ts.to_pydatetime(),
        "item_count": int(row.get("item_count", 1) or 1),
        "basket_value": float(row.get("basket_value", 0.0) or 0.0),
        "freight_value": float(row.get("freight_value", 0.0) or 0.0),
        "seller_count": int(row.get("seller_count", 1) or 1),
        "category_count": int(row.get("category_count", 1) or 1),
        "payment_type_primary": str(row.get("payment_type_primary") or "unknown"),
        "installment_count": int(row.get("installment_count", 1) or 1),
        "estimated_delivery_horizon_days": float(
            row.get("estimated_delivery_horizon_days", 0.0) or 0.0
        ),
        "customer_state": str(row.get("customer_state") or "unknown"),
        "seller_state_primary": str(row.get("seller_state_primary") or "unknown"),
        "geo_distance_km": float(row.get("geo_distance_km", 0.0) or 0.0),
    }
    for key in (
        "handling_days",
        "remaining_to_promise_days",
        "handling_frac_of_promise",
        "limit_miss",
        "same_state",
        "seller_order_count_7d",
        "seller_order_count_30d",
        "seller_order_count_90d",
        "seller_late_rate_7d",
        "seller_late_rate_30d",
        "seller_late_rate_90d",
    ):
        if key in row and pd.notna(row[key]):
            payload[key] = float(row[key])
    return PredictRequest.model_validate(payload)


def _predict_inprocess(service: PredictionService, request: PredictRequest) -> dict[str, Any]:
    t0 = time.perf_counter()
    resp = service.predict_one(request)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "order_id": resp.order_id,
        "promise_miss_probability": resp.promise_miss_probability,
        "risk_band": resp.risk_band,
        "model_version": resp.model_version,
        "latency_ms": latency_ms,
        "http_status": 200,
        "error_class": None,
    }


def _predict_http(
    client: httpx.Client,
    base_url: str,
    request: PredictRequest,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = client.post(base_url, json=json.loads(request.model_dump_json()))
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if r.status_code >= 400:
            return {
                "order_id": request.order_id,
                "promise_miss_probability": None,
                "risk_band": None,
                "model_version": None,
                "latency_ms": latency_ms,
                "http_status": r.status_code,
                "error_class": "http_error",
            }
        body = r.json()
        return {
            "order_id": body.get("order_id", request.order_id),
            "promise_miss_probability": body.get("promise_miss_probability"),
            "risk_band": body.get("risk_band"),
            "model_version": body.get("model_version"),
            "latency_ms": latency_ms,
            "http_status": r.status_code,
            "error_class": None,
        }
    except Exception as exc:  # noqa: BLE001 — continue replay on transport errors
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "order_id": request.order_id,
            "promise_miss_probability": None,
            "risk_band": None,
            "model_version": None,
            "latency_ms": latency_ms,
            "http_status": 0,
            "error_class": type(exc).__name__,
        }


def _meta_for_model(model_path: Path, explicit: Path | None) -> Path:
    if explicit is not None and explicit.exists():
        return explicit
    sibling = Path(str(model_path).replace(".joblib", "_meta.json"))
    return sibling


def run_replay(
    *,
    holdout_path: Path = DEFAULT_HOLDOUT,
    log_path: Path = DEFAULT_LOG,
    data_dir: Path = Path("data/fixtures"),
    base_url: str = "http://127.0.0.1:8080/v1/predict",
    inprocess: bool = True,
    scenario: str = "baseline",
    seed: int = 42,
    max_events: int = 2000,
    champion_model: Path = Path("artifacts/model.joblib"),
    champion_meta: Path = Path("artifacts/model_meta.json"),
    challenger_model: Path | None = Path("artifacts/model_challenger_bad.joblib"),
    challenger_meta: Path | None = Path("artifacts/model_challenger_bad_meta.json"),
    use_challenger: bool = True,
) -> Path:
    """
    Replay holdout events.

    Attribution: ``traffic_bucket`` = hash(order_id) % 10 → challenger if 0 else champion.
    When ``inprocess`` and a challenger artifact exists, challenger-bucket events use it.
    """
    setup_logging()
    settings = get_settings()
    frame = load_replay_frame(holdout_path, data_dir=data_dir, settings=settings)
    if frame.empty:
        raise SystemExit("Replay holdout is empty")

    time_col = "handoff_ts" if "handoff_ts" in frame.columns else "prediction_ts"
    ordered = frame.sample(frac=1.0, random_state=seed).sort_values(
        time_col, kind="mergesort"
    )
    if len(ordered) > max_events:
        ordered = ordered.iloc[:max_events]

    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()

    champion_svc: PredictionService | None = None
    challenger_svc: PredictionService | None = None
    client: httpx.Client | None = None

    if inprocess:
        champion_svc = PredictionService(settings)
        champion_svc.load(champion_model, champion_meta)
        if not champion_svc.ready:
            raise SystemExit(f"Champion model not ready at {champion_model}")
        if use_challenger and challenger_model is not None and challenger_model.exists():
            meta_path = _meta_for_model(challenger_model, challenger_meta)
            challenger_svc = PredictionService(settings)
            challenger_svc.load(challenger_model, meta_path)
            if not challenger_svc.ready:
                logger.warning("Challenger failed to load; serving champion for all buckets")
                challenger_svc = None
    else:
        client = httpx.Client(timeout=30.0)

    n = 0
    with log_path.open("w", encoding="utf-8") as fh:
        for _, row in ordered.iterrows():
            request = row_to_request(row)
            traffic_bucket = traffic_bucket_for_order(request.order_id)
            promise_label = None
            if "promise_miss" in row and pd.notna(row["promise_miss"]):
                promise_label = int(row["promise_miss"])
            long_label = None
            if "long_delivery" in row and pd.notna(row["long_delivery"]):
                long_label = int(row["long_delivery"])

            if inprocess:
                assert champion_svc is not None
                if traffic_bucket == "challenger" and challenger_svc is not None:
                    pred = _predict_inprocess(challenger_svc, request)
                else:
                    pred = _predict_inprocess(champion_svc, request)
            else:
                assert client is not None
                pred = _predict_http(client, base_url, request)

            record = {
                "event_id": f"{scenario}-{request.order_id}",
                "order_id": request.order_id,
                "snapshot_id": None,
                "scenario": scenario,
                "request_ts": datetime.now(UTC).isoformat(),
                "model_version": pred.get("model_version"),
                "promise_miss_probability": pred.get("promise_miss_probability"),
                "proba": pred.get("promise_miss_probability"),
                "risk_band": pred.get("risk_band"),
                "latency_ms": pred.get("latency_ms"),
                "http_status": pred.get("http_status"),
                "error_class": pred.get("error_class"),
                "traffic_bucket": traffic_bucket,
                "label_promise_miss": promise_label,
                "label_long_delivery": long_label,
                "seed": seed,
            }
            fh.write(json.dumps(record, default=str) + "\n")
            n += 1

    if client is not None:
        client.close()
    logger.info("Wrote %s prediction log rows → %s", n, log_path)
    return log_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Replay holdout traffic for canary demos")
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--data-dir", type=Path, default=Path("data/fixtures"))
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://127.0.0.1:8080/v1/predict",
        help="HTTP predict URL when --inprocess is false",
    )
    parser.add_argument(
        "--inprocess",
        type=lambda s: str(s).lower() not in {"0", "false", "no"},
        default=True,
        help="Use local PredictionService (default True; no server required)",
    )
    parser.add_argument("--scenario", type=str, default="baseline")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-events", type=int, default=2000)
    parser.add_argument("--champion-model", type=Path, default=Path("artifacts/model.joblib"))
    parser.add_argument("--champion-meta", type=Path, default=Path("artifacts/model_meta.json"))
    parser.add_argument(
        "--challenger-model",
        type=Path,
        default=Path("artifacts/model_challenger_bad.joblib"),
    )
    parser.add_argument(
        "--challenger-meta",
        type=Path,
        default=Path("artifacts/model_challenger_bad_meta.json"),
    )
    parser.add_argument(
        "--no-challenger",
        action="store_true",
        help="Serve champion artifact for all buckets (attribution still 90/10)",
    )
    args = parser.parse_args(argv)
    run_replay(
        holdout_path=args.holdout,
        log_path=args.log_path,
        data_dir=args.data_dir,
        base_url=args.base_url,
        inprocess=bool(args.inprocess),
        scenario=args.scenario,
        seed=args.seed,
        max_events=args.max_events,
        champion_model=args.champion_model,
        champion_meta=args.champion_meta,
        challenger_model=None if args.no_challenger else args.challenger_model,
        challenger_meta=None if args.no_challenger else args.challenger_meta,
        use_challenger=not args.no_challenger,
    )


if __name__ == "__main__":
    main()
