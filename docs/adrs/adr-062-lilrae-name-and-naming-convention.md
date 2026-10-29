# ADR-062: LilRAE Name and Naming Convention for New Code

## Status

accepted

## Date

2026-10-05

## Context

The APTL (Advanced Purple Team Lab) repository was transferred into the OpenRAE
organization and renamed to
[OpenRAE/lilrae](https://github.com/OpenRAE/lilrae). The transfer retained the
source, Git history, features, and issue tracker.
[Issue #1229](https://github.com/OpenRAE/lilrae/issues/1229) records the
tracker reconciliation, and
[issue #1230](https://github.com/OpenRAE/lilrae/issues/1230) updates repository
location wiring.

Public-facing documentation still introduced the project as APTL. Users who
arrive through the renamed repository need to recognize LilRAE as the same
project. The code, packaging, configuration, and runtime still carry `aptl`
identifiers that existing installations, scripts, and records depend on.

[ADR-054](adr-054-lilrae-core-and-experience-ownership.md) describes APTL and
LilRAE as one product across a rename and proposes a broader capability
ownership model. It remains proposed. This ADR records only the completed
repository and name change and the limited naming transition; it does not
accept ADR-054 or claim that its migration work is complete.

## Decision

LilRAE is the project's name. APTL is its former name. They identify one
project; there is no second backend, wrapper, or product layer.

### Limited public naming transition

The transition changes only the public entry points needed for users to
recognize LilRAE, and explains the legacy name where users still meet it:

| Surface | Change |
| --- | --- |
| `README.md` | Heading, introduction, safety lead sentence, and a prominent note explaining the move and rename and the retained package and command names. |
| `docs/index.md` | Heading, introduction, safety warning, the same rename note, and the install task label. |
| `docs/getting-started/installation.md` | Names LilRAE at the install step and explains why the package is `aptl-labs` and the command is `aptl`. |
| `mkdocs.yml` | Site title, site author, and the install navigation label. |

Other current pages, generated help, and interface text continue to say APTL
where they do. The rename note makes those occurrences unambiguous, so they
are not changed by this decision. Repository URLs belong to #1230.

### Retained compatibility identities

The rename does not change any executable or persisted identity, including:

- the `aptl-labs` distribution, the `aptl` import root, and the `aptl` and
  `aptl-misp-suricata-sync` commands;
- the `aptl.*` entry-point groups;
- `aptl.json`, configuration fields, `APTL_*` environment variables, and the
  `.aptl` state directory;
- container, image, network, volume, and label names, Compose project names,
  and backend target strings;
- schema identifiers, run records, archives, signatures, and evidence;
- CLI help text, web interface titles, API descriptions, and MCP server
  descriptions;
- quality-gate project keys and the `.ground-control.yaml` project identity.

A future change to any of these needs its own compatibility and migration
decision. No alias package, compatibility shim, second import root, duplicate
configuration schema, or name toggle is introduced.

### Successor decision: distribution from 8.0.0 (#1367)

Issue #1367 supersedes only the retained `aptl-labs` distribution clause and
current distribution-related install, upgrade, and recovery wording above.
`aptl-labs` 7.0.0 is the final legacy release; the successor distribution is
`lilrae` from 8.0.0. This decision authorizes the cutover; it does not assert
that 8.0.0 has published. Release-please continues to own version selection.

The successor ships the same import packages, commands, entry points, extras,
and bundled asset contract. All other executable, configuration, runtime,
schema, and persisted identities remain unchanged. Installed-provider
provenance records the actual distribution; historical evidence, fixtures,
and the closed legacy startup-reset receipt classifier retain their names.
Migration removes the old distribution before installing the successor;
rollback removes the successor before restoring pinned `aptl-labs==7.0.0`.
No alias package or dual installation is supported. The
[#1367 preflight](../architecture/issue-1367-distribution-cutover-preflight.md)
records the release and consumer boundaries; #1234 owns post-release checks
and legacy archival.

### Successor decision: command name (#1402)

Issue #1402 supersedes only the retained `aptl` and `aptl-misp-suricata-sync`
command clause, the retained CLI help text clause, and the current command
wording above. The
[#1402 preflight](../architecture/issue-1402-command-rename-preflight.md)
records the design guardrails.

| Old command | Primary command |
| --- | --- |
| `aptl` | `lilrae` |
| `aptl-misp-suricata-sync` | `lilrae-misp-suricata-sync` |

The primary commands enter the existing implementations: the one Typer app in
`aptl.cli.main` and the one sync service `main()`. CLI help text, the root
help, and the `--version` output name LilRAE. There is no second command tree.

#### Identity boundary

The command name changes. These identities do not change:

- the `aptl` import root and the `aptl.*` entry-point groups;
- `aptl.json`, its fields, `APTL_*` environment variables (including
  `APTL_SEAT_CLI`), and the `.aptl` state directory;
- Compose project, container, image, network, volume, and label names,
  including the `aptl-misp-suricata-sync` container name;
- the RAES backend identity `aptl`, schema identifiers, protocol selectors,
  run records, evidence, and the release-please component;
- serialized and internal field names, such as `aptl_executable`, whose value
  can now be a `lilrae` path;
- web interface titles, API descriptions, and MCP server descriptions.

The TechVault environment pack installs its own frozen copy of the sync
service. Its package metadata names only `aptl-misp-suricata-sync`, so the
realization probe for that pack content keeps the pack-supplied name. A pack
change, not this decision, can rename it.

#### Deprecation policy

- `aptl` and `aptl-misp-suricata-sync` stay as aliases through all 8.x and 9.x
  releases. LilRAE **10.0.0** removes them;
  [#1403](https://github.com/OpenRAE/lilrae/issues/1403) tracks the removal.
- Each alias invocation writes one fixed notice to stderr before argument
  parsing. The notice names the replacement and the removal release. It also
  prints for `--help`, `--version`, and usage errors.
- Alias stdout, `--json` output, and exit status are identical to the primary
  command. The notice never goes to stdout and never adds a JSON field.
- `LILRAE_SUPPRESS_APTL_DEPRECATION=1` hides the notice. Other values leave it
  on. It is a process-local presentation control, not a configuration field.

#### Generated artifacts and migration

| Artifact | Migration |
| --- | --- |
| Guest forced-command policy (`authorized_keys`) | New generations name the `lilrae` executable. Earlier generations name `aptl` and keep working through the alias until 10.0.0. |
| Host MCP client configurations | They launch pinned SSH, not the CLI, so they do not change. |
| Offline seat image launchers | New images install `/usr/local/bin/lilrae` and `lilrae-misp-suricata-sync`, and keep the alias launchers. First boot, the golden-image scan, and seat qualification call `lilrae`. Signed images keep their bytes; replace them through the normal image lifecycle before 10.0.0. |
| Container commands | The web API image runs `lilrae web serve`. The sync image enters through `lilrae-misp-suricata-sync`. |
| Scripts, CI, and current docs | They call `lilrae`. The clean-wheel CI job proves both names and the notice. |

#### Release impact

Adding the primary commands is a `feat:` change. Release-please owns
`CHANGELOG.md`, so the delivery PR title names the 10.0.0 removal release to
put it in the generated entry. Removing the aliases is a breaking change in
10.0.0 under #1403.

### Naming convention for new code

Use `lilrae` as the naming convention for new code going forward. A new
top-level identity, such as a new module, package, service, environment
variable, resource name, or configuration file, uses `lilrae` (`LILRAE_` for
environment variables, LilRAE in prose).

When new code extends an existing interface, it follows that interface's
current identifiers. Code inside `src/aptl/` still imports through `aptl`.
Extensions register through the existing entry-point groups. New fields join
existing configuration models under their current names. A new identifier
that participates in an existing contract follows that contract rather than
introducing a parallel `lilrae` spelling.

The repository's planning rules in `.gc/plan-rules.md` carry
this convention as a mandatory plan constraint.

### Historical records

Accepted ADRs, preflight notes, review records, requirement history, changelog
entries, and evidence keep the names they were written with. Event listings
and talk titles accepted under the APTL name keep that name.

## Consequences

- Users arriving at the renamed repository or documentation site see LilRAE
  first. From #1402 the command is `lilrae`, and the `aptl` alias tells
  existing users to move before 10.0.0.
- Mixed naming remains on secondary pages and in technical identifiers. The
  rename note and this ADR explain it; a corpus-wide sweep is deliberately
  avoided.
- New code gains a single, stated naming rule without breaking existing
  installations or interfaces.
- Renaming the import package, configuration, or runtime identities remains
  open work that requires its own decision, release, and migration guidance.
  The distribution (#1367) and command (#1402) successor clauses close those
  two parts.
