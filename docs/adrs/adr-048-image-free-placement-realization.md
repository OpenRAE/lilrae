# ADR-048: APTL Image-Free, Placement-Based Realization Envelope

## Status

accepted

## Date

2026-07-20

## Last Updated

2026-10-04

> **Terminology note ([#1193](https://github.com/Brad-Edwards/aptl/issues/1193)).**
> "Image-free" in this record is a historical term, kept so the original
> decision text stays unchanged. Each node starts from a real base image.
> Native materialization then applies its declared state.
> The historical term does not mean absence of container images. Current documentation and code call them
> **base-container-materialized nodes**; see
> [Node Realization Routes](../components/node-realization.md).

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [realization Reference](../components/node-realization.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

ADR-035 adopted RAES SDL and wired APTL in as a conformant RAES backend.
ADR-046 compiles SDL into `RuntimeModel`, plans `ExecutionPlan`, and interprets typed native realization. `AptlRealization` and `DeploymentRealizationSpec` carry that result to the backend. ADR-046's Image Realization Addendum (issue #574) then
defined a node's realized identity as an image: a node `source` is either
pulled (a pullable image reference) or built (from captured `source.build`
provenance).

Issue #581 exposes why that image model is the wrong foundation for APTL's
realization envelope. The backend must demonstrate meaningful realization of admitted RAES declarations within its supported envelope. Booting one fixed appliance does not establish that capability.

A
pre-baked appliance image (for example `wazuh/wazuh-manager:4.x` or
`docker.elastic.co/...`) already contains the node's software, services,
content, accounts, and configuration. When a node is realized by pulling or
building such an image, the SDL is not driving the realization; the image is.
The range's meaningful detail lives outside the SDL, in a hand-curated image
specific to one scenario.

That proves nothing about RAES's ability to compose
ranges. It re-encodes the previously hand-built Docker lab in RAES clothing.

RAES already models the surface needed to do this properly. A compiled
`ProvisioningPlan` carries not only nodes and networks but placements:
`feature-binding`, `content-placement`, and `account-placement`. A node's
`runtime` (`RuntimeConfiguration`) is a deep declarative desired-state contract:
`packages`, `software_components`, `filesystem_inventory`, `local_identity`,
`identity_authorities`, `service_manager_units`, and typed service families such
as `security_monitoring_managers` (Wazuh) and `network_detection_engines`
(Suricata). `Source` is backend-agnostic. So RAES can express an operating
system plus everything running on it; the backend, not an appliance image, is
responsible for materializing that state.

The RAES reference backend (`raes_reference_backend`, RUN-314) realizes plans
over an in-process or OCI driver. It is an emulation backend: its driver stands
up a container from an `image_ref` and records placements for provenance without
installing software. It proves the plan-interpretation and provenance shape, not
real materialization.

APTL is a single-user, local, Docker-based cyber range. That is a load-bearing
property, not an implementation detail. APTL and Shifter (full cloud VMs) are
the two distinct real conformant backends alongside the RAES libvirt reference;
backend diversity is the research value of RAES conformance. APTL must therefore
remain Docker-based and must not migrate to libvirt or VMs, since doing so would
collapse the set of distinct conformant backends.

## Decision

APTL realizes a node's meaningful state from the compiled RAES
`ProvisioningPlan` and `RuntimeConfiguration`, not from a pre-baked appliance
image. This supersedes ADR-046's Image Realization Addendum as APTL's
node-realization model.

1. **Placements and declared runtime state are the realization mechanism.** The backend applies declared packages, software, bindings, content, filesystems, accounts, and local identity to the target. The result must meet the authored granularity, not approximate a Compose role. The SDL and
   its compiled plan are the sole authority for what a node contains.

2. **A generic base substrate is permitted; an appliance image is not.** A node
   still runs on some container base. A generic operating-system base image (the
   substrate a container needs to exist) is allowed. A whole-node appliance must not silently supply scenario software, services, content, accounts, or configuration outside the authored contract. The test is:
   would a generic image of the same OS family still produce the same meaningful node under the declared materialization? If not, the range detail is
   being smuggled in through the image and the realization is invalid.

3. **APTL stays Docker-based and local.** No migration to libvirt or VM targets.
   The original envelope targets a single-user local Docker range. It does not copy the reference backend's implementation choices. The decision covers the whole realization envelope and its security, maintenance, extension, and reliability goals. It is not permission for one-scenario shortcuts.

4. **Expressivity gaps are surfaced upstream, never worked around.** A missing portable node fact needs an upstream RAES contract issue. Local schemas, scenario branches, appliance images, and silent injection cannot replace that contract. Permitted backend detail requires authored open realization scope, `AuthorRealizationPosture.OPEN`. It must not enter through a closed-world default. Surfacing expressivity gaps is an intended output of this work.

5. **`docker-compose.yml` is not an authoring or topology authority.** Any
   retained Compose file is derived reference output only. It is never a
   topology, recovery, packaging, validation, or parity input. Realization,
   lifecycle, and parity all key on the admitted execution identity and the typed
   realization, per ADR-046.

6. **Parity is bidirectional.** Static and live gates prove the realized range
   equals the admitted graph: both missing and unexpected runtime objects
   (containers, networks, volumes, mounts, ports, dependencies, placements) fail.
   A healthy subset is not parity.

The canonical authority chain remains ADR-046's: catalog/SDL, RAES
parse/compile/plan, `interpret_provisioning_plan`, `AptlRealization`,
`DeploymentRealizationSpec`, deployment backend, observation. This ADR changes
what a node's realized content comes from (declared desired state onto a base,
not an appliance image), not the pipeline that carries it.

### Generic materializer contract (the invariant)

APTL's provisioner is a scenario-agnostic materializer. It contains no
per-product, per-node, or per-scenario branch. There is no `wazuh`, `ad`, `misp`,
`shuffle`, or `techvault` special case anywhere. It realizes any conformant node
purely from that node's declared desired state, and this invariant is what proves
RAES can compose an arbitrary conformant SDL. If APTL needs a product-specific
code path to stand a node up, the design has failed the bar.

Concretely, for every node the materializer:

1. **Base substrate.** Starts a generic base-OS container image derived solely
   from the node's `os` and `os_version` through a small, fixed,
   scenario-independent base-image map. There is no per-node image and no
   appliance image.
2. **Software.** Installs the node's declared `runtime.packages` and
   `software_components` (package-manager provenance) via the declared package
   manager. Software identity comes from the SDL, not a baked image.
3. **Filesystem and config.** Places the declared `content` (file, directory, or
   dataset) and `runtime.filesystem_inventory` entries, using APTL's existing
   containment, symlink-rejection, and atomic-write discipline.
4. **Identity.** Creates the declared `runtime.local_identity` (users, groups,
   sudo) and realizes `accounts`, including domain-bound accounts through the
   existing directory provider.
5. **Services.** Installs, enables, and starts declared `service_manager_units` and units implied by typed service families. One generic mechanism owns this work without product-specific startup paths.
6. **Runtime wiring.** Applies declared networks, mounts, published ports,
   environment (reference names and classification only), Linux capabilities, and
   container settings.
7. **Verify.** Observes the realized node and asserts it satisfies the declared
   runtime desired-state contract by read-after-write. A fact APTL cannot
   observe and verify is not claimed as realized.

APTL's backend manifest is expanded to honestly declare exactly the realization
kinds the materializer both materializes and verifies (`packages`,
`software_components`, service units and families, `filesystem_inventory`,
`local_identity`), drawn from RAES's published controlled vocabularies. An unsupported declared fact requires an upstream contract fix or blocking admission diagnostic. It must not disappear or use a product-specific workaround.
Capability-specific knowledge (which packages, which config, which service units
make a working Wazuh) lives entirely in the SDL.

## Consequences

### Positive

- This supplies a native demonstration of supported RAES declarations. A hand-built Compose lab with renamed inputs would not establish that research claim.
- The realization envelope generalizes beyond TechVault: any node describable by
  RAES features, content, and accounts realizes without a bespoke image.
- Expressivity gaps in RAES are surfaced as concrete upstream issues, improving
  the contract for every conformant backend.

### Negative / costs

- Substantially more realization work than pulling images: features, content,
  and accounts must be provisioned onto a base substrate. TechVault is large; a
  full local range may need 20GB+ of memory. This is accepted.
- The TechVault SDL must declare node features, content, and accounts at
  docker-compose granularity or better. Nodes that previously leaned on an
  appliance image must express that capability declaratively.
- This is a large change delivered as one branch, many commits, one PR.
- The image-based node realization from ADR-046's Image Realization Addendum and
  its supporting code is superseded and removed from the operational path.

### Risks

- Some node capabilities may exceed the current RAES expressivity, or exceed what
  a single generic base-OS container can host. Mitigation: file RAES contract
  issues and, where legitimate, author open realization scopes; never fall back
  to an appliance image. A node that cannot yet be realized image-free fails
  admission loudly rather than silently regressing to an image.

## Supersession

> **Superseded in part by [ADR-051](adr-051-component-level-raes-realization.md)
> (2026-07-28).** Decision point 2 no longer prohibits every component image.
> ADR-051 supersedes that generic-substrate-only clause. Authored `Source.artifact_requirement` can require a pinned upstream or digest-bound component artifact.
>
> SEM-218 binds that posture; the backend cannot substitute generic materialization for an exact declaration. Other decisions remain: placement ownership, observed refusal, no scenario branches, local single-user scope, bidirectional parity, derived Compose, and no whole-range appliance. ADR-051 requires a complete runtime contract for every node.
>
> A component image cannot own scenario topology, credentials, accounts, seeded content, or peer wiring.

This decision supersedes ADR-046's original image addendum from #574. ADR-051 later permits component artifacts under authored contracts, as the update above states. ADR-046 otherwise remains authoritative
for the dynamic realization pipeline, network realization, generated-model and
lifecycle contract, and parity model. ADR-046's addendum is annotated to point
here.
