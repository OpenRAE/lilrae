# Issue #1607: Process runner architecture preflight

Issue #1607, the [shared foundation design](issue-1557-go-foundation-design.md)
and [ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md)
govern. Inspection used `6d3e220b` on `1607-process-runner`. This note records
boundaries and design guardrails, not an implementation plan or a passed design
check. At that revision, no `internal/process` package or model component exists.

The foundation boundary is suitable. Before code, the delivery design must
resolve group identity across exit/reaping, Windows launch and graceful stop,
and the bound on launch itself. A direct translation of the Python runner or
an `exec.CommandContext` wrapper does not establish those guarantees.

## Ownership and reuse

`internal/process` owns one local invocation's OS process group, pipes, output
budget, deadline and cleanup. It belongs to the existing `foundation` layer
of `architecture/model.yaml`. Consumers define small runner interfaces;
the package returns concrete results. Standard `context`, `time`, `os/exec`
and platform APIs are the starting point. `golang.org/x/sys` is already in
the root module for platform calls, but process-specific permission still
belongs in the model. Product code must not import `tools/internal/git` or
other tooling. Its Git wrapper's unbounded buffers and argv/stderr errors
are not suitable process-runner contracts.

Canonical incumbents, with Python source paths relative to `src/aptl` and
test paths relative to the repository root:

| Concern | Incumbent and required boundary |
| --- | --- |
| Bounded invocation | `workbench/process.py`, `workbench/_pipe_exchange.py`, `tests/test_workbench_process.py` and `tests/test_lilrae_participant_cancellation.py`. Preserve their behavioral invariants and #963 lessons, not their private helper structure or POSIX-only test skip. |
| Command and transport policy | `core/deployment/docker_compose.py` owns `_command_kwargs`, captured/streaming/input variants and backend timeout translation; SSH overrides the transport environment. `utils/shell.py` selects Git Bash; `utils/curl_safe.py` keeps credentials outside argv. These remain consumer responsibilities, not runner modes. |
| Invocation admission | `workbench/agent.py` owns `_admitted_executable`, `_prepare_work_dir`, `_read_private_config`, `_assert_config_unchanged` and minimal child environments. `workbench/lilrae_opencode.py` owns provider environment and prompt/model/limit admission. Keep these checks before every launch, including discovery. |
| Domain result and evidence | `ProcessResult`, `ProcessCleanup` and `BoundedProcessError` define the behavioral reference. `workbench/runtime.py`, `backends/_raes_participant_evidence.py`, `backends/raes_participant_provider.py` and `backends/lilrae_participant_execution.py` distinguish safe summaries, detailed cleanup evidence and indeterminate native effects. Foundation must supply facts for these translations, not reproduce RAES outcomes or workbench exceptions. |
| Time and files | Use standard monotonic elapsed time and context deadlines, consistent with `internal/clock` and `internal/wait`. Do not add a second clock framework or put process teardown into generic readiness polling. `internal/securefile` owns contained/private file operations when callers need credential files; the runner needs no file store. |

The seven Python runner types are not seven implementations or public APIs to
port here. Captured local processes, interactive terminals, SSH commands and
daemon-owned containers have different lifecycles. In particular,
`core/ephemeral_containers.py` owns daemon-side helper removal: killing a
Docker CLI does not remove its container or remote work.

## Required passage through cross-cutting layers

```text
authenticated entry -> admitted operation/executable/explicit environment
  -> process mechanism -> owned OS group/job and private pipes
  -> raw bounded result OR safe failure + cleanup facts
  -> owner-specific parsing/outcome -> redacted presentation/evidence
```

The runner has no listener, authorization decision or configuration loader.
These layers constrain future consumers; they are not imports into foundation.

| Layer and canonical gate | How the intended design satisfies it |
| --- | --- |
| Entry and external shapes: `api/deps.py`, `api/session.py`, `api/middleware/bff.py`, `api/schemas.py`; MCP common `src/config.ts` and `src/server.ts` | Token/session, Host/Origin, capability and closed Ajv argument validation remain before effects. Add no generic execute-command route/tool, alternate DTO or authority inferred from an argv array. Existing controllers retain HTTP, CLI and MCP result envelopes. |
| Config and secret sourcing: `core/config.py:AptlConfig`, `core/env.py`, `utils/placeholders.py`, `core/_credential_sources.py` | Preserve strict config shapes, placeholder rejection, non-secret source descriptors and exact grants. `EnvironmentGrant` matches pack, consumer and variable; a matching host variable name is not a grant. Foundation receives resolved values, never discovers `.env`, credentials or pack policy. |
| Environment delivery: `core/deployment/_environment_bindings.py`, `_realization_primitives.py`, `_compose_environment.py:compose_process_environment` | Authored/generated/granted/adapter source selection and Docker/Compose env-file representability stay with their owners before mutation. Do not copy their validators into process or apply env-file escaping to an OS environment. Pass an explicit child environment; nil must not silently inherit the parent. Specify Windows key equivalence, duplicate disposition and any required runtime additions such as `SYSTEMROOT`; qualify these against the Go runtime. |
| Invocation shape and OS exposure | Check nonempty executable, NUL/OS representability, valid environment entries, positive finite bounds and safe duration/size arithmetic before effects. Empty argument values remain legal. Caller supplies an admitted executable path and working directory; do not silently search the parent's PATH/current directory or override `exec.ErrDot`. No global chdir/environment mutation, shell joining, batch-file fallback or raw Windows command-line override. Use standard quoting for supported executables; parser exceptions remain explicit consumer decisions. Credentials/prompts stay in explicit environment, stdin or caller-managed private files, never argv/URLs. A bounded runner is not a sandbox against same-user inspection or group escape. |
| Errors, output and observability: ADR-065, `utils/redaction.py`, MCP `redaction.ts`, `utils/logging.py`, MCP telemetry and existing runstore/evidence serializers | Use standard `errors.Is`/`errors.As` and minimal actionable categories: cancellation, deadline, overflow, launch/I/O failure and cleanup residue. Preserve both the initiating cause and cleanup facts. Raw output is sensitive even within the byte limit. Bound failures withhold it and expose only categories/counts/cleanup facts. Do not wrap a secret-bearing `PathError`, `exec.Error`, `ExitError.Stderr`, or context cancellation cause into an outward error chain. Sanitize by extracting safe typed causes, not by string matching. No argv, env, stdin, cwd or output in errors, default struct formatting, logs or spans. Prefer no foundation logging; entry owners use the shared Go redactor when delivered by Go port 07, with explicit `slog` if needed. Do not build a runner redactor or telemetry exporter. |
| Persistence and workflow: `core/runstore.py`, workbench records, RAES evidence/outcome contracts, lifecycle locks | Return concrete in-memory cleanup facts; existing owners project them into their records and preserve current serialization. No new report file/schema version, process registry, repository or retry workflow. Residue cannot become a successful/definitive native outcome, and uncertain effects cannot be replayed automatically. |

OS shape checks and caller authorization check different invariants; retaining
both is not duplicate validation. Secret admission cannot be implemented by
guessing token patterns in the runner.

## Invocation and cleanup invariants

- One monotonic execution deadline starts before launch and covers launch,
  stdin delivery and capture, bounded by any earlier caller deadline. A
  timeout must not restart for each pipe or phase. Pre-cancellation launches
  nothing. `Start` is synchronous: measuring its duration is not proof it can
  be interrupted. The platform design must explain launch cancellation and
  ownership if launch completes late; a goroutine abandoned at the deadline
  is not a solution. State OS limitations rather than promising hard real-time
  scheduling or claiming `CommandContext` bounds every launch syscall.
- Use finite in-memory stdin, as the incumbent does. Do not accept arbitrary
  blocking readers/writers unless their interruption and ownership are part
  of a separately qualified contract. Concurrent input/output must progress
  without pipe deadlock; short writes, early stdin close and binary output
  need explicit behavior. Close stdin at completion. Every goroutine, pipe,
  process/thread/job handle and partially created resource has one owner and
  a bounded release path, including launch/setup failure.
  Follow ADR-065's `golang.org/x/sync/errgroup` rule for concurrent workers;
  record its module/import permission if used, and close owned I/O to unblock
  workers before joining. Cancellation alone does not interrupt a pipe syscall.
- One synchronized byte budget covers stdout plus stderr, with separate raw
  byte results and no claimed cross-stream ordering. Exactly the limit is
  permitted; the next byte signals overflow. Reject invalid/overflowing limits
  without allocating them; never buffer unrestricted output and truncate
  afterwards. Byte counts on failure mean retained/withheld bytes, not a
  fabricated total of everything a child emitted.
- Direct-child exit ends result capture after a bounded snapshot of pending
  output, as `_pipe_exchange.py:drain` does. A descendant writing later cannot
  extend a successful result, exhaust its budget or keep capture waiting for
  EOF. Selectors/FIONREAD are POSIX mechanisms, not a Windows implementation;
  qualify an equivalent capture boundary there. Cleanup drains/discards within
  its own bound so full pipes cannot obstruct graceful termination.
- Cleanup runs after success, nonzero exit, overflow, deadline, cancellation
  and internal I/O/setup failures once resources exist. It has a separate,
  finite budget that survives caller cancellation, following ADR-065's bounded
  `context.WithoutCancel` rule. A second cancellation cannot skip escalation.
  Total duration is execution plus cleanup and scheduling allowance, not just
  the invocation timeout. All waits consume fixed phase budgets once.
- Escalation depends on owned group/job survival, even after the direct child
  exits. Sending a kill, reaping the direct child and seeing EOF are three
  different observations; none alone proves the group is gone. Nonzero exit
  remains an exit result, separate from supervision failure. Residue after
  exit zero makes the invocation fail safely. Preserve timeout/cancellation/
  overflow as the initiating reason when cleanup also fails.

The extension seam is explicit invocation values plus per-run cleanup grace,
reap and stream-release budgets, with the consumer defining the runner
interface. Distinguish natural exit from forced stop: the Python reference
uses 20 s graceful shutdown after natural exit versus 1 s on forced stop,
then 1 s each for reap and stream release. Its 20 s budget accommodates MCP
SSH shutdown and trace flush. Preserve that caller's policy without embedding
MCP names, timeouts or provider branches in foundation. Keep platform control
private behind build-specific files, not an exported process-backend registry.

## Platform obligations before code

**Linux and macOS.** Create a fresh owned group/session before executable code
can spawn descendants. Do not signal the runner's group, all user processes,
or PIDs collected from a process-name/tree scan. The Python reference admits
a race between probing a PGID and signalling it after reaping the leader.
Never copy that race as satisfaction of #1607's no-reused-group requirement.
The design must establish how identity remains reserved through the final
possible signal, including direct-child exit/reaping order; an unreaped-leader
strategy needs platform proof and reconciliation with `Cmd.Wait` ownership.
Once ownership is lost or disappearance confirmed, send no further signal to
that numeric ID; report uncertainty when appropriate. A Linux pidfd for one
process does not by itself identify an entire group or solve macOS.

Reap the direct child exactly once and confirm remaining group disappearance
within the bound. Grandchildren may be reaped only by their parent/adopter;
do not use global `wait(-1)` or a process-wide subreaper that steals unrelated
children. Permission denial is not disappearance; zombies may keep cleanup
unconfirmed without proving a live helper. Keep the existing distinctions
between child not reaped, output streams held and group cleanup unconfirmed.
Do not promise detection of an escaped process that closes all owned pipes.

**Windows.** Use an invocation-owned, non-inheritable
[Job Object](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
for descendant termination, with kill-on-close and no permitted breakaway.
Establish membership before the child runs; assigning it after ordinary
`Start` races descendant creation. Qualify creation-time
[job-list attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
or suspended creation with complete failure cleanup against the repository's
pinned Go runtime and supported hosts. Test nested CI jobs, access denial and
handle inheritance. Never fall back to child-only kill or `taskkill /T`.
Job termination is forceful; define the safe cooperative stop and grace
behavior for both console and headless execution. A
[console control event](https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent)
has console/group restrictions and is not group ownership. Do not broadcast
to group zero or detach/reattach the host's console globally. Missing required
capability fails explicitly without an unowned launch. Report job membership
and cleanup facts without presenting a Windows PID as a POSIX PGID, and
confirm emptiness with job accounting/notifications rather than assuming a
job handle is signalled after arbitrary termination.

[Go's exec contract](https://pkg.go.dev/os/exec) makes `CommandContext` kill
its own process by default; `WaitDelay` bounds some pipe/process waits but
does not prove group termination. `Wait` also owns pipe/copy completion.
The delivery design must reconcile capture, reaping and identity with those
rules instead of racing `Wait` against pipe readers or adding detached waiters.

## Repository checks and evidence boundaries

Before implementation, the #1607 `*-design.md` front matter must name exact
packages, production/test imports and model changes, and pass
`go run -C tools ./cmd/archcheck design -base origin/go-cutover <note>`.
Use the existing model and generated diagram; this preflight does not add a
stale component or empty package to manufacture a pass. The checker proves
dependency permissions, not process security. CI must also pass whole-repo
architecture/PR/diagram checks against the final code.

Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `go.mod`/`go.sum`,
`.golangci.yml`, `.gc/pack-ownership.json`, `tools/check_pack_boundary.py`,
`tools/ci/select_checks.py`, `tools/ci/go-gates.sh`, `.github/workflows/checks.yml`
and `tools/mutation-thresholds.json`; add no parallel checker or runner test
script. Scenario facts stay outside foundation. Targeted local tests go
through `tools/run-targeted-tests.sh`, with staged `pre-commit run` for hygiene;
full suites, lint, coverage, mutation and whole-repo gates remain in CI.

Real-process evidence must run on Linux, macOS and Windows: blocked stdin,
full pipes, combined exact-limit/overflow on both streams, natural/nonzero
exit, cancellation, stubborn descendants after parent exit, graceful shutdown,
escaped stream holders, safe residue reporting, concurrent invocations and
unrelated processes left untouched. Include cwd/environment/argv fidelity,
Windows quoting and denied/partial launch cleanup. Use synthetic secret canaries
in every input/output and outward error format. Keep fixture helpers finite
and independently cleaned if assertions fail. Real processes prove OS behavior;
small injected platform faults can supplement permission/reuse race coverage.
Use `testing/synctest` only for suitable deterministic timer logic, not as
replacement for real OS tests or by copying Python private mocks.

CI already executes product tests on all three systems and mutation on Linux
and macOS. Windows mutation is explicitly skipped pending #1617 in
`checks.yml`. That is an acceptance dependency for Windows-only process code,
not mutation evidence or permission for #1607 to claim its gate passed.
Retain the 100% efficacy/coverage thresholds and resolve the dependency before
claiming complete mutation qualification; no skip, exclusion or lower threshold
can establish it.

## Non-goals and anti-patterns

No command selection, SSH or Docker execution/cleanup, interactive terminal,
provider protocol parsing, credential broker, authorization, environment-grant
schema, persistent report store, OS sandbox, resource quota service, automatic
retry, process discovery daemon or migration of all Python callers. No common
effects container, parallel exception hierarchy, global signal handlers, mutable
package registries, unbounded `CombinedOutput`, per-stream limits, unbounded
reader goroutines, secret-bearing errors or success inferred from kill/EOF.
This issue delivers local supervision facts; the existing owners retain
business policy, transport ownership, evidence and user-visible contracts.
