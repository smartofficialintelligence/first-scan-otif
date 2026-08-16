"""Offline policy replay comparing NO_ACTION / threshold / expected-value (D5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from olist_ml.actions.executor import ActionExecutor
from olist_ml.decisions.economics import PolicyEconomicsConfig, load_policy_economics
from olist_ml.decisions.schemas import ActionType, DecisionContext
from olist_ml.decisions.service import DecisionService

PolicyName = Literal["no_action", "threshold", "expected_value"]


@dataclass
class ReplayRow:
    order_id: str
    prediction_id: str
    model_version: str
    long_delivery_probability: float
    basket_value: float
    observed_long_delivery: bool


def _threshold_action(probability: float, threshold: float = 0.70) -> ActionType:
    return ActionType.EXPEDITE if probability > threshold else ActionType.NO_ACTION


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

    for policy in ("no_action", "threshold", "expected_value"):
        interventions = 0
        spend = 0.0
        gross_avoided = 0.0
        net_value = 0.0
        simulated_long = 0
        observed_long = 0
        action_counts: dict[str, int] = {}
        true_pos_interventions = 0
        flagged_long = 0

        for row in rows:
            observed_long += int(row.observed_long_delivery)
            if policy == "no_action":
                action = ActionType.NO_ACTION
                decision_id = f"replay-na-{row.order_id}"
                policy_version = "no-action-v1"
                expected_net = 0.0
            elif policy == "threshold":
                action = _threshold_action(row.long_delivery_probability, threshold)
                decision_id = f"replay-th-{row.order_id}"
                policy_version = f"threshold-{threshold:.2f}-v1"
                expected_net = None
            else:
                decision = decision_svc.decide(
                    DecisionContext(
                        order_id=row.order_id,
                        prediction_id=row.prediction_id,
                        model_version=row.model_version,
                        long_delivery_probability=row.long_delivery_probability,
                        basket_value=row.basket_value,
                    )
                )
                action = decision.recommended_action
                decision_id = decision.decision_id
                policy_version = decision.policy_version
                expected_net = decision.expected_net_value

            result = executor.execute_decision(
                decision_id=decision_id,
                prediction_id=row.prediction_id,
                order_id=row.order_id,
                action_type=action,
                model_version=row.model_version,
                policy_version=policy_version,
                observed_long_delivery=row.observed_long_delivery,
                basket_value=row.basket_value,
                expected_net_value=expected_net,
                execution_source="replay",
            )
            action_counts[action.value] = action_counts.get(action.value, 0) + 1
            if action != ActionType.NO_ACTION:
                interventions += 1
                if row.observed_long_delivery:
                    true_pos_interventions += 1
            spend += result.simulated_cost
            gross_avoided += result.simulated_gross_avoided_loss
            net_value += result.simulated_net_value
            simulated_long += int(result.simulated_long_delivery)
            flagged_long += int(row.observed_long_delivery and action != ActionType.NO_ACTION)

        prevented = observed_long - simulated_long
        summaries["policies"][policy] = {
            "interventions": interventions,
            "intervention_rate": interventions / max(len(rows), 1),
            "intervention_spend": spend,
            "observed_long_deliveries": observed_long,
            "simulated_long_deliveries": simulated_long,
            "simulated_long_deliveries_prevented": prevented,
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
            "recall_of_long_among_interventions": (
                flagged_long / observed_long if observed_long else None
            ),
            "action_distribution": action_counts,
        }

    return summaries


def replay_from_frame(
    frame: pd.DataFrame,
    *,
    probability_col: str = "long_delivery_probability",
    label_col: str = "long_delivery",
    basket_col: str = "basket_value",
    order_col: str = "order_id",
    model_version: str = "replay",
    **kwargs: Any,
) -> dict[str, Any]:
    rows: list[ReplayRow] = []
    for i, r in frame.iterrows():
        oid = str(r[order_col])
        rows.append(
            ReplayRow(
                order_id=oid,
                prediction_id=f"pred-replay-{oid}-{i}",
                model_version=model_version,
                long_delivery_probability=float(r[probability_col]),
                basket_value=float(r[basket_col]),
                observed_long_delivery=bool(int(r[label_col])),
            )
        )
    return replay_policies(rows, **kwargs)
