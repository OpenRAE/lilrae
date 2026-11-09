"""Open node OS fields take the adapter's known identity before start."""

from types import SimpleNamespace

from raes_contracts.planning import (
    ChangeAction,
    ProvisionOp,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
)

from aptl.backends.raes_prepared_completions import complete_operating_systems


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


def test_backend_selected_values_are_prepared_in_readback_form():
    from raes.runtime_configuration import RuntimeConfiguration

    from aptl.backends.raes_prepared_completions import complete_backend_selections

    open_ = RealizationAuthorityMode.OPEN
    request = SimpleNamespace(realization_authority=(
        ResolvedRealizationAuthority(
            address="provision.node.misp", field_path="runtime.environment", domain="provisioning",
            requirement_kind="runtime-environment", payload_pointer="/spec/node/runtime/environment",
            mode=open_, source=RealizationResolutionSource.AUTHORED_LEAF,
        ),
    ))
    operation = ProvisionOp(action=ChangeAction.CREATE, address="provision.node.misp", resource_type="node",
                            payload={"name": "misp", "spec": {"node": {"runtime": {}}}})
    runtime = RuntimeConfiguration.model_validate({"environment": [
        {"name": "DISABLE_CA_REFRESH", "value": "true"},
        {"name": "ADMIN_KEY", "value_classification": "redacted"},
    ]})
    node = SimpleNamespace(address="provision.node.misp", runtime=runtime,
                           backend_selected_concerns=("compute-substrate", "runtime-environment"))
    operations = {operation.address: operation}
    complete_backend_selections(request, operations, SimpleNamespace(nodes=(node,)))
    prepared = operations[operation.address].payload["spec"]["node"]["runtime"]["environment"]
    assert sorted(item["name"] for item in prepared) == ["ADMIN_KEY", "DISABLE_CA_REFRESH"]
    # A value already in the plan stays as it is.
    complete_backend_selections(request, operations, SimpleNamespace(nodes=(replace_runtime(node),)))
    assert operations[operation.address].payload["spec"]["node"]["runtime"]["environment"] == prepared


def replace_runtime(node):
    from raes.runtime_configuration import RuntimeConfiguration

    return SimpleNamespace(**{**vars(node), "runtime": RuntimeConfiguration.model_validate(
        {"environment": [{"name": "OTHER", "value": "x"}]})})


def test_observed_records_follow_the_declared_order():
    from aptl.backends._raes_declared_order import in_declared_order

    declared = {"ship_targets": [{"target_id": "b", "port": 1514}, {"target_id": "a", "port": 1515}]}
    observed = {"ship_targets": [{"target_id": "a", "port": 1515}, {"target_id": "b", "port": 1514}]}
    assert in_declared_order(observed, declared) == declared
    files = [{"path": "/root/root.txt"}, {"path": "/var/log/x"}]
    assert in_declared_order(list(reversed(files)), files) == files
    # Without a shared unique identity, the observed order stays.
    unnamed = [{"mode": "0600"}, {"mode": "0600"}]
    assert in_declared_order(unnamed, [{"mode": "0600"}]) == unnamed
    # An observed record that the scenario does not declare goes last.
    assert in_declared_order([{"path": "/extra"}, *files], files)[-1] == {"path": "/extra"}
