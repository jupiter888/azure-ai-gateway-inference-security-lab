"""
Local policy-governance workflow.

Three distinct subjects propose, approve, and apply a change.
Immutable proposals bind approval to a specific policy version.

This module does not authenticate callers, persist state, or
modify the deployed gateway policy.
"""

from dataclasses import dataclass, replace
from threading import Lock
from uuid import uuid4

from src.identity.jwt_validator import AuthenticatedPrincipal


ALLOWED_INFERENCE_ROLES = frozenset({
    "Inference.Reader",
    "Inference.Admin",
})

ALLOWED_MODELS = frozenset({
    "research-model",
    "restricted-model",
})


class GovernanceError(Exception):
    pass


@dataclass(frozen=True)
class PolicyChange:
    change_id: str
    model: str
    roles: frozenset[str]
    base_version: int
    proposer: str
    status: str = "proposed"
    approver: str | None = None
    deployer: str | None = None


class PolicyGovernance:
    def __init__(self):
        self._policy = {
            "research-model": frozenset({"Inference.Reader"}),
            "restricted-model": frozenset({"Inference.Admin"}),
        }
        self._version = 1
        self._changes: dict[str, PolicyChange] = {}
        self._lock = Lock()

    @staticmethod
    def _require(
        principal: AuthenticatedPrincipal,
        required_role: str,
    ) -> None:
        if (
            not isinstance(principal.subject, str)
            or not principal.subject
            or required_role not in principal.roles
        ):
            raise GovernanceError("Governance authorization denied")

    def _get(self, change_id: str) -> PolicyChange:
        change = self._changes.get(change_id)
        if change is None:
            raise GovernanceError("Unknown policy change")
        return change

    def propose(
        self,
        principal: AuthenticatedPrincipal,
        model: str,
        roles: frozenset[str],
    ) -> PolicyChange:
        self._require(principal, "Governance.Proposer")

        # Take an immutable copy before storing the proposal.
        requested_roles = frozenset(roles)

        if (
            model not in ALLOWED_MODELS
            or not requested_roles
            or not requested_roles.issubset(ALLOWED_INFERENCE_ROLES)
        ):
            raise GovernanceError("Invalid policy change")

        with self._lock:
            change = PolicyChange(
                change_id=str(uuid4()),
                model=model,
                roles=requested_roles,
                base_version=self._version,
                proposer=principal.subject,
            )
            self._changes[change.change_id] = change
            return change

    def approve(
        self,
        principal: AuthenticatedPrincipal,
        change_id: str,
    ) -> PolicyChange:
        self._require(principal, "Governance.Approver")

        with self._lock:
            change = self._get(change_id)

            if principal.subject == change.proposer:
                raise GovernanceError("Separation of duties required")
            if change.status != "proposed":
                raise GovernanceError("Change is not awaiting approval")
            if change.base_version != self._version:
                raise GovernanceError("Stale policy change")

            approved = replace(
                change,
                status="approved",
                approver=principal.subject,
            )
            self._changes[change_id] = approved
            return approved

    def apply(
        self,
        principal: AuthenticatedPrincipal,
        change_id: str,
    ) -> PolicyChange:
        self._require(principal, "Governance.Deployer")

        with self._lock:
            change = self._get(change_id)

            if principal.subject in {
                change.proposer,
                change.approver,
            }:
                raise GovernanceError("Separation of duties required")
            if change.status != "approved":
                raise GovernanceError("Approved change required")
            if change.base_version != self._version:
                raise GovernanceError("Stale policy change")

            applied = replace(
                change,
                status="applied",
                deployer=principal.subject,
            )

            self._policy[change.model] = change.roles
            self._version += 1
            self._changes[change_id] = applied
            return applied

    def snapshot(self) -> tuple[int, dict[str, frozenset[str]]]:
        with self._lock:
            return self._version, dict(self._policy)