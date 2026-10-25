# Issue #1409 Node Runtime Security Preflight

The supplied GitHub issue is the delivery contract. This note fixes the
architecture and verification boundaries before implementation; it is not an
implementation plan. No new ADR is needed: ADR-003 owns the shared MCP HTTP
client, ADR-026 owns supply chain pinning and blocking image scanning, ADR-034
owns MCP TLS selection, and the existing appliance build/trust documentation
owns seat-image replacement.

## Decisions and concept boundaries

The remediation is a runtime replacement, not an HTTP workaround. Preserve the
three existing MCP transport states and upgrade every reachable Node runtime to
a supported fixed release. Do not disable Brotli, rewrite `Accept-Encoding`,
add an application decompressor, or move the system-trust case from `fetch()`
to a new transport. Those changes would alter HTTP semantics while leaving
other uses of the vulnerable runtime exposed.

Keep these identities separate:

- A Node image tag states the intended release; its OCI index digest binds the
  pulled multi-architecture bytes. Both are required. A digest without an
  explicit patch-version tag is immutable but does not make the security floor
  reviewable.
- The appliance uses the official Node.js release tarball because Ubuntu 26.04
  does not provide the fixed Node 22 release. Its pinned release key and signed
  checksum manifest authenticate provenance; `node-runtime.sha256` binds the
  admitted bytes. Neither fact proves what the finalized guest executes.
- `node --version` from a built image or finalized guest proves effective
  runtime selection. It does not replace the source pin or byte identity.
- The web Node stage is a build tool only. The final `aptl-web-ui` image is a
  Caddy image and should continue to contain no Node runtime. Verify the named
  builder stage rather than adding Node to the final image.
- `@types/node` versions are compile-time type declarations, not runtime
  identities. Changing them does not remediate the CVE and they must not be
  treated as runtime evidence.
- A rebuilt or published artifact is not an updated consumer. Existing seat
  selections are digest-sticky, locally built Compose images can remain cached,
  and running scenario containers keep their old filesystem until recreated.

The supported-version policy must be an allow-list of supported majors with a
per-major minimum, initially 22.23.4, 24.22.1, and 26.12.1. A numeric
"major >= 22" test is unsafe because it accepts unsupported odd majors such as
25 and will eventually accept an end-of-life even major. Extend the existing
version parsing/checking seam in `src/aptl/core/_doctor_common.py` and the
`lilrae doctor` Node check rather than introducing a second product validator.
The supply chain tests should consume the same policy and fail closed on an
unknown major, an incomplete/unparseable version, or a version below that
major's floor. A future supported line should require one policy entry, not
edits to several independent comparison algorithms.

## Whole-repository owners and required passage

| Layer | Canonical incumbent and required result |
| --- | --- |
| Appliance runtime acquisition | `scripts/appliance/acquire-guest-node-runtime.sh` downloads the official Node.js release, verifies `SHASUMS256.txt.asc` with a content- and fingerprint-pinned Node.js release key, and admits only the archive in `appliance/guest/node-runtime.sha256`. `appliance/guest/provision-offline.sh` rechecks that byte lock before safe extraction under versioned `/opt` storage. Keep Node.js out of the Ubuntu package closure, do not fetch in the guest, and do not loosen the exact-set, signature, fingerprint, or hash checks. |
| Appliance build, qualification, trust, and adoption | `scripts/appliance/build-seat-image.sh`, `appliance/guest/scan-golden.sh`, `scripts/appliance/qualify-seat-image.sh`, `seat-build-record.py`, `publish-seat-image.sh`, and `docs/reference/appliance-seat-launcher.md` own the finalized disk, live qualification, byte record, signature, publication, and explicit update flow. The finalized guest must report an allowed full Node version. Publish and qualify an immutable digest before moving a mutable tag; existing seats then require `lilrae seat stop`, `lilrae seat update`, and restart. |
| Generic Node substrate | `containers/generic-systemd-node22-base/Dockerfile` and the Node-22 selection in `_raes_backend_implementation_profiles.py` / `_raes_backend_implementation_images.py` are one contract: a declaration of Node 22 selects a Node 22 substrate. Use an explicit patched Node 22 image tag plus the corresponding multi-architecture index digest. Do not change the semantic selector to 25/26 or create a second substrate identity for this patch. `tests/test_substrate_posture_real_docker.py` is the existing effective-image readback seam. |
| Web builder | `web/Dockerfile` owns the Node 26 builder; its final Caddy stages, non-root user, static-SPA boundary, and absence of control-plane secrets remain unchanged. `docker-compose.yml`, `scripts/appliance/build-local-images.sh`, and the `trivy-image` matrix build it locally. Verify `node --version` in the `builder` target; do not claim the final Caddy image contains the runtime. |
| Runtime policy and source assertions | `src/aptl/core/_doctor_common.py`, `src/aptl/core/doctor.py`, and `tests/test_doctor.py` own host prerequisite parsing and user guidance. `tests/test_supply_chain_pinning.py` owns repository-wide structural pinning. Extend those incumbents so Docker Node tags, the authenticated appliance archive, CI Node selectors, and active operator prerequisites cannot admit a vulnerable floor or an end-of-life major. Keep Trivy as the vulnerability scanner; do not build a parallel Dockerfile scanner or treat an advisory database result as the version-policy schema. |
| CI tool runtimes | `.github/workflows/checks.yml` and the Phase E workflow currently request Node 22 by major only. Their effective runtime must pass the same policy, and the MCP job remains the canonical place to rebuild and test every `aptl-mcp-common` consumer. Action SHA pinning remains owned by `tests/test_supply_chain_pinning.py`; do not conflate the action's own Node runtime with the `setup-node` toolchain it installs. |
| Active host/workshop guidance | `README.md`, `docs/getting-started/prerequisites.md`, `docs/workshop/walkthrough.md`, and `lilrae doctor` currently admit Node 20. `docs/workshop/hosted-backup-seats.md` installs the exact, end-of-life Node 20.20.2 archive on a reachable operator build path. These must not remain valid instructions after adding an end-of-life-major gate. If the active hosted-seat patch changes, preserve the digest chain in `tools/workshop/stage_hosted_seat_payload.py`, its tests, and the runbook; do not blanket-match deleted lines in the patch as effective packages. Historical evidence fixtures may remain historical only when clearly non-executable and explicitly excluded by the assertion. |
| MCP HTTP request boundary | `mcp/aptl-mcp-common/src/config.ts` owns `LabConfig`, environment substitution, and CA-path resolution; `endpoint-url.ts` rejects caller-controlled cross-origin destinations before auth; `http.ts` owns auth headers, timeouts, response parsing, `HTTPError`, system-trust `fetch()`, custom-CA agents, and the Wazuh-only insecure agent; `api-handlers.ts` owns argument schemas and public error envelopes. Exercise malformed Brotli through a real local response and the system-trust `HTTPClient` path. Preserve origin checks, auth ordering, timeout cleanup, TLS selection, and existing response/error shapes. |
| Security scanning and workflow | ADR-026, `.github/dependabot.yml`, `.github/workflows/checks.yml`, `.trivyignore.yaml`, `.ground-control.yaml`, and `.gc/plan-rules.md` stay authoritative. Docker bases remain digest-pinned and Dependabot-watched; Trivy continues to gate fixable platform-image findings. Local verification stays targeted, while CI rebuilds all common-MCP consumers and owns full/clean lifecycle gates. |
| Container publication and redeployment | `scripts/appliance/publish-images.sh` is the existing immutable candidate publisher for the generic Node substrate, and refuses replacement of an existing tag. The repository has no current workflow that invokes it, and it does not publish `aptl-web-ui`; Release Please intentionally publishes Python artifacts only. Therefore delivery evidence must name the actual publication procedure and resulting immutable digest. For the local-only web UI, affected consumers must rebuild/recreate it from the patched source. Do not report source merge, a Trivy build, or an unchanged local tag as republished/redeployed. |

## Security-layer passage

- **Auth surface:** the malformed-Brotli regression must use the existing
  `HTTPClient` and a same-origin path. `resolveApiRequestUrl()` must still run
  before `buildAuthHeaders()`, and no test server receives a real credential.
  This issue adds no route, permission, authentication mode, or authority.
- **Secret handling:** no new environment variable, config field, token, CA, or
  credential store is needed. Keep auth headers out of process argv, fixtures,
  diagnostics, and captured server output. Existing MCP redaction remains the
  serialization boundary; a decoder failure should not include response bytes
  or request headers.
- **Config and validation shapes:** preserve `LabConfig`, per-query inheritance,
  JSON-schema argument validation, `verify_ssl`, and `ca_cert_path`. Preserve
  the RAES Node-22 declaration and backend selector rather than adding a patch
  version to the scenario schema: patch selection is substrate supply chain
  policy, not authored scenario intent.
- **OS/process exposure:** no port, listener, capability, mount, user, systemd
  policy, Docker socket, or host binding changes. Runtime probes use fixed
  list-form commands such as `node --version`; no secrets or untrusted values
  enter shell text or argv. The web final image stays non-root and Node-free.
- **Errors and observability:** malformed Brotli must reject as an ordinary
  bounded transport failure without crashing the process. Preserve `HTTPError`
  for HTTP status failures and the generic/predefined-query envelopes for
  public projection; do not create a Brotli exception hierarchy or return raw
  compressed bytes. Artifact verification should emit only the component,
  expected policy, observed public version, and immutable artifact identity.
  Publication evidence belongs with existing build/registry records, not lab
  run persistence.
- **Persistence:** there is no new application or database state. Seat image
  selection, cache retention, overlay reset, build records, and Cosign trust
  continue through their existing owners. Never mutate an existing signed disk
  or a running consumer in place.

## Verification guardrails

The source assertion and effective-runtime checks prove different properties
and both are required. Structural coverage must reject the current Node 25
substrate, the vulnerable appliance pin, unsupported/EOL majors, ambiguous
major-only Docker tags, stale CI/tool prerequisites, unauthenticated appliance
archives, Node packages leaking into the Ubuntu closure, and versions below
the applicable floor. It should
also prove that every Node Dockerfile remains digest-pinned and Dependabot
watched through the existing generic tests.

Effective checks must read the full semantic version from the finalized
appliance guest, the built generic Node substrate, and the web `builder` stage.
The generic substrate check belongs beside the real-Docker substrate posture
tests or the existing build/publication gate, not in a second image harness.
The appliance check strengthens `scan-golden.sh`'s current `v22.*` assertion and
is repeated by disposable qualification. A source grep or successful image
build is not effective-version evidence.

The malformed-Brotli regression belongs in `mcp/aptl-mcp-common/tests` and must
use a bounded local server that sends `Content-Encoding: br` with malformed
data. It must prove that the system-trust/global-`fetch` branch was selected,
body decoding rejected before application response handling, and the Node
process stayed alive. Keep the payload minimal and non-exploitative; do not add
weaponized crash bytes to the repository. Because `aptl-mcp-common` is shared,
CI must continue to rebuild every dependent MCP after this test passes.

Rebuild/redeployment evidence must bind source revision, upstream base/package
identity, effective `node --version`, candidate/published digest, and the
consumer action. At minimum this distinguishes the signed seat image, the
published generic Node substrate, the local web builder/final image, and any
already-running or sticky consumer. Cached old images and seats may remain for
rollback, but must be identified as vulnerable and must not be selected for
normal use.

## Extensibility seam, non-goals, and anti-patterns

The extension seam is one supported-major-to-minimum-version policy consumed by
host admission and repository assertions, plus artifact-specific readback at
the existing build boundaries. Adding the next supported Node line changes that
policy and the relevant explicit build identity; it must not require another
validator, schema, transport, or Docker image selector. Dependabot remains the
digest-refresh mechanism, while human-reviewed policy changes decide supported
majors and security floors.

Non-goals are an MCP API redesign, a TLS-policy change, custom Brotli handling,
an application-level decompression limit feature, a new image registry or
release workflow, scenario-schema changes, npm dependency upgrades unrelated
to runtime compatibility, and replacement of the final Caddy stage with Node.
Do not use a mutable Node tag, a platform-specific child digest where the issue
requires a multi-architecture pin, `apt-get upgrade` as proof of the selected
Node release, a major-only/EOL check, scanner suppression, `|| true`, cached
image success, or documentation-only version claims. Do not publish, retag,
redeploy, or alter live consumers during preflight; those actions belong to the
authorized implementation and release workflow.
