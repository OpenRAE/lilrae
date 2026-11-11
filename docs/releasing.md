# Releasing aptl

[release-please](https://github.com/googleapis/release-please) automates
releases. Nobody runs a script, hand-edits the version, or edits
`CHANGELOG.md`.

## Per PR (all contributors / agents)

- **Squash-merge** PRs so the PR title becomes the commit on the branch.
  The `dev` merge queue squash-merges each PR
  ([ADR-068](adrs/adr-068-dev-merge-queue.md)). The repository sets the
  squash commit message to blank, so the commit is the PR title only. A merge
  commit puts the PR title in its body. Release Please then reads the change
  two times and writes it two times in `CHANGELOG.md`.
- The PR title must be a **Conventional Commit** (`<type>: <lowercase subject>`).
  These are the bump rules:
  - `feat:` → minor.
  - `fix:` / `perf:` → patch.
  - `feat!:` or a `BREAKING CHANGE:` footer → major (demoted to minor while
    `0.x`).
  - Other types (`docs`, `chore`, `refactor`, `test`, `ci`, `build`) → no
    release.
- Use one Conventional Commit type and scope only. Release Please cannot parse
  compound titles such as `fix(...) + docs:`.
- **Do not** edit `CHANGELOG.md` or the version. Release Please owns both.
  Feature PRs never touch `CHANGELOG.md`, so concurrent PRs never conflict on
  it.

## Promoting `dev` to `main`

Feature PRs land on `dev`. Nothing releases until a promotion moves `dev` to
`main`.

Milestone 44 is the exception. Its PRs land on `go-cutover` and use a type
that does not release. Go port 31 merges `go-cutover` into `dev` with a merge
commit, so Release Please keeps each commit subject. See
[CI verification](architecture/ci-verification.md#go-cutover-branch).

Open the promotion PR with:

```bash
make devmain
```

That command creates a `dev` → `main` PR titled `chore(main): promote dev`.
The title is fixed, not free-form, because it is unambiguous. `chore` is a
no-release type, so the promotion never computes a version bump of its own.

GitHub's web and API flows can generate the branch title `Dev` instead. The
PR-title guard accepts that fallback only for the exact same-repository
`dev` → `main` branch pair in the event. The normal Conventional Commit policy
still applies to forks, differently named heads, other base branches, and
arbitrary titles.

**Merge the promotion with a merge commit. Do not squash it.** This is the one
place in the workflow where squashing is wrong. Release Please computes the
version and `CHANGELOG.md` from the Conventional Commit subjects on `main`. A
squash collapses every feature commit in the batch into a single subject. The
release then loses its changelog entries and can compute the wrong bump.

A merge commit preserves each subject underneath.

The subject of the merge commit (`Merge pull request #N from ...`) is not a
Conventional Commit and does not need to be. Release Please reads the feature
commits that the merge commit carries, not the merge subject.

Promotion also refreshes repository posture. `.github/workflows/scorecard.yml`
runs only on pushes to `main`. Thus the published OpenSSF Scorecard result and
the README badge do not update until a promotion lands.

## How a release happens

1. On merges to `main`, Release Please keeps a **release PR** open
   (`chore(main): release X.Y.Z`). The release PR has the computed version
   bump in `pyproject.toml` and the generated `CHANGELOG.md` section.
2. Treat the release PR head as the immutable release candidate.
   Build its wheel and sdist.
   Then have a person complete the
   [Release Candidate Manual QA](testing/smoke-test-plan.md).
   The QA covers the exact candidate wheel and a clean checkout of the same
   commit.
   Attach or link the completed, redacted record from the release PR.
   Every row is release-blocking.
   A changed commit or artifact invalidates the record.
3. **Merge that release PR only after the manual QA record passes.**
   `GITHUB_TOKEN` opens the release PR.
   GitHub restricts workflow runs that this token triggers.
   The Actions settings of the repository decide the result.
   The runs may not start, or they may wait for approval.
   Thus do not expect the required checks to go green on their own.
   Merge the release PR as an admin.
   To enforce checks on the release PR, wire a PAT.
4. The merge tags `vX.Y.Z` and cuts the GitHub Release.
   The `publish` job then builds the sdist + wheel and generates an SBOM.
   It then publishes to PyPI via OIDC.
   The current workflow rebuilds at publish time.
   Thus a later `pip install lilrae==X.Y.Z` check is corroboration.
   It is not the pre-cut release gate or proof that the bytes are identical.
   If byte-for-byte promotion becomes required, publish the tested artifacts.
   Do not rebuild them.
5. Then a workflow opens a `main`→`dev` **back-merge PR** automatically.
   Its title is `chore: back-merge <tag> into dev`.
   `main` now has the version bump + `CHANGELOG.md`.
   Do not use the merge queue.
   **Admin-merge it with the "Create a merge commit" option.**
   This keeps `dev` current.
   Like the release PR, a bot opens it.
   Thus do not rely on its required checks to run.
   Do not squash it.
   A squash copies the release changes but leaves the release commit out of
   the `dev` history.
   The next promotion then replays the version bump against `dev`.
   It can conflict, as it did in #1375.

## Baseline

`.release-please-manifest.json` and `pyproject.toml` record the release
baseline. Do not duplicate a version number in this guide. Release Please
computes the next version from that baseline plus the Conventional Commits
merged since. Nobody hand-edits a version, the manifest, or `CHANGELOG.md`.

## PyPI trusted publisher (one-time)

On pypi.org, open the `lilrae` project → Settings → Publishing. The trusted
publisher must have owner `OpenRAE`, repository `lilrae`, workflow
`release-please.yml`, and environment `pypi`. PyPI matches these names in the
OIDC token. Thus a publisher with other names rejects the upload. Before the
first release of a new project, add the same values as a pending publisher
under Account → Publishing. The first upload then creates the project.

`raes` must be on PyPI first, because the project depends on it. The
distribution is named `lilrae` because `aptl` is reserved on PyPI. The import
package and CLI stay `aptl`. Releases up to 7.0.0 published as `aptl-labs`
([ADR-062](adrs/adr-062-lilrae-name-and-naming-convention.md)).

## Seat image cuts

VM images are built, qualified, signed with Cosign and published locally to GHCR.
They are independent of Python package releases. Release Please does not build,
qualify or publish seats. Its back-merge does not depend on a seat tag.
Follow the [seat image procedure](reference/appliance-seat-launcher.md#building-the-image).
Preserve actual manual VM evidence for each cut.
