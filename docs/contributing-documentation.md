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

The shared `documentation` skill supports these steps in Claude Code and Codex.
Its canonical file is `~/.codex/skills/documentation/SKILL.md`.
The Claude directory `~/.claude/skills/documentation` links to that directory.
The skill is installed at the user level. Do not commit another copy here.

## Run writing checks

Run checks on explicit changed paths during editing:

```shell
bash tools/vale-lint-hook.sh docs/contributing-documentation.md
bash tools/ste-lint.sh docs/contributing-documentation.md
```

The STE wrapper installs the checksum-pinned `ste-cli` release `v0.10.1`.
The [upstream tool](https://github.com/TudorAndrei/ste-cli/tree/v0.10.1)
uses the MIT license. `tools/install-ste.sh` records its source and checksums.
The binary runs locally under `.tools/ste/0.10.1/`.
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
