# Containment case ledger

Reader purpose: Reference.
This page records the source of the containment engine and the tests for each known bypass.
[ADR-068](../adrs/adr-068-shared-containment-wrapper.md) records the decision.

## Provenance

| Item | Value |
| --- | --- |
| Engine | RAPTOR `core/sandbox` |
| Fork | <https://github.com/OpenRAE/raptor> |
| Upstream | <https://github.com/gadievron/raptor> |
| Pinned commit | `28c996ca997c0aeaf94080c88733788a3b26c9e5` |
| Pin location | The `third_party/raptor` submodule and `src/aptl/containment/engine_pin.json` |
| Local engine changes | None |
| Retained regressions | `core/sandbox/tests/` at the pinned commit |
| License | MIT, in `LICENSE` at the pinned commit |

The license notice at the pinned commit reads:

```text
MIT License

Copyright (c) 2025-2026 Gadi Evron, Daniel Cuthbert,
Thomas Dullien (Halvar Flake), Michael Bargury, and John Cartwright
```

A copy or distribution of the engine must include the full `LICENSE` file.

## Qualification environments

| Name | Environment | What runs |
| --- | --- | --- |
| `ci-restricted` | GitHub-hosted `ubuntu-latest` runner with the default AppArmor user-namespace restriction | The refusal test |
| `ci-full` | The same runner after `kernel.apparmor_restrict_unprivileged_userns=0` | The wrapper proof, the escape probes, and the retained regressions |

The CI job is `Containment wrapper proof and retained engine regressions` in `.github/workflows/checks.yml`.
Only that job selects the `containment` pytest marker. The default run and the catch-all integration lane exclude it.

The retained regressions use the engine's locked test environment from `uv.lock` at the pinned commit.
They run in two passes, as the fork's CI runs them.
The first pass uses the default markers. The second pass selects `slow or integration`.
Fork CI covers the macOS, WSL, and kernel-feature matrices.
These are outside the supported LilRAE profile.

## Cases

Each probe runs once without containment as the positive control.
The control must show that the operation is `allowed`.
The contained run must print the `reached` marker and show `denied`.

| Known bypass | Protection | Retained regression | Wrapper probe | Denied operation | Environment |
| --- | --- | --- | --- | --- | --- |
| Absolute read of a host file | Mount namespace bind tree and Landlock read allowlist | `test_sandbox_attack_scenarios.py`, `test_fake_home_private_tmp.py` | `host-file-read` | Read a canary file outside the grants | `ci-full` |
| Write outside the output grant | Landlock write allowlist and mount view | `test_tmp_baseline_e2e.py`, `test_host_output_isolation.py` | `host-file-write` | Create a file in a host directory | `ci-full` |
| Write to read-only input | Read-only bind of the input directory | `test_spawn_mount_ns.py` | `input-write` | Create a file in the input directory | `ci-full` |
| Read another process's environment | PID namespace with a fresh procfs | `test_fresh_procfs_contract.py`, `test_pidns_proc_mount.py` | `host-process-environ` | Read `/proc/<host-pid>/environ` | `ci-full` |
| Signal a host process | PID namespace and broadcast-signal filter | `test_signal_broadcast_deny.py` | `host-process-signal` | `kill(<host-pid>, 0)` | `ci-full` |
| Connect to a host loopback service | Empty network namespace | `test_sandbox_attack_scenarios.py` (`test_net_ns_hides_host_tcp`), `test_e2e_sandbox.py` | `host-loopback-connect` | TCP connect to a host listener on `127.0.0.1` | `ci-full` |
| Connect to a host Unix socket | Mount view and AF_UNIX connect scope | `test_unix_connect_scope.py` | `host-unix-socket-connect` | Connect to a pathname socket outside the grants | `ci-full` |
| Connect to an abstract Unix socket | Network namespace | `test_unix_connect_scope.py` | `abstract-unix-socket-connect` | Connect to a host abstract socket | `ci-full` |
| Use a dangerous system call | Seccomp-bpf filter | `test_seccomp_policy_pins.py`, `test_seccomp_family_deny.py` | `keyctl-syscall` | `keyctl(KEYCTL_GET_KEYRING_ID)` | `ci-full` |
| Create a nested namespace | Seccomp namespace-creation deny | `test_ns_creation_block.py` | `nested-user-namespace` | `unshare(CLONE_NEWUSER)` | `ci-full` |
| Use an inherited descriptor | Descriptor closure and the pass-fds gate | `test_pass_fds_gate.py`, `test_death_pipe_sibling_fds.py` | `inherited-descriptor` | Use an open file or socket descriptor above 2 | `ci-full` |
| Read a credential from the environment | Explicit worker and target environments | `test_target_env_strip.py` | `environment-canary` | Read a canary variable from the consumer environment | `ci-full` |
| Keep a descendant alive through a new session | PID namespace teardown | `test_spawn_timeout_setsid_escape.py` | `detached-descendant` | A double-forked `setsid` heartbeat continues after the run | `ci-full` |
| Forge a setup result with an exit status | Separate worker report and the engine setup-status pipe | `test_setup_status_integrity.py` | Report-spoof test | A target prints a report and exits with status 126 | `ci-full` |
| Run changed engine code or a planted bytecode cache | Verified read-only snapshot; workers import it with bytecode off | None; wrapper control | `test_containment_engine.py` snapshot cases | Import a changed source file or a `.pyc` file | Workstation and CI unit tests |
| Run on a host without a required layer | Per-property check before the target starts | `test_untrusted_failclosed_gates.py` | Refusal test | The target starts on a restricted host | `ci-restricted` |

The integration tests are in `tests/containment/test_containment_proof.py`.
The probe payload is `tests/containment/fixtures/probe_payload.py`.
