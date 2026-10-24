# Issue #1097 Trusted Source Image Selection Preflight

This note fixes design boundaries for #1097; it is not an implementation plan.
The supplied issue is the delivery contract. The inspected dependency pins are
`raes==6.0.1` and `raes-env-packs==6.2.1`. No release-wide kit coverage or live
image availability has been established by this preflight.

## Decisions and boundaries

**A source selector is not an artifact identity.** A declared name/version such
as `postgresql` / `17` or an explicit `stable` entry selects a reviewed,
LilRAE-owned catalog record. It does not authorize constructing a registry tag,
querying a registry for the newest version, or treating the selector as integrity
evidence. Every successful catalog selection yields one repository plus digest
and recorded provenance. A floating alias moves only in a reviewed catalog
change. Missing version, `*`, case folding, spelling aliases, and version ranges
must not acquire implicit fallback semantics.

**Extend the incumbent backend catalog, not a parallel resolver framework.**
`_raes_backend_implementation_catalog.py`,
`_raes_backend_implementation_types.py`, and
`_raes_backend_implementation_profiles.py` already own semantic implementation
policy. Keep shared image identities there; source selectors may refer to the
same implementation records rather than copy their digests. Keep source-only
selection distinct from a profile's optional `runtime_selections`: choosing an
image does not grant permission to inject environment, ports, credentials,
entrypoints, or capabilities. Existing runtime-only open selections must keep
working for source-less nodes.

Matching uses the declared source and applicable typed runtime facts. Require
one eligible record, consistent with OS/distribution/release, product/version,
and required execution mechanics. Contradictory facts fail; they do not rank
one selector over another. No kit/scenario/node name, Compose alias, profile
hint, or local cache hit participates. A service name is a deployment binding
after selection, never an image selector. Distinct eligible records are
ambiguous even when they currently share a digest but differ in policy or
mechanics; duplicate keys must not be erased by dictionary construction.

**Preserve authored authority and the three ADR-051 routes.**
`raes_image_realization.resolve_node_image()` remains the source-image boundary.
An authored exact artifact must be obtained exactly or rejected. Constrained
selection remains within authored candidates/specifications; open selection
requires the matching declared mechanism and realization authority. Reuse
`raes_artifact_mechanisms.select_route_over_mechanisms()`,
`artifact_availability_for_scenario()`, `select_route()`, and the RAES planner
and runtime gates. An unresolved authored artifact cannot fall into the new
catalog, legacy build provenance, or generic substrate as a rescue path.

For a legacy source with no `artifact_requirement`, the catalog is a backend
binding policy, not an invented author-declared exact requirement. Retain the
original source on `DeploymentImageRealization.source_name/source_version`;
put the chosen immutable reference in `image_ref`. Disclose the choice as
backend-realized through the existing provenance/evidence surfaces. Do not
rewrite SDL or fabricate an artifact requirement merely to obtain a satisfaction
record. Existing `compute-substrate` and per-concern OPEN checks in
`raes_backend_implementation.py` still govern backend additions; catalog
membership cannot reopen a closed concern.

Dynamic composition remains a separate admitted route over
`raes_base_substrate.base_container_spec()` / `raes_substrate.resolve_substrate()`.
It must not be reclassified as a component pull. Catalog membership is not proof
that packages, configuration, identities, persistence, or readiness were realized.

**Fail during shared admission, before provisioning.** Unknown and ambiguous
selectors need distinct stable reason codes on the existing redacted
`aptl.provisioner.image-policy-rejected` diagnostic, rather than a generic
pull failure. For example, use `unknown-source` and `ambiguous-source` consistently.
`windows-server` must fail planning with a named unsupported-source/OS diagnostic,
even if an image or Linux fallback could otherwise match. Reuse RAES's OS
admission diagnostic where it covers the source; otherwise add a bounded reason
at the existing source policy gate. Do not extend Windows support.

All callers share `raes.admit_raes_scenario()`, `plan_aptl_scenario()`,
`AptlProvisioner.realize_plan()`, and `qualify_admitted_runtime()`. Selection errors
must reach the admitted execution diagnostics before deferred builds, image
pulls, generated-artifact writes, networks, or containers. Preserve direct
provisioner/apply guards as defense in depth. Carry the admitted selection
through `AptlRealization` and `DeploymentRealizationSpec`; do not resolve again
at apply time or store a mutable selection on a reusable backend singleton.

## Existing traps the implementation must address

- The issue's digest-only premise is stricter than current legacy behavior:
  `_allowed_exact_tag_ref()` accepts tag-only pulls, and
  `tests/test_raes_authored_artifact_authority.py` explicitly preserves them.
  A catalog miss must never reach that path, including `stable` on an allowlisted
  repository. Make this compatibility change explicit in affected contracts and
  tests; do not claim that existing tag syntax proves an immutable pin.
- `matching_backend_implementation_profile()` returns `None` for both zero and
  multiple matches. Its callers can then choose a base substrate. This behavior
  cannot implement #1097's ambiguity refusal. Distinguish these outcomes at the
  canonical matching boundary without another exception hierarchy.
- `_node_source()` defaults an absent version to `*`, and
  `_realize_node()` may attempt semantic selection after unresolved source
  resolution. Neither may turn an unknown/ambiguous declared source into an
  apparently successful fallback. Preserve the source-policy error.
- `DeploymentImageRealization.provenance` is currently `dict[str, int]`, used
  for counts; it cannot carry provenance references or review metadata. Reuse
  RAES provenance contracts and a small backend-owned catalog evidence
  projection where needed; do not put strings into that count map or create a
  second portable artifact schema. A digest proves integrity, not publisher
  authenticity: record the reviewed origin, pin evidence, and catalog record
  identity/revision without claiming unverified signatures or attestations.
- `container_image_digest()` follows the owned container's `.Image`, but
  `_image_manifest_digest()` takes the first `RepoDigests` entry and falls back
  to a config ID. That is insufficient for a catalog-pinned pull. Correlate
  readback with the selected repository/digest using the canonical
  `_docker_image_identity.py` normalization and identity helpers. A missing,
  mismatched, malformed, or uncorroborated digest fails readiness. Multiple
  aliases alone are not ambiguity when the selected identity is independently
  proven; never pick the first alias as proof.
- OCI index digest, platform manifest digest, Docker config ID, Dockerfile byte
  digest, and pack set digest identify different bytes. Keep their media types
  and relationships truthful. For multi-platform pins, prove the selected pin's
  association with the actual daemon-local image and compatible platform;
  neither compare unlike hashes nor claim the selected index was read directly
  from the container. Prefer a platform-specific pin if that relationship cannot
  be established through the existing backend contract.
- `satisfactions_for_plan()` only handles authored artifact requirements.
  Legacy catalog selection needs an explicit selected-versus-observed check at
  the existing observation/provisioner boundary; adding a catalog entry alone
  does not create a RAES artifact gate for that node. Where a requirement exists,
  reuse `ArtifactSatisfactionDisclosureModel` and its verified integrity and
  provenance subset checks. Failure retains the baseline snapshot.
- `_raes_apply_reporting.bounded_apply_details()` compacts away node images.
  Required source/selection/readback evidence must remain in a durable bounded
  projection or referenced run artifact even when compaction occurs. Preserve
  failure evidence too; an expected digest is never an observed digest.

## Required cross-cutting passage

| Layer and canonical incumbents | Required outcome |
| --- | --- |
| API auth: `api/main.py`, `BFFMiddleware`, `deps.verify_token`; CLI lab ingress | Use the same admission path. Add no image-selection endpoint, credential input, or bypass of Host, CSRF, session, or bearer checks. |
| Pack ingress: `ScenarioBundle`, `env_pack_bundle()`, `_pack_staging.py`, env-packs public validators, `utils/pathsafe.py` | Consume validated, digest-bound released declarations. Preserve contained no-follow reads, exact inventory, and immutable staging. Pack metadata cannot replace the backend's trusted catalog. |
| Config and typed shapes: strict `AptlConfig`/`ScenarioSourceConfig`, RAES parser/compiler, `RuntimeConfiguration.model_validate()` | No parallel source/runtime schema or new config/env override for arbitrary images. Validate catalog-owned fields once at their owner; reuse upstream shape and policy gates. New catalog records need strict reference syntax: the permissive `_safe_image_name()` and a digest suffix alone do not exclude controls, credentials, or option-like operands. |
| Artifact and authority gates: ADR-051, `raes_manifest.py`, `ArtifactAvailabilityContext`, `raes_backend_implementation.py` | Retain address partitioning, allowed mechanisms, authored exact/constrained/open domains, and per-concern authority. Catalog trust is distinct from target availability and from verified publisher authenticity. Advertise capabilities only when realization and independent readback exist. |
| OS/runtime policy: `APTL_OPERATING_SYSTEMS`, `parse_os_release()`, `base_container_spec()`, `runtime_authority.py` | The selected image must satisfy finite declared OS support and runtime mechanics; a Linux container does not prove its distro/release or service behavior. No Windows, added capabilities, privileged mode, Docker socket, namespace/device exposure, mounts, or host publication implied by catalog selection. |
| Secrets/environment: ADR-029/052, `_environment_bindings.py`, `EnvironmentBindingContext`, `environment_file_line()`, `_compose_runtime_config.py` | Selection consumes no secret. Any existing profile additions still validate as typed runtime, pass pack-scoped grants/generated-output shapes and pre-mutation binding checks, and use owner-only env-file delivery. Never inline a credential or put it in a registry reference, argv, evidence, or diagnostic. |
| Host/daemon/process: `DeploymentBackend`, `DockerComposeBackend._run()`, `execution_boundary`, project-label ownership | Inspect, acquire, and observe through the bound target daemon and list-form bounded runner, including SSH transport. Preserve endpoint revalidation and lifecycle locking. No shell expansion, controller-local cache assumption, registry login helper, or full inspect/environment dump. |
| Deployment/model: `_compose_image_realization.py`, `_docker_image_identity.py`, `_compose_runtime_config.py`, effective Compose validators | Pull/run the immutable selected reference; validate cached pins and native platform, literal Compose values, merged model and runtime security. Preserve offline/staged refusal rather than network fallback. Generated Compose and static `docker-compose.yml` are not alternate catalog authorities. |
| Failures/logging: `raes_diagnostics.diagnostic()`, `_policy_diagnostic()`, `render_raes_diagnostics()`, `ApplyResult`, `LabResult`, deployment errors, `get_logger()`, `redact()` | Address-scoped stable reasons; bounded redacted envelopes. Catch existing transport/validation failures at their current boundary. No new exception tree, raw Docker stderr, rejected source strings, host paths, tokens, or copied logging pipeline. |
| Evidence/persistence: `observe_realization()`, `DeploymentObservationContext`, `snapshot_after_apply()`, RAES provenance, `raes_repro.RunRecordInputs`, `runstore.py` | Retain declared source, catalog provenance, selected digest and independently observed digest, correlated by resource and execution identity. Reuse existing run-record/backend evidence and redacting structured writers; preserve size/shape checks, sealed-run immutability, and truthful absent observations. No database, cache-as-authority, or new evidence store. |
| Distribution/supply chain: `pyproject.toml`, `_asset_manifest.py`, `hatch_build.py`, `assets.materialize()`, `appliance/input_images.py`, existing staging scripts | Catalog must ship in the wheel. If data assets are necessary, register them in the existing asset mechanism rather than assume a checkout path. Appliance input inventory must consume selected pins, not duplicate a kit image list; offline staging must include them. Reuse pinning/refresh/scanner conventions and report new catalog coverage gaps rather than assuming Dockerfile-only checks cover Python catalog constants. |

## Extensibility and acceptance boundaries

The seam is the existing backend policy lookup: declared source name/version
plus typed runtime compatibility facts selects one catalog record; the deployment
backend resolves/verifies it on its admitted target platform. Make aliases,
supported OS/release and platform constraints data on that policy record, not
new kit branches. Preserve the issue's one digest per source name/version;
runtime facts constrain compatibility rather than silently choose another pin.
An index pin can cover more than one proven platform, or a record can explicitly
support only one platform. A subsequent source version or supported architecture
should change reviewed policy data, not admission, DTO lowering, readback, and
archival algorithms. Do not add an ordered list of fallback images or a generic
plugin framework.

Coverage is the Linux kit inventory of the pinned current env-packs release,
not just TechVault, the default configured pack, or three examples in the issue.
Use env-packs' public inventory/validation APIs and existing pack test fixtures;
do not mirror its schemas, parse private package layouts, or search other
checkouts. Evidence must name the release and the tested selector/runtime set.
A future release changes the coverage input, not selector behavior. If released
declarations lack an admissible route or sufficient portable facts, surface that
specific contract gap; do not synthesize permissions or hide it with a kit name.

Reuse `test_raes_authored_artifact_authority.py`,
`test_raes_backend_implementation.py`, `test_raes_artifact_availability.py`,
`test_raes_artifact_satisfaction.py`, `test_docker_image_identity.py`,
`test_env_pack_realization.py`, `test_raes_repro.py`, and existing wheel/appliance
contracts as applicable. Acceptance needs real shared admission and observation
boundaries: unknown/ambiguous/Windows refusals before mutation, immutable floating
alias resolution, exact-authority precedence, contradictory runtime/platform
refusal, cache/offline behavior, wrong/missing digest refusal, evidence under
compaction, and installed-wheel/release-wide coverage. Renaming a node/scenario
must not change the image. Local verification stays targeted through
`bash tools/run-targeted-tests.sh` and staged `pre-commit run`; full suites and
clean lab lifecycle remain CI-owned under `.ground-control.yaml` / `.gc/plan-rules.md`.

Non-goals: implementing Windows, changing LilRAE's stack, authoring scenario
content, redesigning RAES/env-packs, adding artifact mechanisms or registries,
registry authentication, automatic tag tracking, arbitrary user image overrides,
product-specific provisioning branches, a second lifecycle/admission pipeline,
or broad legacy cleanup. This issue does include the narrow shared matching,
readback, evidence, packaging, and compatibility changes necessary to make its
catalog selection and all stated acceptance criteria true. Existing routes and
unrelated API/config/error contracts remain within their current ownership.
