---
design: 1
issue: 1609
packages:
  - path: internal/filelock
    component: file-lock
    imports:
      - golang.org/x/sys
      - github.com/OpenRAE/lilrae/internal/wait
  - path: internal/securefile
    component: secure-file
    imports:
      - golang.org/x/sys
model_changes:
  - component:file-lock
---

# Issue #1609: File locks design

This design adds the foundation package for the file locks of Go port 06
([#1557](issue-1557-go-foundation-design.md)). The front matter of this note is
its design record.

## Evidence

| Fact | Source |
| --- | --- |
| Each POSIX caller locks with `fcntl.flock`: exclusive or shared, with or without `LOCK_NB`, and it unlocks with `LOCK_UN`. No caller uses `fcntl.lockf`. | `core/lifecycle_guard.py`, `core/runstore.py`, `core/session.py`, `core/archival/discovery_index.py`, and the workbench and appliance seat modules. |
| On Windows, `core/lifecycle_guard.py` locks one byte at offset 0 with `msvcrt.locking(LK_NBLCK)`, and it refuses a shared lock. The other callers lock only on POSIX. | Source. |
| A `flock` lock belongs to the open file description. Two opens of one file exclude each other, also in one process, and a Go lock and a Python lock on one file exclude each other. | `flock(2)`. |
| `msvcrt.locking` locks a byte range from the current position with `LockFile`. `LockFileEx` on the same range excludes it. | Microsoft C runtime and Win32 documentation. |
| A blocking `flock` or `LockFileEx` call cannot be cancelled with a context. | `flock(2)`; Win32 documentation. |
| `github.com/gofrs/flock` opens the path itself, and the lock package of the go command is internal. No maintained module locks a file that the caller opened. | Module documentation. |
| The lifecycle guard opens its lock file with `O_RDWR`, `O_CREAT`, and `O_NOFOLLOW` under a no-follow walk, with the mode `0600`, and it sets `0600` with `fchmod`. | `core/lifecycle_guard.py`; `core/runstore.py`. |

## Decisions

1. **Locks on an open file.** `filelock.TryLock`, `filelock.Lock`, and
   `filelock.Unlock` take an `*os.File` and a mode, `Shared` or `Exclusive`.
   `TryLock` returns `ErrBusy` when another holder keeps a conflicting lock.
2. **The Unix lock.** On Linux and macOS, the package calls `flock` through
   `golang.org/x/sys/unix`, the primitive of each Python caller.
3. **The Windows lock.** On Windows, the package locks byte 0 for a length of
   1 with `LockFileEx`, as the lifecycle guard does with `msvcrt.locking`. A
   shared lock returns `errors.ErrUnsupported`, because the Python guard fails
   closed there.
4. **Blocking with a deadline.** `Lock` takes a context and a timeout, as the
   foundation design requires. It calls `TryLock` through `wait.Until` every
   20 ms, because a blocking call cannot be cancelled. No caller relies on
   the order in which the kernel wakes waiters.
5. **Caller policy stays with the caller.** Reentrancy, the scope, and the
   order of the locks stay with each caller, as #1609 states.
6. **The lock file.** `securefile.Dir.OpenLockFile` creates each missing
   directory with the mode `0700`, and it opens or creates the lock file for
   reading and writing without following a link. It refuses a file that is
   not regular, and it sets the mode `0600`, as the lifecycle guard does.
7. **Tests.** Tests take real locks on Linux, macOS, and Windows: two opens
   exclude each other, a shared lock excludes an exclusive lock on Unix, and
   `Lock` waits and times out in `testing/synctest`. A test runs a Python
   child that holds the lock of a Python caller, and a Go lock must not get
   it, and the reverse. The Go product tests job installs Python for it.

## Data flows and threat model

```text
caller -> securefile.Dir.OpenLockFile -> *os.File
caller -> filelock.Lock / TryLock (*os.File, mode) -> flock or LockFileEx
caller -> filelock.Unlock (*os.File)
```

| Threat | Mitigation |
| --- | --- |
| A Go process and a Python process change one project at the same time, for example during an upgrade. | Both use the same primitive on the same byte range, and a test proves that they exclude each other. |
| A lock wait outlives its deadline. | `Lock` polls with `wait.Until`, which stops at the deadline and on the context. |
| A link redirects a lock file to another file. | `OpenLockFile` opens each component without following a link. |
| A crashed holder keeps a lock. | The operating system releases a `flock` or `LockFileEx` lock when the file closes, also when the process ends. |
