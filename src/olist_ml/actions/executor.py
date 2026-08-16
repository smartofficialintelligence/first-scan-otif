"""ActionExecutor — sole execution boundary for simulated interventions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from olist_ml.actions.schemas import ActionRequest, ActionResult
from olist_ml.decisions.economics import PolicyEconomicsConfig, load_policy_economics
from olist_ml.decisions.schemas import ActionType
from olist_ml.simulation.intervention import derive_seed, simulate_intervention


class ActionExecutor:
    """All portfolio actions are simulated; no real-world side effects."""

    def __init__(
        self,
        config: PolicyEconomicsConfig | None = None,
        config_path: Path | str | None = None,
        *,
        base_seed: int = 42,
    ) -> None:
        self.config = config or load_policy_economics(config_path)
        self.base_seed = base_seed

    def execute(
        self,
        request: ActionRequest,
        *,
        execution_source: str = "deterministic_policy",
    ) -> ActionResult:
        econ = self.config.actions.get(request.action_type)
        if econ is None or not econ.eligible:
            raise ValueError(f"Action not approved/eligible: {request.action_type}")

        seed = request.seed
        if seed is None:
            seed = derive_seed(
                request.order_id,
                request.decision_id,
                request.action_type.value,
                base_seed=self.base_seed,
            )

        sim = simulate_intervention(
            action=econ,
            observed_long_delivery=request.observed_long_delivery,
            basket_value=request.basket_value,
            loss_cfg=self.config.business_loss,
            seed=seed,
        )

        return ActionResult(
            action_id=str(uuid.uuid4()),
            order_id=request.order_id,
            prediction_id=request.prediction_id,
            decision_id=request.decision_id,
            action_type=request.action_type,
            status="simulated",
            simulated_cost=float(sim["simulated_cost"]),
            intervention_success=sim["intervention_success"],  # type: ignore[arg-type]
            observed_long_delivery=request.observed_long_delivery,
            simulated_long_delivery=bool(sim["simulated_long_delivery"]),
            simulated_impact_loss_reduction=float(sim["simulated_impact_loss_reduction"]),
            simulated_gross_avoided_loss=float(sim["simulated_gross_avoided_loss"]),
            simulated_net_value=float(sim["simulated_net_value"]),
            execution_source=execution_source,  # type: ignore[arg-type]
            policy_version=request.policy_version or self.config.policy_version,
            model_version=request.model_version,
            assumptions_disclaimer=self.config.assumptions_disclaimer,
            timestamp=datetime.now(UTC),
            seed_used=seed,
        )

    def execute_decision(
        self,
        *,
        decision_id: str,
        prediction_id: str,
        order_id: str,
        action_type: ActionType,
        model_version: str,
        policy_version: str,
        observed_long_delivery: bool,
        basket_value: float,
        expected_net_value: float | None = None,
        execution_source: str = "deterministic_policy",
    ) -> ActionResult:
        return self.execute(
            ActionRequest(
                order_id=order_id,
                prediction_id=prediction_id,
                decision_id=decision_id,
                action_type=action_type,
                model_version=model_version,
                policy_version=policy_version,
                expected_net_value=expected_net_value,
                observed_long_delivery=observed_long_delivery,
                basket_value=basket_value,
            ),
            execution_source=execution_source,
        )
