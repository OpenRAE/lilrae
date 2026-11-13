<a id="historical-arsenal-provisioning-sources"></a>

# Review Historical Arsenal Provisioning Sources

Use this guide to inspect the August provisioning snapshots before proposing a current repair.
You need a checkout and the [branch audit](../../../docs/architecture/issue-1022-historical-branch-audit.md).
The result is a comparison against the current owning module, not a provisioned host.

The snapshots come from `b97746a50442289615c20d00ce5785847fcb34be` on `889-cortex-adr088-envpack`.
Their `.txt` suffix keeps them as non-executable references.
They preserve the boot service, fleet launcher, desktop setup, and temporary SOAR, Suricata, and Kali repairs.
They assume one baked AMI and cloud account.

1. Find the relevant snapshot and compare it with the audit.
2. Locate the current code owner for the behavior.
3. Check whether the current release already implements the repair.
4. If a change remains necessary, implement it in that owner through the normal issue workflow.
5. Verify changed behavior only in CI or an approved isolated VM.

The snapshots include broad Docker cleanup, fixed paths, default credentials, ignored failures, and a capture-admission bypass.
Do not execute them on a shared host or substitute them for `lilrae seat start`.
Use the [QA review guide](../../../docs/workshop/arsenal-2026/qa.md) to inspect the event's evidence.
