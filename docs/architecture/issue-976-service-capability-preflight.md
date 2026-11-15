# Issue #976 Service Capability Preflight

Reader purpose: Explanation. Owner: issue #976.
Source cut: `d9e5e30d5054af86b87297dc4659a8de612cb3c3`, reviewed 2026-11-09.
The supplied issue is the delivery contract; no formal requirement is attached.
This note sets design constraints, not implementation tasks or qualification claims.
The [Samba NT ACL store design](issue-976-samba-acl-store-design.md) records the implemented design.

## Current boundary

The issue predates two changes that affect its application:

- Issue #1121 retired the reverse workstation, its Dockerfile, and its Compose service.
  `tests/test_compose_capability_necessity.py` checks that absence.
  The optional `mcp-reverse` targets an explicitly configured external host; it does not restore that workstation.
  Keep the retirement. Do not introduce Falco or a replacement workstation to satisfy an obsolete deployment assumption.
- Samba still adds `SYS_ADMIN` in `_raes_backend_implementation_profiles._active_directory_base()`.
  The provider runs Samba directly, without systemd, using `containers/generic-samba-ad-base/` and its Wazuh descendant.
  The root Compose `ad` entry is a stub; editing it alone cannot remove the realized grant.

The pinned-pack capability test currently expects no authored AD capabilities.
This does not supersede #976's requirement to preserve separately required `NET_ADMIN` behavior.
An applicable scenario must supply that requirement explicitly; do not add it to the provider minimum.
The generic-substrate qualification gate currently rejects authored capabilities it cannot faithfully lower.
Do not bypass that gate or silently drop a required grant to make AD start.
Record an unsupported required AD variant as a blocker.

## Decisions and service contracts

Keep the ACL storage choice inside the existing Samba provider.
Do not change portable scenario semantics, infer behavior from the node name, or add a capability-management service.
ADR-025, ADR-029, ADR-046, ADR-048, ADR-053, and the #955 substrate boundary already govern this work.
No new ADR, schema, controller, repository, or exception hierarchy is needed.
The typed provider selection, `BaseContainerSpec`, and existing posture contracts remain the executable architecture model.

A database-backed xattr store is a candidate, not a qualified replacement.
Samba documents [`xattr_tdb`](https://www.samba.org/samba/docs/current/man-html/vfs_xattr_tdb.8.html) for storing extended attributes in TDB.
Its upstream [NT ACL helper](https://github.com/samba-team/samba/blob/master/python/samba/ntacls.py) recognizes `xattr_tdb:file`.
These facts support investigation; they do not prove compatibility with the image's installed Samba version or provisioning path.
Record that version and loaded modules with the qualification evidence.

[`acl_tdb`](https://www.samba.org/samba/docs/current/man-html/vfs_acl_tdb.8.html) stores NT ACLs, while `xattr_tdb` stores extended attributes.
Do not treat those modules as interchangeable or replace the AD DC's required VFS stack with a standalone-server recipe.
Preserve domain-controller modules and validate the effective stack through Samba's native parser and real operations.
Do not skip SYSVOL ACL setup, suppress provisioning failures, or substitute permissive POSIX modes.
Samba warns that [`user.NTACL`](https://www.samba.org/samba/docs/current/man-html/vfs_acl_xattr.8.html) can expose ACL metadata to local modification.
That rename is not an acceptable convenience fallback without demonstrated protection and unchanged scenario behavior.

Provisioning and the running daemon must use the same store from the first ACL write.
`provision-domain.sh` currently restores `/var/lib/samba/smb.conf.provisioned` when its persistent `.provisioned` marker exists.
`provider-start.sh` waits for a separate `/run/aptl-samba-provider.ready` marker before executing Samba.
Preserve those distinct meanings: durable provisioning completion and permission to start this process.
Never release readiness after partial provisioning or a missing, unreadable, or incompatible ACL store.

Place durable ACL metadata with the provider's existing persisted Samba state, with restricted ownership and permissions.
Keep it outside exported shares, transient `/run` or `/tmp`, source assets, and host bind mounts.
The store and SYSVOL files must survive together; file-identity-dependent database behavior requires qualification across container recreation.
Previously provisioned volumes can contain native xattrs and an existing completion marker.
Handle that state explicitly: a qualified conversion or a bounded refusal with a recovery explanation.
Do not wipe volumes, silently reprovision a different domain, or claim old native ACLs migrated because the marker exists.

The installed TechVault adapter also updates both saved and active Samba configurations for audit logging.
Its `log_sources.py` must preserve the provider's ACL options through reload and restart.
Provider mechanics belong in generic provider assets; scenario users, groups, weaknesses, and expected audit events belong behind the existing adapter boundary.
AD directory-object DACLs, SYSVOL file ACLs, share permissions, and network ACLs are different contracts.
`raes_acl_realization.py` implements network rules and is not an NT ACL storage extension point.

## Cross-cutting passage and canonical owners

The existing flow remains:

```text
Operator CLI / authenticated API -> admitted scenario and runtime qualification
  -> semantic provider selection -> BaseContainerSpec -> owned Docker/SSH backend
  -> provision domain with protected persistent ACL store -> running Samba
  -> native readback, account reconciliation, adapter audit and scenario proof
  -> bounded LabResult / StartupDiagnostic and redacted local evidence
```

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Authentication and lifecycle authority: `api/main.py`, `api/middleware/bff.py`, `orchestrate_lab_start()`, execution-boundary and lifecycle ownership checks | Keep `verify_token`, Host, CSRF, and browser session checks on the existing API route. Use the same lifecycle path from CLI. Add no bootstrap endpoint or host helper bypass. |
| Scenario and configuration shapes: RAES `RuntimeConfiguration`, `RuntimeCapabilityPolicy`, `AptlConfig`, `qualify_runtime_materialization()`, `effective_runtime_contract_issues()` | Preserve strict parsing, `extra="forbid"`, authored privilege meaning, and pre-mutation qualification. Add no SDL field, `aptl.json` toggle, arbitrary VFS string, or environment-controlled privilege fallback. |
| Provider selection and capability policy: `BackendBaseSelection`, `NodePlanningOptions`, `BaseContainerSpec`, `_ALLOWED_BACKEND_RUN_CAPABILITIES` | Change only the measured provider addition after service qualification. Keep backend additions separate from authored capability policy and Docker defaults. Reconcile the backend allowlist with actual remaining consumers; never convert it into an authored-capability denylist. |
| Environment and credentials: `_environment_bindings.py`, `_compose_environment.py`, `_account_provider.py`, `container_exec_with_input()` | Preserve declared environment names, source classifications, value-shape validation, and owner-only env files. Bootstrap and probe credentials must avoid argv, shell tracing, image layers, logs, and evidence. Use existing stdin delivery where supported; redaction cannot protect process arguments. |
| Commands and native validation: `DockerMaterializationExecutor`, `DeploymentBackend.container_exec()`, Docker/SSH `_run()`, provider shell argument checks | Retain argv lists, bounded timeouts, selected-daemon context, and domain/realm checks. Use `testparm` and actual Samba operations for product semantics. Do not add a second INI schema or shell-interpolate scenario values. |
| Host posture and containment: `_compose_base_substrate.py`, `_compose_substrate_attestation.py`, `_compose_native_boundary.py`, `_native_range_model.py` | Attest the exact expected capabilities on creation and reuse. Keep default seccomp/AppArmor and reject privilege, devices, namespaces, or host mounts that compensate for removal. Native policy's `SYS_ADMIN` admission check must consume the new selection without a special AD exemption. Outer containment remains independently required. |
| Observation and persistence: `raes_runtime_observation`, `_runtime_concern_excess`, `_compose_resource_ownership`, `_compose_resource_resolution` | Keep closed-world capability comparison and native-ID ownership receipts. Reject stale containers that retain the grant; never delete a foreign container by name. Keep the existing named-volume lifecycle and cleanup owner. Store redacted evidence through existing run serialization. |
| Readiness and observability: `ProvisionDomainAuthorityOp`, `raes_materializer_engine`, `_compose_account_realization`, `aptl_techvault/service_readback.py`, `aptl_techvault/log_sources.py` | Reuse domain identity readback, account reconciliation, native effective-config parsing, and fresh audit-event proof. A process, open port, completion marker, or successful config parse alone does not prove working ACLs or winbind. |
| Errors and logging: `MaterializationCommandError`, backend errors, `LabResult`, `StartupDiagnostic`, `get_logger()`, `redact()`, adapter `ReadbackUnavailable` | Keep bounded node/step/reason diagnostics and existing failure translation. Do not return raw stderr, inspect JSON, full configs, credentials, or ACL database contents. A failed observation remains unknown or failed, never an empty successful result. |
| Packaging and CI: `_compose_generic_base_images.py`, `hatch_build.py`, `tools/ci/select_checks.py`, `.github/workflows/checks.yml` | Reuse tracked-asset packaging, parent-image rebuilds, descendant image selection, scans, and installed-wheel qualification. Prove both bare Samba and the Wazuh descendant. Cached `latest` tags or a checkout-only script cannot establish delivery. Preserve offline staging's refusal to download or rebuild missing artifacts. |

Include generated Samba bootstrap passwords in the credential boundary review, alongside operator-supplied values and authenticated test probes.
Paths in the table are under `src/aptl/` unless their package or repository location is explicit.
This surface includes Linux xattr permissions, Docker effective capabilities, filesystem identity, the selected remote daemon, and Samba's installed modules.
It also includes the root Compose reference, generated models, provider assets, installed adapter, wheel assets, and CI routing.
Inspect the artifact that actually starts each service; reference Compose output is not deployment authority.

## Extensibility seam

Use the existing semantic provider selection and shared provisioning script as the extension seam.
Domain and realm already travel through typed `provider_parameters`; node names must not select storage policy.
Keep the ACL store location in one provider-owned definition, consumed consistently by provisioning, daemon configuration, persistence, and qualification.
If a second supported store becomes necessary, select a bounded backend policy at that seam.
Do not create a public storage abstraction or arbitrary path/module parameter for one candidate.
Future scenarios continue to author identity and ACL intent rather than repeat container privilege recipes.

The reverse retirement resolves its shipped grant by absence, not by qualifying a new Falco deployment.
Shared `INSTALL_FALCO`, log templates, and rules remain elsewhere; their presence does not establish a reverse consumer.
If a supported consumer actually requires Falco, its owner must establish driver, kernel, telemetry, and first-boot compatibility.

Falco documents [modern eBPF](https://falco.org/docs/concepts/event-sources/kernel/) as a supported non-kmod path.
Its [container guidance](https://falco.org/docs/setup/container/) still requires capabilities and host visibility.
Non-kmod does not mean unprivileged or container-local observation.
Do not copy a host-observer recipe, mount the Docker socket, broaden host visibility, or fall back to kmod or `SYS_ADMIN`.

## Proof obligations and boundaries

The delivery evidence must establish:

- Real first provisioning without `SYS_ADMIN`, correct domain identity, DNS/Kerberos/LDAP/SMB availability, and functioning winbind identity resolution and authentication.
  Exercise SYSVOL/NETLOGON access, account/group reconciliation, SID mapping, and configured AD behavior.
- The released scenario's planted ACL weaknesses still produce their intended effects.
  Include independently expected allowed and denied operations, inheritance, owner/SID/DACL readback, and unchanged non-planted protections.
  Map directory-object and filesystem weaknesses separately; an ACL backend change must neither repair intended weaknesses nor create substitute ones.
  If the released pack supplies no applicable weakness contract, record the evidence gap instead of inventing a pass condition.
- Fresh images and empty state work, restart and container recreation preserve ACL meaning, and existing-volume behavior is explicit.
  Failed or interrupted provisioning and an unavailable ACL database cannot yield readiness or successful reuse.
  Audit configuration survives all paths and produces a fresh event through the existing Wazuh path.
- Inspect readback and effective process capabilities exclude `SYS_ADMIN`; no replacement host authority hides in flags, mounts, devices, file capabilities, or helpers.
  Preserve any required `NET_ADMIN` behavior through its own declared contract and real active-response proof.
  A fixture with no `NET_ADMIN` is not that proof.

Reuse `tests/test_compose_capability_necessity.py`, `tests/test_raes_base_substrate.py`, and `tests/test_compose_substrate_attestation.py` for generic contracts.
Released-pack and adapter cases belong under `tests/techvault/`, using its existing read-only fixtures and independent expectations.
Update the necessity rationale with measured replacement evidence; preserve prior measurements as historical records.
The current source-string assertions and kernel xattr write prove neither domain provisioning nor planted ACL behavior.
The existing domain and share readback also does not attest the complete NT ACL contract.
Use focused negative controls and mutation checks on changed policy and readiness logic, including a reintroduced grant or ignored ACL failure.

Run behavior and mutation tests only in CI or an explicitly approved isolated VM, through the existing targeted-test workflow.
Select the existing installed-wheel boot/teardown and full live qualification owners for their respective scopes.
The neutral clean-install smoke scenario does not qualify Samba, winbind, or the released scenario's ACL weaknesses.
Skipped Docker tests, absent images, a green static suite, or a healthy subset cannot complete #976.
Record image/package identity, kernel/runtime/filesystem, pack identity, exact posture, results, and blockers in the existing redacted evidence path.
Either unresolved grant or lost required behavior keeps the issue incomplete.

Non-goals are restoring reverse, removing Falco from unrelated consumers, redesigning Wazuh, changing generic init, or banning scenario-required privileges.
This work also excludes new external services, schema forks, duplicated validators, custom ACL engines, and lifecycle or error-handling frameworks.
Do not edit another checkout or change a released pack implicitly.
An upstream contract or scenario gap requires an explicit blocker and separately owned change.
This preflight changed guidance only. The design note records the implementation and its tests.
