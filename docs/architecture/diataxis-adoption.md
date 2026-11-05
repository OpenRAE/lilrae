# Diataxis adoption

## Scope

[Issue #1662](https://github.com/OpenRAE/lilrae/issues/1662) defines this design.
The [milestone](https://github.com/OpenRAE/lilrae/milestone/45) holds the
implementation issues. This design does not perform the documentation rewrite.

Apply Diataxis to all repository-owned documentation. Include the published
site, root policies, nested READMEs, agent guidance, and documentation in source
files. Include the maintained sources of generated documentation.

The current tree has 516 tracked Markdown files. Most are under `docs/`.
The architecture, ADR, and requirement directories contain 364 files.
This count describes the design revision; it is not a completion threshold.
Check the full tracked tree again when each implementation issue starts.

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

Use the existing Vale installation and add the upstream
[write-good package](https://github.com/vale-cli/write-good). It has an MIT
license and supplies checks for passive voice and wordiness. Pin its source
revision. Check both a fresh style install and an existing Google style cache.
Do not add a custom tool or skill. Use existing contribution and agent guidance
to give agents the writing and verification steps.

Vale assists the writer. It does not establish Diataxis or full
[ASD-STE100](https://www.asd-ste100.org/) conformance. Review reader purpose,
approved words, sentence limits, active voice, and technical terms separately.
Use the official STE writing rules and dictionary. Do not copy the copyrighted
dictionary into this repository. Keep code, command names, and literal output
exact. Record technical names without changing the names used by the code.

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

Keep current Google error checks. Expose the selected write-good diagnostics
for changed prose without making old corpus warnings block the first tooling
PR. Review and resolve those diagnostics during each rewrite. The last issue
checks the full corpus. Amend
[ADR-038](../adrs/adr-038-docs-style-lint-and-published-site.md) when the tooling
and final policy change.

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
The tooling issue assigns each page and each mixed section. The final issue
checks those assignments against the then-current tracked tree.

## Implementation issues

Each row produces one complete delivery PR. A row owns any pages it creates
when it splits its source material, even when those pages use another form.
The tooling PR records exact page assignments within these scopes. The final
PR checks for omissions and documentation added during the migration.

| Issue | Owned content | Result |
| --- | --- | --- |
| [#1664](https://github.com/OpenRAE/lilrae/issues/1664) | Vale setup, authoring guidance, reader routes, and page assignments | Add proven tools first; amend ADR-038 |
| [#1665](https://github.com/OpenRAE/lilrae/issues/1665) | `docs/getting-started/`, deployment, troubleshooting, workshop, and workshop tool READMEs | Separate learning exercises from operating tasks |
| [#1666](https://github.com/OpenRAE/lilrae/issues/1666) | `docs/reference/`, components, containers, SDL, RAES, taxonomy, image catalog; READMEs under `containers/`, `mcp/`, and `src/`; scenario Markdown | Separate lookup facts, authoring tasks, and explanations |
| [#1667](https://github.com/OpenRAE/lilrae/issues/1667) | `docs/architecture/`, `docs/adrs/`, `docs/requirements/`, `docs/specs/`, and `docs/reviews/` | Separate current explanations from historical records |
| [#1668](https://github.com/OpenRAE/lilrae/issues/1668) | Root and hidden guidance; docs home, coding, release, testing, and security pages; other tool docs; source documentation and generated sources | Rewrite contributor content and verify complete coverage |

Original fixtures and upstream material remain exact under the source-material
rule above. Issue #1668 checks their descriptions and classification too.
Remove temporary migration notes after coverage is complete. Keep the short
authoring guidance and existing checks.

The GitHub blocking API records these dependencies:

- #1664 blocks #1665, #1666, #1667, and #1668.
- #1665, #1666, and #1667 also block #1668, which performs the final audit.

The three middle issues can proceed independently after the tooling issue.
Issue #1662 needs the design and backlog only; their later delivery does not
block this design PR. No new hosting or external text processing is required.

### Backlog verification

GitHub API readback on 2026-11-04 confirmed that issues #1664 through #1668
belong to milestone 45. Each issue body contains the STE rewrite criterion,
the section-by-section code check, and the existing-tools rule.

| Issue | Blocked by, from the GitHub API |
| --- | --- |
| #1664 | None |
| #1665 | #1664 |
| #1666 | #1664 |
| #1667 | #1664 |
| #1668 | #1664, #1665, #1666, #1667 |

The relationships were set through `gh api` with the issue IDs. Repeat the
readback from `repos/OpenRAE/lilrae/issues/{number}/dependencies/blocked_by`.
Read each issue's `milestone` and `body` fields from the issue API too.

## Sources

- [Diataxis compass](https://diataxis.fr/compass/)
- [Diataxis incremental adoption guidance](https://diataxis.fr/how-to-use-diataxis/)
- [ASD-STE100 official source](https://www.asd-ste100.org/)
- [Vale write-good source and license](https://github.com/vale-cli/write-good)
