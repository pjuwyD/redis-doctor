"""Structured logging with secret scrubbing.

Any password that has been registered via `register_secret` is replaced with
`***` in every log record, regardless of where it appears in the message.
"""

from __future__ import annotations

import logging
import re

_REDACTION = "***"

# Secrets registered at runtime (passwords). Stored only to scrub them out.
_secrets: set[str] = set()

# Redact `redis://user:password@host` and `:password@` patterns in URLs.
_URL_PASSWORD_RE = re.compile(r"(?P<scheme>rediss?://)(?P<user>[^:@/]*):(?P<pw>[^@/]+)@")


def register_secret(secret: str | None) -> None:
    if secret:
        _secrets.add(secret)


def clear_secrets() -> None:
    _secrets.clear()


def scrub(text: str) -> str:
    """Remove known secrets and URL-embedded passwords from a string."""
    if not text:
        return text
    out = _URL_PASSWORD_RE.sub(
        lambda m: f"{m.group('scheme')}{m.group('user')}:{_REDACTION}@", text
    )
    for secret in _secrets:
        if secret:
            out = out.replace(secret, _REDACTION)
    return out


class _ScrubbingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        if record.args:
            record.args = tuple(scrub(a) if isinstance(a, str) else a for a in record.args)
        return True


def configure(level: int = logging.WARNING) -> logging.Logger:
    logger = logging.getLogger("redis_doctor")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        handler.addFilter(_ScrubbingFilter())
        logger.addHandler(handler)
    return logger


def get_logger(name: str = "redis_doctor") -> logging.Logger:
    return logging.getLogger(name)
