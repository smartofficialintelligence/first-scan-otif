"""DecisionService — deterministic NOC policy on top of PredictionService outputs."""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from olist_ml.decisions.economics import PolicyEconomicsConfig, load_policy_economics
from olist_ml.decisions.policy import apply_noc_policy
from olist_ml.decisions.routing import requires_agent_review
from olist_ml.decisions.schemas import DecisionContext, DecisionResult
from olist_ml.schemas import PredictResponse


@lru_cache(maxsize=1)
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
    """NOC band policy decisions from prediction metadata + order clocks."""

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
        loss, recommended, alternatives, meta = apply_noc_policy(context, self.config)
        agent_flag = requires_agent_review(
            recommended=recommended,
            routing=self.config.routing,
        )
        source = "agent_review_pending" if agent_flag else "deterministic_policy"
        band = str(meta["policy_band"])
        rationale = (
            f"NOC band {band}: remaining_to_promise_days="
            f"{context.remaining_to_promise_days}. "
            f"score={context.promise_miss_probability:.4f} "
            f"(P1>={meta['p1_score_threshold']:.4f}, P2>={meta['p2_score_threshold']:.4f}). "
            f"upgrade_eligible={meta['upgrade_eligible']}. "
            f"Selected {recommended.action.value} under {self.config.policy_version} "
            f"({self.config.policy_config_version}). "
            f"business_loss_if_miss={loss:.4f}. {recommended.formula}."
        )
        if agent_flag:
            rationale += " Flagged for agent execution of the frozen policy action."
        if meta["requires_human_approval"]:
            rationale += (
                f" Human approval required (upgrade_cost={meta['upgrade_cost']:.2f} "
                f">= {self.config.noc_policy.human_approval_upgrade_cost_min:.2f})."
            )

        return DecisionResult(
            decision_id=str(uuid.uuid4()),
            prediction_id=context.prediction_id,
            order_id=context.order_id,
            promise_miss_probability=context.promise_miss_probability,
            model_version=context.model_version,
            policy_version=self.config.policy_version,
            policy_config_version=self.config.policy_config_version,
            recommended_action=recommended.action,
            policy_band=band,  # type: ignore[arg-type]
            upgrade_eligible=bool(meta["upgrade_eligible"]),
            upgrade_cost=meta["upgrade_cost"],  # type: ignore[arg-type]
            remaining_to_promise_days=context.remaining_to_promise_days,
            expected_intervention_cost=recommended.expected_intervention_cost,
            expected_avoided_loss=recommended.expected_avoided_loss,
            expected_net_value=recommended.expected_net_value,
            alternative_actions=alternatives,
            requires_agent_review=agent_flag,
            requires_human_approval=bool(meta["requires_human_approval"]),
            decision_source=source,  # type: ignore[arg-type]
            rationale=rationale,
            decision_timestamp=datetime.now(UTC),
            git_sha=_git_sha(),
            basket_value=context.basket_value,
            business_loss_if_miss=loss,
            assumptions_disclaimer=self.config.assumptions_disclaimer,
        )

    def decide_from_prediction(
        self,
        prediction: PredictResponse,
        *,
        basket_value: float,
        seller_id: str | None = None,
        feature_version: str | None = None,
        remaining_to_promise_days: float | None = None,
        geo_distance_km: float | None = None,
        same_state: float | None = None,
        freight_value: float | None = None,
        p1_score_threshold: float | None = None,
        p2_score_threshold: float | None = None,
    ) -> DecisionResult:
        if not prediction.prediction_id:
            raise ValueError("PredictResponse.prediction_id is required for decisions")
        ctx = DecisionContext(
            order_id=prediction.order_id,
            prediction_id=prediction.prediction_id,
            model_version=prediction.model_version,
            promise_miss_probability=prediction.promise_miss_probability,
            basket_value=basket_value,
            seller_id=seller_id,
            prediction_timestamp=prediction.prediction_timestamp,
            feature_version=feature_version,
            remaining_to_promise_days=remaining_to_promise_days,
            geo_distance_km=geo_distance_km,
            same_state=same_state,
            freight_value=freight_value,
            p1_score_threshold=p1_score_threshold
            if p1_score_threshold is not None
            else prediction.p1_score_threshold,
            p2_score_threshold=p2_score_threshold
            if p2_score_threshold is not None
            else prediction.p2_score_threshold,
        )
        return self.decide(ctx)
