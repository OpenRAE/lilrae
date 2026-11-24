# Release contract

This Reference lists the Python release inputs.
Follow [Release LilRAE](../releasing.md) for the procedure.

## PR titles

Use `<type>: <lowercase subject>` or one type with an optional scope.

| Type | Release effect |
| --- | --- |
| `feat` | Minor version |
| `fix`, `perf` | Patch version |
| `feat!` or `BREAKING CHANGE:` footer | Major version; minor while the project is at `0.x` |
| `docs`, `chore`, `refactor`, `test`, `ci`, `build` | No release |

Release Please reads Conventional Commit subjects on `main`.
Feature PRs use squash commits. Promotions and release back-merges use merge commits.
[ADR-068](../adrs/adr-068-dev-merge-queue.md) records the history and merge-queue decision.

## Promotion title

`make devmain` opens `dev` into `main` with `chore(main): promote dev`.
The title guard also accepts GitHub's exact `Dev` title for that same-repository branch pair.
This exception does not apply to forks, other heads or bases, or arbitrary titles.
`tools/check_pr_title.py` owns that validation.

## Baseline

`.release-please-manifest.json` and `pyproject.toml` record the baseline.
Release Please computes the next version from that baseline and later Conventional Commits.
It owns the manifest, version, and generated `CHANGELOG.md` edits.

## PyPI publisher

| Field | Value |
| --- | --- |
| PyPI project | `lilrae` |
| GitHub owner | `OpenRAE` |
| Repository | `lilrae` |
| Workflow | `release-please.yml` |
| Environment | `pypi` |

`.github/workflows/release-please.yml` owns release and publication jobs.
The current workflow rebuilds at publication time.
A matching version is not proof of matching candidate bytes.

## Package names

The distribution and command are `lilrae`.
The Python import package remains `aptl`.
Releases through 7.0.0 used `aptl-labs`; releases from 8.0.0 use `lilrae`.
The candidate package metadata still registers the deprecated command aliases.
Their planned removal target was 10.0.0; issue #1403 tracks removal.
Code determines the aliases available in a release.

Use the [installation guide](../getting-started/installation.md) for package migration.

## Seat artifacts

Seat VM images are separate artifacts.
Their process builds, qualifies, signs with Cosign, and publishes to GHCR.
The Python release workflow does not create or qualify them.
