# ADR-066: Descriptor Walk for Contained Files on Unix

## Status

accepted

## Date

2026-11-01

## Context

[ADR-065](adr-065-go-implementation-and-engineering-standards.md) states:
"Use `os.Root` for contained file access. Replace a file atomically with
`github.com/google/renameio/v2` inside the root (`WithRoot`)."

The Go port must keep the protection of `utils/pathsafe.py`
(Go port 06b, #1605). That module opens each component of an untrusted path
with `O_NOFOLLOW`, so it refuses a link anywhere in the path, also a link that
stays inside the trusted directory. It traverses a directory with `O_PATH` on
Linux and `O_SEARCH` on macOS, so a caller can read through an execute-only
directory. The appliance access service makes such a directory (mode `0711`).

`os.Root` in Go 1.27 gives neither guarantee. It follows a link whose target
stays inside the root, and it opens each directory with read access, which an
execute-only directory refuses. renameio contains a write only through an
`*os.Root`, and Go has no `*os.Root` for an open directory descriptor.

## Decision

On Linux and macOS, `internal/securefile` walks directory descriptors with
`golang.org/x/sys/unix`:

- It opens each component with `O_NOFOLLOW`, and each directory with `O_PATH`
  on Linux and `O_SEARCH` on macOS.
- It writes a temporary file under the verified directory descriptor, syncs
  it, and publishes it with `linkat` for a create-once write or `renameat`
  for a replacement. Then it syncs the directory.

On Windows, `internal/securefile` keeps `os.Root` where its containment contract
suffices, with parent-relative no-follow handle operations for the stricter
contract. Every untrusted component must be opened without reparse processing,
then checked through that handle before use, including junctions and other
reparse points. Reuse `golang.org/x/sys/windows` and the package's native
metadata boundary; keep these details inside `internal/securefile`.

The #1605 architecture preflight corrects the earlier prescription of a
following open plus `Lstat`/`os.SameFile`: an entry can change from a link to
its target between those calls and pass the identity check. That sequence
does not establish no-follow access. [Go's Root contract](https://pkg.go.dev/os#Root)
permits internal links; Windows offers no-follow opens through
[`NtCreateFile` with `FILE_OPEN_REPARSE_POINT`](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntcreatefile).
This corrects the mechanism without lowering the original protection.

This record supersedes the `os.Root` and renameio clause of ADR-065 for
`internal/securefile` on Linux and macOS. Other code keeps that clause.

## Consequences

### Positive

- The Go code keeps each protection of `utils/pathsafe.py`.
- One package owns contained file access, so other packages do not walk
  paths.

### Negative

- The package has code for each platform, and each platform needs real tests.

### Risks

- A wrong flag or a missed check weakens containment. Tests on Linux, macOS,
  and Windows, and fuzz tests of the walk, check each rule.
- Handle identity checks supplement no-follow opens; they cannot replace
  them. Static trees and cross-compilation do not qualify races or Windows
  reparse handling. The [#1605 design](../architecture/issue-1605-securefile-design.md)
  separates visibility, create-once publication, durability and ACL contracts.
