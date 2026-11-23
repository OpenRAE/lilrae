---
name: wave-issue-coverage
description: Ensure each DRAFT requirement in a selected wave has a linked GitHub delivery issue. Requires Ground Control MCP and gh.
---

# Cover a requirement wave with issues

Use this workflow when the user requests issue coverage for a wave.
Process requirements sequentially. Do not delegate or run parallel writes.

## Inputs

Accept a wave number or `all`.
For `all`, process waves from the lowest number to the highest.

## Preconditions

1. Read `.ground-control.yaml` with `gc_get_repo_ground_control_context`.
2. Use its `project` and `github_repo` values for repository operations.
3. Confirm the Ground Control MCP tools are available.
4. Confirm `gh auth status` reports access to that repository.
5. Read the repository's issue instructions and requirement-file format.

## Workflow

### 1. Resolve the requirement list

Read `docs/requirements/<UID>/requirement.md` files.
Select files whose front matter has `status: DRAFT` and the requested `wave`.
Keep each exact UID, title, type, priority, wave, and path.
Do not synthesize a UID or substitute an internal database identifier.
The requirement files and their `## Traceability` sections are authoritative.

### 2. Choose progress tracker

For at most 25 requirements, use the client's task tracker when available.
For larger lists, use a checkbox file under `/tmp/wave-issue-coverage-<wave>-<timestamp>.md`.
If the client has a task tracker, link that file from one active progress task.
Update the tracker after each requirement.

### 3. Process sequentially; DO NOT parallelize

For each requirement:

1. Read its `## Traceability` section for `GITHUB_ISSUE` links.
2. Search GitHub for the exact UID:

   ```shell
   gh issue list --repo <github_repo> --state all --search "<UID> in:title,body" --json number,title,state
   ```

3. If there is no UID match, search one to three strong terms from the requirement.
4. Read each candidate issue and determine which clauses it covers.
5. Reuse an issue that covers the requirement. Do not create duplicate delivery work.
6. If coverage is partial, preserve its link and create a separate issue with explicit remaining acceptance criteria.
7. If no issue covers the work, use `gc_create_github_issue` with the exact UID, project, and repository path.
8. Inspect any returned `traceability_error`. A created issue alone does not prove the link succeeded.
9. Add missing requirement scope with `gc_update_issue_requirements`, `operation="add"`, and the exact UID.
10. Do not edit the issue's Requirements section with `gh issue edit`.
11. For a DRAFT requirement, record the missing issue link as `DOCUMENTS` in the requirement's `## Traceability` section.
12. Preserve existing links and lifecycle status. Deliver requirement-file edits through the repository's normal reviewed PR workflow.
13. Apply labels as described below.
14. Read back both the issue scope and requirement link before marking the item complete.

A link uses the repository's existing format:

```text
- DOCUMENTS → GITHUB_ISSUE `#<number>` (<issue title>)
```

### 4. Apply labels

Add `requirement` and `wave-<N>` to each issue handled by this workflow.
If needed, create the wave label:

```shell
gh label create wave-<N> --repo <github_repo> --description "Wave <N> requirement" --color B60205
```

Add one to three relevant labels from the repository's existing labels.
Do not create topic labels. Preserve labels already present.
Do not use tracking, epic, or umbrella issues; use milestones to group work.
Use GitHub's blocking API for dependencies.

### 5. Report back

Report the requirement count, existing coverage count, and created issue count.
State any link or publication failure that prevents complete coverage.
Do not report a local requirement edit as merged traceability.

## Notes

`gc_create_github_issue` selects `DOCUMENTS` for non-ACTIVE requirements.
Its returned traceability result determines whether manual repair is needed.
DRAFT status does not authorize an `IMPLEMENTS` claim.

Only `gc_update_issue_requirements` writes an existing issue's Requirements section.
Removing scope needs the user's explicit decision; this workflow only adds scope.

## Quick reference; MCP calls

```text
gc_get_repo_ground_control_context(repo_path=<absolute repo path>)
gc_create_github_issue(uid=<exact UID>, project=<project>, repo_path=<repo path>)
gc_update_issue_requirements(repo_path=<repo path>, issue_number=<number>, operation="add", requirement_uids=[<exact UID>])
```

Before using a tool, check its current input schema.
Do not call retired requirement-list or backend traceability tools.
