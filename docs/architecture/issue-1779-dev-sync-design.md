---
design: 1
issue: 1779
packages:
  - path: internal/config
    component: configuration
    imports:
      - github.com/OpenRAE/lilrae/internal/canonical
      - github.com/OpenRAE/lilrae/internal/securefile
    test_imports:
      - github.com/google/go-cmp
  - path: internal/digest
    component: digest
model_changes: []
---

# Issue #1779: Merge of dev into go-cutover after #1763 design

This design records the merge of `dev` into `go-cutover` after #1763. The front
matter of this note is its design record. The
[#1747 configuration design](issue-1747-go-config-design.md) applies.

## Decisions

1. **History.** #1763, #1780, #1784, and #1789 were squash-merged. Thus `dev`
   is not an ancestor of `go-cutover`, although `go-cutover` contains the `dev`
   changes to `fea7cad0b`. The repair is a merge commit with the `go-cutover`
   tip and the `dev` tip as its parents.
2. **Content.** `fea7cad0b` is the last `dev` commit that `go-cutover`
   contains. The merge from that base has no conflicts. It adds #1773, #1776,
   #1786, and the 10.2.0 release. Only
   `docs/reference/evidence-bundle-export.md` changed on both sides, and the
   merge keeps both changes.
3. **Merge method.** The pull request is a draft, so the automatic merge does
   not squash it. The maintainer merges it with a merge commit. The
   [cutover contract](ci-verification.md#go-cutover-branch) gives this rule.
4. **Configuration members.** #1740 adds `deployment.dedicated_vm` and
   `experiment.trial_episode_seconds` to `aptl.json`. #1773 and #1776 add
   `run_storage.free_space_reserve_percent` and
   `run_storage.capture_progress_timeout_seconds`. `internal/config` decodes
   and checks them as the Python release does, and the published schema gives
   them. Decision 10 of the #1747 design gives the details.
5. **Vectors.** #1773 removes the capture limits. It moves the collector
   registry schema to v4 and the capture plan schema to v3. The
   `collector-registration-digest` and `capture-plan` vectors follow it.
   TechVault writes native responses without a byte bound, so the
   `techvault-bounded-json` vectors keep only the readiness owner.
6. **Sonar finding on `go-cutover`.** The `go-cutover` push analysis of #1780
   reports `godre:S8193` in `internal/digest/digest_test.go`. The test declares
   an unnecessary variable in a condition. #1784 removes the variable.
7. **No model change.** The change stays in the `configuration` and `digest`
   components and uses only their existing dependencies.

## Verification

- `git merge-base --is-ancestor` shows that the `dev` tip is an ancestor of
  the merge commit.
- `git show --format=%P` shows the two parents of the merge commit.
- The decode tests cover each new member with accepted and rejected values.

## Threats

| Threat | Mitigation |
| --- | --- |
| A squash merge delivers the files but not the history. | The pull request is a draft and requires a merge commit. The ancestry checks above show the result. |
| The resolution drops a change from `dev` or `go-cutover`. | The merge from `fea7cad0b` has no conflicts. Each changed `dev` file has its `dev` content. |
| The Go port accepts a configuration that Python rejects, or the reverse. | The decode tests cover each new member with accepted and rejected cases. The #1747 design lists the deliberate strict rejections. |
| The published schema rejects a configuration that the release writes. | The conformance cases check the resolved configuration against the schema. |
