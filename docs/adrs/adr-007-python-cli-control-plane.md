# ADR-007: Python CLI as Primary Control Plane

> Historical note: references to `aptl scenario` in this ADR describe the retired pre-SDL runtime, not the current SDL-only branch.

## Status

superseded in part by ADR-070

[ADR-070](adr-070-go-implementation-and-engineering-standards.md) replaces Python as the language of the control plane with
Go. The CLI stays the primary control plane. The Python CLI stays in force until
Go port 31 removes it.

## Date

2026-02-07

## Context

From v2.0 through v3.x, the 273-line `start-lab.sh` script managed lab lifecycle.
It generated SSH keys, prepared the environment and certificates, and ran Compose.
It also synchronized credentials and examined service health.
The script had the following limitations.

### Problems with start-lab.sh

1. **No error handling**: Commands that failed silently left the lab in an inconsistent state. Certificate-generation failure did not stop startup. Containers could then start without valid certificates and fail with TLS errors.

2. **No parallelism**: Every operation ran sequentially. Docker image pulling, health checking, and SSH testing all blocked the main thread. Startup took longer than necessary.

3. **No state management**: The script had no concept of lab state. Running it twice could produce duplicate certificate generation, conflicting Docker Compose processes, or orphaned containers. There was no `stop` or `status` command.

4. **Only 4 of 9 profiles**: The script hardcoded `--profile` flags for only 4 Docker Compose profiles (wazuh, victim, kali, reverse). As the SOC stack and enterprise infrastructure were added, the script could not deploy them. Users had to manually add `--profile soc --profile enterprise` flags.

5. **No configuration validation**: The script read `aptl.json` for container enable/disable state but did not validate the configuration. Invalid JSON, missing fields, or impossible combinations (SOC without Wazuh) passed silently.

6. **Bash limitations**: Complex operations like NDJSON parsing (`docker compose ps --format json` outputs one JSON object per line, not a JSON array), credential file manipulation with regex, and structured logging were awkward or fragile in bash.

### Requirements

- Start, stop, and status commands with proper lifecycle management
- Configuration validation before deployment
- Structured error handling—fail early, report clearly
- All Docker Compose profiles supported via `aptl.json`
- Health check orchestration that waits for dependencies
- SSH connectivity verification
- Credential synchronization across Wazuh components
- SSL certificate generation/management
- Extensible for future commands (`aptl scenario`, `aptl config`)

## Decision

Use the Python CLI as the primary control plane instead of `start-lab.sh`.
The original command name was `aptl`; [ADR-062](adr-062-lilrae-name-and-naming-convention.md) records the later `lilrae` name.
The tree and sequence below describe the original design.
[ADR-064](adr-064-layered-architecture-and-code-conventions.md) defines the later staged layer refactor.
The [CLI reference](../reference/cli.md) owns supported current commands.

### Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| CLI framework | **Typer** | Declarative command definitions, auto-generated help, type annotations for argument validation |
| Configuration | **Pydantic** | Schema validation, type coercion, clear error messages for invalid configs |
| Output | **Rich** | Colored terminal output, progress indicators, tables—without manual ANSI escape codes |
| Structure | **src layout** | `src/aptl/` package with `pyproject.toml`. Standard Python packaging. |

### Architecture

```
src/aptl/
├── cli/              # Thin CLI layer (typer commands)
│   ├── main.py       # aptl entry point
│   ├── lab.py        # aptl lab start|stop|status
│   ├── scenario.py   # aptl scenario start|stop|list
│   ├── container.py  # aptl container list|shell|logs
│   └── config.py     # aptl config show|validate
├── core/             # Domain logic (no CLI dependencies)
│   ├── lab.py        # Lab lifecycle: start, stop, status, orchestration
│   ├── config.py     # Pydantic models: AptlConfig, ContainerConfig
│   ├── env.py        # .env file management, EnvVars
│   ├── ssh.py        # SSH key generation (Ed25519)
│   ├── certs.py      # SSL certificate generation via Docker
│   ├── credentials.py # Wazuh credential synchronization
│   ├── services.py   # Health checks, readiness probes
│   ├── sysreqs.py    # Platform-aware system requirements
│   ├── snapshot.py   # Range snapshot capture
│   └── scenario.py   # Scenario engine
└── utils/
    └── logging.py    # Structured logging
```

The separation between `cli/` and `core/` is intentional—the core domain logic has no dependency on Typer, Rich, or terminal I/O. This enables:

- **Testing**: Core functions are testable without mocking CLI frameworks
- **Reuse**: The future web UI backend ([ADR-011](adr-011-web-ui.md)) shares the same `core/` modules
- **Scripting**: Core functions can be imported directly for custom automation

### 12-Step Lab Orchestration

> **Superseded in part by [ADR-030](adr-030-startup-partial-readiness-classification.md)
> (issue #1018).** The fixed 12-step list and the rule that every step fails the
> sequence no longer describe `aptl lab start`. The source defines step order in
> `_LAB_START_STEPS` in `src/aptl/core/lab.py`.
> Startup uses the RAES realization handoff rather than direct `docker compose up`.
>
> ADR-030 classifies later failures as fatal, `degraded_unusable`, or `degraded_usable`. Requirement
> [CLI-003](../requirements/CLI-003/requirement.md) states the current ordering
> invariants and failure policy. The list below is the original decision.

`aptl lab start` executes a deterministic sequence:

1. Load and validate configuration (`aptl.json`)
2. Load environment variables (`.env`)
3. Check system requirements (including `vm.max_map_count >= 262144` on native
   Linux Docker Engine)
4. Generate SSH keys (Ed25519, if not present)
5. Generate SSL certificates (via Docker container, if not present)
6. Synchronize credentials to Wazuh config files
7. Pre-pull Docker images (with progress visibility)
8. Start containers via `docker compose up --build -d` with profile flags
9. Wait for Wazuh Indexer to be healthy
10. Wait for Wazuh Manager API to be ready
11. Test SSH connectivity to all SSH-enabled containers (with retry: 60s timeout, 5s interval)
12. Capture range snapshot

Each step reports its status and fails the entire sequence on error, with a clear message about what went wrong and how to fix it.

### Test Coverage

The historical delivery recorded more than 587 tests across 12 files.
This count is not current coverage or qualification evidence. Tests use mocking for Docker and subprocess calls to run without a live lab environment.

### Security Guardrail: Project-Rooted Credential Writes

> **Superseded in part by [ADR-028](adr-028-runtime-rendered-service-config.md)
> (issue #200).** Credential synchronization no longer writes back over the
> checked-in `config/` files—those are source-owned templates. The
> credentialized result is now *rendered* into the ignored `.aptl/config/`
> state tree (`0700` dirs / `0600` files, atomic write), and `docker-compose.yml`
> mounts that rendered copy. The project-rooting boundary below still applies,
> now to *both* the source template path and the rendered output path.

Wazuh credential synchronization is part of startup.
The API constructs source and rendered paths from the caller's `project_dir`.
Source templates belong under `config/wazuh_dashboard/` and `config/wazuh_cluster/`.
Rendered output belongs under `.aptl/config/`.
The core owner resolves each path and refuses access outside the resolved project root before I/O.

Caller-provided arbitrary output paths are not part of this writer contract.
Future project-owned writers must accept a project root and fixed relative target.
They must validate containment at the core boundary before I/O.

## Consequences

### Positive

- **Reliable startup**: Every step validates its preconditions and reports failures clearly
- **All profiles supported**: `aptl.json` configuration drives which profiles are activated—all 6 profile groups work
- **Extensible**: Adding `aptl scenario start/stop` was straightforward because the core domain logic was already separated
- **Testable**: 587+ tests provide confidence in orchestration logic, credential handling, certificate management
- **Shared core**: Web UI backend can import `src/aptl/core/` directly instead of shelling out to the CLI

### Negative

- **Python dependency**: Users must have Python 3.11+ and install the package (`pip install -e .`). The bash script had no dependencies beyond Docker.
- **Two systems**: `start-lab.sh` was retained as an alternative through v4.2.1, creating confusion about which was authoritative. It was removed in v4.2.2.
- **Startup overhead**: Python interpreter startup adds ~1 second vs. bash. Negligible compared to Docker operations but noticeable for `aptl --help`.

### Risks

- The `subprocess.run()` calls to `docker compose` are a fragile interface—changes to Docker Compose's CLI, output format, or exit codes can break the orchestration. The NDJSON parsing bug (v4.5.0) was an example.
- Credential synchronization uses regex to modify Wazuh configuration XML files. A polynomial backtracking (ReDoS) vulnerability was found and fixed in v4.6.5. XML manipulation via regex remains fragile.
- The startup sequence is serial. Its later steps could potentially be parallelized for faster startup, but the dependency ordering makes this non-trivial.

## Python 3.14 dependency boundary

The RAES 9.2.0 and environment-packs 6.5.0 dependencies require Python 3.14.
The CLI, development environment, CI, and release jobs now use that interpreter.
Package metadata limits support to Python `>=3.14,<3.15`, matching the qualified dependencies.
This supersedes the earlier Python minimum for the application control plane.
Guest workload interpreter versions remain part of their own declared images.
