# Scoped tool qualification

This historical Reference preserves the issue’s recorded candidate and qualification limits.
Its commands and observations do not authorize workstation execution or qualify a later release.
Use [Verify a change](index.md) for current test boundaries.



The scoped-tool repair uses the existing participant action boundary.
The [design](../architecture/issue-1646-scoped-tool-affordances-design.md) describes its authority and data flow.

`tests/test_lilrae_scoped_tools.py` qualifies one shared red/blue policy.
The participants have distinct scoped affordances, action contracts, and native MCP mappings.
Each participant dispatches its own tool and fails to dispatch its peer's tool.

Both completion orders retain accepted histories.
The same cases cover participant selectors and role selectors.
These handlers are deterministic local substitutes.

They establish no live provider or operating-system isolation claim.

The installed test builds a wheel without network access.
An isolated child interpreter loads that wheel outside source imports.
It constructs the public LilRAE runtime target without changing its manifest.

The public RAE tool gate and installed binding checks must pass.
The child then executes the scoped scheduler cases.
The scheduler fixture uses stub provisioning services with the real LilRAE participant runtime.

It does not establish installed-lab provisioning qualification.

Malformed support strength, presence, semantic versions, and contracts fail public validation.
Missing scoped support and exceeded profile capacity fail the public capability gate.
Changed action digests, peer bindings, and wrong targets fail native planning.

Existing composition tests retain resource, crossing, and shared-time refusal before effects.
Targeted mutations remove the scoped declaration and the installed participant-scope check.
The corresponding behavioral tests must fail.


The installed test writes `candidate.json` into its pytest temporary directory.
It records the wheel SHA-256, distribution versions, scenario digest, implementation digest, and backend manifest digest.
The issue's qualification record pairs this output with the immutable Git tree and delivery commit.

The tested artifact stays local; no new hosting is required.
A release rebuild has its own artifact identity and needs separate byte-level qualification.
Configuration and scenario inputs in this test are synthetic and contain no credentials.


Reproduce the selected checks:

```bash
bash tools/run-targeted-tests.sh tests/test_lilrae_scoped_tools.py \
  tests/test_lilrae_tool_runtime.py tests/test_lilrae_tool_composition.py \
  tests/test_lilrae_participant_tools.py tests/test_lilrae_concurrent_participants.py \
  tests/test_lilrae_participant_architecture.py -q -s
```

The issue record states the exact dependency tuple for each run.
Full suites and installed-lab qualification remain in CI.
