"""ClientInfo (Section 8.8)."""

from __future__ import annotations

from pydantic import BaseModel


class ClientInfo(BaseModel):
    addr: str = ""
    name: str = ""
    user: str = ""
    db: int = 0
    age_seconds: int = 0
    idle_seconds: int = 0
    flags: str = ""
    last_cmd: str = ""
    output_buffer: int = 0
