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
model_changes: []
---

# Issue #1779: Merge of dev into go-cutover after #1763 design

This design records the Go changes that the merge of #1740 into `go-cutover`
needs. The front matter of this note is its design record. The
[#1747 configuration design](issue-1747-go-config-design.md) applies.

## Decisions

1. **Merge base.** #1763 was squash-merged, so git does not record the `dev`
   commit `d7be5deb9` in `go-cutover`. The merge uses that commit as its base.
   The pull request uses a merge commit, so `dev` becomes a parent of
   `go-cutover`.
2. **Configuration members from #1740.** #1740 adds `deployment.dedicated_vm`
   and `experiment.trial_episode_seconds` to `aptl.json`. `internal/config`
   decodes and checks them as the Python release does. Decision 10 of the
   #1747 design gives the details.
3. **No model change.** The change stays in the `configuration` component and
   uses only its existing dependencies.

## Threats

| Threat | Mitigation |
| --- | --- |
| The Go port accepts a configuration that Python rejects, or the reverse. | The decode tests cover each new member with accepted and rejected cases. |
| The published schema rejects a configuration that the release writes. | The conformance cases check the resolved configuration against the schema. |
