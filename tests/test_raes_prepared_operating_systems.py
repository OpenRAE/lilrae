"""Open node OS fields take the adapter's known identity before start."""

from types import SimpleNamespace

from raes_contracts.planning import (
    ChangeAction,
    ProvisionOp,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
)

from aptl.backends.raes_prepared_operating_systems import complete_operating_systems


def _authority(address: str, kind: str, mode: RealizationAuthorityMode) -> ResolvedRealizationAuthority:
    field = kind.replace("-", "_")
    return ResolvedRealizationAuthority(
        address=address, field_path=field, domain="provisioning", requirement_kind=kind,
        payload_pointer="/" + field, mode=mode, source=RealizationResolutionSource.AUTHORED_LEAF,
    )


def _node(name: str, **payload: object) -> ProvisionOp:
    return ProvisionOp(action=ChangeAction.CREATE, address=f"provision.node.{name}",
                       resource_type="node", payload={"name": name, "os_distribution": None,
                                                      "os_version": "", **payload})


def test_only_blank_open_fields_of_known_nodes_are_completed():
    open_, exact = RealizationAuthorityMode.OPEN, RealizationAuthorityMode.EXACT
    request = SimpleNamespace(realization_authority=(
        _authority("provision.node.ad", "os-distribution", open_),
        _authority("provision.node.ad", "os-version", open_),
        _authority("provision.node.db", "os-distribution", open_),
        _authority("provision.node.misp", "os-distribution", exact),
        _authority("provision.node.misp", "os-version", exact),
        _authority("provision.node.db", "os-version", open_),
        _authority("provision.node.dns", "os-distribution", open_),
        _authority("provision.node.dns", "os-version", open_),
    ))
    operations = {op.address: op for op in (
        _node("ad"), _node("db", os_distribution="debian"), _node("dns"), _node("kali"), _node("misp"))}
    known = {"ad": ("ubuntu", "26.04"), "db": ("ubuntu", "24.04"), "kali": ("debian", "13"), "misp": ("debian", "13")}
    complete_operating_systems(request, operations, known)
    payload = {name: operations[f"provision.node.{name}"].payload for name in ("ad", "db", "dns", "kali", "misp")}
    assert (payload["ad"]["os_distribution"], payload["ad"]["os_version"]) == ("ubuntu", "26.04")
    # An open field that already holds a value keeps it; a blank one is completed.
    assert (payload["db"]["os_distribution"], payload["db"]["os_version"]) == ("debian", "24.04")
    # A node the adapter does not know, or without open authority, is unchanged.
    assert (payload["dns"]["os_distribution"], payload["dns"]["os_version"]) == (None, "")
    assert (payload["kali"]["os_distribution"], payload["kali"]["os_version"]) == (None, "")
    assert (payload["misp"]["os_distribution"], payload["misp"]["os_version"]) == (None, "")
