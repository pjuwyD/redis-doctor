"""Typed exceptions mapped to the exit-code contract (Section 7.4)."""

from __future__ import annotations


class ExitCode:
    """Mandatory exit-code contract."""

    SUCCESS = 0
    FINDINGS_WARNING = 1
    FINDINGS_CRITICAL = 2
    CONNECTION_ERROR = 3
    INVALID_CONFIG = 4
    INTERNAL_ERROR = 5


class RedisDoctorError(Exception):
    """Base class. Carries the process exit code to use when uncaught."""

    exit_code: int = ExitCode.INTERNAL_ERROR


class ConnectionError(RedisDoctorError):
    """Connection or authentication failure."""

    exit_code = ExitCode.CONNECTION_ERROR


class ConfigError(RedisDoctorError):
    """Invalid config file or invalid CLI arguments."""

    exit_code = ExitCode.INVALID_CONFIG


class UnsafeCommandError(RedisDoctorError):
    """A command blocked by the safety layer was attempted."""

    exit_code = ExitCode.INTERNAL_ERROR


class InternalError(RedisDoctorError):
    """Unexpected internal failure."""

    exit_code = ExitCode.INTERNAL_ERROR
