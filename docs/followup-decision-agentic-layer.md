# Follow-up: Decision + Agentic Action Layer

**Status:** D1–D13 shipped on EV-argmax policy; **superseded as the live policy by ADR 0006 NOC bands** (`noc-handoff-policy-v1`, `econ-sim-v3`). Agent now copies `policy_recommendation.recommended_action`. Causal ROI remains disallowed.  
**Saved:** 2026-08-16 (historical spec). Do not implement EV-argmax as the hero path.

## Accepted deltas (before D1)

Agreed amendments vs the original instruction set:

1. **Target language:** use `long_delivery_probability` / long-delivery risk (ADR 0005).
2. **Flat loss v1:** `loss = fixed_cost + basket × rate` — no day-severity multipliers yet.
3. **`prediction_id`:** thin adapter on `PredictResponse` / `PredictionService.predict_one` (UUID).
4. **Local ledger first** for D4 (JSONL/SQLite); BigQuery decision tables later.
5. **CUSTOMER_NOTIFICATION EV:** `P(risk) × loss × impact_reduction − cost` (prevention = 0).
6. **`basket_value` required** on `DecisionContext`.
7. **Portfolio cut:** D1–D2 now; D3–D6 next; LangGraph/LangSmith after policy replay proves value.
8. **H9/H10:** example economics in `config/policy_economics.yaml` are temporary simulation defaults until human approval.
9. **Policy ignores `risk_band`** — decides from calibrated probability + economics.
10. **Do not confuse** model-traffic `docs/simulation.md` with intervention simulation (new package later).

---

## Adaptation notes (repo reality)

The original prompt assumes `P(late_delivery)` / `late_delivery_probability`. This repo was retargeted (ADR 0005) to:

- target: `long_delivery` (delivery_days > 14 from `prediction_ts`)
- API field: `long_delivery_probability`
- MCP: `predict_long_delivery` / `explain_long_delivery`

When implementing, map all “late delivery” decision wording to **long-delivery risk** unless H1 is changed again. Prediction-service integration remains the same: consume `PredictionService` outputs; do not retrain or redesign the model for this layer.

Economics / action labels (EXPEDITE, etc.) still make sense for “slow delivery” risk.

---

## Cursor Instruction Set — Add Decision + Agentic System to Existing Production ML Model

### Objective

Extend the existing production ML system with a production-grade decision and agentic action layer.

The predictive model is already built. Do not redesign, retrain, or replace it unless integration requires a narrowly scoped adapter.

The new system should demonstrate the full chain:

```text
prediction
→ decision
→ action selection
→ optional agent reasoning
→ controlled execution
→ outcome
→ business value
→ evaluation
→ feedback
```

The architecture must clearly separate:

1. predictive model
2. deterministic decision policy
3. agent orchestration
4. tools/MCP
5. action execution
6. business-outcome simulation
7. agent evaluation
8. monitoring and feedback

The agent must not become a replacement for deterministic business logic.

---

### 1. Existing System Boundary

Assume the current production ML system already provides:

```text
features
   ↓
production model
   ↓
prediction service
   ↓
P(risk)   # long_delivery_probability in this repo
```

Integrate with the existing prediction service rather than modifying model internals.

Required prediction metadata:

- `prediction_id`
- `order_id`
- `long_delivery_probability` (was `late_delivery_probability` in the original prompt)
- `model_version`
- `feature_version` if available
- `prediction_timestamp`

Do not duplicate model inference logic.

---

### 2. Target Decision

The business decision is:

Given an order’s predicted probability of long delivery, should the system intervene, and if so, which approved intervention should it take?

Initial actions:

- `NO_ACTION`
- `EXPEDITE`
- `SELLER_ESCALATION`
- `CUSTOMER_NOTIFICATION`
- `MANUAL_REVIEW`

Actions must be configurable and represented as typed domain objects.

---

### 3. Decision Architecture

```text
Existing ML Prediction
        │
        ▼
DecisionContext
        │
        ▼
Deterministic Policy Engine
        │
        ├──────── clear decision ────────► ActionExecutor
        │
        └──────── ambiguous/high-value ─► LangGraph Agent
                                            │
                                            ▼
                                       bounded tools
                                            │
                                            ▼
                                      ActionExecutor
                                            │
                                            ▼
                                   simulated intervention
                                            │
                                            ▼
                                      outcome ledger
                                            │
                                            ▼
                                    business-value metrics
```

The deterministic policy must exist before the agent.

---

### 4. Business Economics

Create explicit configurable simulation assumptions.

Do not hard-code assumptions throughout business logic.

Example configuration structure:

```yaml
business_loss:
  fixed_late_cost: 10.0
  order_value_loss_rate: 0.10
actions:
  EXPEDITE:
    cost: 8.0
    late_prevention_probability: 0.60
  SELLER_ESCALATION:
    cost: 4.0
    late_prevention_probability: 0.35
  MANUAL_REVIEW:
    cost: 5.0
    late_prevention_probability: 0.30
  CUSTOMER_NOTIFICATION:
    cost: 1.0
    late_prevention_probability: 0.0
    customer_impact_reduction: 0.20
```

These values are simulation assumptions.

They must never be represented as empirically estimated causal effects.

---

### 5. Business Loss Function

Implement a configurable late/long-delivery cost model.

Initial formulation:

```text
business_loss_if_late
=
fixed_late_cost
+
(order_value × variable_loss_rate)
```

Optionally include lateness severity:

- 1–2 days late → 1.0x
- 3–5 days late → 1.5x
- 6+ days late → 2.0x

Keep the implementation modular so the business-value model can later be replaced.

---

### 6. Expected-Value Decision Policy

Implement a deterministic baseline decision policy.

For each eligible action:

```text
expected_avoided_loss
=
P(risk)
× assumed_action_effectiveness
× business_loss_if_late

expected_net_value
=
expected_avoided_loss
-
action_cost
```

For customer-impact-only actions, incorporate the configured impact reduction rather than pretending lateness is prevented.

Select:

```text
argmax(expected_net_value)
```

subject to:

```text
expected_net_value > 0
```

Otherwise: `NO_ACTION`.

The policy must return the economics for every considered action, not just the winner.

---

### 7. Required Decision Domain Models

Create typed schemas for at least:

- `DecisionContext`
- `ActionType`
- `ActionEconomics`
- `ActionCandidate`
- `ActionRecommendation`
- `DecisionResult`
- `PolicyVersion`

`DecisionResult` should contain:

- `decision_id`
- `prediction_id`
- `order_id`
- `long_delivery_probability`
- `model_version`
- `policy_version`
- `recommended_action`
- `expected_intervention_cost`
- `expected_avoided_loss`
- `expected_net_value`
- `alternative_actions`
- `requires_agent_review`
- `decision_source`
- `rationale`
- `decision_timestamp`

---

### 8. Policy Versioning

Treat the decision policy as a production artifact.

Each decision must identify:

- `policy_version`
- `policy_config_version`
- Git SHA if available

Examples:

- `expected-value-policy-v1`
- `expected-value-policy-v2`

Changes to action costs, effectiveness assumptions, business-loss parameters, or routing thresholds must produce a traceable policy/config version.

---

### 9. Agent Routing

Do not send every order to an LLM.

Implement deterministic routing. Example:

- if best expected value ≤ 0 → `NO_ACTION`
- elif clear policy winner → execute deterministic recommendation
- elif high-value order → route to agent
- elif top actions are close → route to agent
- elif special context requires review → route to agent

Make routing thresholds configurable.

Suggested signals: order value, absolute expected value, difference between top two actions, prediction uncertainty, missing/contextual information, manual-review policy.

---

### 10. Agent Framework

Use:

- **LangGraph** — agent state, branching, tool invocation, bounded workflow, human approval nodes, failure handling, checkpointing where useful
- **LangChain** — only where useful for model/tool integrations; do not wrap deterministic business logic
- **LangSmith** — tracing, tool-call traces, latency, tokens, cost, offline/online eval, regression, human review
- **MCP** — expose reusable business capabilities as explicit tools

---

### 11. Agent Workflow

Approximate flow:

```text
AgentReviewRequested
        │
        ▼
load prediction
        │
        ▼
get order context
        │
        ▼
get seller/contextual information
        │
        ▼
list approved actions
        │
        ▼
calculate economics for candidate actions
        │
        ▼
compare options
        │
        ▼
choose approved action
        │
        ▼
human approval if required
        │
        ▼
ActionExecutor
```

The agent should produce a concise decision rationale tied to tool-derived evidence.

---

### 12. Agent Restrictions

The agent must not:

- change the ML prediction
- change action-cost assumptions
- change intervention-effectiveness assumptions
- invent new actions
- bypass `ActionExecutor`
- write directly to outcome tables
- change policy thresholds
- trigger real-world external actions

It may only select from approved actions. Validate the final agent action before execution.

---

### 13. MCP Tools

Expose tools such as:

- `get_order_risk(order_id)`
- `get_order_context(order_id)`
- `get_seller_context(seller_id)`
- `list_available_actions(order_id)`
- `calculate_action_value(order_id, action)`
- `recommend_policy_action(order_id)`
- `execute_simulated_action(order_id, action)`
- `get_action_outcome(action_id)`
- `get_decision_history(order_id)`
- `get_policy_metrics()`

Tool contracts must use typed schemas. The agent should not access underlying databases directly when an approved tool exists.

---

### 14. Shared Service Architecture

REST, MCP, deterministic policy, and the agent must reuse domain services:

- `PredictionService`
- `DecisionService`
- `PolicyService`
- `ActionValueService`
- `ActionExecutor`
- `OutcomeService`

```text
REST ──────┐
           │
MCP ───────┼──► domain services
           │
LangGraph ─┘
```

Do not duplicate logic among REST routes, MCP tools, and LangGraph nodes.

---

### 15. Counterfactual Action Simulator

There is no intervention dataset. Implement an explicit simulation layer.

Suggested modules:

```text
src/.../simulation/
    assumptions.py
    intervention.py
    outcomes.py
    business_value.py
```

For an observed late/long order:

```text
intervention_success ~ Bernoulli(configured_effectiveness)
```

Use seeded randomness. Never overwrite historical outcomes. Persist both `observed_outcome` and `simulated_outcome`.

For `CUSTOMER_NOTIFICATION`: lateness may remain unchanged but simulated customer-impact loss is reduced.

---

### 16. Action Executor

Dedicated execution boundary:

```text
ActionExecutor.execute(ActionRequest) -> ActionResult
```

Portfolio implementation is simulation only.

`ActionRequest`: `order_id`, `prediction_id`, `decision_id`, `action_type`, `model_version`, `policy_version`, `agent_run_id` optional, `expected_net_value`.

`ActionResult`: `action_id`, `status`, `simulated_cost`, `simulated_effect`, `execution_source`, `timestamp`.

All execution paths must go through this component.

---

### 17. Decision / Action / Outcome Ledger

Persist end-to-end lineage. Conceptual stores:

- predictions
- decisions
- actions
- outcomes
- agent_runs

BigQuery table names (example): `decision_predictions`, `decision_recommendations`, `decision_actions`, `decision_outcomes`, `decision_agent_runs`.

Traceability chain:

```text
order_id → prediction_id → model_version → decision_id → policy_version
         → agent_run_id? → action_id → observed/simulated outcome → business value
```

A reviewer must be able to query: why did this order receive this action?

---

### 18. Offline Policy Replay

Historical replay harness comparing:

- Policy A: `NO_ACTION`
- Policy B: simple probability threshold (e.g. if P > 0.70 → `EXPEDITE`)
- Policy C: expected-value optimization
- Policy D (later): agent-assisted policy

---

### 19. Business-Value Metrics

Calculate (all financial results labeled **simulated**):

orders evaluated, interventions, intervention rate, intervention spend, observed late/long deliveries, simulated late/long deliveries prevented, gross avoided loss, net simulated value, ROI, value per order, value per intervention, precision of interventions, recall of positives, action distribution, value by action / seller / geography / segment. Bootstrap CIs where informative.

---

### 20–22. Agent Evaluation + Regression Gate

Use LangSmith plus custom deterministic evaluators under `evals/` (datasets + evaluators + `run_agent_evals.py`).

Required evals: policy compliance (100%), tool trajectory, decision correctness, business value vs baseline, agent regret, efficiency (latency/tokens/cost).

Deployment gates: compliance 100%, invalid actions 0, no ActionExecutor/human-gate bypasses, regret/value/latency/cost within configured tolerances. Do not rely exclusively on LLM-as-judge.

---

### 23–24. Human Gates

- **H9** — business economics assumptions
- **H10** — intervention effectiveness / impact-reduction assumptions
- **H11** — agent action scope / when human review is mandatory
- **H12** — any future real external execution (out of scope; all actions simulated)

LangGraph human-review node for high value / high cost / low dominance / exception / uncertainty. Persist approval outcome.

---

### 25. REST Extensions

- `POST /v1/decision`
- `POST /v1/action/simulate`
- `GET /v1/actions/{action_id}`
- `GET /v1/orders/{order_id}/decision`
- `GET /v1/policies/current`

---

### 26. Monitoring

Decision + agent metrics layered on existing service/model monitoring (intervention rate, EV, simulated realized value, ROI by model/policy version; agent-review rate, tool/LLM calls, regret, human overrides, compliance failures). LangSmith for agent traces.

---

### 27. Airflow Integration

Add batch DAG conceptually like `daily_decision_evaluation` (reconcile predictions/decisions/actions/outcomes → model/policy/agent metrics → drift triggers). Do **not** use Airflow for interactive agent orchestration (LangGraph owns that).

---

### 28. Model vs Policy vs Agent Optimization

Keep objectives separate:

- **Model:** accurately estimate P(risk)
- **Policy:** maximize expected business value under constraints
- **Agent:** valid contextual decision within bounded tools/policies

Do not optimize the classifier directly against simulated financial value in this phase.

---

### 29. Causal Limitation

Document prominently:

`P(risk | X)` does **not** give `P(outcome | action, X)`.

Intervention effects are simulated. Do not claim empirical causal effectiveness. Future extensions (RCT, uplift, causal forests, bandits, RL) are out of initial scope.

---

### 30. Production Lineage

```text
raw data → dbt feature version → Feast → model version → prediction
        → policy version → agent run? → action → observed/simulated outcome → business value
```

Must be persisted and queryable.

---

### 31. Demo Scenarios

Deterministic harness covering:

- A Prediction
- B Deterministic decision + economics table
- C Simulated execution
- D Policy value comparison (NO_ACTION / threshold / EV)
- E Agent review (ambiguous/high-value) with LangGraph trace
- F Agent evaluation suite
- G End-to-end lineage for one order

---

### 32. Suggested Repository Extensions

Adapt names to this repo (`src/olist_ml/...`). Suggested layout:

```text
src/olist_ml/
  decisions/   schemas, economics, policy, routing, service
  actions/     schemas, executor, registry
  simulation/  assumptions, intervention, outcomes, business_value
  agents/      state, graph, nodes, routing, prompts
  tools/       decision_tools, mcp_tools
  outcomes/    ledger, reconciliation
  monitoring/  decision_metrics, agent_metrics
evals/
  datasets/ evaluators/ run_agent_evals.py
airflow/dags/daily_decision_evaluation.py
```

Reuse existing `PredictionService`, schemas, MCP server, and monitoring rather than duplicating.

---

### 33. Testing

Unit tests for economics, EV policy, NO_ACTION, ties, routing, simulation reproducibility, ActionExecutor validation, forbidden agent actions, policy-version persistence.

Integration: prediction → decision → action → ledger → metrics; agent → MCP → ActionExecutor; LangSmith eval execution.

---

### 34. Security and Guardrails

Treat the agent as an untrusted decision participant. Validate tool args, action enum, order IDs, policy version, ActionExecutor authorization. No secrets/DB credentials in model context. Least-privilege tool access.

---

### 35. Implementation Order

| Milestone | Scope | Status |
|---|---|---|
| D1 | Decision domain schemas + service boundaries | done |
| D2 | Deterministic EV policy + economics | done |
| D3 | Simulation + ActionExecutor | done |
| D4 | Persistence / lineage | done |
| D5 | Historical replay (NO_ACTION / threshold / EV) | done |
| D6 | REST | done |
| D7 | MCP tools | done |
| D8 | LangGraph agent review | done (tool-driven; no LLM key required) |
| D9 | LangSmith + agent eval harness | done — local JSON evals + optional LangSmith ([d9-langsmith.md](d9-langsmith.md)) |
| D10 | Human approval node | done |
| D11 | Airflow batch evaluation | local-first stub done |
| D12 | Monitoring | decision/agent counters on `/v1/metrics` |
| D13 | Demo harness | `scripts/demo_decision_chain.py` / `make demo-decision` |

Human gates **H9–H12** formalized: [h9-h10-economics-gate.md](h9-h10-economics-gate.md). H9/H10 approved for simulation defaults; causal ROI claims remain off. H12 real execution remains disabled.

Each milestone must leave the system runnable. **Do not start with the LLM agent.**

---

### 36. Cursor Operating Rules

1. Inspect the existing repository before creating new architecture.
2. Reuse the existing production model and prediction service.
3. Do not redesign the current ML pipeline.
4. Keep model, policy, agent, and execution layers independent.
5. Do not duplicate feature or inference logic.
6. Do not start by implementing the LLM agent.
7. Build the deterministic expected-value baseline first.
8. Every action must flow through ActionExecutor.
9. Every agent tool must have a typed contract.
10. The agent may select only approved actions.
11. Persist full decision lineage.
12. Treat intervention effects as simulations.
13. Do not claim causal validity.
14. Make all economics configurable.
15. Version policies/configuration.
16. Use seeded simulation randomness.
17. Add tests alongside each milestone.
18. Use LangGraph for interactive agent workflow.
19. Use LangSmith for tracing/evaluation.
20. Use Airflow only for batch/scheduled workflow orchestration.
21. Stop for human review when assumptions or existing architecture are materially affected.
22. Do not add additional frameworks unless there is a concrete missing capability.

---

### 37. First Execution Prompt (when unblocked)

Read the existing repository enough to understand prediction-service interface, API/service boundaries, schemas, persistence, MCP, Airflow, and test conventions.

The production model is already built. Do not change model training or model-serving behavior.

Implement only **D1 and D2**:

1. Decision domain models
2. Configurable business-loss model
3. Action economics
4. Deterministic expected-value policy
5. `DecisionService` integrating with existing prediction output
6. Unit tests

Supported actions: `NO_ACTION`, `EXPEDITE`, `SELLER_ESCALATION`, `CUSTOMER_NOTIFICATION`, `MANUAL_REVIEW`.

Before writing code, show:

A. How the existing prediction path works  
B. Where `DecisionService` integrates  
C. Exact new/modified files  
D. Existing abstractions to reuse  
E. Coupling risks between decision logic and the model  
F. Any architectural decision requiring human approval  

Do not proceed past a material architectural decision without approval.

Do not implement yet: LangGraph, LangSmith, MCP additions, ActionExecutor, intervention simulation, Airflow changes, agent prompts, DB migrations (unless required for D1/D2), or real external actions.
