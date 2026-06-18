"""Stream models (Section 8.7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StreamConsumer(BaseModel):
    name: str
    pending: int = 0
    idle_ms: int = 0


class StreamGroup(BaseModel):
    name: str
    consumers: int = 0
    pending: int = 0
    last_delivered_id: str = "0-0"
    lag: int | None = None
    consumer_list: list[StreamConsumer] = Field(default_factory=list)


class StreamInfo(BaseModel):
    name: str
    length: int = 0
    first_id: str = "0-0"
    last_id: str = "0-0"
    groups: list[StreamGroup] = Field(default_factory=list)
