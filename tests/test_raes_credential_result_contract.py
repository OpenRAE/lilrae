"""Credential-bearing apply results meet RAES's closed result contract.

When a plan carries account credential bindings, RAES checks every returned
entry against the submitted operation: the entry status must name what the
backend did with the operation, and every payload value outside an admitted
realization concern must equal the operation's. APTL used to write RAES's
generic ``ready`` default and to remove every concern it did not observe, so
RAES refused every successful credential-bearing apply.

An unobserved concern is still removed where the plan admits realization
authority, so RAES's gate never compares the plan with itself (issue #578).
Where a credential-bearing plan closes the concern or grants no authority at
that address, RAES reads no observation and the value is the plan's, carried
through like a name. Any other plan keeps every unobserved concern removed
(ADR-046).
"""

from __future__ import annotations

import importlib.resources as ir
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import raes_processor.planner as raes_planner
from raes.runtime_configuration import RuntimeCapabilityPolicy
from raes_contracts.evaluation import EvaluationExecutionState, EvaluationResultStatus
from raes_contracts.planning import (
    ChangeAction,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
    RuntimeDomain,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.semantics.realization import CONCERN_PAYLOAD_PATH
from raes_processor.semantics.realization_runtime_common import (
    MISSING_CONCERN_VALUE,
    concern_value,
)
from raes_runtime.backend_account_credentials import (
    plan_has_account_credentials,
    sanitize_account_credential_result,
)

from aptl.backends.raes_diagnostics import (
    realized_changed_addresses,
    snapshot_after_apply,
)
from aptl.backends.raes_evaluator import AptlEvaluator
from aptl.backends.raes_observation import ObservedResource
from aptl.backends.raes_provisioner import closed_credential_result
from tests.test_raes_evaluator import _evaluation_plan, _snapshot_with_node_status

_NODE = "provision.node.vm"
_ACCOUNT = "provision.account-placement.analyst"
_DNS = CONCERN_PAYLOAD_PATH["runtime-dns-services"]
_ENVIRONMENT = CONCERN_PAYLOAD_PATH["runtime-environment"]
_PACKAGES = CONCERN_PAYLOAD_PATH["runtime-packages"]
_TOPOLOGY = CONCERN_PAYLOAD_PATH["domain-topology"]
_NODE_TYPE = CONCERN_PAYLOAD_PATH["node-type"]
_PORTS = CONCERN_PAYLOAD_PATH["published-ports"]
_CAPABILITIES = CONCERN_PAYLOAD_PATH["linux-capabilities"]
_COMPONENTS = CONCERN_PAYLOAD_PATH["runtime-software-components"]
_PAYLOAD_MISMATCH = "credential-bearing backend payload does not match the submitted plan"


def _payload() -> dict[str, object]:
    return {
        "name": "vm",
        "node_kind": "vm",
        "domain_topology": None,
        "spec": {
            "node": {
                "runtime": {
                    "dns_services": [],
                    "environment": [],
                    "packages": [{"name": "curl"}],
                    "network": None,
                }
            }
        },
    }


def _authority(kind: str, mode: RealizationAuthorityMode) -> ResolvedRealizationAuthority:
    path = CONCERN_PAYLOAD_PATH[kind]
    exact = mode is RealizationAuthorityMode.EXACT
    return ResolvedRealizationAuthority(
        address=_NODE,
        field_path="nodes.vm." + ".".join(path[2:] or path),
        domain="runtime-realization",
        requirement_kind=kind,
        payload_pointer="/" + "/".join(path),
        mode=mode,
        source=(
            RealizationResolutionSource.AUTHORED_LEAF
            if exact
            else RealizationResolutionSource.APPARATUS_DEFAULT
        ),
    )


def _operation(address, resource_type, payload, action=ChangeAction.CREATE):
    return ProvisionOp(
        action=action, address=address, resource_type=resource_type, payload=payload
    )


def _plan(operations, *authority: ResolvedRealizationAuthority) -> ProvisioningPlan:
    return ProvisioningPlan(
        resources={
            op.address: PlannedResource(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=op.payload,
            )
            for op in operations
        },
        operations=list(operations),
        realization_authority=authority,
    )


def _account_operation() -> ProvisionOp:
    """An account whose login carries a fixture credential."""

    binding = {
        "credential_id": "analyst-primary",
        "purpose": "primary_authentication",
        "auth_method": "password",
        "material": {"classification": "secret_fixture", "value": "fixture-value"},
    }
    account = {"spec": {"username": "analyst", "credential_bindings": [binding]}}
    return _operation(_ACCOUNT, "account-placement", account)


def _node_plan(
    *authority, action=ChangeAction.CREATE, credentials=False
) -> ProvisioningPlan:
    operations = [_operation(_NODE, "node", _payload(), action)]
    if credentials:
        operations.append(_account_operation())
    plan = _plan(operations, *authority)
    assert plan_has_account_credentials(plan) is credentials
    return plan


def _closed_and_open_plan(*, credentials=True) -> ProvisioningPlan:
    return _node_plan(
        _authority("runtime-dns-services", RealizationAuthorityMode.CLOSED),
        _authority("runtime-environment", RealizationAuthorityMode.OPEN),
        _authority("runtime-packages", RealizationAuthorityMode.OPEN),
        credentials=credentials,
    )


def _entry(plan: ProvisioningPlan, observed: ObservedResource):
    snapshot = snapshot_after_apply(plan, RuntimeSnapshot(), {_NODE: observed})
    return snapshot.entries[_NODE]


@pytest.mark.parametrize(
    ("action", "status"),
    [
        (ChangeAction.CREATE, "applied"),
        (ChangeAction.UPDATE, "applied"),
        (ChangeAction.UNCHANGED, "unchanged"),
    ],
)
def test_entry_status_names_what_the_backend_did_with_the_operation(action, status):
    plan = _node_plan(action=action)

    assert _entry(plan, ObservedResource(realized=True)).status == status


def test_unobserved_concern_keeps_the_plan_value_only_outside_admitted_authority():
    entry = _entry(_closed_and_open_plan(), ObservedResource(realized=True))

    # CLOSED, and no authority at all: RAES reads no observation there.
    assert concern_value(entry.payload, _DNS) == []
    assert concern_value(entry.payload, _TOPOLOGY) is None
    # Admitted but unobserved: absent, so RAES never accepts the plan's value.
    assert concern_value(entry.payload, _ENVIRONMENT) is MISSING_CONCERN_VALUE
    assert concern_value(entry.payload, _PACKAGES) is MISSING_CONCERN_VALUE


def test_an_observed_value_is_reported_even_where_the_plan_closes_the_concern():
    observed = ObservedResource(realized=True, concerns={_DNS: [{"name": "named"}]})

    entry = _entry(_closed_and_open_plan(), observed)

    assert concern_value(entry.payload, _DNS) == [{"name": "named"}]


@pytest.mark.parametrize(
    "plan",
    [
        pytest.param(_closed_and_open_plan(credentials=False), id="no-credentials"),
        pytest.param(_node_plan(credentials=True), id="no-authority"),
    ],
)
def test_other_plans_remove_every_unobserved_concern(plan):
    """Without credentials RAES needs no plan value (ADR-046); without authority
    it admits concerns from a compiled model the backend never sees."""

    entry = _entry(plan, ObservedResource(realized=True))

    for path in (_DNS, _ENVIRONMENT, _PACKAGES, _TOPOLOGY):
        assert concern_value(entry.payload, path) is MISSING_CONCERN_VALUE


@pytest.mark.parametrize("status", ["applied", "unchanged"])
def test_a_condition_reads_an_applied_or_unchanged_node_as_ready(status):
    result = AptlEvaluator().start(
        _evaluation_plan(), _snapshot_with_node_status(status)
    )

    condition = EvaluationExecutionState.from_payload(
        result.snapshot.evaluation_results["evaluation.condition.vm.health"]
    )
    assert condition.status == EvaluationResultStatus.READY
    assert condition.passed is True


# --------------------------------------------------------------------------- #
# Whole results through the installed RAES credential closure
# --------------------------------------------------------------------------- #


def _closed_result(plan, observations) -> ApplyResult:
    snapshot = snapshot_after_apply(plan, RuntimeSnapshot(), observations)
    return closed_credential_result(
        plan,
        ApplyResult(
            success=True,
            snapshot=snapshot,
            changed_addresses=realized_changed_addresses(plan, snapshot),
            details={"profiles": ["compose"]},
        ),
    )


def _closure_refusal(plan, observations) -> str | None:
    try:
        sanitize_account_credential_result(
            _closed_result(plan, observations), plan, RuntimeSnapshot()
        )
    except ValueError as exc:
        return str(exc)
    return None


def _credential_plan() -> ProvisioningPlan:
    """One node and one account whose login carries a fixture credential."""

    return _node_plan(
        _authority("node-type", RealizationAuthorityMode.EXACT),
        _authority("runtime-dns-services", RealizationAuthorityMode.CLOSED),
        _authority("published-ports", RealizationAuthorityMode.OPEN),
        credentials=True,
    )


def test_a_result_that_observes_the_plan_passes_the_closed_contract():
    """Status and plan-owned values are APTL's part, on every RAES release."""

    observations = {
        _NODE: ObservedResource(realized=True, concerns={_NODE_TYPE: "vm"}),
        _ACCOUNT: ObservedResource(realized=True),
    }

    assert _closure_refusal(_credential_plan(), observations) is None


@pytest.fixture(scope="module")
def techvault_plan(tmp_path_factory) -> ProvisioningPlan:
    """Plan the installed TechVault pack, whose SOC logins carry credentials."""

    from aptl.backends.raes import (
        RuntimeManager,
        create_aptl_runtime_target,
        parse_sdl_file,
    )
    from aptl.core.config import AptlConfig
    from aptl.core.scenario_bundle import env_pack_bundle
    from tests.techvault_pack import PROJECT_ROOT, _TECHVAULT_FLAG_PARAMETERS

    pack = ir.files("raes_env_packs") / "resources" / "packs" / "techvault"
    bundle = env_pack_bundle(
        tmp_path_factory.mktemp("credential-result"),
        identity="techvault",
        source_pack=pack,
    )
    config = AptlConfig(
        lab={"name": "tv"},
        containers=dict.fromkeys(
            ("wazuh", "soc", "enterprise", "victim", "kali", "fileshare", "dns"), True
        ),
    )
    target = create_aptl_runtime_target(
        project_dir=PROJECT_ROOT, config=config, backend=MagicMock(), bundle=bundle
    )
    plan = RuntimeManager(target).plan(
        parse_sdl_file(bundle.sdl_path), parameters=_TECHVAULT_FLAG_PARAMETERS
    ).provisioning
    assert plan_has_account_credentials(plan)
    return plan


def _admitted(plan: ProvisioningPlan) -> dict[str, set[str]]:
    admitted: dict[str, set[str]] = {}
    for authority in plan.realization_authority:
        if authority.mode is not RealizationAuthorityMode.CLOSED:
            admitted.setdefault(authority.address, set()).add(authority.requirement_kind)
    return admitted


def _observed_choice(path: tuple[str, ...], planned: object) -> object:
    """Observe the plan's value, or a capability choice where it declares none."""

    if planned is None and path == _CAPABILITIES:
        return RuntimeCapabilityPolicy(add=["CAP_NET_ADMIN"]).model_dump(mode="json")
    return deepcopy(planned)


def _differing_observations(plan: ProvisioningPlan) -> dict[str, ObservedResource]:
    """Observe every admitted concern; reorder one collection; choose open values.

    The choices are an OPEN capability policy where the plan has ``null`` and
    OPEN published ports under a ``null`` network parent.
    """

    admitted = _admitted(plan)
    observations = {}
    for address, resource in plan.resources.items():
        concerns = {}
        for kind in admitted.get(address, ()):
            path = CONCERN_PAYLOAD_PATH.get(kind)
            planned = concern_value(resource.payload, path) if path else MISSING_CONCERN_VALUE
            if planned is not MISSING_CONCERN_VALUE:
                concerns[path] = _observed_choice(path, planned)
            elif kind == "published-ports":
                concerns[path] = []
        observations[address] = ObservedResource(realized=True, concerns=concerns)
    reordered = next(
        observed.concerns
        for observed in observations.values()
        if len(observed.concerns.get(_COMPONENTS, ())) > 1
    )
    reordered[_COMPONENTS] = list(reversed(reordered[_COMPONENTS]))
    return observations


def test_differing_observations_are_admitted_once_raes_carries_rae_1640(
    techvault_plan,
):
    """raes 7.0.0 compares the whole payload; rae#1640 admits observed concerns.

    On 7.0.0 the only refusal left is that payload comparison, which shows that
    all 132 entry statuses already pass.
    """

    observations = _differing_observations(techvault_plan)

    refusal = _closure_refusal(techvault_plan, observations)

    if hasattr(raes_planner, "realization_payload_projections"):
        assert refusal is None
    else:
        assert refusal == _PAYLOAD_MISMATCH
