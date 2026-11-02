---
design: 1
issue: 1607
packages:
  - path: internal/process
    component: process
    imports: [golang.org/x/sys]
model_changes:
  - component:process
---

# Issue #1607: Process runner design

This design implements the process concern of the
[foundation design](issue-1557-go-foundation-design.md).
The Python behavior reference is `workbench/process.py` and `_pipe_exchange.py`.
Issue #963 supplies the cleanup and pipe failure cases.

## Components and contracts

`internal/process` is one foundation component.
It uses the standard library and the existing `golang.org/x/sys` module.
It contains no command selection, SSH, Docker, authentication, or product policy.
Consumers define the small interface that they need.

`Runner.Run` takes a context and a request.
The request supplies an argument array, directory, environment, input bytes, timeout, and combined output limit.
An empty environment stays empty.
The caller supplies an absolute executable path.
No shell interprets the argument array.
The caller must keep secrets out of arguments.
Input and the explicit environment can carry secrets.

The result contains the exit code, stdout, stderr, and cleanup report.
A nonzero exit code is a process result, not a runner failure.
Failures have fixed categories and contain no argument, directory, environment, input, output, or native error text.
Bound failures withhold output and report only captured byte counts.
Output bytes remain sensitive data that the consumer must protect.
The package writes no logs and adds no redactor.

## Deadline and pipes

One monotonic deadline starts before pipe creation and launch.
An earlier caller deadline wins.
Launch time does not restart the budget.
The runner checks cancellation before launch and after the native launch returns.
The kernel launch call itself has no portable cancellation API.
A delayed kernel return can therefore delay cleanup entry.
No abandoned launch goroutine can start a process after the runner returns.

One owned goroutine writes stdin concurrently with output capture.
Closing its pipe interrupts a blocked write.
The runner joins that goroutine before return.
The child can close stdin early without failing an otherwise valid invocation.

The supervisor reads only bytes reported as available by each output pipe.
It uses `FIONREAD` and `poll` on Unix, and `PeekNamedPipe` on Windows.
Each turn reads a bounded chunk from each stream.
The two buffers share one byte budget.
Exactly the limit succeeds; the next byte fails.
At child exit, capture drains a snapshot of the available bytes.
Later helper output is discarded during cleanup.
No stream holder can extend capture to the invocation deadline after child exit.

## Ownership and cleanup

Cleanup follows success, nonzero exit, cancellation, timeout, and output overflow.
Its elapsed time and residual observations are separate from the invocation deadline.
The default termination grace is one second.
Helpers after normal child exit receive the Python shutdown grace of 20 seconds.
The reap and stream-release phases each have a one-second bound.
Runner fields permit explicit positive bounds for a consumer or a test.

On Linux and macOS the child starts a new session.
The direct child remains unreaped until every possible group signal is complete.
Its allocated PID reserves the group identifier, including after child exit.
Linux uses `waitid` with `WNOWAIT` to observe exit.
macOS reads the child's kernel process status.
The supervisor checks other group members through `/proc` on Linux and `kern.proc.pgrp` on macOS.
An observation failure cannot prove that the group is empty.
The runner sends TERM only while owned members can remain.
It waits the grace period and sends KILL if members can still remain.
It then reaps the direct child and probes group disappearance without further signals.
This ordering prevents signals to a reused group identifier.

Windows uses an unnamed Job Object with kill-on-close and no breakaway permission.
`PROC_THREAD_ATTRIBUTE_JOB_LIST` assigns the child to that job during `CreateProcess`.
The child cannot create a helper before assignment.
An explicit inherited-handle list permits only its three pipes.
Windows argument quoting uses `windows.ComposeCommandLine`.
The supervisor uses original handles to observe process exit and job membership.
It requests console group shutdown where available, then terminates the owned job after the grace period.
The cleanup report states whether the cooperative stop request was accepted.
Headless Windows sessions can require forced termination after the grace period.
Job queries, rather than a successful terminate call, establish cleanup.
The implementation fails closed if job creation or assignment fails.

The cleanup report names a child not reaped, output streams still held, and group cleanup not confirmed.
On Windows, the report identifies the job's root process PID, not a POSIX process group.
An unreaped orphan zombie can keep group cleanup unconfirmed.
The report does not claim that such a process is live.
A Unix descendant that changes its session can escape the group.
It is observable only while it holds an output pipe.
Process supervision is not isolation.
Independent services retain their own lifecycle.

## Data flow and trust boundaries

```text
trusted consumer
  | argument array, directory, explicit environment, stdin, limits
  v
[foundation boundary: request validation and fixed error categories]
  process supervisor <---- monotonic deadline and caller cancellation
  |                    |
  | private pipes      | owned session / Job Object handle
  v                    v
[OS boundary: untrusted child and its owned helpers]
  | stdout / stderr / exit status / pipe and process observations
  v
  bounded memory buffers ----> result or safe failure and cleanup report
  | sensitive successful output
  v
trusted consumer ----> later shared redaction and presentation
```

The package has no persistent data store.
Only the caller owns presentation and storage of returned output.

```text
validate -> launch -> exchange -> child exit or limit -> cleanup -> return
cleanup: stop input -> drain snapshot -> TERM -> grace -> KILL if needed
         -> bounded reap -> bounded pipe release -> report observations
```

## Security controls and verification

| Threat and boundary | Control | Evidence |
| --- | --- | --- |
| Shell expansion changes the command at the OS boundary. | Native argument arrays and Windows quoting. | Real children echo metacharacters and Unicode arguments unchanged. |
| Ambient credentials enter the child. | Explicit environment and pipe-handle inheritance. | A child observes only the supplied environment. |
| Native launch errors disclose a secret. | Fixed categories with no raw error wrapping. | Canary values in paths, environment, input, and output never enter errors. |
| Input blocks capture or capture exhausts memory. | Concurrent input, available-byte reads, one output budget. | Full duplex, non-reading child, exact-boundary, and combined-stream tests. |
| Cancellation leaves owned helpers. | Cleanup on all outcomes and bounded group escalation. | Real helpers after success, nonzero exit, cancellation, overflow, and timeout. |
| Cleanup signals an independent or reused group. | Reserve the Unix leader PID through the last signal; retain Windows job handles. | An independent process survives; a second cleanup cannot signal a reaped child. |
| An escaped descendant holds output. | Bounded stream release and explicit residue. | A real Unix escaped stream holder is reported without output disclosure. |
| A successful terminate call hides residue. | Independent membership, reap, and pipe observations. | A Windows child with a query-only job handle proves denied cleanup and kill-on-close. Mutation checks protect observation decisions. |

The existing architecture checker owns the model and design checks.
The only model change adds the `process` component to the foundation layer.
The generated Go architecture diagram gains that component.
The shared foundation decisions already permit this package, so no ADR changes are necessary.
Existing CI runs real product tests on Linux, macOS, and Windows.
It runs the whole-repository architecture check and the available platform mutation gates.
The existing Windows mutation-tool limitation is tracked in #1617.
Cross-compilation supplies build evidence only.
Python production code, user documentation, and distribution stay unchanged.

## References

| Source and version | Section and use |
| --- | --- |
| [Go 1.27.3 os/exec](https://pkg.go.dev/os/exec) | CommandContext, WaitDelay, and argument handling; direct-child cancellation is insufficient. |
| [Linux man-pages wait](https://man7.org/linux/man-pages/man2/waitid.2.html) | `WNOWAIT`; retain the exited child until signalling ends. |
| [Linux man-pages process status](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html) | State and process-group fields; bounded ownership observation. |
| [Apple XNU process definitions](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/proc.h) | `extern_proc` and `SZOMB`; observe exit without reaping. |
| [Microsoft Job Objects, Windows 10 and later](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) | Membership, child inheritance, termination, and accounting. |
| [Microsoft process attributes, Windows 10 and later](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute) | Job and handle lists; atomic containment at launch. |
| [Microsoft pipe observation](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe) | Available-byte counts on asynchronous pipe handles. |
| [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf) | Short descriptive sentences, one topic, consistent technical names, and approved word meanings. |
