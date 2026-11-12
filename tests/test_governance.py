"""
Local governance tests using synthetic principals.

No Azure authentication or deployed policy mutation occurs.
"""

from dataclasses import FrozenInstanceError

import pytest

from src.identity.jwt_validator import AuthenticatedPrincipal
from src.policy.governance import GovernanceError, PolicyGovernance


def actor(subject, *roles):
    return AuthenticatedPrincipal(subject=subject, roles=roles)


PROPOSER = actor("synthetic-proposer", "Governance.Proposer")
APPROVER = actor("synthetic-approver", "Governance.Approver")
DEPLOYER = actor("synthetic-deployer", "Governance.Deployer")
INFERENCE_ADMIN = actor("synthetic-admin", "Inference.Admin")
NEW_ROLES = frozenset({"Inference.Admin"})


def proposal(workflow):
    return workflow.propose(PROPOSER, "research-model", NEW_ROLES)


def test_three_party_workflow_changes_only_local_policy():
    workflow = PolicyGovernance()
    change = proposal(workflow)

    assert workflow.snapshot()[1]["research-model"] == frozenset({
        "Inference.Reader"
    })

    approved = workflow.approve(APPROVER, change.change_id)
    assert approved.status == "approved"

    # Approval alone does not apply the change.
    assert workflow.snapshot()[0] == 1

    applied = workflow.apply(DEPLOYER, change.change_id)
    version, policy = workflow.snapshot()

    assert applied.status == "applied"
    assert applied.proposer == PROPOSER.subject
    assert applied.approver == APPROVER.subject
    assert applied.deployer == DEPLOYER.subject
    assert version == 2
    assert policy["research-model"] == NEW_ROLES


@pytest.mark.parametrize("operation", ["propose", "approve", "apply"])
def test_inference_admin_has_no_governance_authority(operation):
    workflow = PolicyGovernance()
    change = proposal(workflow)
    workflow.approve(APPROVER, change.change_id)
    before = workflow.snapshot()

    with pytest.raises(GovernanceError):
        if operation == "propose":
            workflow.propose(
                INFERENCE_ADMIN,
                "research-model",
                NEW_ROLES,
            )
        elif operation == "approve":
            workflow.approve(INFERENCE_ADMIN, change.change_id)
        else:
            workflow.apply(INFERENCE_ADMIN, change.change_id)

    assert workflow.snapshot() == before


def test_proposer_cannot_self_approve_even_with_role():
    workflow = PolicyGovernance()
    change = proposal(workflow)
    combined = actor(
        PROPOSER.subject,
        "Governance.Proposer",
        "Governance.Approver",
    )

    with pytest.raises(GovernanceError):
        workflow.approve(combined, change.change_id)


@pytest.mark.parametrize("subject", [PROPOSER.subject, APPROVER.subject])
def test_deployer_must_be_distinct_from_both_parties(subject):
    workflow = PolicyGovernance()
    change = proposal(workflow)
    workflow.approve(APPROVER, change.change_id)

    with pytest.raises(GovernanceError):
        workflow.apply(
            actor(subject, "Governance.Deployer"),
            change.change_id,
        )


def test_unapproved_change_cannot_be_applied():
    workflow = PolicyGovernance()
    change = proposal(workflow)

    with pytest.raises(GovernanceError):
        workflow.apply(DEPLOYER, change.change_id)

    assert workflow.snapshot()[0] == 1


def test_stale_approved_change_cannot_overwrite_new_policy():
    workflow = PolicyGovernance()
    first = proposal(workflow)
    second = proposal(workflow)

    workflow.approve(APPROVER, first.change_id)
    workflow.approve(APPROVER, second.change_id)
    workflow.apply(DEPLOYER, first.change_id)
    before = workflow.snapshot()

    with pytest.raises(GovernanceError):
        workflow.apply(DEPLOYER, second.change_id)

    assert workflow.snapshot() == before


def test_applied_change_cannot_be_replayed():
    workflow = PolicyGovernance()
    change = proposal(workflow)
    workflow.approve(APPROVER, change.change_id)
    workflow.apply(DEPLOYER, change.change_id)

    with pytest.raises(GovernanceError):
        workflow.apply(DEPLOYER, change.change_id)

    assert workflow.snapshot()[0] == 2


def test_returned_proposal_cannot_be_modified():
    workflow = PolicyGovernance()
    change = proposal(workflow)

    with pytest.raises(FrozenInstanceError):
        change.roles = frozenset({"Inference.Reader"})


def test_snapshot_mutation_does_not_change_internal_policy():
    workflow = PolicyGovernance()
    _, policy = workflow.snapshot()
    policy["research-model"] = NEW_ROLES

    assert workflow.snapshot()[1]["research-model"] == frozenset({
        "Inference.Reader"
    })


@pytest.mark.parametrize(
    "model,roles",
    [
        ("unknown-model", NEW_ROLES),
        ("research-model", frozenset()),
        ("research-model", frozenset({"Governance.Deployer"})),
    ],
)
def test_invalid_policy_changes_rejected(model, roles):
    workflow = PolicyGovernance()

    with pytest.raises(GovernanceError):
        workflow.propose(PROPOSER, model, roles)