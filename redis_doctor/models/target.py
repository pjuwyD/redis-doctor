"""RedisTarget — parsed connection params. Never serializes the password value."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RedisTarget(BaseModel):
    """Parsed connection parameters.

    Stores *whether* a password exists, never the value in serialized output.
    """

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    username: str | None = None
    has_password: bool = False
    tls: bool = False
    socket_path: str | None = None

    # Excluded from serialization so it can never leak into a report.
    password: str | None = Field(default=None, exclude=True, repr=False)

    socket_timeout: float = 5.0
    connect_timeout: float = 5.0
    tls_ca_cert: str | None = None
    tls_cert: str | None = None
    tls_key: str | None = None

    def redacted_url(self) -> str:
        """Build a connection string with the password replaced by ***."""
        if self.socket_path:
            base = f"unix://{self.socket_path}"
            return f"{base}?db={self.db}" if self.db else base
        scheme = "rediss" if self.tls else "redis"
        auth = ""
        if self.username or self.has_password:
            user = self.username or ""
            secret = "***" if self.has_password else ""
            auth = f"{user}:{secret}@" if secret else f"{user}@"
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"

    def __str__(self) -> str:
        return self.redacted_url()
