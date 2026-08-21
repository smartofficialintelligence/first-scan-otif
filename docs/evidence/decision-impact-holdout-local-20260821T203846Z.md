# Simulated policy impact — champion `local-20260821T203846Z`

> Snapshot of `artifacts/decision_impact.md` from `make decision-eval` after a full
> holdout policy replay (n = 9,647 orders, champion `local-20260821T203846Z`,
> econ-sim-v3, 2026-08-21). Regenerate: score the replay holdout, run
> `scripts/policy_replay.py --ledger`, then `make decision-eval`.
>
> **Supersedes, but does not invalidate,**
> [`decision-impact-holdout.md`](decision-impact-holdout.md) — the snapshot for
> the previous champion `local-20260819T170145Z`. Both are kept. See
> [Why the figures moved](#why-the-figures-moved).

Performed 196 late notices, 329 at-risk notices, 78 remaining-leg upgrades, and
9,044 no-action; moved 25 deliveries from late to on-time; spent $1,199.88 to do it.

## Action mix

| Action | Count |
|---|---:|
| `LATE_NOTICE` | 196 |
| `AT_RISK_NOTICE` | 329 |
| `REMAINING_LEG_UPGRADE` | 78 |
| `NO_ACTION` | 9,044 |

## Outcomes (simulated)

- Observed late deliveries: **882**
- Still late after simulation: **857**
- Moved late → on-time: **25**
- Delay-days avoided: **86.4**
- Spend: **$1,199.88**
- Net simulated value: **$915.71**

_Simulated under econ-sim-v3. Not observed P&L and not a causal ROI claim. Upgrade
flips use an assumed Bernoulli prevent rate; notices do not change on-time status
or days late._

## Policy comparison — same 9,647 orders, three policies

| | Do nothing | Naive threshold (score ≥ 0.70, notice only) | **Frozen NOC policy (P0–P3)** |
|---|---:|---:|---:|
| Interventions (rate) | 0 | 332 (3.4%) | **603 (6.3%)** |
| Precision of interventions | — | 94.6% | 69.8% |
| Observed misses reached | 0% | 35.6% | **47.7%** |
| Moved late → on-time | 0 | 0 | **25** |
| Delay-days avoided | 0 | 0 | **86.4** |
| Simulated spend | $0 | $332 | $1,200 |
| Net simulated value | $0 | $1,089 | $916 |

The naive threshold still **"wins" on simulated net value while changing nothing
physical** — it only sends notices, never upgrades a shipment, so zero deliveries
arrive on time that would not have. The NOC policy is the only arm that moves
outcomes. That asymmetry is the argument for a banded capacity rule rather than
EV-argmax, and the reason intervention lift waits for an experiment on the actions
rather than a bigger simulation.

## Why the figures moved

Ranking did not change in any way that matters; the **action mix** did, because the
frozen policy thresholds moved.

| | prev champion `…0819T170145Z` | this champion `…0821T203846Z` |
|---|---:|---:|
| Top-2.5% precision | 0.4598 | **0.4598** (identical) |
| Top-10% recall | 0.4873 | **0.4963** |
| Test PR-AUC | 0.3104 | 0.3091 |
| P1 / P2 thresholds | 0.5000 / 0.2471 | **0.4895 / 0.2387** |
| Interventions | 630 | 603 |
| Moved late → on-time | 27 | 25 |
| Delay-days avoided | 88.8 | 86.4 |
| Spend / net | $1,432 / $550 | $1,200 / **$916** |

The cause was a point-in-time correctness fix, not a modelling change. The pandas
feature builder cut its history window at the row's position rather than at the
first row sharing that timestamp, so orders scanned in the same instant counted
each other as prior history — 9,937 of 96,475 rows, always exactly one too high,
contradicting the "strictly before `handoff_ts`" rule in ARCHITECTURE §3. A second
bug on the warehouse side truncated the `long_delivery` label to whole hours.
Fixing both brought the pandas and dbt/Feast implementations into exact agreement
and shifted the frozen validation thresholds slightly, which changes how many
orders land in each band.

Net effect: the corrected policy intervenes on 27 fewer orders, spends $232 less,
converts 2 fewer deliveries, and returns $366 more simulated net value. Queue
precision at the top of the ranking is unchanged.
