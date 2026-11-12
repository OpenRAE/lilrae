# Write documentation

Use this guide to change LilRAE documentation. Start with the reader's task.

## Select a reader purpose

Use the [Diataxis compass](https://diataxis.fr/compass/) to select a purpose.
Use a Tutorial for a learning exercise. Use a How-to guide for an operating task.
Use Reference for exact facts. Use Explanation for reasons and relationships.
Split mixed content when this helps the reader.

Keep existing page paths and useful heading links. Add real pages to the
reader routes in `mkdocs.yml`. Keep Home. Do not add empty directories.

## Verify the facts

Read the relevant code, configuration, and supported interfaces before you edit.
Use [the architecture overview](architecture/index.md) and
[the interface reference](reference/cli.md) to find the owners.
Use the source revision for historical claims. Use candidate code for current claims.

Preserve facts, quantities, units, qualifiers, obligations, and conditions.
Keep technical terms, commands, identifiers, and literal output exact.
Do not invent an actor or strengthen a recommendation into a requirement.
Keep evidence, generated records, license text, and third-party notices intact.
Edit maintained generator prose at its source.

Record source paths, revision, checks, and corrected differences in the PR.
Use the [migration assignments](architecture/documentation-assignments.md)
to find the delivery issue. Newly added documentation also needs an owner.

## Write the change

Use one instruction per sentence. Put a condition before its action.
Keep instructions within 20 words. Keep descriptive sentences within 25 words.
Give each paragraph one topic and at most six sentences.

Put information in logical order. Use one consistent name for each thing.

Use [the official ASD-STE100 source](https://www.asd-ste100.org/) for rules
and vocabulary. Do not copy the specification or dictionary into the repository.
Use [Diataxis application guidance](https://diataxis.fr/how-to-use-diataxis/)
for incremental changes. Keep a small edit small.

## Set up the shared tools

Use Linux or macOS on x64 or arm64.
Install `bash`, `curl`, `tar`, Python 3, and `sha256sum` or `shasum`.
From the repository root, install the pinned package:

```shell
bash tools/install-doc-tools.sh
bash tools/ste-lint.sh docs/contributing-documentation.md
```

The first command prints the installed package directory.
The second checks an explicit page and installs the package's pinned ste-cli when needed.
No personal skill installation is needed for writing checks.

LilRAE pins [doc-tools v0.1.0](https://github.com/OpenRAE/doc-tools/releases/tag/v0.1.0).
Its source revision is `97866fad14d7fbb0d6752788ebdc5ae4f235573a`.
The archive SHA-256 is:

```text
125104c0cc535698d1cc9bba3e57883bdf9d87db6da346ff583967c4ce42de6c
```

`tools/install-doc-tools.sh` verifies that digest before extraction or execution.
The archive installs under `.tools/doc-tools/0.1.0/`.
The package separately verifies the ste-cli archive before installing its binary.
A failed download or checksum stops the check.
The package and binary caches remain trusted after installation.

The package uses the MIT license. Keep its `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `skills/documentation/LICENSE` intact.
Those notices identify the LilRAE, RAE, ste-cli, and skill guidance sources.
See the [package reference](https://github.com/OpenRAE/doc-tools/blob/v0.1.0/docs/reference.md) for platform checksums and source revisions.

## Install the documentation skill

The package supplies the existing shared `documentation` skill.
It supports reader-purpose selection, code verification, and meaning preservation.
Do not commit a copy here.
Existing user-level installations remain usable during migration.
Tool setup does not change personal skills or client settings.

For a new Claude Code installation, register the verified local marketplace from the repository root:

```shell
PACKAGE="$(bash tools/install-doc-tools.sh)"
claude plugin marketplace add "$PACKAGE"
claude plugin install doc-tools@openrae-doc-tools
```

The package marketplace uses a relative plugin source within the verified archive.
It does not fetch the skill through a mutable Git tag.
Keep the package directory while this marketplace is registered.
The [client installation reference](https://code.claude.com/docs/en/plugins/install) supports local marketplace directories.

For a new Codex installation, use its supported installer with the recorded source commit:

```shell
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo OpenRAE/doc-tools --path skills/documentation \
  --ref 97866fad14d7fbb0d6752788ebdc5ae4f235573a
```

Compare the installed skill and license with the verified archive:

```shell
PACKAGE="$(bash tools/install-doc-tools.sh)"
cmp "$PACKAGE/skills/documentation/SKILL.md" "${CODEX_HOME:-$HOME/.codex}/skills/documentation/SKILL.md"
cmp "$PACKAGE/skills/documentation/LICENSE" "${CODEX_HOME:-$HOME/.codex}/skills/documentation/LICENSE"
```

If either comparison fails, move the installed skill outside active skill directories before starting another session.
Investigate the difference before use. Do not accept the tag as a substitute for the commit and digest.

The Codex installer refuses an existing `documentation` directory.
The current personal location can remain `~/.codex/skills/documentation/SKILL.md`.
Claude Code can continue using its current link to that directory.

To migrate, first record existing directories and symlink targets.
Move the old directory and client links to a backup outside active skill directories.
Then install through the selected package route. Confirm that the client discovers one documentation skill.
Retain the backup until an authoring task succeeds.
For rollback, disable the package installation and restore the saved directory and links.

The [package installation guide](https://github.com/OpenRAE/doc-tools/blob/v0.1.0/docs/how-to-install.md) describes both client routes.

## Upgrade or roll back

1. Read the package release notes and `SHA256SUMS`.
2. Check the source revision and license notices.
3. Update the version and digest together in `tools/install-doc-tools.sh`.
4. Update the source record and client commit references in this guide and ADR-038.
5. Install into the new version directory. Keep the previous directory.
6. Run writing checks on explicit changed pages.
7. Run targeted documentation integration tests in CI or an approved isolated VM.

For rollback, restore the previous reviewed pin and its compatible invocation changes together.
Restore the previous skill reference if the skill changed.
Run the same checks. Do not weaken `.ste-required.txt` to make an upgrade pass.
An installation failure never selects an older cache automatically.

## Run writing checks

Run checks on explicit changed paths during editing:

```shell
bash tools/vale-lint-hook.sh docs/contributing-documentation.md
bash tools/ste-lint.sh docs/contributing-documentation.md
```

The STE wrapper delegates to the pinned package.
The package owns `.ste.yml`, the ste-cli version, and its platform checksums.
`tools/install-ste.sh` remains available as a thin installation command.
The binary runs inside the package's `.tools/ste/` directory.
No document text leaves the machine.

The selected rules cover sentence length, paragraph length, and contractions.
The wrapper sets `--fail-over 0`. A selected finding fails the command.
Other STE rules are disabled initially. Vale keeps the Google error checks.
Its contraction suggestions are disabled because they conflict with STE.

Inspect findings. Correct real problems. Preserve accurate technical text when
a finding is wrong. Document a narrow exception when necessary.
The checker assists review. It does not establish full STE conformance.

CI reports selected STE findings across tracked Markdown during migration.
Legacy findings do not fail this report. Rewritten pages listed in
`.ste-required.txt` must pass. Add pages to that list as each rewrite ships.
For a partial rewrite, check the rewritten passage through standard input:

```shell
bash tools/ste-lint.sh - < /path/to/rewritten-section.md
```

Keep exact source records outside the rewrite gate. Check their owned
descriptions and links. Do not suppress a real problem to clear a gate.

CI runs the strict MkDocs build and the corpus prose checks.
Behavior tests run only in CI or an approved isolated VM.
Use targeted test paths. Workstation pre-commit runs staged hygiene and secrets checks.
See [ADR-038](adrs/adr-038-docs-style-lint-and-published-site.md)
and the [contribution guide](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md).
