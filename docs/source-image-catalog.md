# Trusted source image selection

LilRAE binds a legacy node source name and version to a reviewed image reference
in its backend implementation catalog. This applies to sources without an
authored `artifact_requirement`. Authored artifacts and dynamic composition
keep their existing RAES admission rules.

For example, `bind9` / `9`, `postgresql` / `17`, and `nginx` / `stable` select
explicit catalog entries. The planner never turns an unknown selector into a
registry tag, looks up the newest image, or tries a list of fallback images.
An alias such as `stable` changes only through a reviewed catalog edit.
The in-tree paper scenario's `postgres` / `16` source also has an explicit pin.
The catalog keeps its declared major version separately from PostgreSQL 17.

## Authority and compatibility

Catalog selection requires an OPEN `compute-substrate` constraint. It selects
an image. It adds no environment variables, credentials, capabilities,
mounts, entrypoints, or published ports. Runtime facts can exclude incompatible
catalog records. Kit names, scenario names, node names, and Compose service
bindings do not select the image.

Each successful selection must have one eligible catalog record. Distinct
eligible records are ambiguous even when they share an image digest. Unknown
versions, omitted versions, wildcards, and spelling variations have no implicit
alias. Existing authored exact artifacts and trusted local component builds
keep their own routes. An unresolved authored artifact cannot use the catalog
as a fallback.

The existing `aptl.provisioner.image-policy-rejected` diagnostic reports a
bounded reason and does not echo a rejected source value:

| Reason | Meaning |
| --- | --- |
| `unknown-source` | No reviewed source/version binding exists. |
| `ambiguous-source` | More than one compatible policy record exists. |
| `incompatible-source` | Declared runtime or OS facts contradict the record. |
| `invalid-catalog-entry` | The record lacks a safe immutable reference or provenance. |
| `source-not-authorized` | Compute-substrate selection is closed. |
| `unsupported-windows-source` | A `windows-server` source is outside this backend's supported stack. |
| `catalog-image-unverified` | Independent readback could not corroborate the selected pin. |

Selection errors reach shared planning and direct apply validation before
provisioning. Catalog membership does not establish that the remaining runtime
contract can be realized.

## Provenance and running-image evidence

Image realization keeps the declared source, selected immutable reference,
catalog record identity, and provenance references. Existing image pins refer
to the immutable repository revision that declared them. New records keep the
upstream registry repository/tag used to retrieve and hash the manifest on
2026-10-15. These references document catalog inputs. They do not claim a
publisher signature or vulnerability attestation.

`catalog_revision` identifies the source aliases, image identity, compatibility
selector, OS constraints, and provenance references with RAES canonical JSON.
It identifies the selected non-secret policy record independently of a mutable
alias or a package version.

Readback uses the owned container's actual image ID, then examines that image's
repository digests against the selected repository and digest.
The existing image identity helper normalizes Docker Hub's canonical name aliases.
The helper never assumes that the first repository alias is the selected artifact.

Evidence distinguishes the selected registry digest from the observed Docker
configuration digest. A registry digest can identify a manifest or index.
`.Image` identifies the image configuration. The configuration digest is not
reported as though it were the selected registry digest. Missing or mismatched
readback fails apply and keeps its baseline snapshot.

For successful one-shot jobs, the existing completion receipt captures the
correlated configuration and selected repository digest before container
removal. Observation accepts that receipt only for the exact selected reference
and after inspection confirms that the container is absent. A replacement
container must pass its own live readback, even if its image ID is unreadable.

Successful snapshot entries keep this observation in
`payload.backend_evidence.source_image`, except for plans with account
credential bindings or materialization reporting. The credential result contract
admits no backend evidence in its entries (ADR-046), and materialization requires
portable payloads. The run outcome keeps the observation in both cases. Full
apply details keep it in `observation_evidence`. Compact reports keep
`source_image_evidence`. The run outcome carries the same bounded projection for
successful and failed applies, so it can reach the existing reproducibility archive.

## Release coverage and selected distributions

The coverage fixture was extracted with the public
`raes_env_packs.kits.load_kit_release()` API from the latest version of every kit
in [env-packs v6.3.1](https://github.com/OpenRAE/env-packs/releases/tag/v6.3.1),
revision `65d7272340f99a76eb7e5f58f2e88e717a925dff`.
It contains 46 kits and 51 nodes: 44 distinct Linux selectors and the Windows
selector. The fixture records the released source and runtime facts. It is not
a claim that all kits can already provision successfully.

The user approved more vendor registries and vetted community
distributions on 2026-10-15. The catalog covers all 44 Linux selectors. Every
source is resolved without a registry request during planning. Representative
distribution choices are:

| Selector | Selected distribution |
| --- | --- |
| `minio` / `stable` | PGSTY's community MinIO distribution, release `2026-08-04`, keeps the MinIO binary and interfaces. |
| `kea` / `stable` | The catalog uses ISC Kea DHCP4 `3.0.2` from `docker.cloudsmith.io`. |
| `application-service` / `stable` | Mendhak HTTP echo `42` gives the abstract HTTP response surface on port 8080. |
| `linux` / `stable` | Panubo SSHD `1.9.0` gives the Linux/SSH substrate on port 22. |
| `nftables` / `stable` | Nicolaka Netshoot's published build includes nftables. |
| `devpi` / `6` | The catalog uses Jonas Alfredsson's Devpi Server image. Its build provenance points to a lock for server `6.20.3`. |
| `openldap` / `stable` | The catalog uses the OpenLDAP distribution from Vegard IT. |
| `samba` / `4` | The catalog uses Instant Linux's Samba distribution with Samba DC and file-server components. |

All selected references are digest-pinned in the catalog. This includes choices
whose provenance tag is `latest`. The MinIO vendor repository denied anonymous
manifest access. The catalog explicitly records the approved community
distribution. It does not claim a vendor artifact.

Its
[release history](https://github.com/pgsty/silo/releases/tag/RELEASE.2026-08-04T00-00-00Z)
and immutable source revision are provenance inputs. The catalog does not
automatically track the later Silo distribution rename.

Source selection does not certify a complete kit startup. Configuration,
credentials, domain provisioning, capabilities, storage, and service readiness
remain independently admitted and observed through the existing runtime
boundaries. Image selection adds none of those permissions.

`src/aptl/backends/_lilrae_source_image_catalog.py` owns source aliases and pins.
Aliases of existing semantic profiles share their existing pins.
See [maintain source-image entries](reference/source-image-maintenance.md) for the editing and verification procedure.
