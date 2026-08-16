#!/usr/bin/env python3
"""Report H9/H10 economics gate status (does not auto-approve)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from olist_ml.decisions.economics import clear_policy_cache, load_policy_economics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/policy_economics.yaml"),
        help="Path to policy economics YAML",
    )
    parser.add_argument(
        "--require-approved",
        action="store_true",
        help="Exit 1 unless H9 and H10 are both approved",
    )
    args = parser.parse_args()
    clear_policy_cache()
    cfg = load_policy_economics(args.config)
    gate = cfg.economics_gate
    report = {
        "policy_version": cfg.policy_version,
        "policy_config_version": cfg.policy_config_version,
        "economics_gate": gate.model_dump(),
        "is_approved": gate.is_approved,
        "causal_roi_claim_allowed": gate.is_approved,
        "disclaimer": cfg.assumptions_disclaimer,
        "guidance": (
            "Simulation defaults only."
            if not gate.is_approved
            else "H9/H10 approved — still not a causal guarantee."
        ),
    }
    print(json.dumps(report, indent=2))
    if args.require_approved and not gate.is_approved:
        print("H9/H10 not approved — refusing causal-ROI claim path.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
