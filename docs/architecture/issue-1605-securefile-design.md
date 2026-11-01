---
design: 1
issue: 1605
packages:
  - path: internal/securefile
    component: secure-file
    imports:
      - golang.org/x/sys
model_changes:
  - component:secure-file
---

# Issue #1605: Contained files design

This design adds the foundation package for contained file access, atomic
writes, and file modes of Go port 06
([#1557](issue-1557-go-foundation-design.md)). The front matter of this note is
its design record. [ADR-066](../adrs/adr-066-descriptor-walk-for-contained-files.md)
records the decision about `os.Root`.

## Evidence

| Fact | Source |
| --- | --- |
| `pathsafe` rejects an absolute path, a NUL byte, an empty component, `.`, and `..` before any system call, with a reason code for each. | `utils/_pathsafe_core.py`. |
| `pathsafe` opens each component with `O_NOFOLLOW` under the descriptor of its parent, so it refuses a link anywhere, and it opens the target once. | `utils/pathsafe.py`; `tests/test_pathsafe.py`. |
| `pathsafe` traverses directories with `O_PATH` or `O_SEARCH`, so a caller reads through an execute-only directory. The access service makes a `0711` directory. | `utils/_pathsafe_read.py`; `appliance/access_service.py`. |
| A create-once write writes a temporary file with a mode of `0600`, syncs it, links it to the final name with no replacement, removes the temporary name, and syncs the directory. | `pathsafe.create_exclusive_nofollow`. |
| A private replacement clears group and other write on each directory below the root, requires a leaf parent that the caller owns with no group or other access, refuses an existing leaf that is not a regular file, and renames a synced temporary file onto the leaf. | `pathsafe.replace_private_nofollow`. |
| `pathsafe` has no Windows path: it needs `dir_fd`. On Windows, `core/ssh.py` restricts a private key with `icacls /inheritance:r /grant:r <user>:R`. | Source; the Windows job of `checks.yml`. |
| `os.Root` follows a link that stays inside the root, and it opens each directory with read access. | Go 1.27 `os/root_unix.go`, `os/root_windows.go`; a probe. |
| An `os.Root` open, then `Lstat` of the same name and `os.SameFile`, refuses a link: the link and its target are different files. | A probe on Linux. |

## Decisions

1. **A trusted directory and untrusted names.** `securefile.OpenDir` opens a
   directory that its owner trusts. Each method takes an untrusted relative
   path with `/` separators and checks the lexical rules first.
2. **The Unix walk.** On Linux and macOS, the package opens each component
   with `golang.org/x/sys/unix.Openat` and `O_NOFOLLOW`, and each directory
   with `O_PATH` or `O_SEARCH` (ADR-066). A link is a `symlink` error, a
   missing component is `not_found`, and a target that is not a regular file
   is `not_regular_file`.
3. **The Windows walk.** On Windows, the package uses `os.Root`, and it
   refuses a link with `Lstat` and `os.SameFile` at each component.
4. **Operations.** `Open` and `ReadFile` read a regular file through one
   handle. `ReadDirNames` lists a directory. `CreateOnce` publishes a file
   with no replacement and returns `os.ErrExist` when the name exists.
   `Replace` replaces a private file. `PrivateDir` creates or opens a private
   directory. `Remove` removes a regular file, and `RemoveAll` removes a tree,
   both without following a link. Each operation keeps the rules in the
   evidence.
5. **Durability and modes.** A write syncs the file before it publishes it
   and syncs the directory after. The temporary name is random and created
   with `O_EXCL`. The final mode is set through the descriptor before the
   publication, never by path after it.
6. **Owner-only access.** `RestrictToOwner` gives a file the access that
   `core/ssh.py` gives a private key: the mode `0600` on Unix, and on Windows
   a protected access list that lets only the current user read the file. It
   acts on the open handle.
7. **Errors.** An `*Error` holds the operation, the relative path, and one of
   the `pathsafe` reason codes, because callers act on them. It holds no file
   content.
8. **No renameio on Unix.** renameio contains a write only through an
   `*os.Root`. The descriptor walk publishes with `linkat` and `renameat`
   instead (ADR-066).
9. **Tests.** Tests use real files on Linux, macOS, and Windows, including
   links, execute-only directories, foreign ownership where the platform
   allows it, and the race lessons of #966. Fuzz tests check the lexical
   rules and the walk. A Go test job on macOS and Windows runs the package.

## Data flows and threat model

```text
owner: trusted directory -> securefile.OpenDir -> Dir
caller: untrusted relative path -> lexical rules -> descriptor walk -> file
caller: bytes -> temporary file (0600, sync) -> link or rename -> sync dir
```

| Threat | Mitigation |
| --- | --- |
| A path escapes the directory through `..`, an absolute path, or a link. | The lexical rules, and no component is followed when it is a link. |
| A link inside the directory redirects a write to another file of the directory. | Each component is opened without following a link. |
| A component changes between a check and an open. | The walk opens each component once, under the descriptor of its parent, and uses that handle. |
| A crash leaves a partial file or a false create-once success. | A temporary file is synced before the link or rename, and the directory is synced after. |
| Another user reads or replaces a private file. | The final mode is set before the publication, the leaf parent must belong to the caller, and directories lose group and other write. On Windows, `RestrictToOwner` sets the access list. |
| An error leaks file content. | Errors hold the operation, the path, and the reason only. |
