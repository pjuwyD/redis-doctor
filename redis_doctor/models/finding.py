"""Finding — the central object. Every analyzer emits a list of these."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Category(str, Enum):
    SERVER = "server"
    MEMORY = "memory"
    KEYSPACE = "keyspace"
    TTL = "ttl"
    BIGKEY = "bigkey"
    TYPES = "types"
    STREAMS = "streams"
    CLIENTS = "clients"
    SLOWLOG = "slowlog"
    LATENCY = "latency"
    CONFIG = "config"
    PERSISTENCE = "persistence"
    REPLICATION = "replication"
    SECURITY = "security"
    SENTINEL = "sentinel"
    CLUSTER = "cluster"


class Finding(BaseModel):
    id: str
    severity: Severity
    category: Category
    confidence: Confidence = Confidence.HIGH
    title: str
    explanation: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_checks: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    affected: list[str] = Field(default_factory=list)
