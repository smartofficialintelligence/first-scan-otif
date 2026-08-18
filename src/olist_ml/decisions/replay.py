"""Offline policy replay comparing NO_ACTION / threshold / NOC bands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from olist_ml.actions.executor import ActionExecutor
from olist_ml.decisions.economics import PolicyEconomicsConfig, load_policy_economics
from olist_ml.decisions.schemas import ActionType, DecisionContext
from olist_ml.decisions.service import DecisionService

PolicyName = Literal["no_action", "threshold", "noc"]


@dataclass
class ReplayRow:
    order_id: str
    prediction_id: str
    model_version: str
    promise_miss_probability: float
    basket_value: float
    observed_promise_miss: bool
    remaining_to_promise_days: float | None = 5.0
    geo_distance_km: float | None = 150.0
    same_state: float | None = 0.0
    freight_value: float | None = 15.0
    p1_score_threshold: float | None = None
    p2_score_threshold: float | None = None


def _threshold_action(probability: float, threshold: float = 0.70) -> ActionType:
    return ActionType.AT_RISK_NOTICE if probability > threshold else ActionType.NO_ACTION


def replay_policies(
    rows: list[ReplayRow],
    *,
    config: PolicyEconomicsConfig | None = None,
    config_path: str | None = None,
    threshold: float = 0.70,
    base_seed: int = 42,
) -> dict[str, Any]:
    """
    Run three policies on the same historical rows with seeded simulation.

    Financial outputs are labeled simulated.
    """
    cfg = config or load_policy_economics(config_path)
    decision_svc = DecisionService(config=cfg)
    executor = ActionExecutor(config=cfg, base_seed=base_seed)

    summaries: dict[str, Any] = {
        "n_orders": len(rows),
        "assumptions_disclaimer": cfg.assumptions_disclaimer,
        "policy_version": cfg.policy_version,
        "policy_config_version": cfg.policy_config_version,
        "policies": {},
    }

    for policy in ("no_action", "threshold", "noc"):
        interventions = 0
        spend = 0.0
        gross_avoided = 0.0
        net_value = 0.0
        simulated_misses = 0
        observed_misses = 0
        action_counts: dict[str, int] = {}
        true_pos_interventions = 0
        flagged_misses = 0

        for row in rows:
            observed_misses += int(row.observed_promise_miss)
            upgrade_cost = None
            freight = row.freight_value
            if policy == "no_action":
                action = ActionType.NO_ACTION
                decision_id = f"replay-na-{row.order_id}"
                policy_version = "no-action-v1"
                expected_net = 0.0
            elif policy == "threshold":
                action = _threshold_action(row.promise_miss_probability, threshold)
                decision_id = f"replay-th-{row.order_id}"
                policy_version = f"threshold-{threshold:.2f}-v1"
                expected_net = None
            else:
                decision = decision_svc.decide(
                    DecisionContext(
                        order_id=row.order_id,
                        prediction_id=row.prediction_id,
                        model_version=row.model_version,
                        promise_miss_probability=row.promise_miss_probability,
                        basket_value=row.basket_value,
                        remaining_to_promise_days=row.remaining_to_promise_days,
                        geo_distance_km=row.geo_distance_km,
                        same_state=row.same_state,
                        freight_value=row.freight_value,
                        p1_score_threshold=row.p1_score_threshold,
                        p2_score_threshold=row.p2_score_threshold,
                    )
                )
                action = decision.recommended_action
                decision_id = decision.decision_id
                policy_version = decision.policy_version
                expected_net = decision.expected_net_value
                upgrade_cost = decision.upgrade_cost

            result = executor.execute_decision(
                decision_id=decision_id,
                prediction_id=row.prediction_id,
                order_id=row.order_id,
                action_type=action,
                model_version=row.model_version,
                policy_version=policy_version,
                observed_promise_miss=row.observed_promise_miss,
                basket_value=row.basket_value,
                expected_net_value=expected_net,
                freight_value=freight,
                intervention_cost=upgrade_cost,
                execution_source="replay",
            )
            action_counts[action.value] = action_counts.get(action.value, 0) + 1
            if action != ActionType.NO_ACTION:
                interventions += 1
                if row.observed_promise_miss:
                    true_pos_interventions += 1
            spend += result.simulated_cost
            gross_avoided += result.simulated_gross_avoided_loss
            net_value += result.simulated_net_value
            simulated_misses += int(result.simulated_promise_miss)
            flagged_misses += int(row.observed_promise_miss and action != ActionType.NO_ACTION)

        prevented = observed_misses - simulated_misses
        summaries["policies"][policy] = {
            "interventions": interventions,
            "intervention_rate": interventions / max(len(rows), 1),
            "intervention_spend": spend,
            "observed_promise_misses": observed_misses,
            "simulated_promise_misses": simulated_misses,
            "simulated_misses_prevented": prevented,
            "gross_avoided_loss_simulated": gross_avoided,
            "net_simulated_value": net_value,
            "roi_simulated": (net_value / spend) if spend > 0 else None,
            "value_per_order_simulated": net_value / max(len(rows), 1),
            "value_per_intervention_simulated": (
                net_value / interventions if interventions else None
            ),
            "precision_of_interventions": (
                true_pos_interventions / interventions if interventions else None
            ),
            "recall_of_miss_among_interventions": (
                flagged_misses / observed_misses if observed_misses else None
            ),
            "action_distribution": action_counts,
        }

    return summaries


def replay_from_frame(
    frame: pd.DataFrame,
    *,
    probability_col: str = "promise_miss_probability",
    label_col: str = "promise_miss",
    basket_col: str = "basket_value",
    order_col: str = "order_id",
    model_version: str = "replay",
    **kwargs: Any,
) -> dict[str, Any]:
    rows: list[ReplayRow] = []
    for i, r in frame.iterrows():
        oid = str(r[order_col])
        rem = r["remaining_to_promise_days"] if "remaining_to_promise_days" in r.index else None
        geo = r["geo_distance_km"] if "geo_distance_km" in r.index else None
        same = r["same_state"] if "same_state" in r.index else None
        freight = r["freight_value"] if "freight_value" in r.index else None
        rows.append(
            ReplayRow(
                order_id=oid,
                prediction_id=f"pred-replay-{oid}-{i}",
                model_version=model_version,
                promise_miss_probability=float(r[probability_col]),
                basket_value=float(r[basket_col]),
                observed_promise_miss=bool(int(r[label_col])),
                remaining_to_promise_days=float(rem) if rem is not None and pd.notna(rem) else 5.0,
                geo_distance_km=float(geo) if geo is not None and pd.notna(geo) else 150.0,
                same_state=float(same) if same is not None and pd.notna(same) else 0.0,
                freight_value=float(freight) if freight is not None and pd.notna(freight) else 15.0,
            )
        )
    return replay_policies(rows, **kwargs)
