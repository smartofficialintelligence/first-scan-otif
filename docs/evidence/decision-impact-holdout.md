# Simulated policy impact — holdout replay snapshot

> Snapshot of `artifacts/decision_impact.md` from `make decision-eval` after a full holdout policy replay (n = 9,647 orders, champion `local-20260819T170145Z`, econ-sim-v3, 2026-08-19). Regenerate: score the replay holdout, run `scripts/policy_replay.py --ledger`, then `make decision-eval`.


Performed 196 late notices, 338 at-risk notices, 96 remaining-leg upgrades, and 9017 no-action; moved 27 deliveries from late to on-time; spent $1,432.35 to do it.

On this ledger the frozen NOC policy performed 196 late notices, 338 at-risk notices, 96 remaining-leg upgrades, and 9017 no-action. Simulation moved 27 of 882 observed-late deliveries to on-time and avoided 88.8 delay-days. Intervention spend was $1,432.35; simulated net value was $550.34.

## Action mix

| Action | Count |
|---|---:|
| `LATE_NOTICE` | 196 |
| `AT_RISK_NOTICE` | 338 |
| `REMAINING_LEG_UPGRADE` | 96 |
| `NO_ACTION` | 9017 |

## Outcomes (simulated)

- Observed late deliveries: **882**
- Still late after simulation: **855**
- Moved late → on-time: **27**
- Delay-days avoided: **88.8**
- Spend: **$1,432.35**
- Net simulated value: **$550.34**

_Simulated under econ-sim-v3. Not observed P&L and not a causal ROI claim. Upgrade flips use an assumed Bernoulli prevent rate; notices do not change on-time status or days late._

## Policy comparison — same 9,647 orders, three policies

The replay runs every order through three policies with the same seeds, so the frozen NOC policy is judged against real alternatives, not against zero.

| | Do nothing | Naive threshold (score ≥ 0.70, notice only) | **Frozen NOC policy (P0–P3)** |
|---|---:|---:|---:|
| Interventions (rate) | 0 | 257 (2.7%) | **630 (6.5%)** |
| Precision of interventions | — | 99.2% | 67.3% |
| Observed misses reached | 0% | 28.9% | **48.1%** |
| Moved late → on-time | 0 | 0 | **27** |
| Delay-days avoided | 0 | 0 | **88.8** |
| Simulated spend | $0 | $257 | $1,432 |
| Net simulated value | $0 | $906 | $550 |

The naive threshold **"wins" on simulated net value — and changes nothing physical.** It only sends $1 notices, whose value here is an assumed customer-impact reduction; it never upgrades a shipment, so zero deliveries actually arrive on time that wouldn't have. The NOC policy spends real (simulated) money on remaining-leg upgrades and is the only arm that moves outcomes: 27 deliveries on-time, 88.8 delay-days avoided, while reaching 48% of misses instead of 29%.

That asymmetry is the argument for the design: the policy is a **banded capacity rule, not an EV-argmax** — under any economics where notices are cheap and credited with soft impact, EV-argmax degenerates into notice-spam that optimizes the simulation instead of the delivery. It is also the argument for the standing caveat: which column you prefer depends entirely on assumed notice-impact and upgrade-prevention rates (`econ-sim-v3`), and the way to settle it is an experiment on the actions — not a bigger simulation.

_Simulated under econ-sim-v3. Not observed P&L and not a causal ROI claim._
