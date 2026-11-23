# ADR-046: Dynamic RAES Scenario Realization

## Status

accepted (amended 2026-10-31)

## Date

2026-06-29

## Last Updated

2026-10-31

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [realization Reference](../components/node-realization.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

ADR-035 adopted RAES SDL as APTL's scenario authoring surface and wired APTL in
as a conformant RAES backend target. Under that decision the RAES runtime stack
compiles an authored SDL document into a typed `RuntimeModel`, plans a composite
`ExecutionPlan` (provisioning, orchestration, evaluation), and applies it
against APTL's registered `RuntimeTarget`.

ADR-035 originally treated Compose and deployment inventory as topology authority. That covered profiles, networks, addresses, names, volumes, health, ports, and dependencies. The cutover then realized one TechVault scenario. Compose was both its transport and its effective topology source.

That framing no longer holds. APTL now realizes a compiled RAES `ExecutionPlan`
whose `RuntimeModel` carries networks, node deployments, feature bindings,
content placements, account placements, and, per SEM-218, typed realization
requirements. The compiled scenario, not the static compose file, decides what
the range contains. The compose file remains the realization vehicle, reached
through a profile index, but it is no longer the source of truth for topology.

The compiler emits these surfaces on `RuntimeModel`
(`raes_processor/models.py`): networks, node deployments, feature bindings,
content placements, account placements, and `realization_requirements`
(`models.py:4264`). The last field is the SEM-218 contract: a tuple of
`CompiledRealizationRequirement`, each carrying an `ExplicitnessClass` of
`EXACT`, `CONSTRAINED`, or `OPEN` (`raes_processor/semantics/realization.py`).
`EXACT` means the authored value must be honored precisely; `OPEN` is the
open-taxonomy sentinel that a backend may satisfy loosely. The planner gates
the manifest's declared realization support against each requirement through
`realization_support_diagnostics` (`raes_processor/planner.py:957`).

LilRAE must realize the compiled plan through existing typed deployment owners. It must not add another topology authority, SDL, Compose parser, or raw Docker path. The owners that already exist are the ones this decision builds
on, not new abstractions.

## Decision

APTL realizes a compiled RAES `ExecutionPlan` dynamically through an
**interpret-then-driver** pattern. The compiled `RuntimeModel` is the
authoritative interpretation input; `docker-compose.yml` is the realization
vehicle selected by profile, not the topology authority.

Two stages compose the realization:

- **Interpret.** `interpret_provisioning_plan`
  (`src/aptl/backends/raes_realization.py:56`) translates the `ProvisioningPlan`
  carried on the `ExecutionPlan` into a typed `AptlRealization`
  (`src/aptl/backends/raes_realization_model.py:77`). Nodes become
  `NodeRealization`, networks become `NetworkRealization`, and feature
  bindings, content placements, and account placements become
  `PlacementRealization`. The interpreter recognizes the resource types in
  `SUPPORTED_RESOURCE_TYPES` (`src/aptl/backends/raes_diagnostics.py:12`):
  network, node, feature-binding, content-placement, and account-placement. An
  unsupported resource type produces a diagnostic rather than a hard failure, so
  a richer authored scenario degrades visibly instead of crashing the apply.

- **Driver.** `select_backend_profiles`
  (`src/aptl/backends/raes_profiles.py:205`) and `ComposeProfileIndex`
  (`src/aptl/backends/raes_profiles.py:31`) map the interpreted realization onto
  the ordered set of Docker Compose profiles to start, including the profile
  dependency closure. `AptlProvisioner.apply`
  (`src/aptl/backends/raes.py:335`) chains the two stages: interpret the plan,
  select the profiles, then drive `DeploymentBackend.start_lab`.

All container, network, and host operations route through the
`DeploymentBackend` Protocol
(`src/aptl/core/deployment/backend.py:33`). No RAES adapter code calls raw
Docker or parses compose output directly. This binds the realization to ADR-037:
the runner boundary is the extensibility seam, not a mixin hierarchy or a
subprocess shortcut.

The realization honors SEM-218 open and closed semantics. APTL consumes
`RuntimeModel.realization_requirements` and declares its own realization support
through the `RealizationSupportDeclaration` in `create_aptl_manifest`
(`src/aptl/backends/raes_manifest.py:160`), which currently claims `CONSTRAINED`
mode for the `runtime-realization` domain. The planner's
`realization_support_diagnostics` gate decides whether that declaration
satisfies each authored requirement; APTL does not re-evaluate the requirements
with a local model.

Realization evidence persists through the existing run-record owners, not a new
record type. Selected profiles, profile dependency closure, and `AptlRealization`
details are written through `LocalRunStore`
(`src/aptl/core/runstore.py:125`) and referenced from `RangeSnapshot`
(`src/aptl/core/snapshot.py:105`), consistent with ADR-044. Durable non-secret
settings bind through strict `AptlConfig` (`src/aptl/core/config.py:182`, per
ADR-025); secret-bearing runtime values stay in `EnvVars` and `.env`
(`src/aptl/core/env.py:25`). The realization record stores digests and
non-secret identities only.

## Paper Scenario Spine Addendum

Issue #573 starts the first end-to-end dynamic realization: the paper scenario
from Brad-Edwards/aces#598. For that scenario, the profile-index driver above is
only historical compatibility for the TechVault curated variants. The paper
scenario must not be realized by selecting profiles over the fixed
`docker-compose.yml`; it must realize the topology declared by the compiled RAES
plan.

The interpret stage remains pure. It consumes `PlannedResource`s and compiled
runtime artifacts and emits portable, typed APTL realization specs: nodes,
networks, participant action contracts, observation boundaries, and evaluator
evidence surfaces. It does not call Docker, read runtime container state, branch
on a scenario name, or construct backend argv.

The driver stage is the `DeploymentBackend` boundary from ADR-037. A new realization operation needs a narrow typed `DeploymentBackend` method. Local and SSH implementations must reuse runner, timeout, project, labels, and error contracts. Do not add
a generic `docker(args)`, `host_run(args)`, or raw Compose-output parser to the
RAES adapter.

Participant action realization must be compiled-artifact driven. The existing
`DEFAULT_PARTICIPANT_ACTIONS` / `PARTICIPANT_ACTION_ADDRESS` TechVault SSH probe
is not the paper-scenario contract. Compiled SDL and runtime artifacts must supply `probe-customer-portal-login` and its actor, target, interaction, result classification, disclosure, snapshot, and shared-state scope.
Scenario identity may select the scenario file; it must not select behavior.

Wazuh evidence for the paper action is evaluator-only evidence. Evaluator-only evidence may use `AptlEvaluator`, `RuntimeSnapshot`, and `LocalRunStore`. It must not enter participant task context or disclosed observations, or claim detection quality. Boundary verification must show that the participant reaches the DMZ portal. Internal database, Wazuh, and evaluator surfaces must remain absent from its disclosed context.

Non-secret realization knobs continue to bind through strict `AptlConfig`
(ADR-025). Secret-bearing runtime values continue to bind through `EnvVars`,
`.env`, rendered config, and placeholder checks (ADR-028/ADR-029). Any
realization evidence persisted to disk must use `LocalRunStore` JSON/JSONL
writers or `RangeSnapshot.to_dict()` so path validation and redaction stay at
the existing serialization boundaries.

The extensibility parameter is the typed realization spec, not the paper
scenario name. Other scenarios should vary source nodes, services, network boundaries, evaluator sources, and project names through compiled input. They should not need a paper-scenario code branch.

## Paper Scenario Evidence Modeling Addendum

Issue #691 removes an accidental equivalence between content placement and
evidence. In RAES SDL, `content` means material intended for placement on a
scenario target. It is not a generic carrier for an observation, an authored
capture obligation, or a captured evidence record. The paper scenario therefore
must not represent participant output, Wazuh evaluator evidence, or negative
boundary-check evidence as `type: dataset` content merely to give those concepts
names.

The existing RAES carriers remain authoritative:

- `observation_boundaries` owns the participant projection and identifies the
  runtime-emitted participant observation. The portable runtime carrier is the
  existing `participant-observation-envelope-v1`; a second APTL observation DTO
  or dataset schema is not permitted.
- `evidence_requirements` owns portable capture intent for Wazuh corroboration
  and negative boundary checks. Each requirement declares its source or source
  class, scope, window/trigger/boundary, channel, sensitivity, redaction,
  integrity, retention, and loss-disclosure expectations through the RAES
  schema. A requirement is not proof that capture occurred.
- Actual evidence and capture success remain runtime concerns. Conditions and
  objective assertions may report observed success; `RuntimeSnapshot`,
  `AptlEvaluator`, and `LocalRunStore` carry or reference captured records.
  `evidence_requirements.*` entries are deliberately not objective targets.

Backend-only participant binding data is also not participant content. When the
paper binding moves off `content`, it must reuse the compiled
`behavior_specifications` governed-extension seam (`x-aptl:*`) and the existing
`aptl-participant-runtime-binding/v1` validation/parser contract. Do not create a
new top-level SDL section, a second binding schema, or a paper-scenario lookup in
Python. A task brief remains genuine participant-visible content only if it
lowers through the existing typed content realization path to a registered,
project-scoped backing volume. Adjudication prose that is not actually placed is
not content and must not be relabeled as an evidence requirement.

The participant projection is a security boundary, not descriptive prose. Disclosed participant output and snapshot fields must exclude raw Wazuh data, private endpoints, backend commands, evaluator notes, and negative-probe internals. Evaluator evidence may
be referenced from the observation boundary as `evidence_only`; its payload
remains behind the existing run-record redaction and persistence boundaries.

The static gate must cover all remaining paper content placements. Each must lower to `DeploymentContentRealization` without `aptl.provisioner.content-placement-rejected`. The gate also asserts
the authored evidence requirements and observation-boundary projection through
the parsed RAES models. It must not special-case the scenario or widen dataset support. Absence of a planner error does not prove native realization.

The extensibility seams are the map-keyed RAES evidence requirement (parameterized
by source, scope, boundary/window, channel, and handling expectations), the
compiled observation-boundary address, and the governed behavior-specification
extension keyed by backend owner. The next scenario can vary those values
without changing the RAES schema, the content realizer, or a scenario-name
branch.

## Image Realization Addendum

> **Superseded by [ADR-048](adr-048-image-free-placement-realization.md)
> (2026-07-20).** APTL no longer realizes a node's scenario-meaningful
> software, services, content, accounts, or configuration from a pulled or
> built *appliance* image. A node's realized state comes from the RAES
> `ProvisioningPlan`'s placements (`feature-binding`, `content-placement`,
> `account-placement`) applied onto a generic base substrate, at
> docker-compose granularity or better. A generic OS base image is still a
> permitted container substrate; an appliance image that encodes the range
> outside the SDL is not. The pull/build model described below is retained only
> for historical context and for a generic base substrate; it is not the
> node-realization authority. See ADR-048 for the current model.

Issue #574 realizes node images from RAES `source` and captured
`source.build` provenance. This is part of the same dynamic realization
boundary as nodes and networks; it is not a Compose-profile aliasing feature.

APTL consumes the RAES `Source` and `ContainerImageBuildProvenance` schemas as
compiled into each node resource payload under `spec.node.source`. Do not define
an APTL-local source, image, Dockerfile, layer, or build-provenance schema. The
interpreter may extract the RAES payload into APTL's typed realization output,
but the source of truth remains the RAES parser/compiler and the backend-facing
`ProvisioningPlan`.

Image realization has two valid outcomes:

- **Pull.** A node `source` resolves through an APTL image policy and resolver
  to a pullable image reference. Digest-pinned references are preferred and are
  the identity recorded in run evidence when available.
- **Build.** A node `source.build` carries enough captured provenance to build a
  local image through the deployment backend. Build provenance is evidence and
  input to a typed build operation; raw Docker history text and layer metadata
  must not be treated as shell script. If the provenance is insufficient to
  construct a safe build context and instruction stream, realization rejects
  with a diagnostic.

The image trust policy is enforced at the realization boundary before any pull,
build, tag, or compose start can use the image. Configurable non-secret policy belongs in strict `AptlConfig`. A fixed policy may instead use a narrow code-owned object at the interpreter/driver boundary. It must not be hidden in `.env`, Compose labels, a
scenario-name branch, or a backend-specific allowlist.

All image side effects route through `DeploymentBackend`. APTL adapter code may
extend `DeploymentRealizationSpec` and add narrow typed backend operations, but
it must not call `docker pull`, `docker build`, `docker tag`, or
`docker compose` directly. Docker Compose and SSH Compose must share the same
runner, timeout, project-name, logging, redaction, and error-envelope behavior
defined by ADR-037.

Rejection is a structured diagnostic, not a raw backend error. Diagnostics may name a node, reason code, or non-secret rule ID. They must exclude image inputs, build values, registry secrets, rendered Dockerfiles, raw errors, and environment values. Use
the existing `aptl.backends.raes_diagnostics.diagnostic()` and
`render_raes_diagnostics()` path so redaction and RAES operation-status
contracts stay intact.

Realization evidence contains non-secret identity and provenance. Permitted examples include resolved image identity, acquisition mode, source version, provenance references, safe digests, and policy decisions. Persist it
through `AptlRealization.details()`, `ApplyResult.details`, `LocalRunStore`, and
`RangeSnapshot.to_dict()` as appropriate. Do not create a second run record or
store registry credentials, build secrets, raw environment values, or rendered
secret-bearing config.

## Network Realization Addendum

Issue #575 realizes networks and node attachments from the compiled RAES
provisioning plan. `NetworkRealization`, node infrastructure links, and declared static addresses own topology. Hand-authored Compose networks are compatibility inputs only for their curated paths.

Network side effects are backend responsibilities. The adapter may add a typed attachment to `DeploymentRealizationSpec` when existing tuples lose address relationships. It must not add another SDL, topology parser, or argument passthrough. Docker Compose and SSH
Compose must implement the same typed backend operation through their existing
runner, timeout, project-name, label-filtering, logging, redaction, and
`LabResult` / `BackendTimeoutError` behavior.

The backend must materialize each declared network with the authored CIDR,
gateway, and `internal` flag when those values are present. `internal: true`
maps to Docker's internal network semantics and is the dynamic-scenario parity
for SAF-002. Authored `internal: false` permits egress.

Omission selects a backend default. That default must not silently widen an exact or constrained SEM-218 network concern. Backend network names must be project-scoped and collision-resistant.

Created networks need the project label used by `host_list_lab_networks()` so inventory and cleanup stay scoped.

Static addresses are per attachment, not per node. Flattening
`static_addresses` loses which network owns which address and breaks
multi-homed nodes such as `wazuh-manager`, `suricata`, `dns`, `webapp`, and
`kali`. Typed input must preserve node, network, address, and authored-link provenance. Backend attachment, participant endpoint resolution, and evidence must use that realized relationship.

APTL relies on RAES parser/compiler validation for SDL shape and SEM-218
explicitness. Provider validation parses typed CIDRs, gateways, and addresses. It rejects out-of-network or duplicate addresses and ambiguous normalized names. Unsupported exact values fail before effects. Rejections are RAES diagnostics via
`aptl.backends.raes_diagnostics.diagnostic()` / `render_raes_diagnostics()`,
not raw Docker stderr, a new exception hierarchy, or English output scraping.

Network evidence contains non-secret topology and provenance. Fields cover authored and backend identity, CIDR, gateway, internal policy, attachments, static addresses, and backend selection. Persist it through
`AptlRealization.details()`, `ApplyResult.details`, `LocalRunStore`, and
`RangeSnapshot.to_dict()` as appropriate. Do not store raw backend stderr,
rendered Compose overrides containing unrelated config, `.env` values, or
secret-bearing service configuration.

## Runtime Service and SEM-218 Execution Addendum

Issue #578 completes runtime-service realization and the SEM-218 execution
wiring. The public RAES execution owner is `RuntimeManager.apply()`: its backend
call boundary validates `ApplyResult`, runs `realization_disclosure` with
`ExecutionPlan.model.realization_requirements`, rejects silent approximation,
and attaches `RealizationProvenanceEntry` values to the returned
`RuntimeSnapshot`. APTL must use that path rather than call
`realization_disclosure` itself, mutate control-plane snapshot internals, or
reimplement phase ordering and provenance attachment.

The provisioner's returned `RuntimeSnapshot` must describe backend-observed
realization. `snapshot_after_apply()` is only the snapshot assembler; neither a
planned resource payload, a successful lowering, nor a successful materializer
call is evidence of runtime state. A successful snapshot requires backend startup and inspection of the concrete project resource. Every claimed concern needs verified evidence. Backend
inspection continues through typed `DeploymentBackend` operations; the RAES
adapter must not call Docker or parse Compose output directly.

Issue #692 makes that rule explicit for every SEM-218 concern in
`raes_processor.semantics.realization.CONCERN_PAYLOAD_PATH`. `aptl.backends.raes_observation.observe_realization()` owns translation from native evidence to concern values. LilRAE must not duplicate the registry or schema, or substitute planned values:

- `node-type` is disclosed only after a concrete, project-owned backend object
  of the corresponding kind is observed: a project-labelled container for
  `vm`, or a project-scoped network for `switch`. Resource routing or a planned
  `node_type` value is not evidence.
- `os-family` comes from the inspected project-owned container platform and is
  normalized into the RAES vocabulary. A missing, malformed, or unsupported
  platform is omitted; it is never guessed from an image name, Compose service,
  host OS, or planned `os_family`.
- `content-type` requires read-back of the realized destination's actual
  filesystem kind after materialization. A successful seed, a running target
  container, `DeploymentContentRealization.source_kind`, and the planned
  `spec.type` are expectations or prerequisites, not observed type. Read-back
  consumes the existing typed `DeploymentContentRealization` and resolves the
  project-scoped target/volume through `DeploymentBackend`; it returns only the
  RAES kind, never content bytes or command output.

An absent object, wrong project label, ambiguous binding, malformed inspection
shape, non-zero probe result, timeout, or backend I/O error produces no observed
concern. It does not fall back to the plan. For an `EXACT` requirement that
omission or mismatch is rejected by RAES as
`runtime.backend-contract-invalid`; non-exact concerns remain undisclosed
rather than being fabricated. Snapshot assembly may preserve non-concern fields
only where the RAES reconciliation contract requires them. In particular, probe
stdout/stderr and sensitive inline content must not enter `RuntimeSnapshot`,
`ApplyResult.details`, logs, API errors, telemetry, or run records.

Service concepts must remain distinct while they pass through the existing
`AptlRealization` to `DeploymentRealizationSpec` seam:

- RAES `Node.services` declares container-facing service bindings (name,
  container port, and transport protocol). It is not a Compose service name, a
  process-start command, or a host publish.
- `runtime.health.status` is a required observed state. It is not a healthcheck
  command. The realized service must supply any required healthcheck. A running service without a healthcheck cannot satisfy `healthy`.
- `runtime.network.published_ports` owns host exposure and preserves host IP,
  host port, container port, and transport protocol as separate fields. Do not
  infer host publishing from `Node.services` or hardcode published ports in the
  endpoint registry. Runtime evidence comes back through backend inventory and
  the existing `ContainerSnapshot.ports` normalization.

Typed realization owns service startup, waits, and inspection. A successful `LabResult` must mean declared topology is running and required healthchecks passed.
The later lab-orchestration readiness and live-validation gates remain
independent operational evidence; they must not be the first place a failed
realization is discovered. Reuse the backend runner, project name and labels,
timeouts, SSH transport, argv-list construction, host-port probing, and
`LabResult` / `BackendTimeoutError` envelope. Do not return raw backend stderr
through diagnostics, logs, API responses, or run records.

Host publishing is also a security decision. Existing SOC and control-plane
services inherit the loopback-only policy pinned by ADR-034 and
`tests/test_docker_compose_port_bindings.py`. That test has no target-surface
class, so every host publication must be a loopback-bound management surface.
An omitted host address must not silently become
all-interface exposure. A new dynamic publish that cannot be classified by the
existing exposure policy fails closed until that policy is extended. Host-port
conflicts reuse `src/aptl/core/host_ports.py`; an exact authored binding must be
rejected when unavailable rather than silently remapped.

Realization provenance uses the RAES `RealizationProvenanceEntry` contract and
its `author-declared`, `processor-derived`, and `backend-realized` vocabulary.
APTL must not define a parallel provenance enum or infer processor provenance
from field values. Processor-derived provenance requires support from `CompiledRealizationRequirement` through runtime disclosure. The dependency contract must supply that path before LilRAE claims support.

The extension point is a typed node/service binding. It joins resource address, backend identity, container endpoint, optional publication, required health, and non-secret provenance. Another scenario can vary ports, protocols, exposure, and health through compiled input. It does not need scenario branches, registry duplication, or another Compose parser.

## Heavy Stateful Service Realization Addendum

Issue #579 applies the interpret-then-driver boundary to Wazuh manager and
indexer, including their generated certificate material, rendered manager
configuration, and mutable persistent volumes. These concerns form one
addressed dependency graph but remain distinct resource concepts. Generated configuration, certificate bundles, and empty mutable volumes are distinct resources.

Ordinary content placement cannot substitute for their lifecycle contracts.
RAES 0.21 left an important boundary ambiguous:
`RuntimeConfiguration` describes `Node.runtime` as declarative required state,
while `RuntimeMount` and its stability/sensitivity vocabulary describe observed
runtime facts. APTL must not resolve that ambiguity by interpreting the nested
node payload as an APTL-local desired-volume schema.

The upstream contract must
clarify and compile the intended semantics while reusing the existing mount
vocabulary where it fits.

The released RAES contract remains authoritative. An upstream configuration/artifact extension may supply these facts. Local metadata, `x-aptl-*`, scenario branches, or model copies must not own artifact consumers, destinations, sensitivity, lifecycle, or provenance. Missing compiled resource or SEM-218 support blocks admission. The upstream contract must be fixed and released, then selected and hash-locked before capability acceptance. A sibling checkout
or an unpinned VCS dependency is not contract evidence.

That gap was resolved upstream by RAES #780/#782 and hardened by RAES #816.
The historical implementation selected `raes` 1.1.0. It supplied addressed artifacts and volumes, outputs and consumers, lifecycle, access, sensitivity, provenance, dependencies, SEM-218, disclosure, and pre-dispatch mount admission. `pyproject.toml` requires
`raes==1.1.0`, and `uv.lock` records the published distribution and
hashes. The earlier 0.21 limitation remains historical rationale, not an active
APTL-local schema seam.

`AptlRealization` and `DeploymentRealizationSpec` remain the single translation
and driver DTO boundaries. They carry typed records from compiled resources. Arbitrary commands, shell fragments, generic hooks, and provider-specific Compose blobs must not enter that input. All shape, reference, dependency, controlled-vocabulary,
capability, and SEM-218 validation stays in RAES. APTL adds only backend-policy
validation such as provider support, contained output paths, declared output
completeness, mount safety, project-scoped volume identity, and local/SSH
materialization feasibility.

The entire addressed prerequisite and service graph is validated before the
first side effect. The graph orders certificate, configuration, and volume prerequisites before consumers. It orders required Indexer readiness before Manager startup, then observation after startup.

The current
operational scenario's reverse indexer-to-manager dependency is not a boot
contract and must not be preserved. Retry must converge on verified generated artifacts and existing named volumes. Ordinary restart preserves volumes; volume-removing project teardown owns destructive cleanup.

Future replace/delete behavior carries RAES `ChangeAction`; absence is
not deletion intent. One validated graph selects compatibility or typed ownership before generic mutation steps. Startup must not recompile or add a separate Wazuh lifecycle owner.

The deployment backend owns every side effect and readback. Configuration
realization reuses ADR-028's checked-in immutable template, fixed contained
output under `.aptl/`, placeholder/env binding, symlink rejection, permissions,
and atomic replacement. Certificate realization reuses the existing Wazuh
generator and `config/certs.yml` subject/SAN contract plus the isolated
generator-project cleanup, but invokes it through the ADR-037 backend runner.

Certificate success needs complete outputs, matching keys, valid chain and subjects/SANs, and correct permissions. One present file or a permission-repair warning cannot prove success. Permissions must support the actual non-root consumer.

A private parent and container-readable file are valid only after verification. Warning-only permission repair is insufficient. Wazuh trust stays separate from the ADR-034 SOC CA.

An administrative generator bundle can be larger than each artifact's declared mount-output set.
Indexer, manager, and dashboard therefore receive separate read-only CA and
service-key subsets. Administrative and cross-service private keys remain
unmounted from long-lived consumers.

Persistent storage reuses project names, labels, runners, convergence, and safe mounts. It is not `NamedVolumeSeed` content and must not report through `BackendSeedError`. Volume identity, consumer, container destination, access
mode, and lifecycle come from the typed graph. Names are stable within the
project, never global or random per start, and the driver verifies the
container's observed mounts after startup. Captured index contents and mutable
manager state are neither SDL content nor reproducibility evidence.

Compose remains a realization vehicle, not an authority for Wazuh identity,
prerequisites, mounts, volumes, dependency order, or evidence. The dynamic path
must not receive acceptance credit by selecting the hand-authored `wazuh`
profile or matching an existing service block. Compatibility services may temporarily serve other curated paths.

Manager and Indexer effective definitions must still come from the typed realization graph. Generated sources and overrides need canonical bind/path validation before Compose startup. A prior base-file scan cannot cover overrides created later.

The fully merged Compose model must also be inspected before startup. A partial
overlay is insufficient because undeclared base service fields survive Compose
merge and would leave the hand-authored service authoritative. The generated
definition must either stand alone or deliberately reset/override every owned
field.

APTL uses service-level `!override` replacement and rejects Docker
Compose versions older than 2.24.4 before artifact mutation, matching the
[Compose merge contract](https://docs.docker.com/reference/compose-file/merge/).
Effective-model inspection must preserve
secret references or redact resolved values in memory; it must never print,
log, or persist a fully interpolated model containing credentials. The generic
lab-start certificate and manager-config steps must not also own artifacts
selected by typed realization.

Suppression matches exact artifact, provider, consumer, and destination. An authored artifact of the same generator kind cannot suppress an unrelated compatibility step. The effective model and any ancillary override
use fixed paths under `.aptl/realization/`, reject symlinked path chains, and
are replaced atomically; callers never supply an output path.

Stop/restart must
retain the same project and effective-model identity. `stop -v` must remove dynamic volumes through the admitted model or project-scoped, label-validated cleanup. Base-file-only teardown must not orphan realized state.

Local and SSH backends preserve the same contract. A locally rendered file is
not available to a remote Docker daemon merely because `DOCKER_HOST` is set.
Until the backend has an explicit contained remote-materialization operation,
an artifact-consuming remote realization fails closed before mutation.

Secret values and private keys must stay outside SDL, realization details, generated overrides, arguments, errors, diagnostics, logs, snapshots, telemetry, and run records. Compose receives secret references through the existing env
boundary rather than resolved values. Readiness and evidence collection resolve
the existing `EnvVars` credentials at the last responsible boundary and pass
authentication through `curl_safe`'s permissioned header file.

A collector's
hard-coded/default credential tuple is test convenience, not an admissible live
gate or evaluator credential source.

A successful snapshot is backend-observed, not a copy of the plan. It records non-secret evidence: addressed status, scoped volume identity and lifecycle, configuration digest, public-certificate identity and validation, health, and authenticated readiness. Static validation proves RAES
parse/compile/plan/SEM-218 lowering and typed backend inputs without Docker.

`raes_observation.py` must handle each new resource type explicitly; falling
through to content/account placement observation is not valid. A resource is
not ready until provider readback has verified its artifact or mount claims and
the manager/indexer authenticated readiness contract.
The clean live gate requires authenticated Indexer and Manager readiness.

It also requires an actual Wazuh alert retrieved through the collector. Container health, an evaluator condition that merely sees
a ready node, declared `evidence_requirements`, or a Suricata-only event is not
Wazuh evaluator evidence. The alert must follow and correlate with the bounded trigger through non-secret event identity.

Stale or unrelated alert counts cannot satisfy that evidence. Only a bounded,
redacted summary (for example rule/source identity, event time, correlation or
action identity, and digest) may enter run artifacts. `AptlEvaluator` results and history must reflect post-action observations.

Pre-action readiness cannot supply acceptance evidence. No parallel Wazuh evaluator model or workflow is added.

The extension point is the compiled addressed-resource graph. It includes provider, target, dependencies, safe inputs, secret references, outputs, consumers, sensitivity, mount access, persistence, and provenance. Certificate
subjects/SANs/consumers, config renderer/template/output/mount, and volume
identity/destination/lifecycle remain typed parameters rather than Wazuh
branches. Another stateful service can add declarations and a bounded provider binding. It must not duplicate the canonical schema, Wazuh orchestration, or a workflow engine.

## Account and Identity Realization Addendum

Issue #577 replaces the account-placement compatibility proof introduced for
the TechVault operational scenario with real backend-owned account
materialization. Parsing an account placement, carrying it in
`DeploymentRealizationSpec.accounts`, or finding the same username in
`containers/ad/provision-users.sh` is not realization. `DeploymentBackend` applies declared groups and account attributes to the resolved target. Success requires non-secret read-after-write verification.

The authoritative input remains the RAES `account-placement` resource and the
compiled SEM-218 account-feature requirements. APTL must consume the released
RAES account-feature extraction, capability-envelope, explicitness, and
realization-provenance contracts. It must not add a local account schema, a
local feature classifier, or a second explicitness model.

In particular,
`raes_backend_protocols.account_features.provisioner_account_features` is the
canonical mapping from an account spec to governed feature terms. APTL's
manifest may advertise only the terms its backend materializes and verifies;
an unsupported term is a blocking RAES diagnostic, not a silently ignored
field. `password_strength` is non-secret policy metadata, not a credential.

It may be claimed only under the consumed RAES contract. The target provider must enforce it without disclosing the resulting secret.

`DeploymentAccountRealization` remains the single APTL backend-facing account
record. It carries the placement address, target-node address, governed
non-secret attributes, and enough provider binding to resolve the concrete
backend-managed node. The corresponding `DeploymentNodeRealization` remains
the authority for service/container identity; account code must not accept an
independent caller-supplied container name. Group names on account placements
are materialized before membership is reconciled and are deduplicated per
target. They do not justify an APTL-local `Group`, directory, repository, or
identity schema: RAES currently models them as account feature values.

Provider selection is a small, code-owned binding from the resolved backend
service/provider kind to its account materializer. The first supported binding
is the Samba AD service on the realized `ad` node. It is not a TechVault or
scenario-name branch. An account targeting an ambiguous node or a service with
no registered account materializer fails validation before account side
effects. Another POSIX, Windows-local, or directory-service provider adds a binding and implementation for the same placement. It must not turn `container_exec` into generic provisioning.

Account realization is a post-start operation because the target identity
service must be running. The backend starts services and reconciles topology, then waits for bounded provider readiness. It applies the account batch before returning success.

The full batch is provider-validated before the first
account mutation. Application is deterministic and convergent: ensure declared
groups, create or update the user, reconcile every supported explicitly
declared attribute, and verify the resulting non-secret state. A retry after a
timeout or partial failure must converge without duplicate users/groups.

This issue does not delete undeclared accounts or memberships. Later deletion must carry RAES `ChangeAction`; absence alone cannot authorize it.

Provider validation is defense in depth, not a duplicate SDL validator. RAES
owns shape, reference, controlled-vocabulary, capability, and SEM-218 checks.
Pre-mutation validation rejects conflicting duplicates, invalid or ambiguous identities, control characters, unsafe lengths or syntax, and attributes the provider cannot faithfully apply. Values travel as structured
arguments or provider API data, never interpolated shell. Usernames, groups, mail addresses, and SPNs are not control-plane secrets. Untrusted values must still remain outside shell syntax, option names, paths, and unbounded diagnostics.

No plaintext credential crosses the RAES/APTL realization or evidence
boundary. `DeploymentAccountRealization`, `AptlRealization.details()`,
`ApplyResult.details`, diagnostics, snapshots, run records, logs, and telemetry
contain only non-secret identity/policy fields and provenance. Credential generation or resolution stays inside the provider boundary.

Secrets must not enter arguments, environments, exceptions, raw errors, overrides, or persisted request/response files. A provider API, descriptor, or stdin carries required credentials. A CLI password positional argument is prohibited.

A failure returns a bounded `LabResult` message naming the placement
address and stable reason, reusing `BackendTimeoutError` for timeouts and the
existing RAES diagnostic/error-envelope translation. Do not add an account-only
exception hierarchy or expose backend stdout/stderr.

Runtime evidence reuses `snapshot_after_apply`, RAES
`RealizationProvenanceEntry`, `RangeSnapshot.to_dict()`, and `LocalRunStore`.
Account-feature provenance names the placement, field path, requirement kind,
explicitness, and author-declared/backend-realized classification; it never
contains the credential or a derived verifier/hash. Use upstream explicitness and provenance to distinguish authored fields. Empty strings and false values cannot reconstruct local defaults or prove authored intent.

The static `check_account_provisioner_parity` regex scan is superseded as an
account-realization authority. A service script may supply extra baseline fixtures. Reconciliation must handle existing declared accounts, but script text is neither schema nor native proof. Static validation proves RAES parse/compile/plan, capability-envelope,
SEM-218 lowering, target/provider binding, and typed backend input. The clean
live gate proves users, groups, memberships, and declared attributes by querying
the target through `DeploymentBackend` after `aptl lab stop -v && aptl lab
start`.

## Declared Fixture Credential Addendum

Issue #1273 adopts raes-env-packs 6.3.1. That release declares each SOC console
login as an SDL account with one authored `secret_fixture` credential binding.
An authored fixture is scenario content: the SDL already carries the value, and
the participant or attacker meets exactly that value. It is not a credential
the backend generates, so the account addendum's no-plaintext rule applies to
it as follows.

- The account gate lowers one primary `secret_fixture` binding into
  `DeploymentAccountRealization.credential`. The value is excluded from `repr`,
  equality and `details()`, so evidence, snapshots, run records and logs name
  only the `credential_id`. An `operator_secret` binding, several bindings, or a
  mismatched auth method is refused, never substituted.
- The account provider comes from the backend implementation that realizes the
  node (`account_provider` on the implementation profile or base), not from the
  node or service name. Samba AD sets a declared fixture through its stdin
  `setpassword` path. Each application provider (OpenSearch security, Wazuh
  API, MISP, TheHive, Cortex, Shuffle) sets or verifies the value inside the
  serving container with every value on stdin, then proves it by
  authenticating with it.
- When the product's image accepts its bootstrap principal only through its
  environment, the value reaches that environment through the startup adapter's
  account reference (`AccountCredentialFixture`). Core resolves the reference
  against the admitted SDL; the adapter holds no value.
- Lab state persists no rendered credential. The participant desktop receives
  the declared logins only in the participant account's private `0600` files.

The manifest therefore advertises `credential_bindings` and `auth_method`.

## Credential-Bearing Apply Result Addendum

RAES gives a plan with account credential bindings a closed result contract
(RAES `specs/sdl/account-credential-bindings.md`, section 6). RAES compares returned entries with submitted operations. Version 7.0.0 kept the planned payload. Version 8.0.0, under OpenRAE/rae#1640, permits admitted observed concern values and keeps a safe projection. The provisioner's snapshot follows that contract:

- Each entry status names what the backend did with its operation: `applied`,
  or `unchanged` for an unchanged operation. The evaluator reads both, and the
  RAES default `ready`, as a realized node.
- An unobserved concern that the plan admits at that address (an open,
  constrained or exact authority, or a planned constraint) is still omitted, as
  the Runtime Service and SEM-218 Execution Addendum requires. If the plan contains a value that the snapshot omits, the entry differs. RAES then refuses the whole result. A credential-bearing start therefore
  fails unless the snapshot retains every admitted concern that has a plan value.
  Materialization plans retain compiler-generated null and empty-string values
  as absence when the concern's observation contract accepts them, without
  claiming an observation. An invalid absence, such as a null capability policy,
  is omitted so readback waits for a valid observation. Other plans omit an
  unobserved concern even when its plan value is `null`.
  RAES's authority check names some of these gaps, but not one whose plan value
  is empty or `null`. So when that check reports nothing, realization readback
  waits for any such omitted concern within its deadline. A concern still
  omitted then fails the start with `aptl.provisioner.admitted-concern-unobserved`,
  which names the address and concern kind.
- An entry carries no `backend_evidence`, because the contract admits no
  backend evidence key in an entry. The run outcome still carries the
  source-image evidence.
- A plan without account credential bindings keeps unobserved concerns omitted,
  apart from compiler absence values retained for materialization. It keeps
  source-image evidence in its entries unless materialization reporting requires
  portable payloads; the run outcome retains that evidence in either case.

### Exception to the #692 rule

The earlier Runtime Service and SEM-218 amendment prohibits reading concern values from the plan. Missing observations cannot fall back to planned values. It allows a plan value only in a non-concern field that the RAES
reconciliation contract requires. This addendum makes one narrow exception at
concern paths:

- It applies only to a plan with account credential bindings and realization
  authority.
- It covers only a concern path that the plan closes, or that has no authority
  at that address. RAES reads no observation there. The historical closed-concern check treated absence and equality alike. Its result contract still required the planned value.
- There the snapshot keeps the plan's value. That value claims no
  observation: it gets no observation disclosure and no realization
  provenance.
- An observed value always replaces the plan's. A closed concern observed with
  a different value is still refused.

Every other concern path, and every other plan, keeps the #692 rule.

## Owner-Declared Image Content Addendum

A bind mount keeps the host owner and mode. An image node can need a declared
file with a different owner. Issue #1273 added an installer for this case.
Issue #1422 adds a second installer for images that run as a non-root user.

- The node's selected entrypoint names the installer. The content mounts read
  the entrypoint and stage each file that the node inventory gives an owner.
- `OWNED_CONTENT_INSTALLER` runs as root. It installs each file with its
  declared owner, group, and mode.
- `OWNED_CONTENT_IMAGE_USER_INSTALLER` runs as the image user. It installs each
  file with its declared mode. It refuses an owner or group that is not the
  current user or group. It never runs the image as root.
- The image-user installer reads a staged copy at mode `0644`. The copy is in
  an owner-only `0700` host directory, which protects it from other host users.
- When the image entrypoint rewrites a declared file after start, the profile
  runs the image entrypoint steps itself. Declared content then writes the file
  last. The profile pins the image digest, so these steps do not change.

The [issue #1422 design](../architecture/issue-1422-wazuh-dashboard-owned-config-design.md)
records the threats, controls, and data flows.

## TechVault Operational Standup Addendum

Issue #689 makes `scenarios/techvault-operational.sdl.yaml` the honest dynamic
TechVault startup contract. The operational SDL is the public `aptl lab start`
target listed in `scenarios/catalog.json`; it does not depend on a deep
captured TechVault inventory (see the Capture Inventory and Parity-Inventory
Removal Addendum below—that review-evidence surface has since been removed
from APTL). Operational SDL must not depend on captured runtime state. This includes `runtime-observed:`, `datasets-in-services`, inventory manifests, logs, dumps, screenshots, and unrecreatable state.

The acceptance bar is backend-guaranteed fidelity from authored RAES resources
through APTL's interpret-then-driver path. RAES must compile addressed nodes, images, networks, attachments, content, and accounts. The interpreter must lower them to typed deployment input or reject them before effects. A placement that
is merely counted in `AptlRealization.details()` is not dynamic realization.

Content in the honest operational SDL is limited to realizable content, as
clarified by the
[issue #875 preflight](../architecture/issue-875-scenario-content-declaration-preflight.md):

- small file content provided as bounded inline text;
- scenario-supplied bytes identified by exact RAES artifact requirements and
  resolved from a validated, content-identified environment pack, never by an
  engine-checkout or host path; and
- explicit empty directories or portable exact owned-item sets. A source
  directory is not an inventory and cannot authorize recursive copying.

Component software and invariant startup mechanics use ADR-051's component
source-artifact mechanisms. Standup-produced keys, certificates, rendered
configuration, and comparable outputs use RAES generated artifacts. Neither is
ordinary scenario content.

Operational content must not encode observed files, generated configuration, mutable volumes, database rows, indexes, captured package manifests, or arbitrary container trees. When #576's placement boundary exists, `AptlRealization` should use its typed backend input. Compose should reuse containment, scoped volumes, argument lists, redacted `LabResult`, and applicable seed/timeout errors. Without that boundary, #689 is blocked or needs a typed `DeploymentBackend` placement operation. It must not add raw Docker, another schema, or scenario branches.

Account declarations must be equally honest. Fixture accounts may be declared only when clean startup creates or preserves them. An existing service provider or typed account-placement owner must supply that behavior. They must not rely on post-capture drift. Designed
weak target credentials are scenario fixture data; operator/control-plane
secrets remain under `EnvVars`, `.env`, rendered config, and ADR-029 redaction.
SDL, evidence, diagnostics, and snapshots must exclude runtime service credentials, registry secrets, SSH private keys, cookies, tokens, hashes, and generated enrollment material.

Capability claims require evidence across the planner, interpreter, typed specification, backend, static checks, and live clean startup. This applies to content, accounts, images, and networks. A broad `ProvisionerCapabilities` value is not a waiver for a
no-op interpreter branch.

## Capture Inventory and Parity-Inventory Removal Addendum

Issue #690 removes the captured TechVault asset inventory
(`docs/raes/inventory/`) and the SCN-010 parity-inventory surface
(`docs/raes/parity-inventory.yaml` / `.md`, `check_parity_manifest`, and the
`required_surface_coverage` contract in the static validation gate) from
APTL. That capture was an experiment run inside APTL to prove out an
asset-inventory capability; the capability itself now lives in RAES
(`docs/raes/inventory/asset-inventory-methodology.md` at
Brad-Edwards/aces/blob/dev/docs/raes/inventory/asset-inventory-methodology.md).
APTL is a RAES-conformant backend: it keeps only the operational SDL
(`scenarios/techvault-operational.sdl.yaml`) as the driving contract, with no
separate capture/parity evidence surface behind it.

Git history preserves removed capture sources. PR #745 deleted `scenarios/techvault.sdl.yaml`, `scenarios/techvault/`, and `scenarios/aces.lock.json`; `205e47d^` still contains them. The #690 delivery removed `docs/raes/inventory/` bundles, available in its parent revision.

## TechVault Full Dynamic Cutover Addendum

Issue #581 closes the remaining compatibility gap for
`techvault-operational`. The compiled RAES execution graph and the typed APTL
realization derived from it are the sole deployment authority for the public
TechVault start path. `docker-compose.yml`, `ComposeProfileIndex`, profile selection, configuration switches, discovery, and tests must not add undeclared runtime resources or lifecycle facts. The admitted graph owns membership and behavior. Configuration may constrain admission or select a registered
scenario/backend; it is not a second topology language.

Docker Compose remains a backend wire format, not an authored model. The
Compose backend renders one standalone, non-interpolated effective model from
the existing `DeploymentRealizationSpec` at a fixed project-contained path
under `.aptl/realization/`. It must not merge a generated overlay with the
hand-authored base file. A repository-root `docker-compose.yml` is either
removed or emitted deterministically by the same renderer as a derived
reference artifact with a drift check. Public start, stop, kill, retry, status,
clean-volume, packaging, and validation paths must not read that reference as
input.

### Admission and ownership boundary

There is one admitted scenario execution per start attempt. After environment and strict configuration validation, orchestration resolves, parses, compiles, plans, interprets, and validates once. It must finish admission before scenario-dependent side effects. Artifact ownership, host exposure, image preparation, generated model
rendering, startup, observation, retry, and run evidence consume that same
execution-plan identity and typed realization. A helper must not re-plan the
SDL to decide whether it or typed realization owns a side effect.

The existing RAES models and APTL realization DTOs are the only desired-state
schemas. Extend typed realization input only for compiled fields with runtime meaning. Do not add local SDL copies, generic service models, Compose fragments, or command escape hatches. Node `source`, `services`, and `runtime`, compiled networks and
dependencies, content/accounts, generated artifacts, and persistent volumes
lower through those owners. `Node.services` remains container-facing service
identity; host exposure remains `runtime.network.published_ports`; observed
health remains distinct from the authored readiness/healthcheck mechanism.

RAES `RuntimeConfiguration` owns portable environment classification, mounts, capabilities, commands, security, namespaces, restart/resources, and networking. Native lowering consumes that contract. APTL lowers those compiled
fields directly into its existing typed realization boundary. It must not copy
them into a local service schema, rediscover them from Compose, or let a provider
binding silently override an authored value. An unrepresentable or unrealizable exact fact fails admission. Missing upstream or backend capability cannot be supplied silently by a legacy Compose file.

The generic materialization operations required by ADR-048 are derived driver
instructions, not another desired-state schema. They may lower admitted runtime configuration into ordered typed package, filesystem, identity, service, and verification operations. Resource identity and authored provenance must survive through `DeploymentRealizationSpec`. They must not copy RAES service-family models,
invent product-level DTOs, or become a second parser/validator. Materializer validation errors become existing RAES diagnostics and `LabResult` failures at admission. They must not create another public exception hierarchy.

A source/provider binding may supply backend mechanics intrinsic to an
addressed resource, such as generic-substrate distribution, package-repository
transport, or a provider-owned entrypoint/readiness mechanism. Per ADR-048, it
may not select an appliance image or inject undeclared scenario topology or
meaningful node state. Every steady-state container, network, volume, mount,
publication, and dependency in the effective model must be attributable to an
addressed compiled resource. A one-shot helper must derive mechanically from an admitted resource. It needs project labels, lifecycle ownership, evidence, bounds, and explicit exclusion from steady-state parity. A Compose profile is never permission to start an
undeclared service.

The historical inventory found 28 of 30 TechVault VM nodes without `source`. `kali-ssh-proxy` and `cortex-index-init` lacked matching SDL nodes. Compose declared 45 volumes, while SDL addressed three. These are cutover gaps, not permission
to retain Compose as an implicit provider catalog. Each admitted runtime fact needs authored/compiled ownership or a bounded backend-policy/provider derivation. Inactive legacy profiles do not acquire scenario membership merely by existing.

At the 2026-07-19 cutover baseline, the configured public profile set selects 32
legacy service blocks, five networks, and 41 named volumes. That inventory declared 30 VM nodes and four switches. Its legacy-only `aptl-control` network was another ownership gap beside the two services above.
These counts are migration diagnostics, not a permanent parity schema. The static gate derives expected resources from admission and declared bounded helpers. Temporary migration comparison must account for every difference, rather than accept a healthy subset.

Every effective field has one inspectable provenance class: authored RAES data, processor-derived data, backend policy/default, or bounded source/provider binding. Missing, ambiguous,
unsupported, or unowned fields are admission errors before side effects. APTL
must not widen its backend-manifest or SEM-218 claims beyond values that the
planner gate and `observe_realization()` can prove. A missing portable exactness contract requires an upstream fix or admission refusal. LilRAE must not invent a local replacement vocabulary.

### Generated-model and lifecycle contract

The standalone model is written with the containment, symlink-chain,
atomic-replacement, and permission behavior already used for generated
credentials and service config. It carries environment reference names and
classification only, preserves Compose interpolation expressions, and is
validated with interpolation disabled. Realization objects, arguments, diagnostics, output, API results, snapshots, telemetry, and records must exclude secret values, private keys, sensitive configuration, and raw backend output.

Rendering and validation are pure, pre-mutation admission work. The backend stages and validates the complete model, safe identity, artifact sources, outputs, and fields. It publishes the admitted lifecycle artifact atomically before native mutation. Generated outputs are
verified after materialization and before their consumers start. Validating only
immediately before `compose up` is insufficient if an earlier realization step
already mutated the Docker daemon or project files.

Project lifecycle mutation has one serialized owner. Manual, API, scheduled, validation, retry, and emergency paths reuse `.aptl/lifecycle/.lock` from `src/aptl/core/lifecycle_enforce.py`. Do not add a second
lock namespace around only the generated file. The lock must exclude other processes on every supported host. The Windows in-process fallback identified in this amendment could not protect the fixed lifecycle artifact.

Before startup, validation covers the standalone Compose model and trusted contained substrate inputs. It covers generated binds, mount access, powers, dependencies, health, network policy, addresses, scoped volumes, and publications. An
authored exact host port fails on conflict; it is not silently remapped. An
omitted host address remains loopback by default. An SSH backend fails before
side effects while it cannot materialize project-local artifacts safely.

Docker control sockets, devices, host namespaces, privilege, unconfined seccomp, and added capabilities need explicit ownership and refusal policy. Legacy services cannot supply them implicitly. Build and Dockerfile paths require project containment and symlink protection. Image trust policy still applies. Build arguments must not contain secret values.
Provider policy may allow only the minimum mechanics intrinsic to the addressed
resource and must preserve read-only access where the contract requires it.

The generated artifact and its non-secret deployment digest are the lifecycle
identity for every operation. The same admitted artifact drives up, readiness,
inspection, retry, stop, kill, and volume-aware cleanup. Without a valid artifact, recovery may use only project/realization labels and bounded backend metadata. Daemon-wide names or prefixes must not authorize broad deletion.
Run evidence records the execution-plan identity, typed realization digest,
field/resource provenance, and observed state through `LocalRunStore` and
`RangeSnapshot`, not a secret-bearing interpolated model. `selected_profiles`
is compatibility evidence, not TechVault realization evidence.

### Parity and cutover proof

Parity is a two-boundary proof, not a resurrected inventory. The static gate covers parsing, compilation, planning, manifest/SEM-218 admission, typed lowering, and complete standalone rendering. It rejects unowned objects and legacy Compose authority. Unsupported
or no-op resources are errors for the full TechVault gate. This gate is
scenario-generic and blocking for the cutover.

The static gate's `_NoStartBackend` remains a conformance harness only. Simulated readback tests envelope integration. It cannot prove native consumers for packages, files, identities, services, mounts, dependencies, health, content, or accounts. Static cutover
proof comes from complete lowering plus standalone-model rendering/validation
and explicit consumer coverage; live read-after-write supplies realization
proof. A stub that echoes the requested graph is not acceptance evidence.

The historical live command was `aptl lab stop -v && aptl lab start`. Live comparison covers labelled containers, networks, attachments, mounts, ports, volumes, health, content, and accounts against admission. It retains authenticated Wazuh
readiness and a post-trigger, correlated alert assertion. A healthy subset, a
profile list, or silently started extra services is failure. The old Compose model can support temporary migration comparison. Neither it nor provisioning-script regexes remain a permanent authority or parity gate.

The cutover includes CLI/API orchestration, RAES planning and realization, deployment rendering, and lifecycle. It includes configuration, environment, credentials, certificates, ports, evidence, endpoints, and TechVault gates. Asset discovery includes `hatch_build.py`, `_asset_manifest.py`, and `core/assets.py`. Tests and operator documents must also stop treating root Compose as an independent input. The canonical asset manifest and scenario catalog replace Compose
as package-root and bundled-asset discovery inputs; a retained derived Compose
file is reference output only.

## Security Layers

| Layer | Requirement |
| --- | --- |
| Control-plane auth gate | Existing CLI and authenticated API lab-start paths converge on the same orchestration. Existing FastAPI dependencies and BFF Host, same-origin, cookie, and session-header checks remain mandatory. Stateful realization adds no endpoint, credential carrier, or authentication bypass. |
| RAES parser and compiler gate | Authored scenarios enter through `raes.parse_sdl_file` and compile through the RAES compiler and planner. APTL does not structurally revalidate RAES SDL or recompile the `RuntimeModel` with local models. |
| Realization requirement gate | SEM-218 open and closed semantics are enforced by the RAES planner's `realization_support_diagnostics` against APTL's `RealizationSupportDeclaration`. APTL reads `realization_requirements`; it does not re-derive explicitness classes locally. |
| Runtime observation gate | `observe_realization()` emits concern values only from project-scoped backend read-back, using RAES's `CONCERN_PAYLOAD_PATH`. Missing, malformed, timed-out, or mismatched evidence omits the concern and lets `RuntimeManager.apply()` fail an exact requirement closed; it never falls back to planned payload values. |
| Deployment boundary gate | Curated compatibility paths outside operational TechVault may still drive `DeploymentBackend.start_lab` with profiles. The paper and operational TechVault scenarios drive typed `DeploymentBackend` realization methods, with Compose rendering confined to that backend. No RAES adapter code calls raw Docker, `docker compose`, or parses compose output directly (ADR-037). |
| Generic substrate and software-source gate | Per ADR-048, a node's substrate resolves only from its declared OS family/version through a small, fixed, scenario-independent base-image policy. A node `Source`, provider binding, Compose service, or scenario name cannot select an appliance image that carries scenario-meaningful state. Substrates and software sources must pass trust/digest admission before effects. Unsupported OS/package-manager pairs fail through existing diagnostics without exposing credentials, build input, or raw errors. |
| Network topology gate | Network creation, IPAM, `internal` egress policy, and per-node attachments come from typed realization specs. Backend validation parses CIDRs, gateways, and addresses, and preserves project labels and scope. Unsupported exact or constrained values fail before effects. |
| Content placement gate | Operational TechVault content must be bounded inline text, project-contained checked-in file source, or project-contained checked-in directory source lowered into typed backend placement input. Path containment, safe relative-path validation, project-scoped volumes/copies, and redacted backend failures reuse existing deployment and seed precedents; captured runtime content is rejected. |
| Stateful prerequisite gate | RAES shape, reference, dependency, and SEM-218 checks precede backend validation. The backend covers providers, paths, complete certificates, cryptographic relationships, mounts, scoped volume lifecycle, and transport feasibility. Generated overrides are rechecked after materialization and before startup; observed mounts, authenticated Wazuh readiness, and actual alert retrieval are required runtime evidence. |
| Artifact path and permission gate | Manager configuration and certificate outputs reuse `credentials.py` containment, symlink-chain rejection, atomic replacement, and verified mode behavior. Declared certificate outputs additionally pass key-pair, CA-chain, subject/SAN, consumer, and completeness checks. No unchecked path, missing output, or warning-only permission failure reaches Compose. |
| Effective Compose model gate | The backend renders and validates one standalone model, generated bind sources, volume declarations, dependency order, loopback publications, and health contract before `compose up`. Validation preserves secret references and runs without interpolation; it neither logs nor persists a fully interpolated model. An overlay/base merge, partial reset, or inherited hand-authored semantic is a cutover failure. |
| Account placement gate | RAES parser/compiler, canonical account-feature extraction, manifest capability checks, and SEM-218 explicitness/provenance run before the backend. The typed node selects the account target. Full-batch and provider validation precede mutation. Bounded readiness precedes reconciliation and non-secret state verification. Raw credentials, hashes, provider stderr, and caller-supplied container identities remain outside typed inputs and evidence. |
| Config, env, and secret binding | Non-secret backend/admission knobs bind through strict `AptlConfig`; config toggles do not add or remove operational TechVault topology. Runtime secrets pass through `hydrate_dotenv`, `load_dotenv`, `env_vars_from_dict`, `find_placeholder_env_values`, and `EnvVars`, while the graph carries only secret-reference names and classification. Values resolve only at the existing renderer/provider/readiness boundary and are passed through the existing env or permissioned-file channels. Hard-coded collector defaults are not a live credential source. The realization record stores digests and non-secret identities, never `.env` values, rendered config, tokens, or key material. |
| Host and process exposure | Existing loopback host-binding policy and published-port conflict checks apply to Wazuh. Docker/Compose execution uses argv lists through the shared local/SSH runner; credentials, private-key contents, and rendered config are never command arguments. An unclassified host bind or a remote artifact path the backend cannot materialize fails closed. |
| Logging and error envelope | Provider failures collapse into bounded, stable `LabResult`, existing deployment exceptions, and RAES diagnostics after shared redaction. Raw output, SDL secrets, rendered configuration, private keys, and alert bodies must not enter logs, API results, telemetry, snapshots, or artifacts. No Wazuh-only exceptions are added. |
| Persistence and redaction | `LocalRunStore` and `RangeSnapshot.to_dict()` serialize safe realization and evaluator evidence. Compatibility profiles remain distinct from dynamic realization identity. ADR-029 redaction and containment still apply. Neither interpolated Compose nor secret-bearing generated configuration is evidence. |
| Static and live validation gate | Static checks must establish complete typed lowering and rendering without unsupported, unowned, or no-op resources. Legacy Compose input cannot supply missing realization. The live gate remains a public clean `aptl lab stop -v && aptl lab start` plus graph-to-observation parity, authenticated readiness, and correlated evidence, not a comparison to captured inventory state. |

## Maintainability

The canonical incumbents this decision builds on are:

- `src/aptl/backends/raes.py` for the `RuntimeTarget` wiring and
  `AptlProvisioner`.
- `src/aptl/backends/raes_realization.py` and
  `src/aptl/backends/raes_realization_model.py` for the interpret stage and its
  typed output.
- `src/aptl/backends/raes_materializer.py` for ADR-048's pure,
  product-agnostic lowering from admitted RAES runtime state to ordered typed
  driver operations. Its operation values are derived instructions carried by
  the deployment realization, not a local runtime/service schema and not a
  public exception boundary.
- `src/aptl/backends/raes_profiles.py` for curated compatibility only. It is
  not the paper-scenario or operational-TechVault topology driver.
- `src/aptl/backends/raes_diagnostics.py` for the supported-resource-type set
  and diagnostics.
- `src/aptl/backends/raes_observation.py` for backend evidence-to-concern
  translation, using the RAES-owned concern path registry rather than an
  APTL-local schema.
- `src/aptl/backends/raes_manifest.py` for the realization support declaration.
- `src/aptl/backends/raes_observation.py` for explicit backend-observed
  realization state; new resource kinds must not fall through to placement
  observation.
- `src/aptl/api/main.py`, `src/aptl/api/deps.py`, and
  `src/aptl/api/middleware/bff.py` for control-plane authentication, Host,
  same-origin/CSRF, and two-factor browser-session enforcement. Realization
  remains behind the existing lab-start surface.
- `raes_backend_protocols.account_features.provisioner_account_features` for
  the governed account-spec-to-feature mapping; do not copy that decision table
  into APTL.
- `src/aptl/core/deployment/` for every Docker, Compose, container, and host
  operation, including any future image pull/build/tag and network/IPAM side
  effects.
- `src/aptl/core/scenario_catalog.py` for registered scenario identity and
  project-contained resolution, and `src/aptl/core/lab.py` for the one public
  CLI/API orchestration and retry boundary. Neither gains a second SDL planner.
- `src/aptl/core/credentials.py` and ADR-028 for contained, atomic manager
  configuration rendering; `src/aptl/core/certs.py` and `config/certs.yml` for
  the existing Wazuh certificate generator/subject contract. These are
  providers behind typed realization, not competing workflow authorities.
- `src/aptl/core/deployment/realization.py` and
  `src/aptl/core/deployment/_compose_realization.py` for the typed realization
  DTO and its ordered backend-owned side effects; do not create a Wazuh
  orchestrator beside them.
- `src/aptl/core/deployment/_compose_port_realization.py` for typed host-port
  exposure decisions and conflict validation. `_compose_image_realization.py` retains compatibility image acquisition. ADR-048 supersedes its operational TechVault appliance-image assumptions. Only generic trust/digest behavior applies to fixed base substrates. Move rendering behind the
  standalone Compose-model boundary; existing overlay/base merge behavior is
  not a cutover contract. Apply ADR-028 containment, symlink, atomic-write,
  permission, and effective-model validation rather than copying unchecked
  file-write details.
- `src/aptl/core/seed_spec.py` and existing named-volume seed behavior for
  project-contained source-to-runtime materialization when content placement
  needs file or directory side effects. Mutable Wazuh persistence reuses its
  project-scoping and runner conventions, not its seed semantics.
- `src/aptl/core/services.py`, `src/aptl/utils/curl_safe.py`,
  `src/aptl/core/collectors.py`, and
  `src/aptl/validation/techvault_live_gate.py`,
  `src/aptl/validation/_live_gate_checks.py`, and
  `src/aptl/validation/_live_gate_probes.py` for shared readiness polling,
  argv-safe authentication, Wazuh alert collection, and the clean-start live
  evidence gate. The Manager probe must use the backend and authenticate readiness. The earlier raw status-only probe and Suricata-or-Wazuh live condition are not acceptable templates.
- `src/aptl/core/runstore.py`, `src/aptl/core/snapshot.py`,
  `src/aptl/core/config.py`, and `src/aptl/core/env.py` for run persistence,
  inventory evidence, config, and env binding.
- `src/aptl/_asset_manifest.py`, `src/aptl/core/assets.py`, `hatch_build.py`,
  and `scenarios/catalog.json` for package assets and lab-root/scenario
  discovery. Compose is removed as an input/marker rather than replaced by a
  second generated asset list.
- `src/aptl/utils/redaction.py`, `src/aptl/core/lab_types.py`, and
  `src/aptl/core/deployment/errors.py` for redaction and the existing result /
  timeout/failure envelopes; do not add Wazuh-specific copies.
- `scenarios/paper-agent-loop.sdl.yaml` for #579's manager/indexer and Wazuh
  evidence contract; `scenarios/techvault-operational.sdl.yaml` for dynamic
  public startup; and `scenarios/catalog.json` for their registered selection.

Tests extend the existing RAES backend and realization seams
(`tests/test_raes_backend.py` and the realization-focused tests) rather than
introducing a new harness.

## Extensibility

The extensibility seam is the boundary between the interpreted realization and
the driver. Interpret produces a typed `AptlRealization` from the compiled plan;
the compatibility driver may map explicitly compatible scenarios onto profiles.
The paper and operational TechVault drivers consume the typed realization spec
directly through `DeploymentBackend`. Standalone rendering is parameterized by
execution-plan identity, `DeploymentRealizationSpec`, backend/provider policy,
project identity, and target capability. Another authored resource extends `SUPPORTED_RESOURCE_TYPES`, interpretation, and any required typed backend operation. It must not add topology authority or scenario-name branching.

The design must stay parameterized by scenario identity and backend manifest
version. It must not assume one scenario, permanent Compose-only deployment, or a fixed realization mode.

The network attachment carries scenario/backend network identity, optional CIDR/gateway/internal policy, node and native identity, optional static address, and authored-link provenance. Future scenarios should be able to vary segmentation,
addressing, and egress policy without editing the compatibility
`docker-compose.yml` network block or branching on scenario names.

Node materialization joins declared OS, fixed substrate policy, compiled runtime configuration, typed ordered operations, provider capability, and observed readback. ADR-048 owns this boundary. The next likely
change is another OS family or package manager, multi-architecture generic base
selection, package-repository authentication, or SBOM/attestation policy. Extensions change the fixed policy map or typed provider operation. They must not select appliance images through RAES `Source`, Compose identity, scenario names, or product branches.

Content and account placement carries its RAES address, target identity, content/account identity, safe provenance, bounded source and destination kinds, and materialization operation. Account provider kind is resolved from the
typed target binding, not from scenario identity. Another scenario should vary source directories, inline files, target nodes, account fixtures, and providers through typed input. It should not need TechVault-only code changes. Future account deletion/replacement reuses RAES `ChangeAction`; it must
not add an APTL-only lifecycle enum.

For generated artifacts and stateful storage, the seam is the addressed
realization graph described by the heavy-service addendum. Provider kind,
target, dependency addresses, output/consumer identity, sensitivity,
mount/access contract, persistence lifecycle, secret references, and provenance
are parameters. Raw commands and Compose fragments are deliberately not
extension points.

For runtime disclosure, the parameterized seam remains
`observe_realization(DeploymentBackend, AptlRealization, ProvisioningPlan)` and
the existing typed realization records. A new backend or a new RAES concern
adds provider-owned read-back behind `DeploymentBackend` and maps only the
observed value at this boundary. The RAES concern kind/path registry, runtime
gate, snapshot DTO, and provenance vocabulary remain upstream-owned and are not
extended with APTL mirrors.

## Consequences

### Positive

- The compiled scenario, not a hand-edited compose file, decides range
  topology. A new scenario realizes without editing `docker-compose.yml`.
- SEM-218 open and closed semantics are honored through the RAES planner gate,
  so APTL's realization claims are contract-validated rather than asserted.
- Realization evidence rides the existing run record (ADR-044); there is no new
  record type to maintain or redact.

### Negative / costs

- The standalone renderer and lifecycle metadata become a versioned backend
  contract. Field provenance, deterministic output, project labels, and
  backward-compatible cleanup must stay aligned across local and SSH targets.
- APTL's realization support declaration must stay honest. Widening the claimed
  realization support without the interpreter and driver to back it would let
  the planner gate pass scenarios APTL cannot actually realize.
- The honest TechVault SDL may be smaller than the captured inventory. Omitting
  non-realizable captured facts is correct; carrying them as no-op operational
  placements is not.

### Risks

- An authored scenario can carry resource types APTL does not interpret.
  Compatibility scenarios may continue to report bounded diagnostics, but the
  full operational TechVault gate treats every unsupported or no-op addressed
  resource as a pre-side-effect error.
- Manifest capability text can drift ahead of backend behavior. The static
  lowering tests and clean-start live gate must catch claims that are parsed
  and counted but never passed to a typed backend operation.
- `RuntimeSnapshot.payload` participates in RAES reconciliation as well as
  disclosure. Removing non-concern fields blindly can force perpetual updates,
  while copying a sensitive planned payload can leak it into the run record.
  Snapshots keep only required reconciliation state, without sensitive content or probe output. A broader desired/observed split belongs in RAES rather than a local schema.
- Disclosure failure happens after backend side effects. It rejects the apply
  and restores the baseline control-plane snapshot, but it is not transactional
  rollback of already-created containers, networks, or volumes. Do not report
  failed observations in `changed_addresses`; cleanup remains the established
  lab stop/kill workflow unless RAES adds an apply rollback contract.

## Non-Goals

- This ADR does not replace Docker Compose as a deployment backend. It does
  replace the repository-root, hand-authored `docker-compose.yml` as the
  operational TechVault realization and lifecycle input; any retained copy is
  deterministic derived/reference output.
- This ADR does not define a new run-record type, scenario schema, or RAES
  mirror model. Realization evidence rides ADR-044's record.
- This ADR does not change APTL's backend profile claim. The manifest and
  conformance gates remain the source of truth for that claim.
- This ADR does not require the operational TechVault SDL to reproduce every
  captured inventory fact. It requires every authored operational fact to be
  dynamically realizable or rejected before startup side effects.
- Issue #577 does not add operator identities, control-plane authentication,
  RBAC, secrets management, or a general directory-service API. It does not
  delete accounts/groups absent from the scenario or migrate the additional
  baseline fixtures in `provision-users.sh`.
- Issue #579 did not add Dashboard realization, CA merging/rotation, mutable-data capture, volume migration, version or credential changes, remote synchronization, or generic workflow/evaluator engines. It may sequence the existing
  action, evidence probe, and `AptlEvaluator` result correctly for Wazuh, but it
  does not create a parallel evaluation contract. An SSH realization may remain
  explicitly unsupported until the backend can materialize its artifacts
  safely.
- Issue #581 added no orchestration language, generic hooks or commands, Kubernetes backend, remote synchronization, API/authentication model, secret store, rollback, or daemon-wide cleanup. Inactive legacy profiles do not define TechVault membership. Operational SDL does. Each service from pre-cutover public startup still needs an addressed resource or bounded helper.
- Issue #692 added no disclosure gate, snapshot/evidence schema, API, configurable probe commands, content-integrity attestation, or transactional rollback.

## Anti-Patterns

- Treating a scenario name as a profile selector instead of deriving profiles
  from the interpreted realization.
- Reading the repository-root `docker-compose.yml`, `ComposeProfileIndex`, or
  `aptl.json` container switches to complete operational TechVault topology,
  service identity, or lifecycle behavior missing from the admitted graph.
- Producing the standalone model by copying legacy Compose service blocks and
  labelling the result "generated" without typed field ownership and
  provenance.
- Re-planning the SDL in artifact preparation, host-port resolution, retry,
  validation, or evidence code instead of consuming the single admitted
  execution/realization identity.
- Using `select_backend_profiles` or `ComposeProfileIndex` as the topology
  driver for the paper scenario.
- Extending `DEFAULT_PARTICIPANT_ACTIONS` with paper-scenario behavior instead
  of deriving participant action specs from compiled SDL/runtime artifacts.
- Emitting participant snapshot entries or shared-state scopes with legacy
  TechVault SSH identifiers after the runtime selected a different participant
  action binding.
- Calling `docker` or `docker compose`, or parsing compose output, from the
  interpret or driver stage instead of routing through `DeploymentBackend`.
- Resolving node images by reading whatever image/build block a pre-existing
  Compose service pins, or treating a Compose profile match as image identity.
- Treating RAES `Source.name` / `version` as a raw Docker image reference until
  it has passed the APTL image resolver and trust policy.
- Building from raw Docker history strings, unbounded Dockerfile text, or
  unvalidated build context paths instead of typed `source.build` provenance and
  project-contained backend operations.
- Adding `runtime-observed:` content, `datasets-in-services`, database dumps,
  log excerpts, package manifests, or arbitrary captured filesystem trees to
  the operational TechVault SDL.
- Treating `content-placement` or `account-placement` resource counts as proof
  of realization when no typed backend operation consumes the placement.
- Treating a successful seed, a running/healthy target container, the typed
  placement's source kind, or `spec.type` as read-back proof of the realized
  content type.
- Treating script text, a create-command success, or an existing username as proof of all account attributes. Backend success requires non-secret read-after-write verification.
- Keeping `check_account_provisioner_parity` as a second account authority after
  backend realization lands, or parsing shell scripts/Compose text to derive
  account state.
- Re-implementing RAES account-feature extraction, explicitness, capability, or
  provenance rules in APTL, or advertising a manifest feature the selected
  account provider does not apply and verify.
- Passing plaintext credentials through realization objects, arguments, environment, generated files, diagnostics, logs, snapshots, telemetry, or artifacts.
- Adding generic remote-account commands or caller-selected container IDs. Provider selection must use the typed target, without a TechVault scenario branch.
- Hiding an unrealizable content/account fact in `metadata`, comments,
  `x-aptl-*`, inventory ledger rows, or a TechVault scenario-name branch.
- Treating generated configuration, certificates, or mutable persistence as ordinary content. Raw `runtime.mounts` cannot replace an upstream compiled volume contract. Missing RAES contracts cannot justify a local stateful-service schema.
- Claiming Wazuh realization because the `wazuh` profile or a hand-authored
  Compose service started, a plan resource was echoed into a snapshot, or only
  `root-ca.pem` exists.
- Adding a generic `run`/hook/command field, invoking a provider-specific shell
  fragment from SDL, or copying Wazuh lifecycle ordering outside
  `DeploymentBackend`.
- Assuming base-file validation covers generated overrides or local files reach a remote daemon. The original reverse Manager/Indexer dependency is not valid boot ordering.
- Using overlays that silently inherit base mounts, environment, dependencies, healthchecks, or commands. Reset/override merge tags also require enforcement of their supported Compose version.
- Interpolating secret values into the generated model, passing them on process
  argv, or persisting/logging the rendered effective configuration as proof.
- Treating container health, node-ready evaluator conditions, authored evidence
  intent, or a Suricata-only event as proof of a functioning realized Wazuh.
- Using default collector credentials, stale alerts, pre-trigger evaluation, or uncorrelated counts. Alert evidence needs a bounded non-secret join to the actual trigger.
- Recreating volumes at every startup or using global/random identities. Absence does not authorize deletion, and mutable Wazuh storage is not a seed.
- Starting with a generated effective Compose model but stopping with only the
  base file when that can leave realized containers, networks, or volumes
  orphaned.
- Calling a selected or healthy subset full parity. The gate must reject extra labelled steady-state objects and missing mounts, publications, volumes, or dependencies.
- Exposing keys, sensitive configuration, secrets, raw alerts, or backend errors. Incomplete outputs, failed permissions, or unchecked certificate relationships cannot count as success.
- Running both the generic lab-start cert/config preparation and typed
  realization for the same manager/indexer artifacts.
- Duplicating the content schema, account schema, path-containment checks,
  volume seed behavior, credential taxonomy, or redaction policy instead of
  reusing the existing RAES/APTL owners.
- Echoing disallowed image refs, registry credentials, build arg values,
  rendered Dockerfile text, or backend stderr in diagnostics, logs, snapshots,
  API responses, or run records.
- Re-evaluating SEM-218 explicitness classes with a local model rather than
  consuming `realization_requirements` and the planner gate.
- Copying concerns from `ProvisioningPlan` or substituting them after failed inspection. Matching names without project labels cannot prove ownership. Raw probe output must remain private.
- Adding a second topology authority, a duplicate compose parser, or a local
  `RuntimeModel` mirror.
- Writing realization evidence to a new record type instead of `LocalRunStore`
  and `RangeSnapshot`, or storing secret values rather than digests and
  non-secret identities.
- Reintroducing captured runtime-observed content (a per-asset inventory
  tree, evidence bundles, or a `capture-evidence.sh`-style runner) into APTL;
  that capture capability lives in RAES, not here.
- Reintroducing a parity-inventory surface (a `required_surface_coverage`
  manifest, a `check_parity_manifest`-style gate check, or a
  represented/deferred contract) as a condition of the static or live
  validation gate.

## Descendant recording and attestation addendum

Issues #1128 and #1130 add cooperative creation recording on the existing Docker daemon.
The maintainer selected recording without another authority enforcement policy.
The host daemon and its configuration remain unchanged.
Raw Docker authority remains host-root-equivalent.
The recorder cannot prove complete coverage against a hostile holder that bypasses it.

The deployment provider records native creation responses before returning them to holders.
Canonical socket delegation preserves the recorded parent chain.
Immutable creation records supplement `WorkspaceOwnership` and `ResourceReceipt`.
Recorded native IDs authorize revalidated child observations, deadlines, and cleanup.
Names, images, topology, and ordinary labels do not authorize adoption.
Uncertain creation or inspection remains an explicit recording gap.

RAES 8.1.0 owns portable membership admission, materialization archives, and SEM-218 provenance.
The provisioner submits materialized SDL through the negotiated descendant and materialization contracts.
It uses the original source, run scope, operation, predecessor, and attempt bindings.
Later inventory refresh is read-only and uses `RuntimeManager.refresh_inventory()`.
The final returned snapshot includes accepted later observations.
The backend never edits the runtime-owned ledger or executable plan.

The [owned descendant design](../architecture/issue-1130-owned-descendant-reporting-design.md) defines the recording boundary, data flows, and recovery behavior.
Mutable native lifecycle records remain separate from sealed run evidence.
The public native-evidence handoff retains immutable runtime state cuts and
original materialization/archive bytes for restricted experiment collectors.

Native observation and verified cleanup records remain backend-owned evidence.
They neither grant resource authority nor replace runtime-derived provenance.
The existing collector source and sealing interfaces retain those original bytes;
participant-visible or byte-redacting bindings cannot consume the protected handoff.

ADR-055's independent operator-grant policy remains proposed and outside this delivery.

## References

- [ADR-025](adr-025-strict-first-party-config-schema.md): strict first-party
  config schema for non-secret realization knobs.
- [ADR-029](adr-029-control-plane-secret-handling.md): runstore and snapshot
  redaction boundaries.
- [ADR-028](adr-028-runtime-rendered-service-config.md): contained, atomic,
  redacted service configuration rendering.
- [ADR-034](adr-034-lab-managed-soc-tls-ca.md): SOC CA ownership and its
  explicit separation from the existing Wazuh certificate chain.
- [ADR-043](adr-043-suricata-runtime-config-ownership-boundary.md): named-volume content
  seeding precedent and the boundary between static content and mutable state.
- [ADR-035](adr-035-raes-sdl-adoption.md): RAES SDL adoption; this ADR
  supersedes its Parity Inventory Boundary realization model while preserving
  its SDL adoption and backend-manifest/conformance model.
- [ADR-037](adr-037-docker-compose-backend-cohesion.md): all Docker and Compose
  operations route through `DeploymentBackend`; the runner boundary is the
  extensibility seam.
- [ADR-044](adr-044-raes-aligned-run-reproducibility-record.md): realization
  evidence rides the run reproducibility record rather than a new type.
- SEM-218 (RAES compiled realization requirements) and RUN-314 / autarchy-ai/aces#197
  (reference emulation backend).
- Related issues: [#554](https://github.com/Brad-Edwards/aptl/issues/554),
  [#556](https://github.com/Brad-Edwards/aptl/issues/556) (superseded paper
  scenario path), [#573](https://github.com/Brad-Edwards/aptl/issues/573),
  [#574](https://github.com/Brad-Edwards/aptl/issues/574),
  [#575](https://github.com/Brad-Edwards/aptl/issues/575),
  [#576](https://github.com/Brad-Edwards/aptl/issues/576),
  [#579](https://github.com/Brad-Edwards/aptl/issues/579),
  [#581](https://github.com/Brad-Edwards/aptl/issues/581),
  [#689](https://github.com/Brad-Edwards/aptl/issues/689),
  [#692](https://github.com/Brad-Edwards/aptl/issues/692),
  [aces#598](https://github.com/Brad-Edwards/aces/issues/598), and
  [aces#600](https://github.com/Brad-Edwards/aces/issues/600); DSL-008 /
  [#422](https://github.com/Brad-Edwards/aptl/issues/422).
