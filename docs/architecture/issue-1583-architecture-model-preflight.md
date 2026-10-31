# Issue #1583: Architecture model preflight

The supplied issue is the delivery contract. This note constrains its design;
it does not implement the model or prescribe an implementation sequence.
[ADR-065](../adrs/adr-065-go-implementation-and-engineering-standards.md)
now selects YAML, `architecture/model.yaml`, a source checker in `tools/`,
Go's parser plus `golang.org/x/mod`, and design-note front matter. It explicitly
replaces go-arch-lint. The existing
[design note](issue-1583-architecture-model-design.md) and model are drafts;
neither proves that the checks or workflow integration exist.
The [#1552 preflight](issue-1552-go-architecture-preflight.md) and
[CI verification](ci-verification.md) remain authoritative.

## Model authority and boundaries

The compiler owns mechanics; the repository model owns policy. Layer names,
component responsibilities, exact package membership, allowed edges, module
permissions, public packages, and rule identifiers with fix-it messages belong
in the model. No LilRAE paths, layer table, plugin exception, or import denylist
belongs in compiler code. Generated analyzer settings, if used, and diagrams
are views of the same validated model, not independent authorities. Generic
rule implementations and supported rule identifiers belong in the checker;
repository-specific permissions and remediation belong in the model.

Use one versioned model schema and one versioned design-record schema, sharing
the relevant definitions and semantic validator. A design record is a proposed
change, not another architecture model. Reject unknown fields, duplicate keys,
multiple YAML documents, unsupported versions, missing values, duplicate
membership, invalid references, and blank rule messages. Bound input size and
YAML expansion; reject unsupported tags and aliases rather than treating YAML
as executable configuration. Schema validation and graph/reference validation
serve different purposes; do not copy their rules into each command.

Permissions must satisfy both layer direction and component edges. An explicit
edge must not override a forbidden layer crossing. Reconcile ADR-065's rules
for consumer-owned interfaces, adapter isolation, and registration only in
`cmd/lilrae` with this model. A layer label alone cannot enforce those rules.
Same-layer imports are not automatic permission to couple separate adapters.
Public API status, executable entry points, test packages, and `internal/`
visibility are different concepts. Commands and external test packages do not
become supported libraries merely because they cannot all live in `internal/`.
Check Go's actual visibility constraints and public signatures; a declaration
of a public API cannot legalize an inaccessible type.

The current `.golangci.yml` keeps depguard's standard-library bans (`io/ioutil`
and `log`); retain those engineering conventions with lint. Component-specific
module permissions belong only in the model, whether evaluated directly or
compiled into analyzer settings. If settings are generated, validate the
composed configuration against the pinned golangci-lint schema; do not assume
that it merges separate configuration files. Keep style, formatting, error
handling, and security lint with their current owners. Existing
Ruff/Python layering, pack ownership, vulnerability scanning, and SonarCloud
quality settings are separate concerns, not rules to copy into this model.
In particular, `tools/check_pack_boundary.py` loads installed adapters and
admitted SDL. Keep it separate from the new static-only architecture checks;
reusing its discovery would violate this issue's no-project-execution boundary.

## Whole-repository coverage

`tools/ci/go-gates.sh` already discovers tracked module manifests, but excludes
`web/caddy-build/**` and test data. A root `./...` does not cover nested modules.
Share and extend repository-contained discovery rather than copying its list
into the compiler and workflow. All first-party Go packages need ownership,
including the compiler itself, tool tests, Caddy entry code, commands, helpers,
conformance tests, and generated code. Keep Caddy's separate dependency graph
and existing web tests. Explicitly distinguish its vendored `third_party`
module, installed `node_modules`, and negative fixture data from first-party
packages. Such source classification is not a blanket Caddy or tests exemption.

Inventory source independently of a successful host-only package load. Under
the current ADR, scan imports in every tracked Go file, including ordinary and
external tests, architecture-specific files, generated code and inactive build
tags. This avoids a build matrix for import admission. Do not union those files
into a pretend compilable package: mutually exclusive implementations can have
different declarations. Syntax scanning does not prove resolution of calls,
public signatures, cycles or compilation; the existing build/lint jobs retain
those responsibilities across their supported platforms and tags. Keep source
classification and module resolution shared by all architecture commands; a
new nested module must not require another hard-coded shell list.

Resolve imports using module metadata, including major-version module paths,
nested modules, standard-library imports, local first-party modules, and
replacements. Prefix matching alone is not module ownership. A local replacement
cannot turn unclassified source into an approved external dependency. Define
permissions for a component's direct imports; distinguish tool directives and
transitive module dependencies rather than treating every `go.sum` entry as
an import or granting every component the tools' transitive graph.

Generation must be deterministic, with stable ordering and no timestamps or
host paths. CI compares regenerated output without modifying tracked files;
missing, extra, or stale generated artifacts fail. Check architecture diagrams
only for facts the model owns: do not claim the package graph generates the
runtime network topology in `docs/architecture/index.md`.

## Design comparison and workflow

The front matter in `docs/architecture/issue-<number>-<topic>-design.md`
must describe the final package dependency sets of the changed packages,
including test dependencies and removals/renames, and each model change.
The pre-code check validates proposed packages without requiring their source
to exist. The post-code check requires actual membership and imports to agree.
Do not weaken missing-package checks in the final repository to support the
pre-code case. Do not enroll imaginary future packages to fill out the diagram.

Compare the design to the base model and its declared amendments, then to the
head model and code. Checking only the head model lets an undeclared policy
relaxation approve itself. Derive the changed-package set from the Git diff;
checking only packages listed by the author misses omitted changes. Use explicit
immutable base/head identities and the PR merge base for change selection,
including deletions and module-manifest changes. A merge checkout is not an
implicit PR head. Check the complete head architecture independently of this
changed-package comparison.

A permitted dependency in the model is an allowance; an observed dependency is
a fact; a design dependency is an intended fact. Keep those meanings separate.
Define exact comparison semantics for build variants, tests, package moves,
and dependency-only updates in the design schema. Historical design notes do
not become permanent snapshots that forbid subsequent issues from changing
the same package. A PR with no package/model changes can have an empty change
set; branch names without issue numbers must not bypass architecture checks.
Promotion and automated dependency PRs need explicit selection semantics using
the existing event/branch conventions, not synthetic issue numbers or a broad
bot exemption.

The installed `/implement` already has mandatory design step 2.6 and
`gc_record_implement_design` before planning. Reuse that completion boundary and
the repository's `.ground-control.yaml`/`.gc/plan-rules.md`; do not introduce a
second workflow, completion marker, or user-level-only enforcement. No design
checker hook is established by this checkout today. The delivery must prove
how the canonical workflow invokes the check before recording design completion,
using a supported integration point. Do not invent a configuration key or edit
only an installed skill copy. Document the real command and record contract in
`docs/CODING_STANDARDS.md`. CI can prove consistency, not that code was written
after a design or that a reviewer approved a model decision. Those remain the
existing design-completion and PR-review responsibilities.

## Cross-cutting passages and reuse

| Layer and incumbent | Required passage |
| --- | --- |
| Tool layout and parsing: `tools/cmd/{regressioncheck,mutationcheck}`, `tools/internal/`, ADR-065 | Keep the CLI thin, share validated model semantics, use `go.yaml.in/yaml/v3`, Go parsing and `golang.org/x/mod` already in the tools module graph. Do not add a second parser, graph framework or product service. |
| Git and identity: `tools/internal/git`, `tools/internal/gittest`, `tools/ci/select_checks.py` | Reuse commit resolution, NUL-delimited paths, no-rename diff conventions, and disposable test repositories. Keep paths/revisions as argv data, with option termination and explicit cwd. Do not use regression replay: design comparison reads source and metadata without running target code. |
| File and configuration admission: ADR-065 strict decoding and `os.Root` | Contain model, design, source and output paths within the selected repo. Reject traversal, absolute-path escape and symlink escape. Keep generation outputs fixed/validated, not arbitrary write destinations from model text. Explicit generation uses atomic replacement; checking is read-only. Do not fetch remote schema references or execute `go generate`, tests, plugins, or project binaries. |
| Runner authority and environment: `checks.yml`, Go module/tool pins, `tests/test_supply_chain_pinning.py` | Keep read-only permissions, SHA-pinned actions and nonpersistent checkout credentials. Set `GOWORK=off`, `GOTOOLCHAIN=local`, and controlled build flags; do not inherit injected `GOFLAGS`, overlays or a package-driver command. Separate established pinned-tool installation from target analysis. An unresolved dependency or tool failure fails the check. No operator dotenv loading, new credentials, privileged event, listener or Docker access. |
| Errors and outputs: existing Go check `Report`/finding patterns and command exit handling | Preserve exit 0 for success, 1 for findings, 2 for inability to check. Return contextual errors and render at the CLI through injected writers; no parallel exception hierarchy or product error DTO. Print rule ID, safe relative location, import/symbol identifier, and model fix-it text. Use the declaration/model location for non-import findings. Never echo source lines, literals, parser excerpts or raw analyzer stderr. Escape control characters and Actions command syntax in untrusted names/messages. |
| Logs, secrets and persistence: ADR-065 and existing CI output/artifact owners | Findings need no runtime telemetry or new logger. Treat parser errors, subprocess errors, paths and model messages as potential leak/annotation inputs. Existing Git errors include raw stderr: sanitize at this boundary rather than blindly printing wrapped errors. Use synthetic secret canaries to verify every failure sink. Persist only reviewed source/generated docs and existing disposable CI state, not an audit database or a new service. |
| Runtime auth, env grants, schemas and storage: `api/deps.py`, MCP common validators, `core/config.py`, `core/env.py`, deployment environment bindings, `utils/{pathsafe,strict_json,redaction}.py`, `core/runstore.py` | These product layers are not traversed by static architecture tooling. Do not import them to obtain validation/redaction, reproduce their DTOs, load lab secrets or change their behavior. The Go tool follows ADR-065's file/input/output rules in its own module. Import compliance is no evidence of authentication, secret protection or persistence safety. |

## Enforcement evidence and limits

Architecture validation must actually run over the full scope on every PR,
including docs-only PRs. Existing Go jobs are selected by changed inputs;
reusing their conditions would miss this contract. Extend `checks.yml` and
`.github/branch-protection-baseline.json` together, retain existing status names
and gates, and verify live required checks on `go-cutover`. A baseline edit is
not proof of live enforcement. Keep `tools/ci/select_checks.py`'s failure handling
and coverage closure; do not force unrelated expensive lanes just to run this
static check. No successful skip may stand in for missing analysis.

Reuse `tools/gates` testscript fixtures, standard `testing`/go-cmp, and focused
contracts in `tests/test_{platform_ci_gates,lilrae_ci_selection,supply_chain_pinning}.py`.
Every modeled rule needs a passing and failing fixture with its exact fix-it
message. Cover malformed inputs, discovery gaps, `internal/` visibility, test
imports, build variants, module replacement, undeclared model amendments,
omitted changed packages, stale diagrams/configuration, tool failure and secret
canaries. Negative packages belong in fixture data, not a baseline or an
unchecked first-party package. Prove the actual CLI and CI invocation as well
as model evaluation; a generated config snapshot alone proves no enforcement.

## Design gaps to settle before implementation

The existing design removes generated analyzer configuration altogether. The
issue explicitly asks for a model compiler and generated-configuration parity.
ADR-065 supports direct checking, but that does not silently remove an issue
criterion. Delivery must reconcile the contract with this choice, naming which
model-derived artifacts constitute compilation and what CI compares. Do not add
an unused generated file just to claim compliance. The preflight does not
independently verify the design note's external scanner experiments.

The design's blanket promotion exemption based on a branch name is unsafe.
An untrusted fork can use the same name, and even a same-repository promotion
can contain changes that never passed this gate. The whole-repository check
always runs. Any design-comparison exception needs authenticated event/repo
identity and evidence for the changes it covers; a branch spelling alone is
not evidence. Define automated dependency PR behavior without forcing a fake
issue or weakening checks. Wire explicit base/head identities rather than
assuming the proposed `-base` argument and checkout identify both.

The design front matter has no explicit removal representation, and
`component:<name>` only identifies the part that changed. Specify how a deleted
package is distinguished from a planned package and how base-to-head values
make an architecture amendment reviewable. Detect model changes semantically,
including rule messages, layer edges and public declarations. A listed component
name must not conceal an unrelated permission expansion. Define how the first
model is checked when the base revision has no model; a bootstrap case must not
turn missing base input into a permanent bypass. Keep one set of schema and
semantic definitions; the issue asks for a schema, not just an informal example.

The public-package heuristic needs a test-only classification: `tools/gates`
contains only `package gates_test`, is outside `internal/`, and the draft has
`public: []`. A test harness is not an exported API. Likewise, identify commands
by package semantics, not just a `cmd/` directory: `web/caddy-build` is `main`.
Keep production and test dependency facts distinguishable even when component
permission applies to both; future production code must not gain test-only
privileges accidentally. Vendored source classification must not authorize
arbitrary first-party local replacements or paths outside this repository.

Strict validation cannot depend on a valid model for its own safe error message.
For missing/invalid model input, return a bounded tool diagnostic with safe
location and exit 2. For an evaluable rule violation, use the validated model's
fix-it and exit 1. Define that boundary consistently with the design's
`invalid-model` rule. Quoting an import alone does not secure output: YAML
decoders, Go parser errors, Git stderr, Markdown/Mermaid labels, file paths and
model fix-it text are all untrusted output surfaces. Validate or escape each
sink, never render raw parser input, and cap diagnostic volume. Diagram syntax
must remain data; no active links or directives supplied by a model label.

Finally, `.gc/plan-rules.md` currently says its rules apply during planning,
after the canonical design step. Adding a sentence there alone does not prove
the checker ran before `gc_record_implement_design`. Resolve the existing
workflow integration boundary and show invocation evidence. The command,
generated diagram and required status are absent from this checkout. Live
branch protection has not been verified by this inspection.

There is no product Go package yet; developer tooling and Caddy are real inputs.
Zero findings must cover them, not an empty product-only scan. No suppression
or policy relaxation may hide a real violation. A verified false-positive
exception needs the issue's specific explanation and review.

This preflight changes guidance only. Delivery may add the model/schema,
compiler, checks, generated settings/diagrams, workflow integration and their
fixtures. It must not port product code, refactor runtime boundaries, alter
public/persisted contracts, replace pack admission, remove ADR-064's Python
checker, merge a PR, or claim SYS-009/SEC-008 verification from import findings.
Local verification stays targeted plus staged `pre-commit run`; CI owns full
repository analysis, coverage and prose checks. The delivery targets `go-cutover`.
