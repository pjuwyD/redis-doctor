"""SlowlogEntry (Section 8.9)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SlowlogEntry(BaseModel):
    id: int = 0
    timestamp: int = 0
    duration_us: int = 0
    command: str = ""
    args: list[str] = Field(default_factory=list)  # redacted if they look like secrets
