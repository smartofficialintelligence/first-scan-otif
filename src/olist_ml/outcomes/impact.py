"""Simulated policy-impact rollup from the decision ledger.

These figures are econ-sim-v3 assumptions applied to executed (simulated) actions.
They are not observed P&L and not a causal ROI claim.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from olist_ml.decisions.schemas import ActionType

ACTION_ORDER: tuple[str, ...] = (
    ActionType.LATE_NOTICE.value,
    ActionType.AT_RISK_NOTICE.value,
    ActionType.REMAINING_LEG_UPGRADE.value,
    ActionType.NO_ACTION.value,
)

_ACTION_NOUNS: dict[str, tuple[str, str]] = {
    ActionType.LATE_NOTICE.value: ("late notice", "late notices"),
    ActionType.AT_RISK_NOTICE.value: ("at-risk notice", "at-risk notices"),
    ActionType.REMAINING_LEG_UPGRADE.value: (
        "remaining-leg upgrade",
        "remaining-leg upgrades",
    ),
    ActionType.NO_ACTION.value: ("no-action", "no-action"),
}

DISCLAIMER = (
    "Simulated under econ-sim-v3. Not observed P&L and not a causal ROI claim. "
    "Upgrade flips use an assumed Bernoulli prevent rate; notices do not change "
    "on-time status or days late."
)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def _action_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("record_type") == "action"]


def _noun(action: str, count: int) -> str:
    singular, plural = _ACTION_NOUNS.get(action, (action.lower(), action.lower()))
    return singular if count == 1 else plural


def _join_clauses(parts: list[str]) -> str:
    if not parts:
        return "no simulated actions"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def format_action_mix(distribution: dict[str, int]) -> str:
    """Human clause: '12 remaining-leg upgrades, 40 at-risk notices, and 3 late notices'."""
    parts: list[str] = []
    seen: set[str] = set()
    for key in ACTION_ORDER:
        n = int(distribution.get(key, 0))
        if n <= 0:
            continue
        parts.append(f"{n} {_noun(key, n)}")
        seen.add(key)
    extras = sorted(k for k, n in distribution.items() if k not in seen and int(n) > 0)
    for key in extras:
        n = int(distribution[key])
        parts.append(f"{n} {_noun(key, n)}")
    return _join_clauses(parts)


def format_money(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def _ordered_distribution(raw: dict[str, Any]) -> dict[str, int]:
    ordered = {k: int(raw.get(k, 0) or 0) for k in ACTION_ORDER}
    for key, n in raw.items():
        if key not in ordered:
            ordered[str(key)] = int(n or 0)
    return ordered


def _impact_report(
    *,
    distribution: dict[str, int],
    n_actions: int,
    observed_late: int,
    simulated_still_late: int,
    moved: int,
    spend: float,
    net: float,
    delay_days: float,
    source: str,
    scope: str,
    empty_message: str | None = None,
) -> dict[str, Any]:
    interventions = sum(
        n for k, n in distribution.items() if k != ActionType.NO_ACTION.value
    )
    mix = format_action_mix(distribution)
    if n_actions <= 0:
        headline = empty_message or (
            "No simulated actions yet. Persist simulate to the ledger, or run "
            "holdout policy replay, then re-run this rollup."
        )
        narrative = headline
    else:
        moved_word = "delivery" if moved == 1 else "deliveries"
        headline = (
            f"Performed {mix}; moved {moved} {moved_word} from late to on-time; "
            f"spent {format_money(spend)} to do it."
        )
        narrative = (
            f"{scope} performed {mix}. "
            f"Simulation moved {moved} of {observed_late} observed-late deliveries "
            f"to on-time and avoided {delay_days:.1f} delay-days. "
            f"Intervention spend was {format_money(spend)}; simulated net value was "
            f"{format_money(net)}."
        )
    return {
        "label": "simulated_policy_impact",
        "economics_version": "econ-sim-v3",
        "causal_roi_claim_allowed": False,
        "source": source,
        "n_actions": n_actions,
        "interventions": interventions,
        "action_distribution": distribution,
        "observed_late_deliveries": observed_late,
        "simulated_still_late": simulated_still_late,
        "moved_late_to_on_time": moved,
        "simulated_delay_days_avoided": round(delay_days, 4),
        "intervention_spend_simulated": round(spend, 4),
        "net_value_simulated": round(net, 4),
        "headline": headline,
        "narrative": narrative,
        "disclaimer": DISCLAIMER,
    }


def summarize_simulated_impact(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll simulated action rows into JD-facing business-outcome numbers."""
    actions = _action_rows(rows)
    dist = Counter(str(r.get("action_type") or "UNKNOWN") for r in actions)
    return _impact_report(
        distribution=_ordered_distribution(dist),
        n_actions=len(actions),
        observed_late=sum(1 for r in actions if _as_bool(r.get("observed_promise_miss"))),
        simulated_still_late=sum(
            1 for r in actions if _as_bool(r.get("simulated_promise_miss"))
        ),
        moved=sum(
            1
            for r in actions
            if _as_bool(r.get("observed_promise_miss"))
            and not _as_bool(r.get("simulated_promise_miss"))
        ),
        spend=sum(float(r.get("simulated_cost") or 0.0) for r in actions),
        net=sum(float(r.get("simulated_net_value") or 0.0) for r in actions),
        delay_days=sum(
            float(r.get("simulated_delay_days_avoided") or 0.0) for r in actions
        ),
        source="decision_ledger",
        scope="On this ledger the frozen NOC policy",
    )


def summarize_from_replay_policy(
    policy: dict[str, Any],
    *,
    n_orders: int,
    policy_name: str = "noc",
) -> dict[str, Any]:
    """Same operator-language rollup from a `replay_policies` policy block."""
    dist = _ordered_distribution(dict(policy.get("action_distribution") or {}))
    n_actions = sum(dist.values()) or int(n_orders)
    return _impact_report(
        distribution=dist,
        n_actions=n_actions,
        observed_late=int(policy.get("observed_promise_misses") or 0),
        simulated_still_late=int(policy.get("simulated_promise_misses") or 0),
        moved=int(policy.get("simulated_misses_prevented") or 0),
        spend=float(policy.get("intervention_spend") or 0.0),
        net=float(policy.get("net_simulated_value") or 0.0),
        delay_days=float(policy.get("simulated_delay_days_avoided") or 0.0),
        source=f"policy_replay:{policy_name}",
        scope=f"On this {n_orders:,}-order holdout replay the frozen NOC policy",
    )


def render_impact_markdown(report: dict[str, Any]) -> str:
    dist = report.get("action_distribution") or {}
    rows = "\n".join(
        f"| `{name}` | {int(count)} |" for name, count in dist.items()
    )
    return (
        "# Simulated policy impact\n\n"
        f"{report['headline']}\n\n"
        f"{report['narrative']}\n\n"
        "## Action mix\n\n"
        "| Action | Count |\n"
        "|---|---:|\n"
        f"{rows}\n\n"
        "## Outcomes (simulated)\n\n"
        f"- Observed late deliveries: **{report['observed_late_deliveries']}**\n"
        f"- Still late after simulation: **{report['simulated_still_late']}**\n"
        f"- Moved late → on-time: **{report['moved_late_to_on_time']}**\n"
        f"- Delay-days avoided: **{report['simulated_delay_days_avoided']:.1f}**\n"
        f"- Spend: **{format_money(float(report['intervention_spend_simulated']))}**\n"
        f"- Net simulated value: **{format_money(float(report['net_value_simulated']))}**\n\n"
        f"_{report['disclaimer']}_\n"
    )
