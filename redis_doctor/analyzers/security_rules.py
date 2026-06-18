"""Security/hygiene analyzer (Section 9.14)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.finding import Category, Confidence, Finding, Severity
from .base import Analyzer

if TYPE_CHECKING:
    from ..pipeline import RunContext

DEFAULT_USER_SHARE = 0.5


def _default_user_nopass(acl_list) -> bool | None:
    """True if the default user has nopass; None if ACL info is unavailable."""
    if not acl_list:
        return None
    for line in acl_list:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "user" and parts[1] == "default":
            return "nopass" in parts
    return None


class SecurityAnalyzer(Analyzer):
    name = "security"

    def analyze(self, ctx: RunContext) -> list[Finding]:
        data = ctx.collected.get("security")
        if data is None:
            return []

        findings: list[Finding] = []
        requirepass_set = data.get("requirepass_set", False)
        nopass = _default_user_nopass(data.get("acl_list"))

        # No auth: no requirepass and the default user requires no password
        # (or ACL info unavailable, in which case assume the legacy default).
        no_auth = not requirepass_set and (nopass is None or nopass is True)
        if no_auth:
            findings.append(
                Finding(
                    id="security.no_auth",
                    severity=Severity.CRITICAL,
                    category=Category.SECURITY,
                    confidence=Confidence.HIGH if nopass is not None else Confidence.MEDIUM,
                    title="Redis has no authentication configured",
                    explanation=(
                        "An unauthenticated Redis lets anyone who can reach the port "
                        "read and modify all data."
                    ),
                    evidence={"requirepass_set": requirepass_set, "default_user_nopass": nopass},
                    suggested_checks=["redis-cli ACL LIST", "redis-cli CONFIG GET requirepass"],
                    suggested_fixes=[
                        "Set requirepass or configure ACL users with passwords",
                        "Restrict network access with a firewall",
                    ],
                )
            )

        total = data.get("total_clients", 0)
        default_clients = data.get("default_user_clients", 0)
        default_share = (default_clients / total) if total else 0
        if (nopass is True) or (total and default_share >= DEFAULT_USER_SHARE):
            findings.append(
                Finding(
                    id="security.default_user",
                    severity=Severity.WARNING,
                    category=Category.SECURITY,
                    title="The default user is enabled / widely used",
                    explanation=(
                        "Relying on the default user makes it hard to scope and revoke "
                        "access. Per-service ACL users are safer."
                    ),
                    evidence={
                        "default_user_nopass": nopass,
                        "default_user_clients": default_clients,
                        "total_clients": total,
                    },
                    suggested_checks=["redis-cli ACL LIST", "redis-cli ACL WHOAMI"],
                    suggested_fixes=["Create per-service ACL users", "Disable or restrict default"],
                )
            )

        if data.get("protected_mode") == "no":
            findings.append(
                Finding(
                    id="security.protected_mode_off",
                    severity=Severity.WARNING,
                    category=Category.SECURITY,
                    title="protected-mode is disabled",
                    explanation=(
                        "With protected-mode off and no auth, Redis accepts commands "
                        "from any client that can reach it over the network."
                    ),
                    evidence={"protected_mode": "no"},
                    suggested_checks=["redis-cli CONFIG GET protected-mode"],
                    suggested_fixes=["Enable protected-mode or require authentication"],
                )
            )

        return findings
