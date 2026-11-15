# Release LilRAE

Use this guide to promote reviewed changes and release the Python package.
Release Please owns versions and `CHANGELOG.md`. Do not edit either by hand.
Use the [release contract](reference/release-contract.md) for title rules, baseline files, and publisher identities.

## Per PR (all contributors / agents)

1. Give the PR one Conventional Commit type and optional scope.
2. Use a lowercase subject. Do not combine types such as `fix(...) + docs:`.
3. Deliver feature PRs to `dev` through its squash merge queue.
4. Keep the repository's squash commit message blank, so the PR title becomes the commit subject.
5. Do not add a manual changelog or version edit.

[ADR-068](adrs/adr-068-dev-merge-queue.md) explains the queue and release-history constraints.

## Promoting `dev` to `main`

Feature PRs normally land on `dev`.
For the milestone 44 Go-port exception, follow [CI verification](architecture/ci-verification.md#go-cutover-branch).

1. Open the promotion PR:

   ```shell
   make devmain
   ```

2. Confirm its source is `dev`, target is `main`, and title is `chore(main): promote dev`.
3. Wait for its required checks and obtain the user's approval before merging into `main`.
4. Merge the promotion with a merge commit. Do not squash it.

The merge commit preserves feature subjects for Release Please.
The promotion also triggers the main-branch Scorecard workflow.
Use the [title reference](reference/release-contract.md#promotion-title) for GitHub's exact `Dev` fallback.

## How a release happens

1. Find the Release Please PR on `main`, titled `chore(main): release X.Y.Z`.
2. Keep its head commit fixed while qualifying the candidate.
3. Build its wheel and sdist from that exact commit.
4. Have a person complete every row of [release candidate manual QA](testing/smoke-test-plan.md).
5. Test the exact wheel and a clean checkout of the same commit.
6. Link the completed, redacted record from the release PR.
7. If the commit or an artifact changes, repeat both installation paths from clean state.
8. Merge the release PR only after the human QA record passes and merge approval is present.

The bot-created release PR might not trigger checks, or its runs might need approval.
Do not assume its required checks will run automatically.
The existing release procedure uses an administrator merge for this PR.
A PAT integration is needed if maintainers choose to enforce those checks automatically.

The merge creates the version tag and GitHub Release.
The publish job builds artifacts, generates an SBOM, records provenance, and publishes through PyPI OIDC.
It rebuilds at publish time. A later package installation does not prove identity with the tested candidate bytes.
For byte-identical promotion, change the release design to publish tested artifacts instead of rebuilding them.

After publication:

1. Find the automatic `main` to `dev` back-merge PR.
2. Confirm its title is `chore: back-merge <tag> into dev`.
3. Obtain the user's merge approval.
4. Use an administrator merge with **Create a merge commit**, outside the queue.
5. Do not squash the back-merge or assume bot-triggered checks will run.

The merge commit retains the release commit in `dev` history.
A squash can make the next promotion replay the version bump and conflict.

## Baseline

Use the [baseline reference](reference/release-contract.md#baseline).
Do not copy a current version into this guide.

## PyPI trusted publisher (one-time)

1. Confirm `raes` is already available on PyPI.
2. Open the `lilrae` project's Settings, then Publishing.
3. Set the trusted publisher to the [recorded identity](reference/release-contract.md#pypi-publisher).
4. Before a new project's first release, add that identity under Account, then Publishing, as a pending publisher.
5. Confirm the first upload creates the intended project.

Do not substitute other names; PyPI matches them against the OIDC token.

## Seat image cuts

Follow [the seat image procedure](reference/appliance-seat-launcher.md#building-the-image).
Preserve actual manual VM evidence for each cut.
Seat images have a separate build, qualification, signing, and GHCR publication process.
Release Please does not perform those steps or wait for a seat tag before its back-merge.
