# Interface and scenario source checks

This record supports issue #1666.
The section review compared current claims with source revision `28fc8f18c0866066ee450ae6e28ed234e93ca6b4` and the candidate documentation changes.
The rewrite does not change runtime code, schemas, dependency locks, or authority.

## Source revision and dependency evidence

`pyproject.toml` declares Python `>=3.14,<3.15`, RAES `>=11.0.0`, and environment packs `>=7.2.4,<8`.
`uv.lock` resolves RAES 10.7.0 and environment packs 7.2.2.
The source review used TechVault SDL and content from the installed 7.2.2 pack.
Its qualified version/digest pair remains owned by `src/aptl_techvault/pack_identity.py`.

Upstream RAES owns SDL and portable record schemas.
Upstream environment packs owns pack formats and TechVault content.
These pages link those owners. They do not copy their schema documentation.
Source inspection invoked no provider, model, external target, or lab operation.

The integration merge added source revision `5c928b06e2f7637cf6c6fadfd0d36e2ba040b8b2`.
Its retained-enrollment contract was checked against `scenario_capture.py`, `_raes_native_evidence_acquisition.py`, `retained_enrollment.py`, and `lifecycle_cleanup.py`.
The merged reference keeps the first-capture authority, trial scope, prior-ID result, refusal conditions, and volume-reset cleanup.
CI owns `tests/test_retained_enrollment.py` and `tests/test_family_adapter_contract.py` for this contract.

## Section correspondence

Each row identifies source checks for its listed pages and their maintained sections.
Historical bodies keep their original revision-specific meaning.
Named tests are regression evidence selected for CI, not a claim of local execution.
Editorial review separately examines reader purpose, literal wording, sentence limits, consistent names, and preserved obligations.
Writing checks give more evidence.

| Pages and sections | Source owners inspected | Checks and corrected differences |
| --- | --- | --- |
| `reference/cli.md`, `reference/project-configuration.md`: groups, first-lab commands, JSON, cleanup, configuration | `src/aptl/cli/main.py`, `lab.py`, `doctor.py`, `config.py`, `_common.py`. `src/aptl/core/lab.py`, `config.py` | `test_docs_user_journey.py`, `test_cli_lifecycle.py`, `test_cli_config.py`. Keep degraded exit behavior, confirmation, failed-start residue, and private configuration. |
| `reference/web.md`, `reference/web-proxy.md`: delivery, defaults, routes, authentication, proxy | `src/aptl/cli/web.py`. `src/aptl/api/main.py`, `deps.py`, `session.py`, `routers/`. `web/src/lib/bff.ts` | `test_docs_user_journey.py`, `test_api_auth.py`, `test_api_bff.py`. Keep required authentication, host rejection, same-origin mutation checks, and API-only limits. |
| `reference/mcp.md`, `reference/mcp-operations.md`, `components/mcp-integration.md`, `components/mcp-smoke-test-protocol.md` | `mcp/mcp-*/docker-lab-config.json`. `mcp/aptl-mcp-common/src/config.ts`, `tool-output-cap.ts`. `.mcp.json.example`. `src/aptl/core/participant_mcp_policy.json` | `test_docs_user_journey.py`, `test_mcp_service_selection.py`. Distinguish built artifacts, selected servers, advertised tools, required-service failures, and omitted services. |
| `reference/host-mcp-access.md`, `reference/host-mcp-operations.md`, `components/participant-workbench.md`, `components/workbench-composition.md` | `src/aptl/core/mcp_policy.py`. `src/aptl/workbench/dispatch.py`, `guest_binding.py`, `relay.py`, `browser_gateway.py` | `test_mcp_access.py`, `test_mcp_transport_processes.py`, `test_host_mcp_boundary.py`. Correct eight-server wording and scope host enrollment to the legacy delivery route. |
| `reference/appliance-seat-launcher.md`, `reference/appliance-seat-operations.md`, `reference/seat-containment.md` | `src/aptl/cli/seat.py`. `src/aptl/appliance/`. `scripts/appliance/build-seat-image.sh`, `qualify-seat-image.sh`, `qualify-seat-privileges.sh` | `test_appliance_seat_cli.py`. Keep acquisition consent, signature checks, sticky image selection, destructive reset, privilege modes, and outer-host qualification limits. |
| `components/appliance-boundary.md`, `components/appliance-qualification.md` | `src/aptl/appliance/policy.py`. `src/aptl/core/appliance_boundary.py`. Boundary implementation and qualification sources | Existing boundary qualification contracts. Separate V1 topology/egress design from current V3 guest-host protection. Keep V2/V3 distinction and observation failures. |
| `components/node-realization.md`, `source-image-catalog.md`, `reference/source-image-maintenance.md` | `src/aptl/backends/raes_realization.py`, `raes_literal_content_realization.py`, `_lilrae_source_image_catalog.py`. `src/aptl/core/deployment/` | `test_lilrae_source_image_catalog.py`. Keep exact source selection, ambiguity, unsupported Windows sources, readback, and distinct registry/configuration digests. |
| `components/kali-redteam.md`, `components/kali-operations.md`, `components/red-side-capture-boundary.md`, `red-team-taxonomy.md` | `containers/generic-systemd-node22-base/Dockerfile`. `containers/kali-capture/`. `mcp/mcp-red/src/classifier.ts`, `extractor.ts`, `logger.ts`, `capture.ts`. `mcp/aptl-mcp-common/src/captures.ts` | MCP classifier, extraction, capture, and redaction checks. Keep prefixes, bounded harvest failures, and the separation of red self-reports from defensive SIEM data. |
| `components/default-defensive-posture.md`, `components/defensive-posture-operations.md`, `components/wazuh-active-response.md`, `components/wazuh-response-operations.md` | `config/wazuh_cluster/wazuh_manager.conf`, `etc/lists/active-response-whitelist`. `containers/_wazuh-agent/aptl-firewall-drop.sh`. `src/aptl/services/misp_suricata_sync/` | `test_wazuh_active_response.py`, `test_misp_suricata_sync.py`. Correct stale agent counts and template-restart assumptions. Keep exact whitelist, disabled blocks, OR semantics, and timeout cleanup. |
| `components/wazuh-siem.md`, `components/wazuh-operations.md`, `components/victim-containers.md`, `components/victim-operations.md`, `containers/victim-template-guide.md` | Installed TechVault SDL. `containers/generic-systemd-wazuh-agent-base/Dockerfile`. `config/wazuh_cluster/`. `src/aptl/core/credentials.py` | Existing static/live scenario contracts. Remove unsupported current Falco and host-port claims. Replace removed Dockerfile instructions with pack authoring and runtime discovery. |
| `reference/techvault-scenario-overview.md`, `src/aptl_techvault/README.md`, `components/techvault-adapter-boundary.md` | Installed TechVault 7.2.2 SDL. `src/aptl_techvault/verification.py`, `pack_identity.py`, `account_environment.py`, `database.py`, `runtime_readback.py`, `capture_registrations.py` | `test_techvault_static_gate.py`, `test_techvault_live_gate.py`. Remove retired mail/reverse nodes and OTel startup claims. Distinguish verifier reachability from startup-generated evidence activity. |
| `reference/participant-profile.md` | `participant-profiles/guided-purple-v1/`. `src/aptl/appliance/input_profile.py`. `src/aptl/core/participant_mcp_policy.json`. `src/aptl/validation/participant_qualification.py` | Existing profile/qualification contracts. Correct the full profile's role-admitted MCP count. Keep separate reduced-fixture budgets and unmeasured limits. |
| `reference/participant-request-manifests.md`, `reference/participant-request-operations.md` | `src/aptl/core/participant_requests/`. `src/aptl/workbench/trial_participants.py`, `opencode_observation.py`, `opencode_history.py`. `src/aptl/core/trial_participants.py` | `test_participant_request_manifests.py` and installed dispatch checks. Keep scope, digest, byte, unsupported-control, missing-usage, and unavailable-observation failures. |
| `reference/opencode-participants.md`, `reference/opencode-operations.md` | `src/aptl/core/opencode.py`. `src/aptl/workbench/opencode_options.py`, `opencode_bootstrap.py`, `opencode_configuration.py`. `tools/install-opencode.sh` | Existing OpenCode installed-transport tests. Keep build/digest and target facts in Reference. Align the current RAES minimum with package metadata. |
| `reference/family-adapters.md`, `reference/family-adapter-operations.md`, `reference/configuration-migration.md`, `reference/migrate-configuration.md` | `src/aptl/backends/scenario_family.py`, `scenario_startup.py`. `src/aptl/core/config.py`. `src/aptl/cli/config.py`. `pyproject.toml`, `uv.lock` | Existing family adapter and configuration migration checks. Label the older structural tuple as historical. Keep atomic qualification and migration refusal cases. |
| `reference/experiment-runs.md`, `reference/run-operations.md`: cleanup, composition, recovery, and export | `src/aptl/core/runstore.py`, `runstore_internals.py`, `snapshot.py`, `snapshot_models.py`, `archival/`. `src/aptl/backends/trial_recovery.py` | Existing run-store, archival, and recovery checks. Keep working runs, sealed snapshots, producer status, cessation, and cleanup as distinct facts. |
| `reference/evidence-bundle-export.md`, `reference/evidence-bundle-operations.md` | `src/aptl/cli/runs.py`. `src/aptl/core/evidence_bundle/build.py`, `closure.py`, `verify.py`, `archive.py`, `envelope.py`. `src/aptl/core/exporter.py` | `test_evidence_bundle_cli.py` and bundle verifier checks. Keep unsafe-path refusal, permissions, loss disclosures, unsealed export, and rejection of unauthenticated verified-seal claims. |
| `sdl/index.md`, `sdl/techvault-curated-variants.md`, `sdl/curated-variant-reference.md`, `sdl/runtime-architecture.md` | `src/aptl/core/scenario_catalog.py`, `scenario_bundle.py`. `src/aptl/backends/raes.py`, `raes_runtime.py`, `raes_dependency_closure.py`. `scenarios/catalog.json` | `test_scenario_catalog.py`, `test_techvault_curated_variants.py`. Keep project containment, acquired-pack failures, content-driven selection, no-start checks, and dependency failures. |
| `raes/techvault-static-validation-gate.md`, `raes/scenario-validation.md`, `raes/techvault-live-validation-gate.md`, `raes/live-validation.md` | `src/aptl/validation/techvault_gate.py`, `_gate_checks.py`, `techvault_live_gate.py`, `_live_gate_models.py`. `src/aptl_techvault/verification.py`. `.github/workflows/checks.yml` | Static/live gate tests. Correct advisory-to-blocking CI status, native `VerificationReport`, current verifier behavior, and post-semantic containment observation. |
| `raes/declared-cleanup.md`, `raes/install-cleanup.md` | `src/aptl/backends/cleanup.py`. `src/aptl/core/deployment/declared_cleanup.py` | Existing declared-cleanup contracts. Keep exact attempt authority, unsupported actions, publication failures, sealed-store refusal, and repeated absence checks. |
| `raes/paper-scenario-realization.md`, `sdl/paper-walkthrough.md` | `scenarios/paper-agent-loop.sdl.yaml`. `src/aptl/backends/raes_participant_runtime.py`. ADR-046 | Existing paper participant and realization contracts. Use `lilrae` in maintained examples. Distinguish capture intent, actual evidence, participant disclosure, and scoring limits. |
| `containers/windows-victim/README.md`, `reference/windows-endpoint.md` | Every selected `.ps1` installer in `containers/windows-victim/` | Static script review only. Remove the implication that macvlan creation connects the VM automatically. Keep estimates and disclose mutable downloads and unqualified integration. |
| `mcp/mcp-reverse/README.md` | `mcp/mcp-reverse/docker-lab-config.json`. `.mcp.json.example` | Existing MCP configuration checks. Keep disabled example target and explicit target requirements. |
| Historical SDL pages, RAES preflights, company/OSINT plans, archived scenarios, and copied `.txt` records | Original bytes at `28fc8f18`. Each file's Git history and embedded evidence dates | The source records keep original bodies and decisions. Added notices distinguish historical claims from current behavior. This change regenerates no live result. |

## Verification boundaries

Vale and the selected STE rules check explicit maintained paths.
For source records, checks cover the new status notice rather than immutable historical prose.
Rewritten maintained pages enter `.ste-required.txt`.
Diataxis purpose, STE sentence structure, and technical-term use receive separate editorial review.
A clean linter result does not prove full language conformance or source correctness.

CI owns strict MkDocs, full prose checks, and behavior tests.
Workstation checks remain source inspection, explicit-path writing checks, Git operations, and staged hygiene.
The PR records actual CI outcomes and remaining qualification limits.
This change adds no documentation tool, classifier, skill, analyzer service, or hosting destination.

## Editorial review

The section correspondence table also defines the scope of the completed editorial review.
The review covers each maintained section in those page groups. It also covers linked procedures and learner exercises.
It excludes exact historical bodies, literal commands, schema identifiers, and generated output.
New notices and record links remain in scope.

The review used the [official ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf) for word meanings and parts of speech.
The specification and dictionary remain outside the repository.
The review examined vocabulary separately from sentence structure and technical accuracy.

| Review area | Applied decision and correction |
| --- | --- |
| General verbs | Use `get`, `keep`, and `examine` instead of general uses of `obtain`, `retain`, and `inspect`. |
| Word meaning and part of speech | Use `check` as a noun. Use `examine` or `make sure` for an instruction. |
| Verification instructions | State digest calculation and comparison explicitly. Keep the separate archive and executable comparisons. |
| Grammar | Use simple tenses, explicit subjects, and active verbs where the source identifies the actor. Replace incomplete command introductions and nonfinite action clauses. |
| Descriptive passive voice | Keep a passive description only where the source does not identify an actor. Do not invent one. |
| Conditions and obligations | Keep authorization, refusal, cleanup, and evidence conditions. Put a procedural condition before its affected action. |
| Sentence and paragraph structure | Keep one action per instruction and one topic per paragraph. Split semicolons and long paragraphs. |
| Names and literal values | Keep one name for each concept. Keep exact program names, keys, versions, digests, quantities, and limits. |
| Reader purpose | Keep lookup contracts in Reference, task sequences in How-to guides, reasons in Explanation, and exercises in Tutorials. |
| Historical records | Keep original evidence and decisions. Use dated notices to distinguish them from current contracts. |

### Technical terms

These terms describe specific software concepts in the inspected owners.
They are not alternative general words.
Their names and meanings remain consistent across the maintained sections.

| Terms | Meaning and source boundary |
| --- | --- |
| run, trial, attempt, placement, ledger | Distinct experiment identities and durable execution state in RAES and `aptl.core.runstore`. An attempt is not a general retry. |
| admission, binding, grant, scope, authority | Different permissions and identity relationships in RAES admission and `aptl.workbench`. None means general host access. |
| capture, provenance, seal, snapshot, commitment | Distinct evidence objects in `aptl.core`. A seal is not a successful outcome or an authenticated external attestation. |
| parser, compiler, schema, manifest, realization | Different source and deployment interfaces. Their owning RAES contracts remain authoritative. |
| MCP, dispatcher, relay, broker, sidecar | Different transport and process components. The terms do not imply equivalent permissions or custody. |
| digest, hash, signature, redaction | Different integrity, authentication, and privacy concepts. A digest alone does not authenticate its source. |
| qualification, readiness, conformance | Different evidence decisions. Their meanings remain limited to the stated version, checks, and runtime boundary. |
| parse, compile, serialize, hash, redact | Technical verbs for the corresponding software operations, not general alternatives for read, write, or hide. |
| admit, bind, seal, provision, dispatch | Technical verbs for the named contract operations. They keep the original authority and lifecycle limits. |

The broader existing `ste-cli` advisory rules also supported this review on explicit paths with the software preset.
Advisories received contextual review rather than automatic replacement.
For example, `attempt` is a technical noun for a RAES execution identity.
A generic suggestion to replace it with `try` would change that contract.
State descriptions and preserved compatibility headings also need contextual judgment.
Neither this advisory run nor the configured gate replaces the editorial review.

The participant profile links directly to the complete workshop Tutorial for current seats.
The separate research fixture links its versioned narrative and uses its matching staged guide.
This change keeps no incomplete duplicate lesson.

Editorial repairs also correct a missing noun in the Kali node description and incomplete command introductions.
They replace incorrect uses of `startup` as a verb with explicit start instructions.
These corrections keep the commands, conditions, and authority unchanged.

Technical nouns such as `working directory`, `working run`, `port mapping`, and `log processing` keep their software meanings.
General process descriptions use explicit subjects and simple verbs.

## Section language assessment

The following assessment covers the maintained introductions and sections.
The source-owner table above supplies the technical correspondence for each page.
These rows identify contextual language evidence, rather than automated rule scores.
Literal identifiers, command output, historical bodies, and compatibility heading names remain exact.
Link-only sections contain a cross-reference rather than another procedure.

### CLI and configuration

| Page and section | Contextual assessment |
| --- | --- |
| `cli.md`: introduction | The command and alias have explicit subjects. The removal version stays exact. |
| Command Groups | Each row names a command and its behavior. Technical command names remain literal. |
| First-Lab Commands | Result verbs describe observed outcomes. Cleanup confirmation precedes the destructive result. |
| Exit Status And JSON Output | Conditional sentences distinguish refusal, failure, degraded startup, and success. Numeric statuses stay exact. |
| Destructive And Emergency Operations | Container removal and volume retention remain different facts. Recovery uses complete start and stop clauses. |
| Configuration And Secrets | The section links the procedure. Secret-bearing filenames remain technical names. |
| `project-configuration.md`: introduction | The existing project is the prerequisite. The guide has one validation task. |
| Configuration And Secrets | Each numbered instruction names an action and object. Private-file obligations remain explicit. |
| `configuration-migration.md`: introduction | The command validates, locks, saves, and replaces. These simple verbs identify its actions. |
| Earlier section links | The exact old heading remains an anchor. Its target is the current procedure. |
| Scenario and provider selection | Source and identity remain distinct inputs. The text does not infer a default scenario. |
| `migrate-configuration.md`: introduction | The reference owns conversion rules. The guide addresses an existing project. |
| Convert an existing project | The omitted-identity condition precedes its command. Backup and ambiguity refusals remain explicit. |

### Web and MCP interfaces

| Page and section | Contextual assessment |
| --- | --- |
| `web.md`: introduction | Operator and target applications have distinct names. Runtime discovery has an explicit command subject. |
| Supported Delivery | Direct and split delivery remain distinct. The private login value is explicitly secret-bearing. |
| Serve Defaults | Values remain exact data. Sentences distinguish a default from an available deployment. |
| Operator Surfaces | Route names remain literal. The surrounding prose identifies browser capabilities and storage limits. |
| Supported API Surface | Authentication and same-origin obligations remain separate. The login-exchange exception precedes those obligations. |
| Safe Exposure | The section links the proxy procedure. Loopback remains the stated default. |
| Proxy configuration | Each setting retains one meaning. Hostnames and ports remain distinct technical concepts. |
| Proxy failures | HTTP codes and literal messages stay exact. The text does not equate CORS with authorization. |
| `web-proxy.md`: introduction | The approved project and network are prerequisites. The reference owns lookup contracts. |
| Start the local interface | Instructions name installation, project selection, startup, and browser actions. Private-URL handling remains explicit. |
| Safe Exposure | The remote-access condition precedes the steps. Each step has one proxy or verification action. |
| Configure split delivery | User and socket-group identities remain distinct. Permission diagnosis precedes any permission change. |
| `mcp.md`: introduction | The control plane builds artifacts and updates private configuration. These are separate actions. |
| Server Availability | Artifacts, client entries, and advertised tools remain different nouns. Exact prefixes and selection values stay literal. |
| Tool Names And Behavior | Examples retain their prefixes. The connected server remains the authority for its schema. |
| Setup And Verification | The section contains a direct procedure link. It introduces no second startup sequence. |
| Security Boundary | The prose identifies private data and bounded errors. It keeps authentication and transport obligations. |
| Scenario service selection | Required, selected, and omitted services retain distinct meanings. Failure conditions precede their outcomes. |
| `mcp-operations.md`: introduction | Authorized scenario selection and the isolated VM are prerequisites. |
| Setup And Verification | Commands remain literal. Subsequent instructions identify client discovery and a read-only first operation. |
| Build and verify artifacts | The approved runner precedes the build. Targeted and full checks remain distinct. |
| Narrow MCP selection | The reference link precedes configuration. The JSON example preserves exact field names. |
| Protect generated data | Each instruction names a protection action. Credential and certificate obligations remain unchanged. |

### Host access and workbench delivery

| Page and section | Contextual assessment |
| --- | --- |
| `host-mcp-access.md`: introduction | The legacy delivery qualifier precedes transport facts. Host and guest credentials retain distinct owners. |
| Guest enrollment | Field names stay literal. The supervisor and dispatcher have explicit, different responsibilities. |
| Host configuration | The section links the guide. It does not duplicate command steps. |
| Discovery, authority and lifecycle | Discovery and authority remain separate nouns. Age limits, expiry, revocation, and reset conditions stay exact. |
| Software integration checks | The link identifies the approved procedure. It does not claim a new test result. |
| Appliance-seat integration | Historical scope remains explicit. Stop, reset, and stale-access outcomes retain simple present verbs. |
| Software integration evidence | Past-tense verbs describe recorded observations. The limits exclude deployed-lab qualification. |
| Client publication contract | Native client files and authentication remain distinct. Failure clauses do not authorize overwrite. |
| `host-mcp-operations.md`: introduction | The CI or approved-VM condition precedes every procedure. |
| Guest enrollment | Each step identifies its action and object. The dedicated account remains separate from general login. |
| Host configuration | Fingerprint comparison has an independent source. The command introduction now has an explicit action and object. |
| Software integration checks | The build condition precedes the test command. Result inspection preserves the qualification limits. |

### Appliance operation and containment

| Page and section | Contextual assessment |
| --- | --- |
| `appliance-seat-launcher.md`: introduction | VM, guest, host, and user remain distinct nouns. V2 and V3 claims retain their qualifiers. |
| Security boundary | The section links the Explanation. It makes no additional containment claim. |
| Prerequisites | The section links the operating guide. The later host-prerequisite section owns the facts. |
| Choose desktop privileges and start a seat | The old heading points to the guide. No parallel privilege procedure remains. |
| Updates are never forced | The heading remains a stable target. Its body links the update procedure. |
| Reserving operator-selected ports | The section links staging steps. Mapping facts remain in their reference section. |
| Reset and recovery | The section links the guide. Reset and recovery retain separate meanings. |
| Participant desktop | Pack, launcher, and publisher actions have named subjects. Paths and POSIX modes stay literal. |
| Directory layout | The literal tree remains data. Its labels distinguish retained images from disposable overlays. |
| Building the image | The section points to the build procedure. It does not duplicate publication instructions. |
| Diagnostics | Failures emit bounded codes. The private-output exclusion remains an explicit sentence. |
| Related documents | Link labels identify their decisions. The section adds no runtime facts. |
| Host prerequisites | The host and starting account have explicit requirements. No actor is inferred from a passive installation statement. |
| Desktop privilege modes | Each mode retains its exact privilege result. Password absence and passwordless sudo remain different facts. |
| Image selection and verification | Finite conditional clauses replace general participial subjects. Acquisition, verification, replacement, and rollback remain distinct. |
| Port mappings and capacity | Fields and quantities stay exact. The allocator is the subject of reservation arithmetic. |
| Desktop endpoints | The private namespace qualifies browser access. Scenario authentication remains separate from seat access. |
| Image build and publication contracts | Build inputs and publication inputs remain distinct. Signature, qualification, and registry access retain separate meanings. |
| `appliance-seat-operations.md`: introduction | Approved host resources precede operation. The reference owns modes and failure contracts. |
| Prerequisites | Each instruction names a host-preparation action. The account that starts the seat owns its private directory. |
| Choose desktop privileges and start a seat | The privilege condition precedes mode selection. Consent and private password entry remain explicit. |
| Rescue a stopped guest | Stop precedes rescue. The exit instruction now names a complete action before another start. |
| Select another publisher | Independent key acquisition precedes selection. Immutable references and verification obligations remain exact. |
| Participant desktop | Readiness precedes browser access. Provider and application logins remain distinct. |
| Updates are never forced | Stop, update, and start remain ordered actions. Destructive reset and interrupted-reset recovery remain explicit. |
| Reserving operator-selected ports | The contract link precedes mapping input. Port selection does not imply ordinary host-browser access. |
| Reset and recovery | Separate commands preserve their separate effects. Reconciliation conditions precede the required recovery. |
| Building the image | Source selection precedes build. Publication approval and qualification precede channel promotion. |
| `seat-containment.md`: introduction | The page explains reasons and limits. It links facts and procedures separately. |
| Security boundary | QEMU and its Unix account have explicit subjects. Shared-account access is not described as isolation. |
| Limits of the outer boundary | Risk reduction and proof remain distinct. Recommendations retain their original strength. |
| Limits inside the guest | Range, guest-host protection, and physical host remain different scopes. Reset does not imply restored host trust. |
| Qualification evidence | Recorded observations keep their exact scope. An inner observation cannot qualify the outer host. |

### Evidence and run records

| Page and section | Contextual assessment |
| --- | --- |
| `evidence-bundle-export.md`: introduction | The exporter has an explicit subject. Packaging does not imply analysis or publication permission. |
| Build a bundle | The section links the procedure. Archive facts remain in Reference. |
| Verify a bundle | The section links verifier steps. Integrity and authentication remain different concepts. |
| Bundle layout | Paths remain literal data. The inventory description states what each row records. |
| The `aptl-evidence-bundle/v1` envelope | The inventory references RAES artifacts. A complete sentence excludes copied source fields. |
| Determinism | The text states reproducibility conditions. Canonical JSON and USTAR retain their technical meanings. |
| Projections | Each projection has a stated source and loss boundary. Unsupported formats remain explicit failures. |
| Security posture | The exporter reads and rejects. These verbs identify containment actions without a general participial clause. |
| Run store permissions | The section links permission steps. Permission contracts remain below. |
| Seal state and partial runs | Seal labels stay literal. Completeness, success, integrity, and authentication remain distinct. |
| Export options | Exact flags and defaults remain data. Self-verification has an explicit default statement. |
| Output and source permissions | Exporter and store actions have named subjects. Repeated-export and existing-root behavior remain separate. |
| Verification contract | The verifier streams and recomputes. Its exclusions do not imply an external attestation. |
| `evidence-bundle-operations.md`: introduction | Existing local evidence is the prerequisite. Export grants no publication authority. |
| Build a bundle | Private output selection precedes export. Each instruction has an action and object. |
| Verify a bundle | The command has a complete introduction. Report limitations remain part of the result. |
| Run store permissions | Path inspection precedes permission changes. The selected-store qualifier remains explicit. |
| `experiment-runs.md`: introduction | Adapter inputs have explicit receiver sentences. Recovery, cessation, capture, and cleanup keep separate identities. |
| Clean State Between Runs | Cleanup has an explicit project scope. Confirmation and preserved state remain distinct facts. |
| Run Directory Structure | Literal paths remain data. Each writer and publication boundary has a stated role. |
| Run Provenance (`provenance/`) | Complete clauses describe repeated publication. Provisional evidence cannot silently become a canonical record. |
| Sealed Run Records (`manifest.json`, `seal.json`) | Producer status, archive identity, and the seal remain distinct. Writers explicitly refuse another write after sealing. |
| Range Snapshot | The field-list introduction now names its subject. Snapshot storage and privacy conditions remain explicit. |
| CLI Commands | Literal commands remain exact examples. Operating and recovery steps reside in the guide. |
| Key Source Files | Source-path labels remain data. Their descriptions name responsibilities without hidden action clauses. |
| `run-operations.md`: introduction | Approved isolation precedes lifecycle work. The reference owns record contracts. |
| Clean State Between Runs | Project selection and evidence retention precede destruction. Failure cannot establish clean state. |
| Compose trial services | Each step names an admitted input or installed service. Original identities remain required. |
| Recover an assigned trial | Original stores and identities precede recovery. Completion claims follow evidence inspection. |
| Inspect and export | Commands identify working records and archive paths separately. Export does not establish a seal. |
| Recover a failed start | Selection precedes cleanup. Volume destruction remains an explicit choice. |

### Family and participant contracts

| Page and section | Contextual assessment |
| --- | --- |
| `family-adapters.md`: introduction | Adapter installation and pack acquisition remain distinct facts. The page describes contracts. |
| Discovery and versions | Each version has one role. Qualification is not inferred from package compatibility. |
| Sealed trial handoff | Core and caller have explicit responsibilities. Snapshot bytes and identity commitments remain distinct. |
| Supported imports and callbacks | Literal public imports stay exact. Bounded callback authority remains explicit. |
| Restart and auxiliary interfaces | An installation change cannot alter the pinned finalizer. Retry and reset retain their conditions. |
| Supported release tuple | Historical qualification precedes the version table. Structural evidence does not imply execution evidence. |
| Compatibility evidence | Tests have stated purposes and negative cases. No new local execution result is claimed. |
| Optional host requirements and supporting imports | Declarations and kernel probes have distinct owners. No absent demand produces a probe. |
| `family-adapter-operations.md`: introduction | Trusted assembly and approved installation precede the task. |
| Register the adapter | Each instruction declares or registers a specific input. Mixed-provider refusal remains explicit. |
| Compile and admit a trial | Plan sealing follows parameter resolution. Snapshot conditions precede the affected step. |
| Start and finalize | Native readback precedes fact acceptance. Cleanup precedes the next trial. |
| `opencode-participants.md`: introduction | Participant implementation and browser agent remain different concepts. |
| Install | The link preserves the old heading. It points to the installation procedure. |
| Configure and invoke | The link identifies trusted assembly steps. It adds no alternate invocation contract. |
| Evidence and limits | Records contain bounded metadata. Simple clauses distinguish commitments from raw bytes and actual served identity. |
| Supported build and route | Build identities remain exact. Requested routing and served identity remain separate. |
| Configuration targets | Target names, domains, and integer bounds stay literal. No unsupported control becomes implicit. |
| Factory contract | Each required input has a named owner. Credential references are not credential values. |
| Installation verification | The helper and executor have explicit verification actions. Trials do not acquire or update executables. |
| `opencode-operations.md`: introduction | Isolation precedes installation and invocation. The reference owns build contracts. |
| Install | Start has a complete verb clause. Archive and executable digest comparisons remain separate instructions. |
| Configure and invoke | Credential handling precedes participant preparation. Each participant retains its independent admitted binding. |
| `participant-request-manifests.md`: introduction | The consumer gives reviewed inputs. Publication makes no provider connection. |
| Public interfaces | Policy values remain literal. A complete conditional clause describes changed commitments. |
| Configuration targets | Each target keeps its type and scope. Artifact names do not authorize executable discovery. |
| Request support and limitations | Unknown usage remains unknown. Model controls and context commitments retain their distinct limits. |
| Content verification | The owner examines exact bytes and identities. Different bytes cannot change the selected commitment. |
| Compatibility evidence | Installed imports and transport tests have stated scopes. No fake-provider result becomes a model qualification. |
| Actual provider observation | The plugin observes and records. Complete failure sentences exclude silent truncation and fabricated usage. |
| `participant-request-operations.md`: introduction | Trusted roles and assets precede assembly. The procedure grants no provider authority. |
| Publish the trusted owner | Each step identifies a constructor or compiler input. Authored names do not select validators. |
| Verify content and dispatch | Content verification precedes dispatch. Cancellation and evidence inputs precede credential acquisition. |
| `participant-profile.md`: Canonical full TechVault | Generated profile paths remain distinct from source inputs. Full-pack evidence retains its own scope. |
| Guided Purple fixture | The profile, narrative, scenario, and lock retain exact roles. Failure conditions stay explicit. |
| Required guided loop | The complete workshop Tutorial is linked directly. The separate research narrative remains separately identified. |
| Derived runtime and participant surfaces | Service and role lists remain data. The registry derives surfaces rather than a copied preset. |
| Participant desktop | Provider, core, account, and publisher responsibilities remain distinct. Private modes and content limits stay exact. |
| Staged asset contract | Asset kinds and digests remain exact. Staging excludes later acquisition without implying outer-payload identity. |
| Budget and report contract | Ceilings remain limits rather than measurements. Attestation trust is independent of the producer. |
| Relation to the appliance work | Inner workload and outer seat responsibilities retain their historical issue boundaries. |
| Full research stack | Full-stack resource claims do not qualify the reduced fixture. |
| Research fixture ownership | Checkout-only inputs remain separate from ordinary package delivery. |

### Scenario and source-image interfaces

| Page and section | Contextual assessment |
| --- | --- |
| `techvault-scenario-overview.md`: introduction | Fictional content and admitted runtime state remain distinct. The page has one reference purpose. |
| Where the scenario is defined | Each package and catalog has an explicit owner. Version and digest remain different facts. |
| Fictional company | Names remain scenario data. Historical proposals do not establish real external assets. |
| Topology | The backend derives topology from admitted content. A scenario name is not a preset selector. |
| Enterprise targets | Node names remain literal. Retired nodes are explicitly excluded. |
| Defensive and SOC stack | Agent count and placement stay exact. Detection, response, and startup traffic remain distinct. |
| Host-published ports | Observed ports and plans retain separate meanings. Declared listeners do not establish host publication. |
| Planted vulnerabilities | The admitted version qualifies each path. A declaration does not prove exploitation or detection. |
| Planted secrets | Fixture credentials remain separate from real secrets. Scope limits do not grant authority by omission. |
| Curated startup variants | Reduced fixtures retain their research scope. Their evidence does not qualify full delivery. |
| `source-image-catalog.md`: introduction | Source names and versions select exact records. Unknown selectors never become inferred registry tags. |
| Authority and compatibility | Eligibility and ambiguity retain exact conditions. Selection does not grant runtime permissions. |
| Provenance and running-image evidence | Past-tense and possessive repairs restore complete sentences. Registry and configuration digests remain distinct. |
| Release coverage and selected distributions | Historical version and approval dates qualify the counts. Community and vendor provenance remain distinct. |
| `source-image-maintenance.md`: introduction | Existing owners and approved registries precede maintenance. |
| Update the existing catalog | Alias conditions precede pin reuse. Contract checks remain bounded to the affected behavior. |
| `windows-endpoint.md`: introduction | The separately managed VM remains outside ordinary startup. |
| Resources and installation limits | Historical estimates remain estimates. Installer completion does not imply compatibility. |
| Script selection | Script names and versions remain exact data. Tool dependencies retain their stated order. |
| Network and MCP limits | Connectivity and tool availability require actual runtime evidence. Historical addresses do not become provisioned endpoints. |
| Source record | The original revision and review date remain explicit. |

### Component references

| Page and section | Contextual assessment |
| --- | --- |
| `appliance-boundary.md`: introduction | Signed policy and admitted range topology remain independent authorities. V1, V2, and V3 retain different meanings. |
| Protected Seat Materialization | Compiler, helper, and gate have named actions. Workload inspection does not become Docker-authority admission. |
| Historical V1 Materialization | The stable heading links the exact historical record. It makes no current V3 claim. |
| Historical V1 Participant Workbench | The section identifies historical design through its record link. |
| Historical V1 Controlled Egress | The section links historical egress design. It does not claim current egress enforcement. |
| Qualification And Start Gate | Evidence identities and failure conditions stay explicit. Ordinary workloads and authority holders retain separate device contracts. |
| Host MCP policy extension | Mapping identity, observation age, and grant scope stay exact. Equal ports do not establish authority. |
| `default-defensive-posture.md`: introduction | Weakness, detection, and response are separate nouns. Runtime observations qualify baseline claims. |
| How to read this doc | Definition rows have complete clauses. Literal posture labels remain exact. |
| Suricata IDS | Detection and prevention remain different functions. Empty seeds do not establish empty runtime state. |
| Wazuh detection rules | Manager and pack actions have explicit subjects. Rule replacement retains its overwrite condition. |
| Wazuh active-response | Disabled blocks, rule IDs, and timeouts stay exact. Whitelist behavior remains command-specific. |
| MISP IOCs | Startup evidence and participant promotion remain distinct. Runtime credentials retain their source boundary. |
| Shuffle SOAR | The declaration does not prove delivery. Pack and backend retain their runtime responsibilities. |
| Identity controls (Active Directory) | SDL, backend, and parity checks have named roles. Fixture and operator credentials remain distinct. |
| Network segmentation | Connectivity is not enforcement. Multiple attachments retain their reachability implications. |
| Cross-references | The labels identify current reference and operating routes. |
| How to extend | The section links the guide. It does not duplicate maintenance steps. |
| Appendix and Per-run mode-gated posture (SCN-001) | The proposed mode remains historical. It does not become a supported schema field. |
| Orchestrator-side continuity carve-out (RTE-001 / #252) | Cleanup has an explicit limited scope. It does not imply general rollback. |
| `kali-redteam.md`: introduction | The corrected sentence explicitly names the pack's Kali node. Red self-reports remain outside defensive SIEM data. |
| Realized Node | Substrate, tools, user, SSH, and capabilities remain distinct facts. The capture image is not the node image. |
| Network Access | Addresses remain data. Peer reachability does not imply defensive monitoring or external egress. |
| Host Access | Relay, workload, and capture broker retain distinct roles. Capture requirements precede access limitations. |
| Session Capture | The broker owns terminal records. The workload does not acquire the capture volume. |
| MCP Integration | Server, broker, and harvester have explicit actions. Failure records do not become complete captures. |
| Experimental record redaction toggle | The parser has explicit trim and case behavior. Data-policy authority remains separate from the toggle. |
| Why no SIEM integration | The section links the Explanation. It preserves the historical heading. |
| `mcp-integration.md`: introduction | The complete introduction states the component boundary. Operating steps remain in the guide. |
| Runtime Flow | The control plane realizes before configuration. An artifact does not establish its target. |
| Server Families | Shared SSH and API responsibilities remain separate. Prefixes identify exact tool names. |
| Configuration Boundary | File ownership and output bounds remain explicit. Truncation does not remove terminal outcome metadata. |
| Development | The shared dependency affects every consumer. The section links the build procedure. |
| `mcp-smoke-test-protocol.md`: whole page | Complete sentences identify the canonical QA record. Automated smoke does not replace target-backed observations. |
| `node-realization.md`: introduction | Both routes retain Docker and image requirements. Their source-of-state distinction stays explicit. |
| Base-container-materialized node | The backend starts a base and applies declared state. Readback remains a separate action. |
| Image-backed node | The admitted image owns software. Compose startup and content placement retain their roles. |
| Compose startup is a separate fact | Direct Docker realization and Compose activation remain different facts. |
| Historical term | The old term is explicitly historical. Identifier changes remain literal data. |
| `participant-workbench.md`: introduction | Participant and operator applications remain distinct. Browser access does not grant management authority. |
| Assembly and authorization | Factory, verifier, gateway, and launcher have different named responsibilities. Caller input cannot select privileged destinations. |
| MCP authority and capture | Inventory verification precedes initialization. Unproved remote cleanup blocks reuse. |
| `reverse-engineering-container.md`: introduction | Retirement and the optional MCP target remain separate facts. The historical description is not current qualification. |
| Container Configuration | The operator owns the target. The removed Dockerfile does not become an install route. |
| Network Access | No default port is inferred. The configured endpoint governs access. |
| MCP Integration | Prefix and SSH owner remain exact. The section links target configuration. |
| SIEM Integration | An MCP connection does not establish Wazuh enrollment. Target monitoring remains separately verified. |
| `victim-containers.md`: introduction | The current reference and historical record remain separate. |
| Container Configuration | Pack declarations and observed realization govern software. Retired image paths do not become instructions. |
| Security Monitoring | Declared log producers and observed services qualify coverage. |
| Wazuh Agent + Falco Integration | The historical heading remains stable. It does not establish a current Falco sensor. |
| Monitored Data | Authored telemetry and successful startup remain distinct from attack coverage. |
| Network Configuration | Declared networks and observed endpoints remain separate facts. |
| Access Methods | The section links supported access steps. It does not restore retired host port 2022. |
| Service Status | The section links service inspection. A process state is not event-delivery evidence. |
| Troubleshooting | The section links the monitoring procedure. |
| `wazuh-active-response.md`: introduction | Alert, response block, agent, and script have distinct roles. |
| Overview | Detection and packet prevention retain separate owners. The decisions remain linked. |
| Architecture | The script reads before it adds. The forwarding-wrapper risk uses an explicit conditional sentence. |
| Available commands | Complete descriptive clauses identify each command's effect. Only the named wrapper has whitelist protection. |
| Wiring a detection rule to AR | The section links the guide. It introduces no second configuration sequence. |
| Whitelist (kali-IP carve-out) | Addresses and exact-line semantics remain literal. Add and delete retain different behavior. |
| Severity gate | The logical OR retains its exact meaning. A combined matcher does not become an AND condition. |
| Timeout strategy | Default values, exercise recommendations, and actual cleanup remain different facts. |
| Default posture | Disabled state remains exact. Detection can still occur. |
| `disable-account` manual procedure (AC#4 of #249) | The old heading points to the account-response guide. |
| Troubleshooting | The section links diagnosis steps. It does not infer a successful action from dispatch. |
| Related | Source and test names remain literal references. |
| Response location | Agent selection and script authority remain separate. Installed Wazuh defines accepted location values. |
| `wazuh-siem.md`: introduction | The page describes component and data-flow facts. |
| Components | Definition rows identify each component. Addresses remain declared values rather than observed publications. |
| Data Flow | Agent, manager, Filebeat, indexer, and dashboard actions have explicit subjects. |
| Wazuh Manager | Listener ports stay exact. Private runtime configuration remains separate from checked templates. |
| Wazuh Indexer | Search and archive behavior retain their required settings. |
| Wazuh Dashboard | Hostname identity remains separate from loopback addressing. The corrected description uses complete sentences. |
| Falco Integration | Historical configuration does not prove a current sensor. |
| MCP Integration | Manager and indexer operations retain different owners. Connected schemas own exact tool contracts. |
| Troubleshooting | The section links the operating guide. |

### Component procedures and explanations

| Page and section | Contextual assessment |
| --- | --- |
| `appliance-qualification.md`: introduction | Approved isolation, resources, and tools precede qualification. |
| Qualification And Start Gate | Each step names an action. Signed identity, retained evidence, browser checks, and promotion retain their conditions. |
| `defensive-posture-operations.md`: introduction | Approved isolation and an admitted scenario precede changes. |
| Inspect the baseline | Identity recording precedes state changes. Startup events remain separate from participant events. |
| Change a response | Detection and action receive separate inspection steps. Cleanup remains required. |
| Extend the maintained baseline | Existing owners precede extension. Decision changes precede ADR updates. |
| `kali-operations.md`: introduction | Approved isolation and declared access precede operation. |
| Use required capture | Each action retains capture custody. Failure inspection precedes completeness claims. |
| Access without required capture | The absence condition precedes direct access. The command introduction has a complete action and object. |
| Configure experimental redaction | Experiment conditions precede the toggle. Policy review precedes evidence collection. |
| `victim-operations.md`: introduction | A running admitted lab is the prerequisite. |
| Open the node | Discovery precedes shell access. The retired port remains explicitly unavailable. |
| Inspect services | The shell context precedes literal service commands. |
| Diagnose monitoring | Fresh agent-attributed events remain distinct from process state. |
| `wazuh-operations.md`: introduction | The approved VM and running scenario precede diagnosis. |
| Troubleshooting | Each instruction names a log, connection, or event check. Authentication remains intact. |
| `wazuh-response-operations.md`: introduction | Disposable scope and the response reference precede changes. |
| Wiring a detection rule to AR | The repaired instruction names severity and agent as inspection objects. Conditions precede the test event. |
| `disable-account` manual procedure (AC#4 of #249) | Account selection precedes the event. Recovery and temporary-resource removal remain explicit. |
| Troubleshooting | Observation and action remain separate columns. Literal messages do not imply a successful target effect. |
| `workbench-composition.md`: introduction | Trusted assembly and valid enrollment precede application construction. |
| Assemble the application | Each step names a trusted input or factory. Participant inputs cannot select management authority. |
| Publish the participant desktop | Account selection precedes startup. Withdrawal remains required after stop, reset, or failure. |
| `red-side-capture-boundary.md`: introduction | The page explains the decision. It links the component facts. |
| Why no SIEM integration | Defensive observations remain separate from red self-reports. Transport availability does not grant forwarding authority. |
| `techvault-adapter-boundary.md`: introduction | The page explains ownership. It links current adapter facts. |
| Why it lives here | Scenario-specific behavior remains separate from generic backend mechanisms. No alternate schema authority is introduced. |

### Scenario procedures and validation

| Page and section | Contextual assessment |
| --- | --- |
| `containers/victim-template-guide.md`: introduction | Retirement precedes authoring guidance. The old procedure remains a historical record. |
| Author a victim | Each instruction names an existing owner or validation action. Static proof does not become runtime proof. |
| Inspect the result | Runtime discovery precedes endpoint use. A declared address does not establish a host port. |
| Earlier section links | Exact historical headings remain compatibility anchors. Link labels do not become current instructions. |
| `raes/declared-cleanup.md`: introduction | Native cleanup and shared-runtime progression retain separate owners. |
| Install the service | The section links the guide. It does not duplicate service assembly. |
| Evidence and failure | Cleanup outcome and trial outcome remain distinct. Receipt, ownership, and publication conditions stay explicit. |
| Supported service contract | Supported actions, unsupported actions, and retry limits remain separate. A scoped refusal cannot authorize project-wide deletion. |
| `raes/install-cleanup.md`: introduction | Trusted composition and isolated execution precede the task. |
| Install the service | Each step identifies an admitted input or delegated method. Evidence inspection precedes further dispatch. |
| `raes/scenario-validation.md`: introduction | The approved runner precedes commands. The reference owns gate semantics. |
| Running the gate | Dependency installation precedes targeted checks. Missing conformance is a failure rather than a warning. |
| `raes/live-validation.md`: introduction | Isolation precedes destructive validation. |
| Prerequisites | Project scope and credential preparation precede startup. Other workloads remain outside the daemon. |
| Running the gate | The warning precedes consent. Existing-range inspection and destructive clean boot remain separate modes. |
| `raes/techvault-static-validation-gate.md`: introduction | The gate parses, verifies, compiles, and interprets. A separate sentence excludes Docker startup. |
| What the gate checks | Each stage has a pass condition and failure case. Scenario names do not select presets. |
| Backend manifest | Public component names and null capabilities remain literal. Upstream RAES retains schema ownership. |
| Advisory today, blocking at cutover | Past and present tenses distinguish the old advisory job from current blocking behavior. |
| Running the gate | The stable heading links the operating procedure. |
| `raes/techvault-live-validation-gate.md`: introduction | The exact report type stays literal. The destructive default precedes operating guidance. |
| What the gate checks | Stages retain their order. A failed boot does not become a semantic failure. |
| Failure categories | Closed category names remain data. Blocked status does not imply a semantic verdict. |
| Run-archive manifest | Section names remain literal. The manifest is an observation rather than authored state or a score. |
| Observable surface | Bundle and interpreter retain distinct responsibilities. Reduced and full qualification remain different. |
| Prerequisites | The section links the guide. It introduces no second resource contract. |
| Where the semantic verdict comes from | Adapter verification and startup stimuli remain distinct. A live pass does not imply new attack coverage. |
| Running the gate | The section links the live procedure. |
| `raes/paper-scenario-realization.md`: introduction | The fixture remains checkout-only. Runtime binding and participant-visible content remain separate. |
| Evidence surfaces | Complete descriptions distinguish observations, capture intent, and placed content. Declarations do not establish collection. |
| Upstream Provenance | Original and local contributions have named owners. Unsupported provenance does not become a backend service. |
| `sdl/index.md`: introduction | RAES owns the language. The text excludes a second local parser. |
| Companion repositories | Each instruction names an upstream owner or supported procedure. Documentation links grant no acquisition authority. |
| Selection and limits | Acquired-pack and explicit-path selection retain different meanings. Invalid packs do not trigger implicit fallback. |
| `sdl/curated-variant-reference.md`: introduction and matrix | Fixture identities and matrices remain literal. Dependency closure is separate from authored node count. |
| Source owners | Each surface has one existing authority. No parallel parser or preset table is introduced. |
| `sdl/techvault-curated-variants.md`: introduction | A matching source checkout precedes fixture changes. |
| Authorities | The source-owner link precedes edits. Participant profile pins remain explicit. |
| Guardrails | Each instruction names a constraint. Rename behavior uses a complete conditional instruction. |
| Curated variants | Explicit selection precedes checks. Static wiring and live proof remain separate. |
| Security And Runtime Boundaries | Scope and containment precede runtime authority. The backend retains resource ownership. |
| Non-Goals | Complete sentences state the procedure's limits. No research fixture becomes ordinary startup selection. |
| `sdl/paper-walkthrough.md`: introduction | The lesson states its learning objective and source prerequisite. It invokes no provider or lab. |
| Find the action | Each learner action names a literal fixture reference. The text explains the observed binding. |
| Follow the observation | Participant information and evaluator-only evidence remain distinct. Existence does not authorize disclosure. |
| Distinguish intent from proof | Declarations and observed evidence retain different meanings. Evaluation remains necessary for outcome claims. |
| `sdl/runtime-architecture.md`: whole page | Historical and current interfaces remain distinct. Named owners and finite clauses describe runtime handoff and bounded failure. |
| `sdl/complex-scenario-authoring-notes.md`: whole page | Retirement and the current authoring route use complete sentences. |
| `sdl/complex-scenarios.md`: whole page | Old design context does not become current authoring guidance. |
| `sdl/limitations.md`: whole page | Current limitations belong to RAES. The historical page retains its status and link. |
| `sdl/parser.md`: whole page | The retired local parser remains separate from the supported RAES entry point. |
| `sdl/precedents.md`: whole page | Historical context is explicitly separate from current schema authority. |
| `sdl/sections.md`: whole page | The old section model remains retired. Current authoring points to RAES. |
| `sdl/testing.md`: whole page | Retired tests and current verification have different scopes. |
| `sdl/validation.md`: whole page | The old validator remains retired. Current parsing and gate owners are explicit. |

### Taxonomy, installers, and adapter prose

| Page and section | Contextual assessment |
| --- | --- |
| `red-team-taxonomy.md`: introduction | Taxonomy and emission boundary have named implementation owners. |
| Required base fields | Literal OCSF keys remain data. Optional extraction has a complete introduction. |
| Activity catalog | IDs stay exact. Simple finite clauses replace general participial algorithm descriptions. |
| Severity defaults | The failure condition precedes promotion. Existing high severity never becomes a lower value. |
| Metadata extraction contract | The extractor accepts or omits. Conservative matching does not imply invented attributes. |
| Credential handling | Literal examples retain their masking boundary. The extractor does not read credential-file contents. |
| Sink and transport | Each writer has a named destination and scope. A missing admitted run ID selects the sentinel explicitly. |
| Cross-references | Decision and source labels remain exact references. |
| `containers/windows-victim/README.md`: introduction | The separately managed VM remains optional. Historical estimates stay in Reference. |
| Prerequisites | Authorization and isolation precede downloads. The guide does not qualify mutable installers. |
| Setup | The heading groups the task steps. It introduces no independent VM-creation capability. |
| 1. Create the VM | Approved image selection precedes resource allocation and recording. |
| 2. Configure Networking | Connectivity inspection precedes integration installation. Historical addresses do not become automatic attachments. |
| 3. Run Setup Scripts | Administrative context precedes commands. Domain parameters and credential defaults receive explicit inspection. |
| 3b. Install Reverse Engineering Tools (Optional) | Tool selection precedes installation. Dependency, reboot, and version checks remain explicit. |
| 4. Verify Integration | Each instruction names an endpoint, service, or event. Process state does not replace delivery evidence. |
| Attack Scenarios | Authorization precedes action. Historical plans remain evidence rather than implemented techniques. |
| MCP Integration | The reference precedes tool use. Actual tool availability remains a separate check. |
| `mcp/mcp-reverse/README.md`: introduction | The optional artifact remains separate from the retired workstation. |
| Configure the target | Target authorization precedes enablement. Read-only discovery precedes state changes. |
| `scenarios/archive/README.md`: introduction | Archive status precedes inspection. Historical YAML is not current startup input. |
| Inspect the archive | Each instruction names an inspection action. Upstream authoring remains the supported change route. |
| `src/aptl_techvault/README.md`: introduction | Entry-point names remain data. Provider discovery has an explicit subject. |
| Declared SOC logins | Account references and credential values remain distinct. Core reads admitted values. |
| Why it lives here | The section links the ownership Explanation. |
| Customer database | Startup owns realization and authentication. Marker conditions preserve participant changes. |
| Startup verification traffic | Old probes remain retired. Current native producers remain separate from participant activity. |
| Compatibility | Version and digest remain one qualification claim. Package compatibility alone does not qualify content. |

### Status notices and assessment metadata

Only the added notices and links receive language changes in the historical pages below.
The original record bodies keep their original wording, decisions, and evidence.
Each notice states a date, status, historical scope, and current documentation route.

| Record or changed metadata | Contextual assessment |
| --- | --- |
| `components/appliance-boundary-history.md` | The notice distinguishes historical V1 design from current V3 delivery. |
| `raes/app-1-appliance-boundary-materialization-preflight.md` | The dated notice does not establish current runtime behavior. |
| `raes/dsl-003-runtime-substitution-preflight.md` | The notice keeps original substitution decisions separate from current contracts. |
| `raes/dsl-005-assertion-evaluation-preflight.md` | The notice keeps original assertion evidence separate from current qualification. |
| `raes/dsl-008-realization-preflight.md` | The notice identifies a historical realization milestone. |
| `raes/dsl-010-participant-runtime-preflight.md` | The notice does not qualify the current participant runtime. |
| `raes/issue-601-participant-demonstration.md` | Run dates qualify recorded observations. The notice grants no new provider authority. |
| `raes/issue-759-libvirt-service-reachability-preflight.md` | The notice identifies historical reachability evidence. |
| `raes/m1-raes-conformance-truth-up-preflight.md` | The notice does not promote old conformance evidence into a current pass. |
| `raes/orchestration-capable-profile-preflight.md` | Historical profile qualification remains explicitly bounded. |
| `raes/techvault-curated-live-validation-gate.md` | Old reduced-range observations remain historical. |
| `raes/techvault-curated-live-validation-preflight.md` | The notice keeps the old plan separate from present evidence. |
| `raes/techvault-live-validation-preflight.md` | The notice does not qualify current full-range realization. |
| `raes/techvault-static-validation-preflight.md` | The notice does not establish a current static pass. |
| `reference/techvault-company-profile.md` | The company proposal remains fictional historical content. |
| `reference/techvault-osint-readiness.md` | The notice grants no external publication or service authority. |
| `scenarios/archive/prime-scenario.md` | The notice identifies retired local-YAML design rather than supported SDL. |
| Copied `.txt` records | Original source text remains exact. Their maintained links identify revision and historical status. |
| `architecture/documentation-assignments.md`: changed rows | Paths and reader-purpose labels remain literal metadata. Unchanged assignments are outside this rewrite. |
| This record: introduction and Source revision and dependency evidence | The source revision is exact. Past-tense verbs describe actual source inspection. |
| Section correspondence | Each row identifies code owners and selected evidence. A test name does not claim execution. |
| Verification boundaries | Local static evidence and hosted behavior evidence remain separate. |
| Editorial review and Technical terms | General words and technical terms receive different contextual treatment. Lint success is not a conformance proof. |
| Section language assessment | The rows identify contextual judgments and preserved meanings. They do not certify unobserved runtime behavior. |

Each page name applies to later section rows until the next page name.
The assessment preserves literal heading names where existing links depend on them.

## Verification sequence

Source inspection and the section assessment supply the pre-push documentation evidence.
Prepared correspondence assertions remain unexecuted until CI can inspect the published candidate.
CI must run those checks, relevant scenario contracts, strict MkDocs, and full prose checks on the PR head.
All required results must pass before merge readiness.
Earlier HEAD results do not qualify this candidate.
