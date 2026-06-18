"""KeySample and KeyInfo — output of the keyspace sampling engine (Section 6)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .finding import Confidence


class KeyInfo(BaseModel):
    key: str
    type: str = "none"
    ttl_seconds: int = -1  # -1 = no TTL, -2 = missing/expired during scan
    memory_bytes: int | None = None
    element_count: int | None = None


class KeySample(BaseModel):
    scanned: int = 0
    estimated_total: int = 0
    duration_seconds: float = 0.0
    complete: bool = False
    confidence: Confidence = Confidence.LOW
    keys: list[KeyInfo] = Field(default_factory=list)
