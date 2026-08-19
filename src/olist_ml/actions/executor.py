"""ActionExecutor — sole execution boundary for simulated interventions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from olist_ml.actions.schemas import ActionRequest, ActionResult
from olist_ml.decisions.economics import PolicyEconomicsConfig, load_policy_economics
from olist_ml.decisions.schemas import ActionType
from olist_ml.decisions.upgrade_cost import remaining_leg_upgrade_cost
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
        if self.config.routing.real_external_execution_enabled:
            raise RuntimeError(
                "H12: real external execution is disabled for this portfolio; "
                "set routing.real_external_execution_enabled=false"
            )

        seed = request.seed
        if seed is None:
            seed = derive_seed(
                request.order_id,
                request.decision_id,
                request.action_type.value,
                base_seed=self.base_seed,
            )

        cost_override = request.intervention_cost
        if cost_override is None and request.action_type == ActionType.REMAINING_LEG_UPGRADE:
            cost_override = remaining_leg_upgrade_cost(
                request.order_id,
                float(request.freight_value or 0.0),
                request.basket_value,
                config=self.config.noc_policy.upgrade_cost,
            )

        sim = simulate_intervention(
            action=econ,
            observed_promise_miss=request.observed_promise_miss,
            basket_value=request.basket_value,
            loss_cfg=self.config.business_loss,
            seed=seed,
            cost_override=cost_override,
            observed_days_late=request.observed_days_late,
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
            observed_promise_miss=request.observed_promise_miss,
            simulated_promise_miss=bool(sim["simulated_promise_miss"]),
            observed_days_late=float(sim["observed_days_late"]),
            simulated_days_late=float(sim["simulated_days_late"]),
            simulated_delay_days_avoided=float(sim["simulated_delay_days_avoided"]),
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
        observed_promise_miss: bool,
        basket_value: float,
        expected_net_value: float | None = None,
        freight_value: float | None = None,
        intervention_cost: float | None = None,
        observed_days_late: float | None = None,
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
                observed_promise_miss=observed_promise_miss,
                observed_days_late=observed_days_late,
                basket_value=basket_value,
                freight_value=freight_value,
                intervention_cost=intervention_cost,
            ),
            execution_source=execution_source,
        )
