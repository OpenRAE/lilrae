# Diataxis adoption

## Scope

[Issue #1662](https://github.com/OpenRAE/lilrae/issues/1662) defines this design.
The [milestone](https://github.com/OpenRAE/lilrae/milestone/45) holds the
implementation issues. The original design and delivery scopes remain in Git history.
The [documentation inventory](documentation-assignments.md) records the reconciled candidate paths and source checks.

Apply Diataxis to all repository-owned documentation. Include the published
site, root policies, nested READMEs, agent guidance, and documentation in source
files. Include the maintained sources of generated documentation.

## Reader needs

Use the [Diataxis compass](https://diataxis.fr/compass/) to classify content.
Each maintained page serves one reader need. Split mixed pages where necessary.
Link to related forms instead of copying their content.

| Form | Reader need | Existing starting point |
| --- | --- | --- |
| Tutorials | Learn by completing a safe exercise | First-lab quick start and workshop walkthrough |
| How-to guides | Complete a specific task | Installation, deployment, recovery, and contribution guides |
| Reference | Look up exact facts | CLI, MCP, API, configuration, and schema descriptions |
| Explanation | Understand reasons and relationships | Architecture descriptions and ADR rationale |

Keep MkDocs, its current theme, and its existing publishers. Keep Home and use
the four forms as reader routes in `mkdocs.yml`. Start each route with real
content. Do not add empty sections, a new documentation system, or a second
navigation file.

Keep existing file paths and heading links where possible. Navigation can group
pages without moving files. If a split changes a useful URL, retain a small
entry page at the old path with links to the new material. Root policy files
keep their standard names. They can link to the relevant reader route.

## Writing and verification

Keep the existing Vale installation and Google error checks.
Use the pinned shared package described in the [toolchain Reference](../reference/documentation-toolchain.md).
Its selected STE rules cover sentence length, paragraph length, and contractions. Disable Google contraction suggestions.
Do not add write-good or another passive-voice gate.

Use one shared user-level `documentation` skill for Claude Code and Codex.
Issue #1664 explicitly authorizes this skill. Keep one canonical copy outside
repository version control and link both clients to it.
Do not add a custom checker, remote analyzer, or dictionary-import pipeline.

The tools assist the writer. They do not establish Diataxis or full
[ASD-STE100](https://www.asd-ste100.org/) conformance. Review reader purpose,
approved words, sentence limits, active voice, and technical terms separately.
Use the official STE writing rules and dictionary. Do not copy the copyrighted
dictionary into this repository. Keep code, command names, and literal output
exact.

Record technical names without changing the names used by the code.

Every issue that changes documentation has this acceptance criterion:
**The documentation is rewritten to conform to ASD-STE100 Simplified Technical
English.** Each rewritten section must also be checked against the code.
The code is the ground truth. Record source paths, revision, checks, and
corrected differences in the delivery PR.

Run Vale on changed documents during the edit. Run only fast staged checks in
pre-commit. CI owns whole-tree prose checks and the strict MkDocs build.
Behavior tests and lab exercises run only in CI or an approved isolated VM.

Reuse the existing publishing, navigation, and interface correspondence tests.
Update them when the documented behavior or routes change. Do not add tests
that only repeat a sentence from a document.

Keep the corpus STE report informational because it includes preserved source records.
Require rewritten maintained prose to pass the selected rules. `tools/ste-lint.sh` uses explicit paths and
`--fail-over 0`. Add finished pages to `.ste-required.txt` as each rewrite ships.
Check partial rewrites through standard input.

Use [the documentation guide](../contributing-documentation.md) for editing commands.
[ADR-038](../adrs/adr-038-docs-style-lint-and-published-site.md) records the local
and CI boundaries. The documentation inventory links final page routes and source checks.

## Records and generated material

Classify dated requirement, review, preflight, and test records as historical
Reference. State their date, source revision, and current status. Rewrite owned
narrative in STE without changing the recorded facts or decision meaning.
Check historical claims against their source revision. Check claims about
current behavior against the candidate code. Link superseded decisions to
their replacements.

Preserve exact evidence, quoted outputs, executable fixtures, generated release
notes, license text, and third-party notices. These are source material, not
editable instructions. Present them as linked Reference material with clear
STE descriptions. Change maintained generator prose at its source. Do not
change `CHANGELOG.md` or release versions by hand.

No maintained prose is excluded because it is hidden, old, or outside `docs/`.
The [inventory](documentation-assignments.md) covers pages, mixed sections, source declarations, and preserved records.
Root policies keep their standard paths.
Agent guidance uses existing prose rules with a narrow exception for precise tool names.
The original delivery breakdown and dependency readback remain in the [design issue](https://github.com/OpenRAE/lilrae/issues/1662).

## Implementation issues

The [inventory](documentation-assignments.md) records delivery provenance and final reader routes.
The current contributor workflow is [Write documentation](../contributing-documentation.md).

### Backlog verification

The final delivery checked GitHub's blocking API: #1664, #1665, #1666, and #1667 were closed.
Their four blocking edges on #1668 remained present.
The original migration backlog remains in the issue history; it does not define new work.
No new hosting or external text processing is required.

## Sources

- [Diataxis compass](https://diataxis.fr/compass/)
- [Diataxis incremental adoption guidance](https://diataxis.fr/how-to-use-diataxis/)
- [ASD-STE100 official source](https://www.asd-ste100.org/)
- [ste-cli source and MIT license](https://github.com/TudorAndrei/ste-cli/tree/v0.10.1)
