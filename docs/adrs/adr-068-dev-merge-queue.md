# ADR-068: Merge Queue for the dev Branch

## Status

accepted

## Date

2026-11-11

## Reader boundary

This Explanation records design reasons and constraints.
`.github/branch-protection-baseline.json` records the intended branch settings.
The live GitHub branch settings are the enforcement authority.
[CI verification](../architecture/ci-verification.md#dev-merge-queue) describes maintained use.

## Context

`dev` required strict status checks.
Each merge into `dev` made the other open pull requests out of date.
Each update ran the full CI again.
[Issue #1735](https://github.com/OpenRAE/lilrae/issues/1735) moves `dev` to a GitHub merge queue.

A merge group contains `dev`, the queued pull requests in front of it, and the pull request.
GitHub reports a required check on a merge group only when its producer runs on the `merge_group` event.
If a required check does not report, the queue does not merge the pull request.

## Decision

1. Pull requests to `dev` merge through a GitHub merge queue.
   `main` and `go-cutover` do not use a merge queue. Merges into `main` stay manual.
2. `dev` does not require strict status checks.
   The queue tests each pull request against the latest `dev`.
   `main` and `go-cutover` keep strict status checks.
3. The queue merges with a merge commit, as `dev` pull requests did before.
   It builds and merges up to five pull requests in one group.
   Each pull request in the group must pass its checks.
4. Each workflow that reports a required `dev` context runs on the `merge_group` event for `dev`.
   No producer of a required context skips itself on a merge group.
   A skipped job reports success, so a skip would let a group merge without a real check.
5. Changed-input selection compares the merge group with `merge_group.base_sha`.
   The diff contains each change that the group merges.
6. The PR title lint reads the pull request number from the merge group ref name.
   It then validates the current title from the GitHub API.
   It fails closed on an incorrect ref, repository, or API response.
7. The SonarCloud quality gate analyzes the merge group ref as a branch.
   That tree is the `dev` tree after the merge.
8. `GitGuardian Security Checks` is not a required context for `dev`.
   The queue does not wait for it.
9. The `/implement` and `/quickfix` readiness step adds a ready pull request to the queue.
   The GRC workflow platform owns that step.
10. `tests/test_platform_ci_gates.py` fails when a required producer for a queued branch has no `merge_group` trigger.
    It also fails when a branch has no strict status checks and no merge queue.

## Alternatives considered

| Alternative | Reason for rejection |
| --- | --- |
| Keep strict status checks on `dev` | Each merge makes every open pull request out of date, and each update runs the full CI again. |

## Consequences

### Positive

- A merge into `dev` does not make the other open pull requests out of date.
- The queue tests the tree that `dev` gets after the merge.

### Negative

- A pull request runs the required checks two times: on the pull request and on the merge group.
- Each merge group analysis adds a short-lived branch to SonarCloud.

### Neutral

- The GitHub merge queue documentation does not say if an edit to the title or body removes a queued pull request.
  The title lint reads the title when the merge group runs.
