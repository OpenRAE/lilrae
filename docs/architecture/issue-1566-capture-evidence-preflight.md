# Issue #1566: Capture and Evidence Architecture Preflight

The helper port contributes raw capture custody to EXP-010. It must preserve
the complete path from admitted capture intent to independently validated,
redacted evidence. It does not implement EXP-010 again inside the helper.
This companion to the [container helpers preflight](issue-1566-container-helpers-preflight.md)
uses revision `f573683d1` and the supplied requirement and issue payloads.
It records boundaries, not an implementation plan or a passed design check.

[ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md)
already selects one static Linux `cmd/lilrae-helper` binary for all roles.
No new ADR is needed. ADR-041/042, the
[EXP-010 preflight](exp-010-capture-admission-evidence-preflight.md), and the
[#992 ownership preflight](issue-992-backend-observability-ownership-preflight.md)
remain the existing capture architecture. Their historical implementation
descriptions do not override current source or later ADR clauses.

## Decisions and ownership

```text
capture spec / scenario demand -> existing admission -> immutable capture plan
  -> backend-owned apparatus activation -> authenticated SSH -> broker-owned PTY
  -> private raw custody files -> quiesce + independent session census -> export
  -> adapter validation/redaction -> evidence persistence/record -> archive seal
```

Paths starting with `core/`, `backends/`, or `utils/` below are relative to
`src/aptl/`. Python owners define compatibility; Go consumers use their delivered
Go counterparts. Do not import Python or developer-tool packages into product Go.

| Concern | Canonical incumbent and guardrail |
| --- | --- |
| Public contracts | RAES owns capture specs, normalized scenario demands, portable evidence records, and semantic validation. The requirement's ACES wording is historical; it authorizes no new schema or wire rename. Use public RAES/env-packs Go APIs when needed. A missing API blocks dependent scope. |
| Admission and capability claims | `core/experiment/{admission,capture_mapping,capture_registry,capture_plan,trial_plan,policy}.py` own exact offers, required/optional capture, limits, versioned plans, and accepted limitation/comparability disclosures. Preserve fail-closed admission before build, pull, probe, or workload execution. A working helper is not an observation capability claim. |
| Concrete policy | `core/deployment/{boundary,_boundary_validation,boundary_compiler}.py` supply the existing enforcement contract. One core Go owner must serve host and helper. Validate at both trust boundaries with the same rules; keep concrete policy separate from signed appliance policy, RAES planning, and nft rendering. |
| Raw source custody | `containers/kali-capture/{broker.py,entrypoint.sh,sshd_config}` own activation, PTY recording, private raw files, and their existing export. They do not emit portable evidence records, build trial plans, select collectors, or apply participant visibility. |
| Source-to-evidence conversion | `backends/{_raes_transcript_export,raes_evidence_acquisition}.py`, `scenario_capture.py`, and the selected adapter own source validation and admitted binding joins. TechVault's `evidence/techvault_transcript.py` owns its retained transcript format. Keep scenario-specific formatting outside the generic broker. |
| Evidence and sealing | `core/evidence/{coordinator,_persist,records,content_store}.py`, `LocalRunStore.finalization_lock()`, and `core/archival/` own redaction, media checks, streaming limits, checksums, create-once records, terminal dispositions, and seals. Export packages evidence; it does not repair missing, invalid, or secret-bearing evidence. |

Keep capture spec version, collector contract/implementation version, channel
version, binding ID, authority schema, plan identity, and record identity distinct.
The [#1372 pin boundary](issue-1372-capture-spec-version-preflight.md) carries
admitted spec identities independently of acquired records. A broker export
cannot supply missing historical pins or prove required capture satisfaction.

## Required passage through cross-cutting layers

The shared preflight covers enforcement, proxy/DNS, images, and general helper
configuration. These additional constraints follow the capture bytes across
owners and apply before the port can claim EXP-010 compatibility.

| Layer and incumbent | Required passage |
| --- | --- |
| Auth and authority: API `deps.py`, session/BFF middleware, terminal routing; common MCP server/config; capture `sshd_config` | Preserve upstream bearer/session, Host/Origin, target, capability, and argument-schema checks. OpenSSH authenticates participants; its ForceCommand enters only the session broker. Activate, export, quiesce, and stop/await controls remain trusted management operations. Add no network control endpoint or remotely selectable helper role. A safe run ID or digest grants no authority. |
| Config, environment, and secret grants: `core/config.py`, `core/env.py`, `_credential_sources.py`, deployment `_environment_bindings.py`, `_realization_primitives.py`, `_compose_environment.py` | Preserve strict config, placeholders, exact pack/consumer/variable grants, generated secret references, and env-file representability. Keep existing `APTL_CAPTURE_*`, `APTL_SESSION_ID`, `APTL_RUN_ID`, and `APTL_TRACE_ID` contracts. Run and trace must equal the active authority. Roots come from trusted role wiring, not participant input; do not discover ambient credentials or add another settings model. |
| Closed shapes and joins: ADR-065, `internal/canonical`, broker authority/session readers, acquisition validators | Bound input before allocation; reject duplicate/unknown/case-mismatched keys, invalid UTF-8, trailing data, invalid types, and invalid missing/null/zero combinations. Preserve OBS-003 IDs and exact run/plan/binding/session joins. Distinguish raw arbitrary bytes from metadata strings; do not reject or convert frame bytes merely because they are not UTF-8. The existing evidence adapter decides whether a source format is usable. |
| OS, SSH, and processes: capture entrypoint, `docker-compose.capture.yml`, foundation process owner | Keep keys in protected files, runtime-only host keys, fixed loopback inner SSH, strict host verification, `--`, explicit environment/descriptor handling, and bounded owned-process cleanup. Keep raw terminal mode, window sizing, interrupt bytes, partial writes, EOF/EIO, and terminal restoration. Do not replace a byte relay with line scanning. Never log original commands, raw SSH/exec errors, frames, keys, or environment. The current original-command argv exposure remains an explicit limitation in the shared preflight. |
| Files and locks: `internal/securefile`, `internal/filelock`, ADR-066; Python `utils/pathsafe.py` | Use trusted roots, derived relative names, descriptor-relative no-follow access, regular-file checks, private modes, and create-once publication. Bound reads on the opened handle; `securefile.ReadFile()` itself has no byte limit. Hold admission/quota locks on stable opened inodes across the full operation. Append ledgers and quota updates need bounded file operations, not a second path library or replacement of a held lock inode. |
| Integrity and clocks: `internal/canonical`, `internal/digest`, `internal/clock`, serialization vectors | Reuse Python-compatible sorted compact JSON for custody files and enforcement digests. Ordinary Go marshal and RFC 8785 are different schemes. Preserve field presence, pair arrays, null/empty values, ordering, escaping, prefixes, and newline rules. Use `clock.ISOZ` for broker UTC text and elapsed time for waits. Keep source clock metadata under the evidence owner; do not invent synchronization claims from a host timestamp. |
| Secret and visibility boundary: ADR-029/033/041/042, shared Python/MCP redaction, adapter transcript validation, evidence `_persist.py` | Raw bytes stay inside authorized capture storage/export. Base64 is not sanitization. Preserve cross-frame secret handling and server-side participant projections. Do not redact source frames before hashing, globally allowlist transcript keys, or expose raw export through a participant result. Source-chain integrity and retained redacted-content integrity remain separate claims. |
| Error envelopes and observability: deployment `errors.py`, `LabResult`, `capture_diagnostic()`, common MCP harvest outcomes | Preserve safe command exits, JSON receipts, named harvest failures, and required-transcript failure dispositions. Use `errors.Is`/`As`; add a category only when a caller branches on it. Raw `securefile.Error`, parser/OS/exec errors, and wrapped causes can expose paths or inputs. Entry projects safe errors once. Explicit `slog` uses safe fields on stderr; logs must not enter PTY or protocol stdout. No new exception tree, logging pipeline, or evidence substitute. |
| Persistence and finalization: broker, `_raes_transcript_export.py`, run store, archive | Keep immutable authority identity, single-use session directories, append-only custody, concurrent quota reservation, and loss disclosure. Metadata commits completion before registration removal. Require quiescence, the independent MCP census, and exact accepted-session reconciliation before full-run export. Preserve finalization exclusion and sealed-run immutability. Successful JSON decode, copy, or checksum alone proves no completeness or authorization. |

The capture sink must remain absent from Kali's mount namespace, including
read-only mounts. Share only its network namespace, never its PID namespace.
The broker owns the PTY master; workload-fed bytes are not an authentic source.
Current SSH capability tests require `AUDIT_WRITE` for PTY login and `KILL` for
root quiescence of kali-owned brokers. Neither restores auditd or accounting.
Real container tests must use the shipped capabilities, mounts, and user IDs.

## Compatibility gaps and extension seams

The shared preflight already records Python-dependent callers, incomplete
foundation delivery, differing host/helper validators, and command argv exposure.
In particular, common MCP `captures.ts` also invokes `python3` before `broker.py`.
An image-only interpreter removal breaks shutdown and harvest as well as startup.
Record the native consumer contract and cutover selection without changing the
Python release or porting host realization in this issue. The shared preflight's
machine-checked delivery design remains required before Go code.

Another baseline ambiguity affects enforcement: helper `_table_comment()` maps
a failed nftables query to `None`, also used for absence. Failed inspection
cannot authorize replacement or successful cleanup. Record the security gap
explicitly; if its repair changes baseline behavior, give it separate bug scope.
Do not claim fail-closed observation from a port that preserves that ambiguity.

The extension inputs are the admitted binding ID, run/session IDs, trusted
capture/runtime roots, clock, and small native effect interfaces. Another family
adapter supplies its own safe binding without editing a constant or claiming
`aptl.*`. A finite entry role selects behavior; it does not load plugins.
Daemon architecture belongs in helper asset selection, independently of host
OS/CPU. Preserve offline embedded binaries, trusted digest-pinned images, and
existing asset/seat inventory owners. No compiler or module download belongs
in `lab init` or an image build. No generic effects container is needed.

The whole-repository capture surface includes common MCP config/SSH/shutdown
and `captures.ts`; `_compose_capture*`; guest probes and ownership receipts;
capture SSH/startup/Compose assets; adapter validation; run/archive readers;
`core/assets.py`, `_asset_manifest.py`, `hatch_build.py`, `appliance/input_images.py`,
and `scripts/appliance/assemble-seat-inputs.py`. These remain subject to
`.ground-control.yaml`, `.gc/plan-rules.md`, `.gc/pack-ownership.json`,
`architecture/model.yaml`, module manifests, `.golangci.yml`, CI selection,
`tools/ci/go-gates.sh`, pre-commit, and installed-lab qualification.

## Evidence obligations and non-goals

Reuse broker, capture Compose/apparatus, transcript export, evidence acquisition,
security, correlation, retained-transcript, and serialization tests. Contract
cases must cover concurrent admission/quota use, duplicate sessions, deferred
teardown during custody writes, repeated signals, hangup, and failed persistence.
Preserve stop-session's selected-session scope, signal-free await-session,
global quiescence, and finalization exits 0, 3 (missing), and 4 (unfinished).
Test actual stored redacted blobs and cross-frame secrets, not just record counts.

Reuse `boundary-policy-digest`, `sorted-compact-json`, `sha256-bytes`, `utc-now`,
and transcript chain/document vectors. The chain starts with 32 zero bytes and
hashes prior chain, sequence, NUL, timestamp, NUL, direction, NUL, and raw bytes.
Broker directions remain `input`/`output`; generic hash cases using `in`/`out`
do not authorize changing the wire values. Add missing helper/export conformance
through the existing corpus before Go, and run it on the Python release first.
Conformance is distinct from a bug regression that must fail on the base revision.

Closed bug lessons include [#1477](https://github.com/OpenRAE/lilrae/issues/1477)
(adapter binding), [#1242](https://github.com/OpenRAE/lilrae/issues/1242)
(workspace sidecar), [#1201](https://github.com/OpenRAE/lilrae/issues/1201)
(retained content after redaction), [#1290](https://github.com/OpenRAE/lilrae/issues/1290)
(timeout ends owned work), and [#1105](https://github.com/OpenRAE/lilrae/issues/1105)
(key symlinks and argv credentials). Open
[#1459](https://github.com/OpenRAE/lilrae/issues/1459) owns narrow management
export replacing broad MCP Docker authority. This port must not cement general
Docker access into its API or claim that separate security work complete.

Use explicit targeted test paths and staged-file `pre-commit run` locally.
CI owns mutation, full architecture/security checks, image scans, and clean
installed-lab/offline qualification. Shared MCP edits require all consumers in
CI. Retain Python traceability until Go port 31; add Go links only for delivered
code and tests. This documentation preflight establishes no runtime evidence.

No implementation, package graph, new portable schema, collector, registry,
workflow engine, persistence store, or endpoint belongs in this preflight.
#1566 excludes host realization (#1571), admission/acquisition (#1572), portable
record/seal logic, participant runtime, and release distribution. Do not restore
historical audit/pcap/accounting features, broaden visibility or privileges,
rename wire contracts, or hide a functional/security repair in a parity port.
