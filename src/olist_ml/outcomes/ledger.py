"""Local JSONL decision / action / outcome ledger (D4)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class DecisionLedger:
    """Append-only lineage store for portfolio demos (no BigQuery required)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record_type: str, payload: BaseModel | dict[str, Any]) -> None:
        if isinstance(payload, BaseModel):
            body = payload.model_dump(mode="json")
        else:
            body = dict(payload)
        row = {"record_type": record_type, **body}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    def append_prediction(self, payload: BaseModel | dict[str, Any]) -> None:
        self.append("prediction", payload)

    def append_decision(self, payload: BaseModel | dict[str, Any]) -> None:
        self.append("decision", payload)

    def append_action(self, payload: BaseModel | dict[str, Any]) -> None:
        self.append("action", payload)

    def append_outcome(self, payload: BaseModel | dict[str, Any]) -> None:
        self.append("outcome", payload)

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def for_order(self, order_id: str) -> list[dict[str, Any]]:
        return [r for r in self.read_all() if r.get("order_id") == order_id]

    def for_action(self, action_id: str) -> list[dict[str, Any]]:
        return [r for r in self.read_all() if r.get("action_id") == action_id]

    def extend(self, records: Iterable[tuple[str, BaseModel | dict[str, Any]]]) -> None:
        for record_type, payload in records:
            self.append(record_type, payload)
