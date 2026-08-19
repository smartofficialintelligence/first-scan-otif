"""Application configuration via environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "olist-ml"
    environment: str = "local"
    log_level: str = "INFO"

    data_dir: Path = Path("data/raw")
    fixture_dir: Path = Path("data/fixtures")
    artifact_dir: Path = Path("artifacts")
    model_path: Path = Path("artifacts/model.joblib")
    model_meta_path: Path = Path("artifacts/model_meta.json")

    model_version: str = "local-dev"
    random_seed: int = 42

    # Optuna / training
    n_optuna_trials: int = 25
    cv_folds: int = 3
    test_fraction: float = 0.15
    valid_fraction: float = 0.15
    replay_fraction: float = 0.10

    # Risk bands
    risk_low_max: float = 0.30
    risk_medium_max: float = 0.60

    # API
    auth_mode: str = "off"  # off | api_key
    api_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8080

    feast_repo_path: Path = Path("feature_repo")
    feast_online_enabled: bool = False

    feature_freshness_sla_hours: int = Field(default=36)

    # Decision policy (D1–D2): versioned simulation economics
    policy_economics_path: Path = Path("config/policy_economics.yaml")
    decision_ledger_path: Path = Path("artifacts/decision_ledger.jsonl")
    decision_base_seed: int = 42


def get_settings() -> Settings:
    return Settings()
