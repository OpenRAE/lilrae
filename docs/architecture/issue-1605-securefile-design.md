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
| Rendered credentials set and verify `0644` after replacement; SOC CA writes set and verify `0644` or `0600` on the temporary file before replacement. Their directories are `0700`. The CA sets the modes of reused files again. | `core/credentials.py`; `core/_soc_ca_io.py`; `core/_soc_ca_generation.py`. |
| `core/ssh.py` sets `0600` on a private key and `0644` on a public key that `ssh-keygen` wrote. On Windows it runs `icacls <key> /inheritance:r /grant:r <user>:R` and sets no mode. | `core/ssh.py`. |
| On Windows, `pathsafe` cannot run, because it needs `dir_fd`. The other modules change modes there only on a best-effort basis. | Source. |
| `filepath.Localize` accepts each name that `fs.ValidPath` accepts, except names that the platform cannot represent: on Windows a name with `\` or `:`, or a reserved name such as `NUL`. | Go 1.27 `path/filepath`. |
| `os.Root` follows a link that stays inside the root, and it opens each directory with read access. `Root.Lstat` and `File.Stat` read the file identity from a handle, so `os.SameFile` does not open a path again. | Go 1.27 `os/root_unix.go`, `os/root_windows.go`, `os/stat_windows.go`; a probe. |
| A handle from `os.Root` has read or write access only, never `WRITE_DAC` alone. `NtCreateFile` opens an entry relative to a directory handle with the access that the caller asks for, and `golang.org/x/sys/windows` wraps it. | Go 1.27 `internal/syscall/windows`; Microsoft Win32 documentation. |
| On Linux, `fchmodat` ignores `AT_SYMLINK_NOFOLLOW`. Go and GNU libc open the file with `O_PATH` and change the mode of that open file through `/proc/self/fd`. macOS supports the flag. | Go 1.27 `internal/syscall/unix/fchmodat_linux.go`. |

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
   `O_NONBLOCK`, so a FIFO cannot block it, and then clears the flag. `Chmod`
   needs no read access: on Linux it opens the file itself with `O_PATH` and
   changes the mode through `/proc/self/fd`, and on macOS it uses `fchmodat`
   with `AT_SYMLINK_NOFOLLOW`. Each failure has the reason code that
   `pathsafe` gives.
3. **The Windows walk.** Keep `os.Root` for containment where its contract
   suffices. Each untrusted component must also be opened without reparse
   processing and checked through that handle before use. Build on the
   package's existing parent-relative `NtCreateFile` metadata boundary,
   rather than adding a second path walker. `Lstat` and `os.SameFile` after
   a following open are insufficient: a link can be replaced by its target
   between the open and the check. Reparse tags must be checked on the
   opened object, including junctions, rather than assuming every reparse
   point has the symbolic-link mode bit. See ADR-066.
   A directory's no-follow handle stays open until the new `os.Root` has
   the same file identity. Reads use the no-follow file handle directly.
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
5. **Durability and modes.** On Unix, a write syncs the file before it
   publishes it and syncs the directory after. The temporary name is random
   and created with `O_EXCL`. Each write sets the final mode through the descriptor and
   verifies it before the sync, so that the sync persists it, and never by
   path after the publication: `0600` for `CreateOnce` and `ReplacePrivate`,
   and the mode of the caller for `Replace`. A mode that the file system did
   not keep is `mode_not_kept`. `Replace` and `Chmod` refuse a mode with
   other bits than the permission bits before any change.
6. **Windows access.** On Windows, a mode sets only the read-only attribute,
   as `os.Chmod` does; it does not establish confidentiality. The POSIX
   ownership/mode rules of `ReplacePrivate` and `PrivateSubdir` have no
   direct Windows equivalent and must not be advertised as ACL protection.
   `RestrictToOwner` gives a file the access that
   `core/ssh.py` gives a key: a protected access list that lets only the
   current user read the file. `Chmod` and `RestrictToOwner` open the entry
   with `NtCreateFile` relative to the handle of the verified parent, with
   only the access of the change and with no access to the content.
   Preserve replacement and ACL behavior independently. Do not promise Unix
   atomic visibility or directory-sync durability from Windows `Rename`.
   Document the supported filesystem guarantees and surface unsupported
   required protection; never emulate replacement with delete-then-rename.
   A new secret must have its required ACL before publication, with private
   staging access from its first byte; subsequent hardening is only for
   existing files, such as keys produced by `ssh-keygen`.
7. **Handle lifetime.** On Linux and macOS, a `Dir` holds its directory in an
   `*os.File`. Each operation duplicates the descriptor while the file holds a
   reference, so that `Close` cannot free the number during the operation. After
   `Close`, each method returns an error, and a second `Close` returns an error
   that matches `fs.ErrClosed`.
8. **Errors.** An `*Error` holds the operation, the path, and one of the
   `pathsafe` reason codes, or `invalid_name` or `mode_not_kept`, because
   callers act on them. It holds no file content. The path and wrapped OS
   errors remain untrusted diagnostic data, not safe user-facing text.
   Preserve `errors.Is`/`As` and system causes, including `fs.ErrExist`,
   `fs.ErrNotExist`, `fs.ErrPermission`, and `fs.ErrClosed`; callers translate
   categories into their existing safe envelopes without parsing prose.
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
    One discovery walk applies all three exclusions and propagates read
    failures. Literal commas are escaped before the Gremlins CSV argument
    parser reads each pattern. Thus an exclusion cannot widen its scope.

## Data flows and threat model

```text
owner: trusted directory -> securefile.OpenDir -> Dir
caller: untrusted relative path -> lexical rules -> walk without links -> file
caller: bytes -> temporary file (0600, mode, sync) -> link or rename -> sync dir
```

The publication flow above describes Unix; Windows guarantees are qualified
separately under decision 6.

| Threat | Mitigation |
| --- | --- |
| A path escapes the directory through `..`, an absolute path, a Windows separator or drive, or a link. | The lexical rules, `filepath.Localize`, and no component is followed when it is a link. |
| A link inside the directory redirects a write to another file of the directory. | Each component is opened without following a link. |
| A component changes between a check and an open. | The walk opens each component without following links, under its retained parent handle, and validates the opened object before use. A later path/identity check is not the no-follow guarantee. |
| A FIFO at a leaf blocks a reader. | The read opens the leaf with `O_NONBLOCK` and refuses a file that is not regular. |
| A crash leaves a partial file or a false create-once success. | Complete staged bytes precede publication; Unix file and directory syncs provide the stated durability. Windows guarantees require separate qualification. A post-publication error does not imply rollback. |
| Another user reads or replaces a private file. | The final mode is set before the publication, the leaf parent must belong to the caller, and directories lose group and other write. On Windows, `RestrictToOwner` sets the access list of a key. |
| A call after `Close` reaches a descriptor number that a later open reuses for another directory. | The `*os.File` of a `Dir` refuses each use after `Close`, and an operation works on its own duplicate of the descriptor. |
| An error leaks a secret or a host path. | File content stays out of errors; entry-layer projections omit raw paths and causes and use the shared redaction policy. |

## Repository-wide guardrails

This package is a byte-level mechanism in the existing `secure-file`
foundation component. It owns no configuration, credential discovery,
authorization, serialization, or persistence policy. Paths below are relative
to `src/aptl/` unless another root is named. The shared
[#1557 preflight](issue-1557-go-foundation-preflight.md) and ADR-065 continue
to apply; existing source is evidence, not certification that these contracts
or the issue's gates have passed.

| Layer and canonical incumbent | Required passage |
| --- | --- |
| Authentication and authority: `api/deps.py`, `api/session.py`, `api/middleware/bff.py`, terminal routing; MCP common `src/{config,server}.ts` | Keep token/session, Host/Origin, tool-schema, capability and target checks before file effects. The owner supplies the authorized root; an accepted relative path grants no authority. Add no route or generic file-access tool in this issue. |
| Configuration and admission: `core/config.py`, `utils/strict_json.py`, `core/experiment/resolver.py`, scenario/pack admission | Strict decoding, field/identity checks, locator parsing and artifact size/digest limits remain with their owners. Reuse `CheckPath` for lexical validation without I/O, and repeat it at the effect boundary; do not duplicate it in each caller or normalize away invalid components. Read/hash/parse from one contained handle. No second config, locator, RAES or record schema. |
| Secret sources and environment shapes: `core/_credential_sources.py`, `core/env.py`, `utils/placeholders.py`, `core/deployment/{_environment_bindings,_realization_primitives,_compose_environment}.py` | Preserve exact pack/consumer/variable grants and authored/generated/granted/adapter distinctions. Validate Docker versus Compose env-file representability before writes. Accept already-rendered bytes; do not read ambient environment or substitute secrets in this package. |
| At-rest exposure: `utils/pathsafe.py`, `core/credentials.py`, `core/_soc_ca_io.py`, `core/_soc_ca_generation.py`, `core/ssh.py`; ADR-028/029/034 | Keep generated paths separate from checked-in templates. Preserve `0700` directories, `0600` keys/passwords, and deliberate `0644` bind-mounted configs, certificates and keystores. Require exact POSIX modes despite umask and recheck reused files. Windows read-only attributes do not replace the SSH DACL. File bytes must never become argv, shell text, logs, or temporary-file names. |
| Persistence and identity: `core/runstore.py`, `core/evidence/content_store.py`, `core/archival/`, `core/lilrae_config_migration.py` | Owners retain configured roots, canonical bytes/digests, structural redaction, compare-on-exists, post-write verification, finalization locks and reserved seal-marker authority. A create-once conflict is not success until the owner compares bytes. Opaque securefile writes do not sanitize run records or create a multi-file transaction. |
| Errors and observability: `core/experiment/errors.py`, `core/deployment/errors.py`, `core/lab_types.py`, `api/schemas.py`, MCP `isError`, `utils/{logging,redaction}.py`, `core/telemetry_export.py` | Reuse current diagnostic/result projections and the redaction parity corpus. Do not export raw `Error.Path`, OS/parser causes or formatted errors into responses, spans or logs. No foundation logger setup, second error hierarchy or copied redaction patterns. Go callers use explicit `slog` and stderr under ADR-065; return an error without also logging it here. |
| OS and runtime: ADR-066, `internal/securefile` platform files, `core/hostenv.py` | Use retained parent/file handles, no-follow opens, regular-file checks and non-inherited descriptors. Preserve execute-only traversal and nonblocking refusal of FIFOs. Metadata changes need only metadata rights. Root trust includes mount layout and protection against foreign directory mutation; containment is not an OS sandbox or proof that a hard link has no other name. |

The reuse inventory also includes seat persistence/image/trust writers in
`appliance/seat/`, `core/{env,host_keys,participant_hosts,exporter}.py`, service
rule writing, workbench client files, deployment recording/ownership helpers,
and scenario/evidence readers. These are later consumers of one file boundary,
not reasons to add another writer or migrate those callers in #1605. The three
Python containment exception classes describe current compatibility needs;
they are not three Go exception hierarchies to reproduce.

Publication contracts remain separate:

- **Visibility:** complete bytes and final protection before the final name
  changes; replacement creates a new inode/object, never truncates a hard-link
  target. Only Unix replacement has the atomic-visibility guarantee here.
- **Create-once:** publish without replacement even under competing writers
  or an existing symlink. Never implement this with an existence check plus
  rename, or write directly to an exclusive final name before filling it.
- **Durability:** sync where required and report write, mode/ACL, sync, close,
  publication and cleanup failures. If publication succeeded but sync or
  cleanup failed, the new file can already exist; do not claim the old bytes
  survived, remove the published file as rollback, or blindly retry. Newly
  created ancestor entries need their containing directories synced if the
  contract promises survival of the entire new path. File sync plus leaf
  directory sync alone does not establish that stronger guarantee.

No mode change by path after publication is part of a write. The standalone
metadata operation serves reuse/external-file hardening and must retain the
no-follow and regular-file rules through the change, including a racing leaf
swap on macOS. Cleanup owns only its temporary names and handles; it must not
mask the primary error or turn a missing target into an error for idempotent
removal. Concurrent `Close` must not let a reused descriptor reach another
directory. Follow ADR-065's context rule at I/O boundaries, without promising
that context cancellation can interrupt every filesystem syscall or abandoning
owned cleanup in a background goroutine.
The Linux `/proc/self/fd` metadata mechanism depends on procfs availability;
failure must not trigger a fallback to the original untrusted pathname.

The extension seams are the caller-supplied root, the final mode/protection
chosen at the write boundary, platform-specific mechanisms, and small
consumer-owned interfaces. A Windows private-key publication must be able to
select its final ACL before visibility. Keep create-once and replace distinct;
do not add a universal filesystem interface, policy registry, or speculative
options framework. Caller durability requirements must be explicit; preserve
the current stronger Unix sync contract rather than adding an implicit
best-effort fallback.

## Verification and boundaries

Build on `tests/test_{pathsafe,credentials,soc_ca,ssh}.py` and the current
`internal/securefile` tests. Require real Linux/macOS/Windows evidence for
applicable guarantees: lexical refusals before effects, internal/external and
dangling links, junctions/reparse points, race swaps, special files, exact modes
under restrictive umask, execute-only traversal, ACL inheritance and owner
access, concurrent create-once publication, replacement, cleanup, and failures
before/after publication. Unprivileged checks must exercise access denial;
root/admin bypasses, skips and cross-compilation are not that evidence. Static
fuzz models do not replace race or failure-path tests. Use bounded fuzz runs
through the existing `go-gates.sh fuzz` discovery, not a second CI runner.

`architecture/model.yaml` owns package/dependency permissions; the design front
matter remains the machine-checked record. Reuse `tools/cmd/archcheck`, its
generated diagram, `go.mod`/`go.sum`, `.golangci.yml`, `tools/ci/go-gates.sh`,
`tools/ci/select_checks.py`, `.github/workflows/checks.yml`, branch protection,
Sonar configuration and `tools/mutation-thresholds.json`. Whole-repository
architecture checks must include every OS/build-tag file. Mutation accounting
must not exclude shared code or erase uncovered mutants merely because a
platform job cannot run the tool. The documented Windows mutation gap (#1617)
is a limitation, not a passing Windows mutation result. Keep required status
names and fail-closed routing. Use the `go-cutover` base and the existing
`.ground-control.yaml`/`.gc/plan-rules.md` workflow; no duplicate gates or
workflow state. Local checks stay targeted; whole-repository gates run in CI.

Non-goals are locks (#1609), domain repositories or schemas, serialization,
redaction policy, CA generation/renewal, SSH process management, caller
migrations, remote filesystems/transports, multi-file transactions, recovery
policy and changes to source/output locations. This preflight changes guidance
only; passing a design check does not prove platform safety, mutation efficacy,
or that the design historically preceded existing code.
