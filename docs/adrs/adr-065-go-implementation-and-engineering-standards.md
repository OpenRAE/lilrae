# ADR-065: Go Implementation, Architecture Model, and Engineering Standards

## Status

accepted

This record supersedes these clauses for the Go implementation. The Python
implementation keeps them until Go port 31 (#1582) removes that code.

- [ADR-003](adr-003-mcp-common-library.md): the TypeScript MCP common library.
  One Go MCP runtime replaces it.
- [ADR-007](adr-007-python-cli-control-plane.md): Python as the language of the
  control plane. The Go `lilrae` binary replaces it.
- [ADR-010](adr-010-sonarcloud-quality.md): the Python and TypeScript scope of
  the quality gates. The gates cover the Go code and the browser UI.
- [ADR-011](adr-011-web-ui.md): the FastAPI backend. The Go web server replaces
  it. The Svelte UI stays.
- [ADR-025](adr-025-strict-first-party-config-schema.md): Pydantic as the
  mechanism of strict configuration. Strict decoding in Go keeps the rule.
- [ADR-037](adr-037-docker-compose-backend-cohesion.md): the Python runner and
  backend class. Its guardrails stay.
- [ADR-064](adr-064-layered-architecture-and-code-conventions.md): the Python
  mechanisms (grimp, Ruff, and the enrolled list) and the rule that no
  first-party package imports a plugin. Its layers and other rules continue in
  the Go form below.

## Date

2026-10-31

## Context

Milestone 44 ports LilRAE to Go and replaces the Python implementation in one
cutover. The Python code cannot become the target design by translation:

- Three import cycles have 28, 14, and 11 modules. `DockerComposeBackend`
  inherits from 37 mixins. `core/lab.py` has 5,106 lines.
- The code types RAES data as `object` in 887 places and reads it with
  `getattr` in 1,035 places.
- The tests make 2,045 patch calls. They test the implementation, not the
  contracts.
- The source has 82 inline suppressions, and SonarCloud has 37 ignore entries.
- Redaction exists twice, in Python and in TypeScript.

The external contracts stay: commands, options, exit codes, JSON output,
configuration, persisted files and digests, Docker resource names and labels,
MCP tools, and the web API. RAES and env-packs also move to Go. Their Go modules
supply the SDL, pack, and planning semantics. Each port keeps the canonical
concerns of the [#1510 preflight](../architecture/issue-1510-code-quality-preflight.md)
and the required passages of the
[#1552 preflight](../architecture/issue-1552-go-architecture-preflight.md).

## Decision

### Language, module, and layout

- Use the latest stable Go release. `go.mod` sets the language version and the
  toolchain, and CI reads both from it. The root `go.mod` ignores
  `node_modules`, so package patterns such as `./...` find only Go code.
- The module path is `github.com/OpenRAE/lilrae`. Release Please sets the
  product version. The product version is not a Go module version, and the
  adapter API has its own version (see Scenario adapter API).
- `cmd/lilrae` builds the `lilrae` binary. It serves the CLI, the web server,
  and the MCP servers. `cmd/lilrae-helper` builds one static Linux binary for
  all container helpers.
- Each package that is not a public API is under `internal/`. A package has one
  responsibility, and its name states that responsibility. Do not use names
  such as `util`, `common`, `helper`, `base`, `misc`, or `models`.
- `adapter/` is the only public package. It holds the scenario adapter API.
- `conformance/` holds the black-box contract suite.
- `tools/` holds the developer tools in Go modules that are separate from the
  product module. Their `tool` directives pin the tools, and their `go.sum`
  files hold the checksums. golangci-lint has a module of its own, because a
  shared module changed the versions of its dependencies, including the library
  that loads its configuration. The fixture tests of the CI gates also have a
  module of their own (Mutation testing).

### Layers

The layers of ADR-064 continue.

| Layer | Holds | May import |
| --- | --- | --- |
| Entry | `cmd/`, CLI commands, HTTP handlers, MCP servers, and the construction of the object graph | Entry, Application, Adapters, Core, Foundation, Plugins |
| Application | Services for one user operation | Application, Core, Foundation |
| Adapters | One adapter for each external system | Its own adapter, Core, Foundation |
| Core | Values, errors, policies, configuration, contracts, and the adapter API | Core, Foundation |
| Foundation | Shared mechanisms with no LilRAE concept | Foundation |
| Plugins | Scenario adapters | The adapter API and the public RAES types it names |

Rules:

1. The compiler rejects import cycles, and `internal/` limits visibility.
2. An application package defines the small interface that it needs. An
   adapter satisfies that interface without an import of the application
   package. Core holds no interface for an adapter.
3. Entry code builds the object graph by hand. Do not use a dependency
   injection framework, `init` registration, or mutable package state.
4. An adapter does not import another adapter. Adapters exchange core values.
5. Only `cmd/lilrae` imports a plugin, to register it. This is the one
   exception to the ADR-064 plugin rule. LilRAE loads no code at run time.

### Architecture model

- `architecture/model.yaml` is the single source of the architecture. Each
  repository has its own model.
- The model names each layer and each component. A component has a name, a
  layer, a responsibility, and an explicit list of packages, so a new package
  needs a model change. The model also lists the third-party modules that each
  component can use, the public API packages, and a fix-it message for each
  rule.
- A compiler in `tools/` validates the model and generates the go-arch-lint
  configuration from it. The compiler rejects unknown keys, a package that has
  no component or two components, an unknown dependency, and a stale
  reference. Do not edit the generated configuration.
- go-arch-lint checks the whole repository: commands, helpers, tools, tests,
  and generated code, for each supported operating system and build tag. Each
  import resolves to its module, so a module permission is never a global
  exemption. The compiler maps each finding to its rule and prints the fix-it
  message.
- The Go code starts with zero findings. The checks have no baseline.
- The pack-ownership check (`.gc/pack-ownership.json`) stays a separate check.
- The architecture diagrams in the documentation come from the model.
- An architecture check proves that packages and imports agree with the model.
  It does not prove design intent or security behavior.

### Design step

- Before the code is written, each issue records a design in the YAML front
  matter of its design note, `docs/architecture/issue-<number>-<topic>-design.md`.
  The design names each new or changed package, its component, its
  dependencies, and each model change.
- The design check compares the design with the model before the code exists.
  A design cannot grant an import that the model forbids. A model change in the
  design is part of the reviewed change.
- CI fails when the code differs from the model or from the design of the pull
  request.
- Go port 02b builds the compiler and the checks.

### Style and lint

The [Google Go Style Guide](https://google.github.io/styleguide/go/) (the guide,
the decisions, and the best practices) is the style. golangci-lint v2 enforces
each rule that a tool can check. `docs/CODING_STANDARDS.md` holds the review
checklist for the other rules.

| Rule | Check |
| --- | --- |
| Formatting | gofmt and goimports (formatters) |
| Names use MixedCaps, and initialisms keep one case | staticcheck ST1003, revive `var-naming` |
| Package names are short and meaningful, with no names such as `util` or `common` | revive `package-naming` |
| Each exported name has a doc comment that starts with the name | revive `exported`, godoclint, staticcheck ST1020 to ST1022 |
| Each package has a package comment | staticcheck ST1000, revive `package-comments` |
| Error strings start in lower case and have no final punctuation | staticcheck ST1005, revive `error-strings` |
| Each error is handled, wrapped with `%w`, and compared with `errors.Is` or `errors.As` | errcheck, errorlint, wrapcheck |
| Error names are `ErrX` and `XError` | errname |
| Receiver names are short and consistent | staticcheck ST1016, revive `receiver-naming` |
| `context.Context` is the first parameter and is not stored in a struct | revive `context-as-argument`, containedctx, contextcheck |
| No `init` functions and no mutable package variables | gochecknoinits, gochecknoglobals |
| Early return, and no `else` after a return | revive `early-return`, `indent-error-flow`, `superfluous-else` |
| No dot imports, and blank imports only in `main` and tests | revive `dot-imports`, `blank-imports` |
| Switches over enumerations are exhaustive | exhaustive |
| Interfaces stay small and functions return concrete types | iface, interfacebloat, ireturn |
| Current idioms (`any`, `min`, `max`, `slices`, `maps`, range over integers) | modernize, revive `use-any`, intrange, copyloopvar |
| HTTP requests carry a context, and response bodies are closed | noctx, bodyclose |
| Tests use no assertion library, and helpers call `t.Helper()` | depguard, thelper, usetesting |
| Security checks | gosec, govulncheck |
| Cognitive complexity is 15 or less | gocognit |
| A suppression names its linter and its reason | nolintlint |

A linter covers part of a rule in some rows. Review covers the rest. A
suppression is permitted only for a verified false positive, and its comment
names the linter and says why the finding is false. CI also runs `go vet`,
`go mod tidy -diff`, and `go fix -diff`. Vale checks Go comments against the
documentation styles. Comments explain why the code is as it is. They do not
record review history.

### Errors, logs, context, and concurrency

- Return errors, and add context with `fmt.Errorf("...: %w", err)`. Define a
  sentinel error or an error type only when a caller acts on it. An error
  message never holds an input value that can be a secret.
- Library code does not panic. `main` and tests can.
- The entry layer turns an error into the user message, the exit status, the
  HTTP response, or the MCP `isError` result.
- Use `log/slog`, and pass the logger explicitly. Logs go to standard error,
  never to the MCP protocol stream.
- One redaction package protects every output: logs, HTTP access logs, command
  results, snapshots, persisted text, and exported spans. A logger setting is
  not sanitization.
- A function that blocks or does I/O takes `ctx context.Context` as its first
  parameter. Cancellation stops owned work and reports the resources that
  remain. Cleanup that must outlive a cancellation uses
  `context.WithoutCancel` with a bounded timeout.
- Each goroutine has an owner and an end. Use `golang.org/x/sync/errgroup`, and
  bound each fan-out.

### Input, serialization, and files

- First-party JSON uses `encoding/json/v2`. Names match exactly, duplicate
  names and invalid UTF-8 are rejected, unknown members are rejected, trailing
  data is rejected, and the input size has a limit. Missing, null, and zero
  values have distinct meanings where the contract says so.
- First-party YAML uses known fields only and one document. Duplicate keys are
  rejected.
- Input that an external system owns follows the contract of that owner.
  JSON Schema validation uses the dialect of the owner, for example draft
  2020-12 for MCP tool schemas, with no coercion and no inserted defaults.
- Validate after decoding, and reject an input before any change.
- The vectors of Go port 04 define each persisted byte form, digest, and
  identifier. One function implements each scheme. Ordinary JSON encoding is
  not canonical encoding.
- Use `os.Root` for contained file access. Replace a file atomically: write a
  temporary file in the same root, sync it, and rename it.
- Time values are `time.Time` in UTC. Their text forms follow the vectors.

### Tests

- Use the standard `testing` package and `github.com/google/go-cmp/cmp`. Do not
  use an assertion library.
- Write table tests and golden files. A test helper calls `t.Helper()`. A
  change to a golden file is a contract change and needs review.
- Replace adapters with fakes through consumer interfaces. Do not patch package
  state.
- Use `testing/synctest` for code that waits or retries. It does not replace
  real socket and process I/O, so keep the effect interfaces and test real
  transports separately.
- Write fuzz tests for parsers, redaction, path containment, and canonical
  encoding.
- CI runs `go test -race -shuffle=on`.
- `testscript` runs the black-box CLI contract suite.
- Tests that need a Docker daemon carry the `integration` build tag. CI runs
  them in jobs that have Docker, and the linters read that tag.

### Mutation testing

- Gremlins mutates the changed lines of the Go production code of each pull
  request. It runs the tests of the package of each mutant. A scheduled run of
  the Checks workflow mutates each whole module.
- Gremlins sets the timeout of each mutant from the test time of the whole
  module. The fixture tests of the CI gates are slow, so they are in a separate
  module.
- Efficacy is killed mutants divided by killed and lived mutants. Mutant
  coverage is killed and lived mutants divided by killed, lived, and uncovered
  mutants. Mutants that do not compile and mutants that time out count in
  neither value. The job reports the mutants that time out.
- `tools/mutation-thresholds.json` holds the threshold of each value. The first
  thresholds come from a measurement on the first packages. The check fails
  when a pull request lowers a threshold.
- When Go production code changed, a tool error or a change where each mutant
  timed out fails the job. Changed lines that hold no mutant pass, and the job
  names the changed files. When no Go production code changed, the job reports
  that no relevant input changed.

### Regression tests

- A regression test carries the line `regression: #<issue>` in the doc comment
  of its test function. Tests for new behavior carry no such line. The check
  rejects a malformed `regression:` line and a line that is not on a test
  function.
- The regression test check runs on each pull request, whatever its
  Conventional Commit type. It reads the issue number from the branch name
  (`<issue>-<topic>`).
- The check replays each regression test for that issue that the pull request
  adds or changes. It runs the test on the base revision with the head test
  files and test data of the package. The test must compile and fail there, and
  it must pass on the head revision. A regression test for another issue is not
  replayed, because the base revision already has its fix.
- A compile error, a missing dependency, no matching test, a skipped test, a
  test that does not finish, or an infrastructure failure is not the required
  failure. A regression test reproduces the bug through the API that the base
  revision has.
- A pull request that changes Go production code for an issue with the `bug`
  label must add or change a regression test for that issue, or the check
  fails.
- A branch name without an issue number, for example a Dependabot or a
  promotion branch, has no replay. The check still validates the
  `regression:` lines of the changed test files.

### Dependencies

Prefer the standard library, then `golang.org/x` modules, then established
modules. An established module is maintained, has a permissive license, and
passes govulncheck. The architecture model permits each module only for named
components.

| Concern | Module |
| --- | --- |
| CLI | `github.com/spf13/cobra` |
| MCP | `github.com/modelcontextprotocol/go-sdk` |
| SSH | `golang.org/x/crypto/ssh` |
| Docker Engine | `github.com/moby/moby/client` |
| Compose model | `github.com/compose-spec/compose-go/v2` |
| YAML | `go.yaml.in/yaml/v3` |
| JSON | `encoding/json/v2` |
| JSON Schema | `github.com/santhosh-tekuri/jsonschema/v6` |
| RFC 8785 | `github.com/gowebpki/jcs` |
| BLAKE3 | `lukechampine.com/blake3` |
| UUID | `uuid` |
| File locks | `github.com/gofrs/flock` |
| Concurrency | `golang.org/x/sync/errgroup` |
| Terminal | `golang.org/x/term` |
| Telemetry | `go.opentelemetry.io/otel` |
| Web API | `github.com/oapi-codegen/oapi-codegen/v2`, from a checked-in OpenAPI document |
| Shell parsing | `mvdan.cc/sh/v3` |
| Tests | `github.com/google/go-cmp`, `github.com/rogpeppe/go-internal/testscript` |
| Lint, architecture, and mutation | golangci-lint v2, go-arch-lint, Gremlins |
| Release | GoReleaser |

### Docker access

- One typed deployment boundary owns daemon selection, project and owner
  scoping, timeouts, and redaction. The ADR-037 guardrails stay: typed
  operations, project scoping, and no command passthrough.
- The Engine API client does every read and container operation: inspect,
  list, exec, logs, events, networks, volumes, and images. No code parses
  human-readable Docker output.
- `docker compose` starts and stops projects, and `compose-go` builds the typed
  project model. LilRAE does not reimplement Compose.
- The transport (local socket or SSH) is a configuration of that boundary, not
  a second deployment provider. The Compose commands use the same endpoint as
  the client. An SSH daemon has no access to local build artifacts.

### Scenario adapter API

- Go interfaces in `adapter/` define the API. Its exported signatures use only
  its own types and the public RAES types, never an `internal/` type.
- The runtime `extension_api_version` and `family_api_version` fields keep their
  meaning. The admission rules of `docs/reference/family-adapters.md` stay:
  one qualified provider for each capability, exact target matching, and
  detached trial inputs. Core keeps persistence and redaction.
- Adapters register at compile time in `cmd/lilrae`.
- The Python entry-point groups end at the cutover. An independent adapter
  owner, for example RPT, builds a `lilrae` binary that includes its adapter
  module. The release includes only first-party adapters.

### Container helpers

- The release build compiles `lilrae-helper` for each supported Linux
  architecture and embeds the binaries in `lilrae`.
- `lilrae lab init` writes the helper binaries into the helper build contexts
  with the other lab assets (DEP-008). Each Dockerfile copies the binary for its
  target architecture into a minimal, digest-pinned runtime image. Neither
  `lab init` nor the image build needs a compiler or a module download.
- A development build produces the helper binaries with `go generate`.
- The seat payload carries the helper binaries inside `lilrae` (ADR-049).

### Distribution

- GoReleaser builds the binaries for the supported platforms with `-trimpath`.
- A release publishes GitHub releases and PyPI wheels that contain the binary.
  It keeps OIDC trusted publishing, and it attests provenance before
  publication. The SBOM covers the Go modules in each binary.
- `lilrae-misp-suricata-sync` is not ported. The TechVault pack carries its own
  copy of that service.
- The deprecated `aptl` command stays until 10.0.0 (ADR-062).

### Cutover

- Each pull request of milestone 44 targets `go-cutover`
  ([CI verification](../architecture/ci-verification.md#go-cutover-branch)).
  The Go code does not ship before Go port 31.
- CI runs the conformance suite and the vectors on both implementations, each
  with its own state.
- Go port 31 merges `go-cutover` into `dev` and switches the release.

## Consequences

### Positive

- The compiler, `internal/`, and the model enforce the architecture, and import
  cycles cannot exist.
- One static binary replaces Python, pipx, and Node.js as user prerequisites.
- Tests replace adapters with fakes through small interfaces. Nothing patches
  package state.

### Negative

- Each new package needs a model change and a design check.
- The release and development builds have two steps: the helper binaries, then
  `lilrae`.
- The repository holds two implementations until the cutover.
- The work that needs RAES waits for the RAES Go module.

### Risks

- The Docker Engine client is earlier than v1, so its API can change. The
  Docker adapter is its only importer.
- go-arch-lint and Gremlins are smaller projects than the core toolchain.
  Pinned versions and the model keep a replacement local to `tools/`.
- Gremlins has no suppression for an equivalent mutant. On a small change, one
  equivalent mutant can fail the mutation gate.

## References

- [Google Go Style Guide](https://google.github.io/styleguide/go/)
- [Go 1.27 release notes](https://go.dev/doc/go1.27)
- [golangci-lint linters](https://golangci-lint.run/docs/linters/)
- [go-arch-lint configuration](https://github.com/fe3dback/go-arch-lint/blob/master/docs/syntax/README.md)
- [Gremlins](https://gremlins.dev/)
- [MCP Go SDK](https://github.com/modelcontextprotocol/go-sdk)
- [Issue #1552](https://github.com/OpenRAE/lilrae/issues/1552)
