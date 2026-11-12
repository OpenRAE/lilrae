# Issue #1566: Container helpers design

This design splits Go port 15 into four sub-issues and records the decisions
that they share. It refines the [container helpers preflight](issue-1566-container-helpers-preflight.md),
the [egress preflight](issue-1566-egress-preflight.md), and the
[capture and evidence preflight](issue-1566-capture-evidence-preflight.md).
Each sub-issue has its own design note, and the front matter of that note is
the design record of its packages.

## Decisions

1. **One sub-issue for each helper.** The helpers have separate contracts,
   runtime dependencies, and security boundaries. One pull request for all of
   them is too large to review with care, so `.gc/plan-rules.md` applies: each
   sub-issue delivers one pull request, and #1566 tracks them.

   | Sub-issue | Scope | Starts after |
   | --- | --- | --- |
   | 15d (#1746) | `cmd/lilrae-helper`, the helper image build, and the operator access relay | #1758 |
   | 15c (#1745) | The appliance egress proxy | #1746 |
   | 15a (#1743) | The boundary policy package, the boundary helper, and the probe | #1607, #1742, #1746 |
   | 15b (#1744) | The kali capture broker | #1607, #1746 |

   #1758 merges `dev` into `go-cutover`, so that each port reads the current
   Python contract. #1607 delivers the process runner. #1742 fixes the boundary
   helper readback before the port.
2. **One binary with fixed roles.** `cmd/lilrae-helper` is the one static
   Linux binary of ADR-065. Its first argument selects a role from a fixed set.
   Each image names its role in its entry point, so an image runs only that
   role. The binary grants no capability, mount, or network. The container
   configuration of the host grants them, as it does now.
3. **Go images beside the Python images.** The Python host runs `python3` in
   the current helper images, and the Python wheel ships their Dockerfiles. The
   Go images thus use new build contexts, and the Python release reads none of
   them. Go port 20 makes the Go host use the Go images. Go port 31 removes the
   Python images.
4. **Binary delivery.** A development build runs `go generate`. It compiles
   `lilrae-helper` with `CGO_ENABLED=0` and `-trimpath` for `linux/amd64` and
   `linux/arm64` into the helper build context. Git does not track the output.
   Each Dockerfile copies the binary for the BuildKit `TARGETARCH`, which is the
   platform of the daemon that builds the image. The image build needs no
   compiler and no module download. The release build and the embedding in
   `lilrae` belong to Go port 30 and Go port 10.
5. **Minimal, pinned images.** Each image has only the files that its role
   needs at run time. The relay and the egress proxy need no operating system
   files. The boundary image keeps `nft`, `ip`, and `tc`. The capture image
   keeps OpenSSH. Each base image is pinned by digest, and Dependabot watches
   each Dockerfile directory. An image that runs as user 65532 or `kali` now
   keeps that user.
6. **Contract cases first.** Each sub-issue adds black-box cases that run the
   helper as a process. The cases pass on the Python helper before the Go code
   exists. They cover the arguments, the environment variables, the exit codes,
   the standard output, and the rejected inputs. The serialization vectors of
   Go port 04 fix the digest bytes.
7. **One boundary policy type.** Sub-issue 15a defines the boundary policy
   once, in the core layer. The Go host of Go port 20 and the helper decode and
   check it with the same function. Before 15a selects the shared rules, it
   records the accepted and rejected cases of the Python host and helper. A
   shared rule must not reject an output that the host can produce.

## Data flows and threat model

```text
host (Go port 20) --policy JSON on stdin--> lilrae-helper boundary --> nft (kernel)
                  <--receipt JSON on stdout--
host --environment--> lilrae-helper relay <--bytes--> one declared target
appliance workload --CONNECT--> lilrae-helper egress --checked address--> model provider
operator --SSH (OpenSSH)--> forced command: lilrae-helper capture --SSH--> kali sshd
                                           \--frames--> private capture files --export--> host
```

The assets are the kernel firewall state, the capture evidence, the private
keys of the capture sidecar, and the egress allowance. The trust boundaries are
the host to container process boundary, the container network boundary, and
the OpenSSH session boundary.

| Threat | Mitigation |
| --- | --- |
| An image runs a role that it must not run, or a role gets more authority. | The entry point of each image names one role. The host keeps each capability grant. Decision 2. |
| A changed rule weakens SAF-002 or NET-005. | The contract cases and the readback of #1742 pass on the Python helper first. A rule change is a security change and needs its own issue. |
| A policy that the host accepts and the helper rejects, or the reverse. | One type and one check function. Decision 7. |
| A cached Python image runs in place of a Go image. | The Go images are separate images. Decision 3. |
| A binary for the wrong architecture runs on the daemon. | BuildKit selects the binary from the daemon platform. Decision 4. |
| An image carries a package with a known vulnerability. | Minimal images, digest-pinned bases, Dependabot, and the Trivy image scan. Decision 5. |
| A secret leaks through an argument, a log, or an error. | Policies pass on stdin, keys pass in protected files, and errors carry no input value. Each sub-issue keeps the redaction of its Python helper. |

The capture broker keeps the PTY ownership rules of
[ADR-042](../adrs/adr-042-sidecar-owned-pty-master.md). The appliance images
keep the offline seat payload of
[ADR-049](../adrs/adr-049-sealed-disposable-lab-appliance.md).
