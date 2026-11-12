# Documentation toolchain

This Reference lists the existing prose-tool inputs and trust boundaries.
Follow [Write documentation](../contributing-documentation.md) for setup and editing.

## Shared package

LilRAE pins [doc-tools v0.1.0](https://github.com/OpenRAE/doc-tools/releases/tag/v0.1.0).
Its source revision is `97866fad14d7fbb0d6752788ebdc5ae4f235573a`.
The archive SHA-256 is:

```text
125104c0cc535698d1cc9bba3e57883bdf9d87db6da346ff583967c4ce42de6c
```

`tools/install-doc-tools.sh` verifies that digest before extraction or execution.
The archive installs under `.tools/doc-tools/0.1.0/`.
The package separately verifies the ste-cli archive before installing its binary.
A failed download or checksum stops the check.
The package and binary caches remain trusted after installation.

The package uses the MIT license. Keep its `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `skills/documentation/LICENSE` intact.
Those notices identify the LilRAE, RAE, ste-cli, and skill guidance sources.
See the [package reference](https://github.com/OpenRAE/doc-tools/blob/v0.1.0/docs/reference.md) for platform checksums and source revisions.

## Rule coverage

The package selects sentence length, paragraph length, and contractions.
Its configuration and ste-cli binary remain package-owned.
LilRAE owns `.ste-required.txt`, `.vale.ini`, reader routes, and publication policy.

Vale applies Google error rules and the project overlay to maintained Markdown.
Generated release records retain their exclusion.
Agent guidance retains precise tool names through the `WorkflowPlatformName` rule exception.
Its other rules remain enabled.

The selected checks assist editorial review; they do not certify STE conformance.

## Execution and publication

Local checks use explicit paths or a rewritten passage on stdin.
Pre-commit runs staged hygiene and secret detection.
CI owns corpus checks, strict MkDocs, and complete verification.
Behavior tests run only in CI or an explicitly approved, isolated VM.

`mkdocs.yml` owns navigation and the canonical site URL.
The existing GitHub Pages and Read the Docs configurations consume that same source tree.
No document text is sent to a new analyzer or host.
