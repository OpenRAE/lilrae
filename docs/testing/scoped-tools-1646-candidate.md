# Scoped tool tested candidate

This record identifies the tested contract candidate for issue #1646.
It is available for consumer authoring validation.
The Git tree identifies the full source snapshot before this evidence record was added.
The delivery commit will carry the same production bytes.
The qualification applies to the local wheel below, not to a later release rebuild.

| Coordinate | Tested identity |
| --- | --- |
| Immutable candidate source tree | `85b675dae78e7136511527541e07d2637bb9475c` |
| Source baseline commit | `0edbfdacd1de5a401f7b338c757807836934c30d` on `dev` |
| Capability source SHA-256 | `682a3b3730cb1993c55169b23a825a1ad26ad934db4a440542ed0f8d01122daa` |
| Artifact | `lilrae-9.0.0-py3-none-any.whl` |
| Artifact SHA-256 | `83facfd8b9cb77c8e6c63a9891fdd804e496a2abe20a9c11878e0e6d4c19a4bb` |
| Distribution | LilRAE 9.0.0 |
| Python | CPython 3.14.7 |
| RAE | 10.6.0 and 10.6.1, independently tested |
| Environment packs | raes-env-packs 7.2.2 |
| Autonomous policy | `participant-autonomous-execution/v1` |
| Tool semantics | `participant-tool-profile/v1` |
| Implementation manifest digest | `sha256:222514fb14dc4ee88f63c757433338bfc8da9b77a49f587a6df8110cf0d2117b` |
| Installed backend manifest digest | `sha256:6c1520ac19fa80c30752e718e70d6a2e0ba919cd4a913967b3ec825488d67aaf` |
| Scenario digest | `sha256:36721b28d4f14400270c9b5c5894a00a8d176261b1bd65add700eae6828c5424` |

All 51 selected tests passed with the locked RAE 10.6.0 tuple.
All 18 scoped-tool and composition tests passed with RAE 10.6.1.
Both installed runs produced the artifact hash above.
The public target manifest passed capability admission without replacement or augmentation.
Participant and role selectors passed in both completion orders.
Each participant dispatched its own tool and failed to dispatch its peer's tool.
Unsupported composition, false claims, capacity overflow, and installed mismatches retained refusal.
Removing the scoped feature caused four regression failures.
Removing participant membership from the installed relation check caused the peer-binding regression to fail.
Both mutations were restored before qualification.

Native MCP handlers, prompts, and configuration are synthetic local fixtures.
No external MCP artifact, harness executable, provider request, or credential is part of this tuple.
No live provider, OS isolation, or installed-lab provisioning claim follows from these checks.
The [qualification method](scoped-tools-1646-qualification.md) gives the exact test commands and limits.

The [machine-readable record](scoped-tools-1646-candidate.json) pins the artifact and compatibility identities.
Run this candidate check from the repository root:

```bash
uv run --frozen --group build --no-default-groups --extra dev --extra web \
  python -m tests.verify_scoped_candidate
```

The verifier archives the exact recorded Git tree and builds that source in a private temporary directory.
It compares the wheel hash, installed capability bytes, dependency tuple, and contract digests with the machine-readable record.
It also executes both selector forms and completion orders against that installed artifact.
The source snapshot is retained by the `qualification-1646-source` Git tag.
Later source changes cannot change this candidate's qualification input.
