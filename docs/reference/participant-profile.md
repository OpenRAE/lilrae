# Participant Profiles

## Canonical full TechVault

Normal local use and seat delivery share the installed TechVault environment
pack. `scripts/appliance/build-seat-image.sh` assembles
`participant-profiles/techvault-full-v1/profile.json` in a clean project tree
from that pack identity, the built MCP artifacts, and the image IDs actually
saved in the guest's Docker archive. This profile path is generated output
under the assembled project, not a source file in the repository. It selects `red` and `blue`, the six
role-admitted MCP servers, and the six registered browser surfaces.

The scenario reference uses `source: env-pack`, the full `PackIdentity`, and
the SDL content digest. Its runtime matrix comes from the admitted pack's
realization, with its exact workloads and networks. It does not add
legacy Compose-only services. Kali access reaches the capture broker at the
live workload address. The private inner sshd remains behind that broker.

The generated asset lock uses `aptl.participant-asset-lock/v2` and binds the
profile documents, MCP artifacts, and saved image config identities. The guest
wheelhouse is locked separately by the hashed runtime requirements. Version 1
locks keep their original allowed kinds. Readiness includes
real MCP operations, authorized browser operations, capture, resource and
offline checks, plus separate `client-transport` checks for Claude Code and
Codex. The release's live VM boot gate must prove Docker and the full lab run
from these staged inputs before the disk is published.

See [host MCP access](host-mcp-access.md) for the delivery contracts.

## Guided Purple fixture

`guided-purple` version 1 is APTL's bounded workshop and classroom profile. It
pins one attack-detect-investigate-purple narrative. It creates no event-specific scenario, Compose profile, or source fork.

The versioned binding is
`participant-profiles/guided-purple-v1/profile.json`. It references, by path
and SHA-256 digest, the narrative, existing `techvault-attacker-target`
scenario, non-secret `aptl.json`, readiness suite, and staged asset lock.

Unknown fields, unsafe paths, digest drift, scenario catalog drift, and a
required narrative operation without a readiness check all fail closed.

## Required guided loop

The [workshop walkthrough](../workshop/walkthrough.md) is the complete learner tutorial for released full-TechVault seats.
The reduced research fixture has a different delivery contract.
Its [versioned narrative](https://github.com/OpenRAE/lilrae/blob/dev/participant-profiles/guided-purple-v1/narrative.json) owns required operations and expected results.
Its matching staged participant guide gives the fixture's learning instructions.
Qualification requires correlated attack, detection, and investigation evidence from one run.

## Derived runtime and participant surfaces

APTL derives the service and network surface from the catalog entry, RAES
planning and dependency closure, the strict profile config, and the Compose
profile index. The current derivation selects `kali`, `victim`, `wazuh`, and
`otel`. This produces ten steady-state services:

- Kali, its capture sidecar, and its loopback SSH proxy.
- The monitored victim.
- Wazuh manager, indexer, and dashboard.
- OpenTelemetry Collector, Tempo, and Grafana.

Both missing and unexpected services fail qualification.

The participant profile composes the workbench contracts introduced by #821:

| Phase | Workbench | MCP servers | Browser bookmarks |
| --- | --- | --- | --- |
| Attack | `red` | `aptl-red` | `aptl-guide`, `kali-desktop` |
| Detect and investigate | `guided-blue` | `aptl-indexer`, `aptl-wazuh` | `aptl-guide`, `soc-wazuh` |

The profile derives these surfaces from the workbench registry. It does not copy them. The full `blue` workbench remains unchanged for research use.
Network IDS, SOAR, threat intelligence, and their bookmarks must be absent
from a guided-purple participant session.

Each enabled MCP qualification starts the real server, examines its exact
workbench tool inventory, invokes a bounded backend operation, and validates
the semantic result. Process health or tool discovery alone is insufficient.

## Participant desktop

The installed `aptl.participant_desktop` provider selects console, credential,
guide and hostname references for the admitted pack. Core resolves those
references against its SDL and the owned running resources. For desktop publication, `LILRAE_PARTICIPANT_DESKTOP_ACCOUNT` must name an existing participant account.
See [publish the desktop](../components/workbench-composition.md#publish-the-participant-desktop) for assembly steps. The guest units set this account for seat delivery.

The account's `~/.config/aptl/desktop/` directory is private (`0700`), and its
files are participant-owned (`0600`). `credentials.html` contains only authored
`secret_fixture` logins. `guide.html` shows escaped guide text without scripts
or remote resources. `consoles.txt` holds the resolved console URLs. The
management handoff publishes `run-ready` after startup succeeds. A new admitted
start, failed start, stop or reset withdraws the previous surface and marker.

The Wazuh and indexer rule tools must have the caller's single XML filename.
They validate its shape and length before authentication. Replacement must have an explicit boolean `params.overwrite`. The generic tools hold no scenario
filename default.

## Staged asset contract

`participant-profiles/guided-purple-v1/asset-lock.json` locks the profile
documents, scenario, Compose model, workbench policy and catalog, released MCP
builds and dependency locks, and every required OCI image identity. Qualification fails if any contained
asset digest drifts.

After staging, the profile must complete without downloads, image pulls, image
builds, or package resolution. The profile asset lock is an input to #823's
signed appliance payload. It is not that outer payload manifest.

## Budget and report contract

The declared minimum fixture is x86-64 with 8 vCPUs, 16 GiB of memory, and
100 GiB of disk. Version 1 ceilings are:

| Dimension | Ceiling |
| --- | ---: |
| Peak profile CPU | 90% |
| Peak profile memory | 12 GiB |
| Staged profile assets | 50 GiB |
| Unique compressed OCI content | 15 GiB |
| Unique expanded OCI content | 35 GiB |
| Peak runtime disk | 30 GiB |
| Cold start | 900 seconds |
| Warm start | 300 seconds |
| Clean inner reset | 600 seconds |

These values are conformance limits, not claimed measurements.

The report binds profile and asset-lock digests to hardware, derived and actual runtime matrices, workbench/MCP/browser surfaces, and readiness results. It also binds denied-egress counters, measurements, the run record, and snapshot.

`lilrae lab qualify-profile --report <path> --public-key <path> --run-id <id>`
verifies the report's Ed25519 attestation against the qualification pipeline's trusted public key. It verifies record and snapshot digests and correlation, derives the expected surface again, evaluates conformance, and persists the redacted result. It exits nonzero for
invalid, unauthenticated, or nonconforming evidence. The protected
qualification pipeline controls the trusted key. A key selected by the report
producer is not a trust anchor.

## Relation to the appliance work

#820, #821, and #822 are peer inputs to #823. This profile owns the bounded
inner workload and clean lab reset. #822 owns zone/egress enforcement. #823
owns the signed outer appliance, kiosk lifecycle, physical-host exposure, and
disposable seat reset, and consumes this profile's lock and qualification
report.

## Full research stack

The packaged full TechVault scenario includes the enterprise, Suricata, MISP,
Shuffle, and other systems. Its generated delivery profile
declares a 32 GiB memory minimum. Its readiness or resource results are not
evidence for `guided-purple`.

## Research fixture ownership

The `guided-purple-v1` profile and its reduced SDL remain APTL-owned research
fixtures. Their strict local catalog is read only by explicit participant-profile
validation, which verifies each referenced file's digest. They require a source
checkout. They are excluded from normal pack selection and default wheel assets.
The full TechVault profile uses the verified acquired-pack identity and is
generated by the seat image builder. Neither fixture presence nor
reduced-profile evidence establishes the full clean-package proof in issue #870.
