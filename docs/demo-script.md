# Demo script (outline)

Locked sequence for interview / portfolio recording. Commands land with later milestones.

## Prep (day of)

1. Confirm `demo-down` from any prior run  
2. `make demo-up`  
3. Wait for smoke green  

## Demo 1 — Features

- Show dbt marts in BigQuery  
- Show Feast registry + online seller lookup  

## Demo 2 — Train

- Trigger Vertex training pipeline  
- Open MLflow run: params, metrics, Git SHA, snapshot ID  
- Show registered candidate (not yet champion)  

## Demo 3 — Serve

- REST `/v1/predict`  
- MCP `predict_late_delivery`  
- Response includes `model_version`  

## Demo 4 — Canary

- Deploy challenger 90/10  
- `make replay-baseline`  
- Show version-attributed prediction logs + comparative metrics  

## Demo 5 — Rollback

- `make canary-bad`  
- Gate fails → traffic back to champion 100%  

## Demo 6 — Drift / retrain

- `make replay-drift`  
- Airflow drift check alarm  
- H5 → pipeline → new candidate (H6 before promote)  

## Demo 7 — Cost / teardown

- Show monitoring signals  
- `make demo-down`  
- Confirm always-on resources gone; note COST.md  

**Never** skip human gates in the recorded story — show the approval step even if it is a CLI confirm.
