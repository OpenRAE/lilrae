---
design: 1
issue: 1605
packages:
  - path: internal/securefile
    component: secure-file
    imports:
      - golang.org/x/sys
  - path: tools/internal/mutation
    component: mutation-check
    imports:
      - github.com/OpenRAE/lilrae/tools/internal/git
      - github.com/OpenRAE/lilrae/tools/internal/golayout
    test_imports:
      - github.com/OpenRAE/lilrae/tools/internal/gittest
      - github.com/google/go-cmp
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
| `pathsafe` opens each component with `O_NOFOLLOW` under the descriptor of its parent, so it refuses a link anywhere, and it opens the target once. A failed open is `symlink` when the entry is a link, `not_found` when the entry is absent or is not a directory, and `open_failed` for another cause. | `utils/pathsafe.py`; `tests/test_pathsafe.py`. |
| `pathsafe` traverses directories with `O_PATH` or `O_SEARCH`, so a caller reads through an execute-only directory. The access service makes a `0711` directory. | `utils/_pathsafe_read.py`; `appliance/access_service.py`. |
| A create-once write writes a temporary file with a mode of `0600`, syncs it, links it to the final name with no replacement, removes the temporary name, and syncs the directory. | `pathsafe.create_exclusive_nofollow`. |
| A private replacement clears group and other write on each directory below the root, requires a leaf parent that the caller owns with no group or other access, refuses an existing leaf that is not a regular file, and renames a synced temporary file onto the leaf. | `pathsafe.replace_private_nofollow`. |
| A private directory requires that the caller owns each component, clears group and other write on each, and clears group and other access on the last. | `pathsafe.open_private_dir_contained_nofollow`. |
| A removal refuses a link and a file that is not regular, treats an absent file or parent as done, and syncs the parent. No caller reads its result. | `pathsafe.remove_contained_nofollow` and its callers. |
| The rendered credentials and the SOC CA files replace a file through a temporary file and then set the mode `0644` or `0600` and verify it on POSIX. Their directories are `0700`. The CA sets the modes of reused files again. | `core/credentials.py`; `core/_soc_ca_io.py`; `core/_soc_ca_generation.py`. |
| `core/ssh.py` sets `0600` on a private key and `0644` on a public key that `ssh-keygen` wrote. On Windows it runs `icacls <key> /inheritance:r /grant:r <user>:R` and sets no mode. | `core/ssh.py`. |
| On Windows, `pathsafe` cannot run, because it needs `dir_fd`. The other modules change modes there only on a best-effort basis. | Source. |
| `filepath.Localize` accepts each name that `fs.ValidPath` accepts, except names that the platform cannot represent: on Windows a name with `\` or `:`, or a reserved name such as `NUL`. | Go 1.27 `path/filepath`. |
| `os.Root` follows a link that stays inside the root, and it opens each directory with read access. `Root.Lstat` and `File.Stat` read the file identity from a handle, so `os.SameFile` does not open a path again. | Go 1.27 `os/root_unix.go`, `os/root_windows.go`, `os/stat_windows.go`; a probe. |
| A handle from `os.Root` has no `WRITE_DAC` access. The Win32 `ReOpenFile` function opens the same file object again with other access, and `golang.org/x/sys/windows` does not wrap it. | Go 1.27 `internal/syscall/windows`; Microsoft Win32 documentation. |

## Decisions

1. **A trusted directory and untrusted names.** `securefile.OpenDir` opens a
   directory that its owner trusts. Each method takes an untrusted relative
   path with `/` separators. `CheckPath` and each method check the `pathsafe`
   rules first, and then `filepath.Localize`. A name that `Localize` refuses
   is `invalid_name`. On Linux and macOS this refuses only invalid UTF-8.
2. **The Unix walk.** On Linux and macOS, the package opens each component
   with `golang.org/x/sys/unix.Openat` and `O_NOFOLLOW` (ADR-066). A read
   traverses each directory with `O_PATH` or `O_SEARCH`. A write opens each
   directory with read access, so that the package can sync it, and creates a
   missing directory with the mode `0700`. A read opens the leaf with
   `O_NONBLOCK`, so a FIFO cannot block it, and then clears the flag. Each
   failure has the reason code that `pathsafe` gives.
3. **The Windows walk.** On Windows, the package opens one component at a time
   through `os.Root` and `Root.OpenRoot`. It refuses a component when
   `Root.Lstat` reports a link or a reparse point, or when the entry is not
   the file that it opened (`os.SameFile`).
4. **Operations.** Each operation keeps the rules in the evidence.

   | Operation | Python source |
   | --- | --- |
   | `Open`, `ReadFile` | `open_contained_nofollow`, `read_contained_nofollow` |
   | `ReadDirNames` (sorted) | `listdir_contained_nofollow` |
   | `Subdir`, `MakeSubdir` | `open_dir_contained_nofollow` |
   | `PrivateSubdir` | `open_private_dir_contained_nofollow` |
   | `CreateOnce` (returns an error that matches `fs.ErrExist`) | `create_exclusive_nofollow` |
   | `Replace` (with a mode) | the credentials and CA writers |
   | `ReplacePrivate` | `replace_private_nofollow` |
   | `Chmod`, `RestrictToOwner` | the mode settings of the CA and `core/ssh.py` |
   | `Remove`, `RemoveAll` | `remove_contained_nofollow`, `remove_tree_contained_nofollow` |

   `Replace` and `ReplacePrivate` refuse an existing leaf that is a link or
   not a regular file. `RemoveAll` refuses a link at the top, and it removes a
   link inside the tree as an entry. An absent file or tree is not an error.
5. **Durability and modes.** A write syncs the file before it publishes it
   and syncs the directory after. The temporary name is random and created
   with `O_EXCL`. Each write sets the final mode through the descriptor and
   verifies it before the sync, so that the sync persists it, and never by
   path after the publication: `0600` for `CreateOnce` and `ReplacePrivate`,
   and the mode of the caller for `Replace`. A mode that the file system did
   not keep is `mode_not_kept`.
6. **Windows access.** On Windows, a mode sets only the read-only attribute,
   as `os.Chmod` does, and the private rules of `ReplacePrivate` and
   `PrivateSubdir` do not apply, as the Python modules give no mode
   protection there. `RestrictToOwner` gives a file the access that
   `core/ssh.py` gives a key: a protected access list that lets only the
   current user read the file. It sets the list on a handle that
   `ReOpenFile` opens from the verified handle.
7. **Handle lifetime.** On Linux and macOS, a `Dir` holds its directory in an
   `*os.File`. Each operation duplicates the descriptor while the file holds a
   reference, so that `Close` cannot free the number during the operation. After
   `Close`, each method returns an error, and a second `Close` returns an error
   that matches `fs.ErrClosed`.
8. **Errors.** An `*Error` holds the operation, the path, and one of the
   `pathsafe` reason codes, or `invalid_name` or `mode_not_kept`, because
   callers act on them. It holds no file content.
9. **No renameio on Unix.** renameio contains a write only through an
   `*os.Root`. The descriptor walk publishes with `linkat` and `renameat`
   instead (ADR-066).
10. **Tests.** Tests use real files on Linux, macOS, and Windows, including
   links, execute-only directories, FIFOs, and the race lessons of #966. A
   test without root cannot make a directory that another user owns, so a
   unit test checks the ownership rule. Fuzz tests check the lexical rules
   against `filepath.Localize`, and the walk against a model that walks with
   `Lstat`.
11. **Each platform runs the gates of its files.** Gremlins walks each file
    below a module, but the tests of the module cannot cover a file of a
    nested module, a file below a directory that the go command ignores, or
    a file that the host does not build. The mutation gate leaves out such
    files, so it no longer counts their mutants as not covered. A new CI job
    runs the tests and the mutation gate of the product module on macOS and
    Windows. `go-gates.sh test` and `mutation` take a module list for it,
    because the tools modules run on Linux only. Gremlins reads no coverage
    on Windows (OpenRAE/go-rae-gremlins#12), so as a temporary measure the
    Windows job runs only the tests, until #1617 restores the mutation gate
    there.

## Data flows and threat model

```text
owner: trusted directory -> securefile.OpenDir -> Dir
caller: untrusted relative path -> lexical rules -> walk without links -> file
caller: bytes -> temporary file (0600, mode, sync) -> link or rename -> sync dir
```

| Threat | Mitigation |
| --- | --- |
| A path escapes the directory through `..`, an absolute path, a Windows separator or drive, or a link. | The lexical rules, `filepath.Localize`, and no component is followed when it is a link. |
| A link inside the directory redirects a write to another file of the directory. | Each component is opened without following a link. |
| A component changes between a check and an open. | The walk opens each component once, under the handle of its parent, and uses that handle. On Windows, `os.SameFile` compares the entry with the opened file. |
| A FIFO at a leaf blocks a reader. | The read opens the leaf with `O_NONBLOCK` and refuses a file that is not regular. |
| A crash leaves a partial file or a false create-once success. | A temporary file is synced before the link or rename, and the directory is synced after. |
| Another user reads or replaces a private file. | The final mode is set before the publication, the leaf parent must belong to the caller, and directories lose group and other write. On Windows, `RestrictToOwner` sets the access list of a key. |
| A call after `Close` reaches a descriptor number that a later open reuses for another directory. | The `*os.File` of a `Dir` refuses each use after `Close`, and an operation works on its own duplicate of the descriptor. |
| An error leaks file content. | Errors hold the operation, the path, and the reason only. |
