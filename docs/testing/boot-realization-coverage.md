# Boot realization coverage

This Reference maps the `realization-envelope-v1` claims to their verification owners.
`src/aptl/backends/raes_realization_envelope.py` owns the disclosure.
The table is maintained by hand; it is not another capability registry.
Issue #1126 tracks derived coverage.

The clean-install job uses the product-neutral [lab fixture pack](lab-fixture-pack.md).
It selects the SDL by explicit path, so the boot proves installed lifecycle behavior rather than pack admission.
Unit tests separately prove admission through the production resolver.

The shared scenario has one causal chain:

1. Inline content moves the SSH daemon from its package-default port.
2. The declared service unit starts it.
3. The declared listener binds the moved port.
4. An exact loopback host binding publishes that port.

`scripts/ci/assert_boot_realization.py` observes effects in the running lab.
A failed placement therefore fails the listener, publication, and endpoint checks.

## Advertised concerns

| Concern | Covered by |
| --- | --- |
| `compute-substrate` | Boot gate (the node's container runs). Focused: `tests/test_compose_base_substrate.py`, `tests/test_raes_base_substrate.py` |
| `operating-system` | Boot gate (the substrate is selected by declared family). Focused: `tests/test_raes_observation.py` |
| `topology`, `network` | Boot gate reads back the node's declared isolated-network endpoint, allocated IPv4 address and DNS alias; a container only on Docker's default bridge fails. Focused: `tests/test_compose_network_readback.py`, `tests/test_compose_boundary_realization.py`, `tests/test_network_boundary_helper.py` |
| `content-placement` | Boot gate, live and causal (exact placed bytes, read inside the container). Focused: `tests/test_content_realization_source_policy.py`, `tests/test_raes_materializer.py`, `tests/test_raes_materializer_engine.py` |
| `account-placement` | Boot gate observes the declared local user and group. Focused: `tests/test_deployment_backend.py`, `tests/test_account_provider.py`. Directory and domain account features stay outside the boot |
| `service` | Boot gate, live (`UnitFileState`, `ActiveState`, `Result` read from the service manager) on the apt/Debian systemd substrate. Focused: `tests/test_raes_materializer.py` pins substrate selection per package family, `tests/test_raes_runtime_observation.py` the observation cases |
| `resource-allocation` | Focused only: `tests/test_raes_runtime_environment.py`, `tests/test_compose_resource_ownership.py`. The boot gate makes no claim |
| `image` | Focused only: `tests/test_docker_image_identity.py`, `tests/test_raes_docker_materializer.py`. Every boot scenario node is [base-container-materialized](../components/node-realization.md) and has no node image, so the boot gate makes no claim |
| `architecture` | Focused only: `tests/test_raes_observation.py`. The boot gate makes no claim |
| `acl` | Focused only: `tests/test_raes_acl_realization.py`. The boot gate makes no claim |
| `feature-binding` | Disclosed `unsupported`. There is no positive claim to cover |

## Beyond the envelope

| Capability | Covered by |
| --- | --- |
| Declared service listeners | Boot gate, live, read from outside the container's trust boundary. Focused: `tests/test_declared_listener_readiness.py`, `tests/test_proc_net_listeners.py` |
| Host-published ports | Boot gate, live: the exact declared loopback tuple, no wider binding, and a real connection. Focused: `tests/test_compose_port_realization.py`, `tests/test_docker_compose_port_bindings.py` |
| Orchestrator `workflows` | Boot gate, live: one end-only workflow driven to a terminal RAES state with history, parsed with the contract model. Focused: `tests/test_raes_orchestrator.py`, `tests/test_workflow_engine.py` |
| Lifecycle and teardown | Boot gate: `lilrae lab stop --volumes` plus the independent absence proof in `scripts/ci/assert_project_teardown.py`, scoped to the project and diffed against a pre-start daemon baseline for anonymous volumes and helper containers. Focused: `tests/test_assert_project_teardown.py`, `tests/test_ephemeral_containers.py`, and `tests/test_container_lifecycle_policy.py`, which fails on any helper or container removal that bypasses the shared policy. A helper stranded by a killed `lilrae` process is removed by `lilrae lab stop` and `lab kill` through its lab-project label; `tests/test_stranded_helper_cleanup.py` |
| The gate's own failure modes | `tests/test_boot_realization_gate.py`, where every check fails closed without Docker |

## Declared dimensions APTL does not read back

SEM-218 forbids silent approximation.
LilRAE refuses a dimension it cannot observe, and the RAES handoff fails lab start.
These shape restrictions apply to the fixture:

- A service unit may declare only the dimensions the service manager is asked
  for: load, enabled and active state. `unit_type`, `unit_file_path`,
  `exec_start` and a `Node.services` back-reference are not read back
  (`_service_unit_shape_supported` in
  `src/aptl/backends/raes_runtime_guest_observation.py`), so declaring one
  fails the boot. `tests/test_boot_realization_gate.py` holds the shipped
  fixture to that shape at unit speed rather than at boot speed.
- A filesystem entry may not declare a content digest, digest algorithm,
  source path or provenance for the same reason
  (`_filesystem_shape_supported`).

## The dnf/RHEL systemd substrate has no live coverage

A service node in the `rhel` package family selects
`aptl/generic-systemd-base` rather than the Debian substrate the boot scenario
uses. That selection is a pure lookup, pinned by
`tests/test_raes_materializer.py::test_service_nodes_use_family_aware_systemd_substrate`,
which runs in CI. What nothing proves is the live fact: that Rocky's systemd
boots under APTL's init flags and runs a declared unit.

A second live scenario used to assert that and was retired in issue #993. It
ran in no CI job, no shipped scenario declares a dnf node, and it re-asserted
the generic admission contract the shared fixture already covers. Restore live
coverage when a scenario actually declares a `rhel` service node, and prove it
through that scenario's own gate rather than a second generic fixture.

Supporting another dimension requires backend readback and its verification evidence.

## Explicitly outside the small boot

The small boot does not cover these surfaces:

- Generated artifacts, persistent volumes, search-index materialization, and forwarding agents.
- Dependency manifests, software components, identity authorities, and participants.
- `runtime.orchestration_authorities`, the host-root-equivalent Docker authority governed by ADR-055.
- Remote Docker endpoints and non-Linux hosts.

Focused unit and integration suites remain their verification owners.
Issues #870, #685, #1214, #1219, and #1220 track full-range qualification.

Follow [fixture maintenance](lab-fixture-pack.md#changing-the-pack) when adding a realization regression.
