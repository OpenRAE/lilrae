# Lab fixture pack

Use this guide to maintain the owned fixture pack for generic lab-machinery tests.
It covers pack admission, content resolution, realization, and the live gate.
Issue #985 introduced it to keep those tests independent of released TechVault content.

## Where it lives and why

Keep the fixture in `tests/fixtures/packs/materialization-envelope/`.
It is not published. This repository and its CI are its only consumers.
Publish only when an external consumer needs it, while retaining this canonical test copy.

The pack contains:

| Member | Purpose |
| --- | --- |
| `sdl/materialization-envelope.sdl.yaml` | The canonical product-neutral scenario: #993's causal chain of inline content, service unit, listener, loopback publication, and one workflow |
| `assets/content/notice.txt` | A small file artifact for pack-file resolution and satisfaction tests |
| `assets/content/tree.tar` | A one-member archive for pack-directory extraction tests |
| `pack.yaml`, `docs/provenance-ledger.yaml` | Pack identity and provenance, as env-packs requires |
| `associated-artifacts.json` | The content manifest binding every member above to its SHA-256 digest |

The scenario's `name` is the pack identity, because env-packs binds the content
manifest to it.

## How tests use it

`tests/fixture_pack.py` admits the pack with the production resolver,
`env_pack_bundle(staging_root, identity, source_pack=...)`. That resolver stages
an isolated copy and runs env-packs' own `validate_pack` and content-manifest
gates, exactly as it does for a released pack. The module is import-safe: it
reads no project `.env` and runs no lab script.

Generic resolver, content, realization, and live-gate cases use the fixture.
TechVault cases separately pin released content identity, evidence contracts, plugin compatibility, and realization, static, and live gates.

## Choose the input for a new test

Use these steps when a new test needs a scenario or pack input.
[The pack boundary](../architecture/pack-boundary-design.md#test-ownership)
gives the two test groups.

1. Find the code that the test checks.
2. If the test checks the TechVault adapter or the released pack, put it in `tests/techvault/`.
3. Otherwise, use `admit_fixture_pack()` for admission and realization cases.
4. For a smaller case, use neutral RAES models, deployment values, or API data.
5. Use the released-pack fixtures in `tests/techvault/conftest.py` only in `tests/techvault/`.
6. Copy nested declarations before a test changes a shared scenario or realization.
7. Run `uv run python tools/check_pack_boundary.py` before you commit.

A generic test must not name the released pack, its hosts, its accounts, or its credentials.
Generic UI fixtures use the types in `web/src/lib/types.ts` and neutral values.
Neutral test data must not change a persisted format or sealed evidence.

The clean-install boot job copies the same SDL into a fresh project and starts
it with `--scenario-path`. An explicit path is a project-tree selection, so that
job proves the installed wheel's lifecycle, not pack admission. Unit tests
prove admission.

## Changing the pack

Every member is bound by its digest.
Run fixture regeneration and behavior checks only in CI or an approved isolated VM.
After an intended member edit, update the manifest:

1. Edit the member. To add a member, also add its entry to
   `associated-artifacts.json`, since the manifest must list the pack's exact
   inventory.
2. Re-derive the manifest with env-packs' own tooling:

   ```bash
   uv run python - <<'EOF'
   import json
   from pathlib import Path

   from raes_env_packs import derive_pack_content_manifest

   pack = Path("tests/fixtures/packs/materialization-envelope")
   derived = derive_pack_content_manifest(str(pack))
   (pack / "associated-artifacts.json").write_text(
       json.dumps(derived.model_dump(mode="json"), indent=2) + "\n",
       encoding="utf-8",
   )
   EOF
   ```

3. In CI or an approved isolated VM, run `tests/test_scenario_bundle.py` and affected fixture consumers.

Never re-derive the manifest to make an unexplained byte change pass: a failing
digest means something changed a member. `.gitattributes` marks the pack
`-text`, so Git never converts its line endings.

Keep the pack small. A new realization regression adds one declaration to the
scenario and one effect assertion to the boot verifier, as
[boot realization coverage](boot-realization-coverage.md) describes. It does
not add a second scenario or a second pack.
