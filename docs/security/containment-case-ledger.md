# Containment case ledger

Reader purpose: Reference.
This page links each known bypass to the protection and the tests of the in-house engine.
It also records what LilRAE mined from RAPTOR.
[ADR-068](../adrs/adr-068-shared-containment-wrapper.md) records the decision.

## Mined from RAPTOR

LilRAE copies no RAPTOR code or tests.
The table records the ideas that LilRAE took from RAPTOR `core/sandbox` and `core/config` at commit `28c996ca997c0aeaf94080c88733788a3b26c9e5`.

| LilRAE element | RAPTOR source |
| --- | --- |
| Seccomp deny list, clone namespace flags, socket families including `AF_UNIX`, `SOCK_RAW`, tty ioctls, and the empty-path `execveat` rule in `src/aptl/containment/policy.py` | `core/sandbox/seccomp.py` |
| Denied environment names in `src/aptl/containment/policy.py` | `DANGEROUS_ENV_VARS` in `core/config/__init__.py` |
| The `/etc` entries that the sandbox binds | `_ETC_MINIMAL_READS` in `core/sandbox/context.py` |
| The launcher closes descriptors from the descriptor table before it lowers `RLIMIT_NOFILE` | The descriptor sweep in `core/sandbox/_spawn.py` |
| Setup status on a descriptor that closes at exec | The setup-status pipe in `core/sandbox/_spawn.py` |
| Each probe pairs a contained run with an unsandboxed control | `core/sandbox/tests/` |

A copy of RAPTOR code or tests must keep RAPTOR's MIT copyright and permission notice.

## Qualification environment

The CI job `Containment wrapper proof` in `.github/workflows/checks.yml` runs on a GitHub-hosted `ubuntu-latest` runner.
It installs Bubblewrap, libseccomp, and Python 3 from Ubuntu packages.
Only that job selects the `containment` pytest marker. The default run and the catch-all integration lane exclude it.
An explicitly approved, isolated test VM with the same host profile can run the same tests with `pytest -m containment tests/containment`.

## Cases

Each probe runs once without containment as the positive control.
The control must show that the operation is `allowed`.
The contained run must print the `reached` marker and show `denied`.

| Known bypass | Protection | Test | Denied operation |
| --- | --- | --- | --- |
| Absolute read of a host file | Mount view and Landlock | Probe `host-file-read` | Read a canary file outside the grants |
| Write outside the output grant | Mount view and Landlock | Probe `host-file-write` | Create a file in a host directory |
| Write to read-only input | Read-only bind and Landlock | Probe `input-write` | Create a file in the input directory |
| Read another process's environment | PID namespace with a fresh procfs | Probe `host-process-environ` | Read `/proc/<host-pid>/environ` |
| Signal a host process | PID namespace | Probe `host-process-signal` | `kill(<host-pid>, 0)` |
| Connect to a host loopback service | Network namespace and Landlock TCP rules | Probe `host-loopback-connect` | TCP connect to a host listener on `127.0.0.1` |
| Connect to a host Unix socket | Mount view | Probe `host-unix-socket-connect` | Connect to a pathname socket outside the grants |
| Connect to an abstract Unix socket | Network namespace and the seccomp `AF_UNIX` deny | Probe `abstract-unix-socket-connect` | Connect to a host abstract socket |
| Connect to a host Unix socket inside the input grant | The seccomp `AF_UNIX` deny | Probe `input-unix-socket-connect` | Connect to a listening socket in the read-only input directory |
| Write a host FIFO inside the input grant | Input mount outside every writable grant, and Landlock | Probe `input-fifo-write` | Open a FIFO in the input directory for writing |
| Read host TLS private keys | The mount view binds only public TLS material | Full-layer fixture test | Find `/etc/ssl/private` in the sandbox |
| Pass the `AF_UNIX` rule with upper domain bits | The rule compares the low 32 bits of the domain | Probe `raw-domain-unix-connect` | `socket(0x100000001, SOCK_STREAM, 0)` and a connect to the input socket |
| Send from a datagram socket pair to a host socket | The seccomp datagram `socketpair` deny | Probe `input-unix-dgram-send`; the host socket receives no datagram | `sendto` from a datagram pair to a datagram socket in the input directory |
| Send from a `SOCK_RAW` socket pair to a host socket | The seccomp `socketpair` deny for `SOCK_RAW`, which `AF_UNIX` accepts as a datagram type | Probe `input-unix-raw-pair-send`; the host socket receives no datagram | `sendto` from a `socketpair(AF_UNIX, SOCK_RAW)` pair to a datagram socket in the input directory |
| Use a dangerous system call | Seccomp filter | Probe `keyctl-syscall`; launcher test without Bubblewrap | `keyctl(KEYCTL_GET_KEYRING_ID)` |
| Create a nested namespace | `--disable-userns` and the seccomp filter | Probe `nested-user-namespace`; launcher test without Bubblewrap | `unshare(CLONE_NEWUSER)` |
| Use an inherited descriptor | Launcher descriptor sweep | Probe `inherited-descriptor`; launcher test without Bubblewrap | Hold an open file or socket descriptor above 2 at exec |
| Read a credential from the environment | `--clearenv` and the launcher environment | Probe `environment-canary` | Read a canary variable from the consumer environment |
| Keep a descendant alive through a new session | Bubblewrap PID 1 reaper and PID namespace | Probe `detached-descendant` | A double-forked `setsid` heartbeat continues after the run. The payload waits up to 5 seconds for the first heartbeat before it ends. |
| Forge a setup result with an exit status | Status descriptors that close at exec | Report-spoof test | A target prints a report and exits with status 126 |
| Run on a host without a required layer | Per-property host checks | Refusal test; adapter refusal tests | The target starts without Bubblewrap |
| Run after a launcher layer fails | The launcher refuses before exec | Adapter and launcher failure tests | The target starts without a layer |

The integration tests are in `tests/containment/test_containment_proof.py` and `tests/containment/test_containment_launcher.py`.
The probe payload is `tests/containment/fixtures/probe_payload.py`.
