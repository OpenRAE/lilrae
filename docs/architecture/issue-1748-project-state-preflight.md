# Issue #1748: Project state and lifecycle lock preflight

Reader purpose: Explanation. Sources were inspected at revision
`69c3732e937639d0c970744a49a500800170e2c8`.
This note constrains the later design; it is not an implementation plan or a passed design check.
The [shared #1559 design](issue-1559-go-config-state-keys-design.md), ADR-064,
ADR-065, and ADR-066 govern the change.
Python paths beginning with `core/`, `api/`, `backends/`, or `utils/` are relative to `src/aptl/`.
Other source paths are repository-relative.

## Scope and ownership

The objective is one core owner for project-state locations, protection rules,
lifecycle root discovery, and lifecycle lock admission.
The issue title mentions workspace identity, but its explicit boundaries assign
that record and Docker resource identity to Go port 09.
A canonical project path locates state; it grants neither credential access nor Docker authority.
ADR-055 is proposed; preserve its implemented safeguards without claiming that the whole proposal is delivered.

Keep these responsibilities separate:

| Concern | Canonical incumbent and boundary |
| --- | --- |
| Project configuration | `internal/config.Find` checks one directory. `Load` and `Decode` own bounded strict decoding and semantic checks. State discovery must not duplicate them. |
| Lifecycle project root | `src/aptl/core/lifecycle_guard.py:canonical_lifecycle_project_root` resolves the candidate, searches it and its ancestors, and selects the nearest configuration owner. With no match, it returns the resolved candidate. |
| Exact placement root | `placement_mutation_lock` does not search ancestors. `backends/trial_serving.py` locks the daemon placement before the project. Preserve that distinction and order. |
| State contents | `core/session.py`, `core/lifecycle_policy.py`, `core/operator_group_state.py`, and `backends/raes_evidence_acquisition.py` retain their models, readers, validation, and recovery policies. |
| Runtime authority | `core/trial_ownership.py`, `core/trial_control.py`, and `backends/trial_serving.py` own retained trial authority. The lifecycle guard must preserve their admission check. |
| Resource ownership and recovery | `core/deployment/_compose_resource_ownership.py`, `core/startup_reset_state.py`, and `core/lifecycle_cleanup.py` retain their receipts and dispatch rules. A state-directory owner does not execute them. |

The core owner depends on `internal/config`, `internal/securefile`, and
`internal/filelock`; foundation must not import the state owner.
Use a responsibility-named package under `internal/`, consistent with ADR-065.
Do not create a public package named `core`, a generic state repository, or one package per Python file.
Entry construction supplies one shared lock owner to related application services.
Do not copy Python's mutable module registry into Go package globals.

## Root and filesystem contracts

Discovery is read-only and does not parse configuration, migrate it, or create `.aptl/`.
`config.Find` follows a configuration symlink and checks for a regular file.
Keep that discovery contract separate from the no-follow rule for state access.
Malformed configuration does not make discovery skip to a different ancestor.
Use the selected root consistently for lock admission and the subsequent operation.
Do not rediscover it after admission or silently fall back after a resolution error.

`securefile.OpenDir` accepts a trusted root, including links in that root path.
Its child operations reject links, traversal, invalid names, and special files.
Therefore opening `.aptl` itself as a trusted root would bypass its validation.
Open the owner-selected project root, then access `.aptl/...` through the contained methods.
Windows lifecycle code also rejects a reparse point on its opened root handle.

The later design must account for that root guarantee; child checks alone do not establish it.
Any missing root-opening capability belongs in `securefile`, with its own reviewed design evidence.
Do not add native handle code to the core package or use check-then-reopen access.

`securefile.Dir.OpenLockFile(".aptl/lifecycle/.lock")` already owns safe lock-file creation.
It opens an existing file without replacement, requires a regular file, and creates missing directories with mode `0700`.
On POSIX it sets the lock file to `0600` through the opened descriptor.
On Windows it opens relative to retained handles and rejects reparse points.
Windows inherits the project ACL here; Unix modes do not establish Windows privacy.
Do not introduce an owner-only ACL requirement for every state object as an unnoticed parity change.

Private content uses `securefile` publication methods and its final protection from the first byte.
Create-once records use `CreateOnce`; replaceable records use their existing replacement contract.
Do not apply atomic replacement, truncation, deletion, or stale-file cleanup to the rendezvous lock.
Replacing its inode can create two independent owners.
Do not remove `.aptl/lifecycle` while any operation can hold or acquire its lock.
Closing the handle releases a lock; deleting the path is not release.

There is no uniform permission rule for every descendant of `.aptl/`.
For example, `core/credentials.py` deliberately uses container-readable `0644`
files behind `0700` directories; private host records and the lock use different rules.
Reuse each producer's protection contract, including generated environment and bind-mounted artifacts.
Do not recursively chmod, chown, relocate, or eagerly create every consumer's state.
Keep `.aptl/` ignored and excluded from packaged assets by `.gitignore` and `_asset_manifest.py`.
Git exclusion is not a filesystem access control.

## Lock admission and lifetime

Use `filelock.TryLock`, never its waiting `Lock`, for lifecycle admission.
On Linux and macOS this is `flock`; Windows locks byte zero for length one.
The foundation already tests Python interoperability in both directions.
The lifecycle owner must exercise those mechanisms on the actual canonical path.
File existence, PID records, workspace IDs, and trial fences do not establish OS lock ownership.

Preserve all of these distinctions:

- An exclusive mutation excludes unrelated mutations and observations immediately.
- POSIX shared observations can overlap and exclude mutations. Windows shared observations fail closed as unsupported.
- Reentrancy belongs to the live related operation, including explicitly delegated callbacks.
  An unrelated goroutine in the same process must still receive busy.
- A delegated reference is valid only while that exact acquisition remains live.
  A stale reference cannot join a later acquisition of the same project.
- Nested exits release one reference each. Only the last exit unlocks and closes the descriptor.
- Observation is not mutation ownership. Do not silently upgrade a shared lock or reuse it as an exclusive lock.
- Different project roots remain independent. A short registry mutex must not serialize unrelated project operations or their I/O.

Go has no supported goroutine identity equivalent to Python's thread key.
Use an explicit operation ownership value or scoped lease for nesting and delegation.
Bind it to the root and the live acquisition; possession of a root string is insufficient.
Keep the registry inside the constructed owner, without a process-global boolean or mutable map.
The design must define release ownership, stale-reference rejection, and simultaneous acquire/release behavior.
Do not infer related work from a PID or bypass acquisition for every caller in the process.

Root aliases must not split reentrancy state; characterize symlink resolution and Windows path casing against Python.
Do not replace resolution with lexical cleaning alone or change no-config behavior for a missing descendant.

After acquiring a fresh mutation lock, preserve `require_trial_owner` before admitting effects.
The existing fence is `.aptl/lifecycle/trial-owner`; its reader reads at most 65 bytes.
An existing value must be exactly 64 lowercase hexadecimal bytes.
A different owner is busy; malformed, unreadable, or unsafe state is unavailable.
Absence alone permits work without a retained owner.
Do not log the owner value or interpret a malformed fence as absence.

Windows reads must use existing-only no-reparse opens, without creating missing fence directories.
This preserves admission; fence creation, reconciliation, and retirement remain with the runtime owner.

Close every failed acquisition and unwind every nested exit, including errors and cancellation.
Use `errors.Join` where necessary to retain cleanup failures without losing the primary category.
Descriptors must not escape into child processes and prolong lock lifetime.
Process death releases the OS lock but does not reconcile retained trial effects.
Preserve the single runtime owner and explicit recovery rules of the
[#1447 note](issue-1447-runtime-owner-handoff.md) and
[#1179 note](issue-1179-pending-lab-cleanup-preflight.md).
Do not equate lock release with successful teardown or completed cleanup.

## Cross-cutting security passage

```text
admitted caller -> selected root -> securefile handle -> nonblocking OS lock
                -> retained trial check -> related operation -> release
busy / unsafe / malformed -> existing safe result; no protected effect
```

The OS lock protects admission and the related operation, including the retained trial check.
The state owner crosses the host filesystem boundary, without adding a network or credential boundary.

| Layer | Required passage and incumbent |
| --- | --- |
| Entry authentication and project selection | Keep `api/deps.py`, `api/session.py`, `api/middleware/bff.py`, API routers, and MCP argument admission outside this package. Authentication, Host/Origin/CSRF rules, and server-selected project scope precede effects. A path is not an authorization token. |
| Configuration and schema | Reuse `internal/config` from #1747 and `aptl-config.schema.json`. Add no config field, second parser, environment-selected state root, or silent migration. The state owner adds no persisted schema. |
| Environment and credentials | `core/_credential_sources.py:EnvironmentGrant`, environment-binding admission, and placeholder checks still govern secret delivery. Owning a directory grants no ambient environment read, credential-source access, or Docker transport selection. This package does not hydrate `.env`. |
| OS access and publication | `securefile` owns lexical validation, contained handle walks, regular-file checks, permissions, and publication. `filelock` owns the OS primitive. Core adds lifecycle policy only. No secret or owner token enters argv, shell text, child environment, or default struct formatting. |
| Runtime and durable authority | Preserve the trial fence check after the OS lock. Docker labels, workspace identity, native-ID receipts, admitted operator groups, and RAES ownership remain separate authorities. No name-based adoption or cleanup from directory membership. |
| Errors and result schemas | Preserve busy versus unavailable versus unsupported internally using `errors.Is`/`As`. Entry projects them into existing `LabResult`, `StartupDiagnostic`, API, and CLI envelopes, including `lifecycle-owner-busy` and `lifecycle-lock-unavailable`. Do not expose wrapped filesystem paths or arbitrary native error text. |
| Logs, traces, and archives | ADR-065 requires injected `slog`, stderr, and one shared redaction path. Python incumbents are `utils/logging.py` and `utils/redaction.py`; Go port 07 owns their Go replacement. That package is absent at this revision: do not invent a local scrubber. Emit only safe categories and bounded metadata; never fence bytes, state contents, or raw errors. |

Filesystem errors can contain a user-selected path, including control characters or sensitive names.
Wrapping a safe lifecycle label around a raw error does not make the public error safe.
Keep causes available for classification without exposing them through presentation or automatic logging.
Add an error category only where a caller must branch; no parallel exception hierarchy or protocol envelope is needed.

## Extension seam and required evidence

The extension seam is an owner-selected root plus explicit operation ownership and protection requirements.
The next certificate, environment, or SSH consumer supplies its existing relative location and mode contract.
It keeps its own codec, semantic validation, grants, and publication decision.

Do not create a mutable path registry, arbitrary permission map, plugin hook system, or universal state CRUD API.
Exact placement locking and discovered project locking must remain distinct entry points.
This also permits future consumers without adding service names to foundation or changing persisted paths.

`file.project-state` in the conformance inventory is a detail with no portable format.
That classification does not waive its protection and lock behavior, and it does not authorize a new umbrella schema.
Reuse `tests/test_lifecycle_guard.py` and `internal/filelock/*_test.go` as behavioral evidence.

Required Go evidence includes related nesting, unrelated goroutines, stale delegation, cross-project independence,
and shared/exclusive exclusion.
Also cover both Python/Go directions, process death, and cleanup after failed admission.
Also cover nearest-root discovery, no-config fallback, exact placement, private modes,
unsafe/special files, trial fence outcomes, and native Windows junction/reparse rejection.
Tests must verify no protected side effect occurs after busy or unavailable admission.
Use real descriptors and synchronized child processes; sleeps, mocks, and cross-compilation alone are insufficient.

Python's lifecycle-policy writer currently writes before chmod.
The session writer opens with truncation before locking, without an explicit private mode.
Those existing protection and persistence inconsistencies must not become patterns for the shared owner.
This preflight does not repair those consumers or claim that all private-state writers already use secure publication.

The later design must record packages, imports, and model changes in an issue-1748 design note before code.
It must pass `archcheck design` against `origin/go-cutover` with the proposed `architecture/model.yaml` changes.
This preflight changes neither model nor generated diagram because it adds no package.

Whole-repository architecture, PR-design consistency, diagram, mutation, coverage,
race, vulnerability, and Sonar checks remain owned by the existing CI gates.
Canonical controls include `.golangci.yml`, `tools/ci/go-gates.sh`,
`tools/ci/select_checks.py`, `tools/mutation-thresholds.json`, and `.github/workflows/checks.yml`.
CI already runs Go product tests on Linux, macOS, and Windows with Python available.
Keep the pinned toolchain, module permissions, pack-ownership gate, and full-coverage selection intact.
Workstation verification is limited to static checks and staged hygiene.
Targeted behavior tests require CI or an approved isolated VM.

## Non-goals

No requirement implementation, requirement transition, implementation sequence, shipping change, or new external service.
No workspace identity format, Docker receipt or naming port, recovery command text, cleanup record migration,
or session/policy/operator-group/capture codec port.
No credential read, certificate generation, or SSH operation.
No new lock algorithm, retry loop, stale-PID repair, automatic recovery, broad filesystem cleanup,
duplicate validator, exception family, schema, telemetry system, or workflow engine.

## Preflight verification

The new note passed the explicit-path STE check with zero findings.
Git diff whitespace checks passed.
The pinned Vale download failed because GitHub DNS resolution was unavailable.
Staging and pre-commit were blocked by read-only Git metadata.
No tests, lab commands, model checks, or design checks ran in this preflight.
These results do not establish behavioral parity or satisfy the later design gate.
