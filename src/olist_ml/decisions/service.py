"""DecisionService — deterministic policy on top of PredictionService outputs."""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from olist_ml.decisions.economics import PolicyEconomicsConfig, load_policy_economics
from olist_ml.decisions.policy import run_expected_value_policy
from olist_ml.decisions.routing import requires_agent_review
from olist_ml.decisions.schemas import DecisionContext, DecisionResult
from olist_ml.schemas import PredictResponse


def _git_sha() -> str | None:
    env = os.environ.get("GIT_SHA") or os.environ.get("GITHUB_SHA")
    if env:
        return env.strip()[:40]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return out.strip()[:40]
    except (OSError, subprocess.SubprocessError):
        return None


class DecisionService:
    """Expected-value policy decisions from prediction metadata + basket value."""

    def __init__(
        self,
        config: PolicyEconomicsConfig | None = None,
        config_path: Path | str | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            self.config = load_policy_economics(config_path)

    def decide(self, context: DecisionContext) -> DecisionResult:
        loss, recommended, alternatives = run_expected_value_policy(
            probability=context.long_delivery_probability,
            basket_value=context.basket_value,
            config=self.config,
        )
        agent_flag = requires_agent_review(
            recommended=recommended,
            alternatives=alternatives,
            basket_value=context.basket_value,
            routing=self.config.routing,
        )
        source = "agent_review_pending" if agent_flag else "deterministic_policy"
        rationale = (
            f"Selected {recommended.action.value} with expected_net_value="
            f"{recommended.expected_net_value:.4f} under {self.config.policy_version} "
            f"({self.config.policy_config_version}). "
            f"business_loss_if_long={loss:.4f}. "
            f"{recommended.formula}."
        )
        if agent_flag:
            rationale += (
                " Flagged for agent review (routing thresholds); "
                "not executed by an agent in D1–D2."
            )

        return DecisionResult(
            decision_id=str(uuid.uuid4()),
            prediction_id=context.prediction_id,
            order_id=context.order_id,
            long_delivery_probability=context.long_delivery_probability,
            model_version=context.model_version,
            policy_version=self.config.policy_version,
            policy_config_version=self.config.policy_config_version,
            recommended_action=recommended.action,
            expected_intervention_cost=recommended.expected_intervention_cost,
            expected_avoided_loss=recommended.expected_avoided_loss,
            expected_net_value=recommended.expected_net_value,
            alternative_actions=alternatives,
            requires_agent_review=agent_flag,
            decision_source=source,  # type: ignore[arg-type]
            rationale=rationale,
            decision_timestamp=datetime.now(UTC),
            git_sha=_git_sha(),
            basket_value=context.basket_value,
            business_loss_if_long=loss,
            assumptions_disclaimer=self.config.assumptions_disclaimer,
        )

    def decide_from_prediction(
        self,
        prediction: PredictResponse,
        *,
        basket_value: float,
        seller_id: str | None = None,
        feature_version: str | None = None,
    ) -> DecisionResult:
        if not prediction.prediction_id:
            raise ValueError("PredictResponse.prediction_id is required for decisions")
        ctx = DecisionContext(
            order_id=prediction.order_id,
            prediction_id=prediction.prediction_id,
            model_version=prediction.model_version,
            long_delivery_probability=prediction.long_delivery_probability,
            basket_value=basket_value,
            seller_id=seller_id,
            prediction_timestamp=prediction.prediction_timestamp,
            feature_version=feature_version,
        )
        return self.decide(ctx)
