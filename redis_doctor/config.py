"""Configuration loading: built-in defaults < config file < env vars < CLI flags.

The full schema is Section 7.2 of the spec. Thresholds are consumed by the rule
engine; analyzers read them via the engine, not directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .errors import ConfigError

ENV_PASSWORD = "REDIS_DOCTOR_PASSWORD"
ENV_USERNAME = "REDIS_DOCTOR_USERNAME"
ENV_CONFIG = "REDIS_DOCTOR_CONFIG"


class ConnectionConfig(BaseModel):
    timeout_seconds: float = 5.0


class ScanConfig(BaseModel):
    sample_size: int = 10000
    count: int = 1000
    max_seconds: float = 30.0
    prefix_depth: int = 2
    prefix_separators: str = ":.|/_"


class Thresholds(BaseModel):
    memory_warning_pct: float = 80
    memory_critical_pct: float = 90
    fragmentation_warning_ratio: float = 1.5
    idle_client_warning_seconds: int = 3600
    idle_client_warning_count: int = 100
    idle_client_critical_count: int = 500
    blocked_client_warning: int = 1
    big_key_mb: float = 10
    huge_key_mb: float = 100
    large_collection: int = 10000
    huge_collection: int = 100000
    stream_length_warning: int = 100000
    stream_pending_warning: int = 10000
    consumer_idle_warning_seconds: int = 3600
    slowlog_max_entries: int = 128
    replica_lag_warning_seconds: int = 30
    replica_lag_critical_seconds: int = 120
    cached_scripts_warning: int = 1000
    scripts_memory_warning_mb: float = 50
    eval_inline_warning: int = 5


class TTLExpectation(BaseModel):
    pattern: str
    ttl_required: bool = False
    max_ttl_seconds: int | None = None


class IgnoreConfig(BaseModel):
    keys: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class OutputConfig(BaseModel):
    format: str = "terminal"
    fail_on: str = "none"


class NotifyConfig(BaseModel):
    slack_webhook_url: str | None = None
    email: str | None = None


class HistoryConfig(BaseModel):
    enabled: bool = False
    path: str = "~/.redis-doctor/history.db"


class Config(BaseModel):
    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    ttl_expectations: list[TTLExpectation] = Field(default_factory=list)
    rules: dict[str, dict[str, Any]] = Field(default_factory=dict)
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)


def _load_file(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must be a mapping at top level")
    return data


def load_config(config_path: str | None = None) -> Config:
    """Resolve defaults < file < env. CLI flags are applied by the caller."""
    path = config_path or os.environ.get(ENV_CONFIG)
    data: dict[str, Any] = _load_file(path) if path else {}

    try:
        cfg = Config.model_validate(data)
    except Exception as e:
        raise ConfigError(f"Invalid config: {e}") from e
    return cfg
