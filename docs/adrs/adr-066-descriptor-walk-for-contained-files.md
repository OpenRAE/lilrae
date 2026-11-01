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

On Windows, `internal/securefile` uses `os.Root`, and it refuses a link: the
entry that `Lstat` reports must be the file that it opened (`os.SameFile`).
Windows has no execute-only directory.

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
