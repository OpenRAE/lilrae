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

1. **History.** #1763 and #1780 were squash-merged. Thus `dev` is not an
   ancestor of `go-cutover`, although #1780 contains the #1740 changes. The
   repair is a merge commit with the `go-cutover` tip and the `dev` tip as its
   parents.
2. **Content.** `d7be5deb9` is the last `dev` commit that #1763 integrated. A
   merge of `dev` from that base changes `go-cutover` in one file only:
   `tests/test_trial_run.py`. There, `go-cutover` has the #1740 version and a
   deadline clock fix for a loaded host. The resolution keeps the `go-cutover`
   version. Thus the merge result has the same files as `go-cutover`.
3. **Merge method.** The maintainer merges the pull request with a merge commit.
   A squash merge repeats the defect. The
   [cutover contract](ci-verification.md#go-cutover-branch) gives this rule.
4. **Configuration members from #1740.** #1740 adds `deployment.dedicated_vm`
   and `experiment.trial_episode_seconds` to `aptl.json`. `internal/config`
   decodes and checks them as the Python release does. Decision 10 of the
   #1747 design gives the details.
5. **Run storage members from #1773.** #1773 adds
   `run_storage.free_space_reserve_percent` and
   `run_storage.capture_progress_timeout_seconds`. `internal/config` decodes
   and checks them as the Python release does. The resolved form of the
   percent uses the float text of the Python json module. Decision 10 of the
   #1747 design gives the details.
6. **Sonar finding on `go-cutover`.** The `go-cutover` push analysis of #1780
   reports `godre:S8193` in `internal/digest/digest_test.go`. The test declares
   an unnecessary variable in a condition. This change removes the variable.
7. **No model change.** The change stays in the `configuration` and `digest`
   components and uses only their existing dependencies.

## Verification

- `git merge-base --is-ancestor` shows that the `dev` tip is an ancestor of
  the merge commit.
- `git show --format=%P` shows the two parents of the merge commit.
- The merge commit has the same tree as the `go-cutover` tip. The checks of
  that tip apply to the files of the merge.

## Threats

| Threat | Mitigation |
| --- | --- |
| A squash merge delivers the files but not the history. | The pull request requires a merge commit. The ancestry checks above show the result. |
| The resolution drops a change from `dev` or `go-cutover`. | The merge from `d7be5deb9` shows one conflict only. The kept version contains the `dev` change. |
| The Go port accepts a configuration that Python rejects, or the reverse. | The decode tests cover each new member with accepted and rejected cases. |
| The published schema rejects a configuration that the release writes. | The conformance cases check the resolved configuration against the schema. |
