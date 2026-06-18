"""Command allow/deny lists and guardrails (Section 5).

Consulted before any Redis command runs. The tool is read-only by default.
`KEYS` and `MONITOR` are blocked unconditionally, regardless of flags.
"""

from __future__ import annotations

from .errors import UnsafeCommandError

# Read-only commands allowed by default. Multi-word commands are keyed by their
# first token; subcommand checking is handled separately where it matters.
ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        "PING",
        "INFO",
        "CONFIG",  # only GET is allowed; SET is in WRITE_COMMANDS
        "DBSIZE",
        "CLIENT",  # LIST / INFO only; KILL is in WRITE_COMMANDS
        "SLOWLOG",  # GET / LEN only; RESET is mutating
        "LATENCY",  # LATEST / DOCTOR only
        "MEMORY",  # STATS / USAGE only; PURGE is in WRITE_COMMANDS
        "SCAN",
        "TYPE",
        "TTL",
        "PTTL",
        "STRLEN",
        "LLEN",
        "SCARD",
        "ZCARD",
        "HLEN",
        "XLEN",
        "XINFO",
        "ACL",  # WHOAMI / LIST only
        "SENTINEL",  # read subcommands only
        "CLUSTER",  # read subcommands only
        "COMMAND",
        "WAIT",  # used by nothing here, harmless read
    }
)

# Commands that require --allow-write. No command path uses this flag.
WRITE_COMMANDS: frozenset[str] = frozenset(
    {
        "FLUSHDB",
        "FLUSHALL",
        "CONFIG SET",
        "CLIENT KILL",
        "EVAL",
        "EVALSHA",
        "SCRIPT",
        "MEMORY PURGE",
        "XTRIM",
        "XGROUP",
        "XAUTOCLAIM",
        "XCLAIM",
        "DEL",
        "UNLINK",
        "EXPIRE",
        "PEXPIRE",
        "PERSIST",
        "SET",
        "GETDEL",
        "GETSET",
        "SLOWLOG RESET",
        "ACL SETUSER",
        "ACL DELUSER",
    }
)

# Bounded read commands, allowed by default. These are cursor- or range-bounded
# and cannot return a whole large value in a single unbounded call when the
# caller passes a COUNT/range (the Explore service always does). Used to "peek"
# into collections without an O(N) full read.
BOUNDED_READ_COMMANDS: frozenset[str] = frozenset(
    {
        "HSCAN",
        "SSCAN",
        "ZSCAN",
        "XRANGE",
        "XREVRANGE",
        "GETRANGE",
        "LINDEX",
        "OBJECT",  # ENCODING / IDLETIME / REFCOUNT / FREQ — all read-only
    }
)

# Full-value reads. These return entire values and are O(N), so they are gated
# behind `allow_expensive` (the Explore tab's "unlock"). They are reads, not
# writes — distinct from WRITE_COMMANDS.
EXPENSIVE_READ_COMMANDS: frozenset[str] = frozenset(
    {
        "GET",
        "MGET",
        "HGETALL",
        "HKEYS",
        "HVALS",
        "HMGET",
        "LRANGE",
        "SMEMBERS",
        "SRANDMEMBER",
        "ZRANGE",
        "ZREVRANGE",
        "ZRANGEBYSCORE",
        "ZRANGEBYLEX",
        "DUMP",
    }
)

# Always blocked, under any flag.
NEVER_ALLOWED: frozenset[str] = frozenset({"KEYS", "MONITOR"})

# Per-command subcommands that are mutating and therefore blocked unless --allow-write.
_MUTATING_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "CONFIG": frozenset({"SET", "RESETSTAT", "REWRITE"}),
    "CLIENT": frozenset({"KILL", "SETNAME", "PAUSE", "UNPAUSE", "NO-EVICT", "NO-TOUCH"}),
    "MEMORY": frozenset({"PURGE", "MALLOC-STATS"}),
    "SLOWLOG": frozenset({"RESET"}),
    "ACL": frozenset({"SETUSER", "DELUSER", "LOAD", "SAVE"}),
    "SCRIPT": frozenset({"FLUSH", "LOAD"}),
}


def _normalize(command: str, *args: object) -> tuple[str, str | None]:
    """Return (COMMAND, SUBCOMMAND or None), upper-cased."""
    cmd = command.strip().upper()
    sub = str(args[0]).strip().upper() if args else None
    return cmd, sub


def check_command(
    command: str,
    *args: object,
    allow_write: bool = False,
    allow_expensive: bool = False,
) -> None:
    """Raise UnsafeCommandError if the command is not permitted.

    `command` is the first token (e.g. "CONFIG"); `args` are its arguments,
    used to inspect subcommands (e.g. CONFIG SET).

    `allow_expensive` unlocks the full-value reads in EXPENSIVE_READ_COMMANDS
    (the Explore tab's "unlock"); they remain reads, never writes.
    """
    cmd, sub = _normalize(command, *args)

    if cmd in NEVER_ALLOWED:
        raise UnsafeCommandError(f"{cmd} is never permitted by redis-doctor")

    # A mutating subcommand of an otherwise-allowed command.
    mutating = _MUTATING_SUBCOMMANDS.get(cmd, frozenset())
    if sub is not None and sub in mutating:
        if not allow_write:
            raise UnsafeCommandError(f"{cmd} {sub} mutates state and requires --allow-write")
        return

    # A bare write command.
    if cmd in WRITE_COMMANDS or (sub and f"{cmd} {sub}" in WRITE_COMMANDS):
        if not allow_write:
            raise UnsafeCommandError(
                f"{cmd}{' ' + sub if sub else ''} mutates state and requires --allow-write"
            )
        return

    # A full-value read, gated by the explicit unlock.
    if cmd in EXPENSIVE_READ_COMMANDS:
        if not allow_expensive:
            raise UnsafeCommandError(
                f"{cmd} reads whole values and requires unlocking full value reads"
            )
        return

    if cmd in ALLOWED_COMMANDS or cmd in BOUNDED_READ_COMMANDS:
        return

    # Anything not explicitly allowed is rejected (default-deny).
    raise UnsafeCommandError(f"{cmd} is not in the read-only allow list")


def is_blocked_unconditionally(command: str) -> bool:
    return command.strip().upper() in NEVER_ALLOWED
