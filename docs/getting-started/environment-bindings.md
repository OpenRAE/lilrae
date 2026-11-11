# Scenario Environment And Docker Authority

This explanation describes how admitted scenarios receive environment values and Docker control.
Use [Scenario Environment Grants](../deployment.md#scenario-environment-grants) to configure an operator source.
The same binding rules apply to base-container nodes and generated Compose services.

## Environment Sources

Authored values are delivered as written.
A generated output reaches only the node that declares its `value_from` reference.
A variable without a value needs a grant or admitted startup-adapter binding if classified `operator_secret`, `redacted`, or `secret_fixture`.
Other variables without values are delivered empty, even when the image has a default.
A matching shell or `.env` name alone does not grant access.

A value-less `secret_fixture` requires OPEN `runtime-environment` authority.
Under EXACT authority, RAES expects that fixture to remain empty.
Missing authority or an incompatible declaration stops binding preflight before scenario network, volume, or container mutation.
An external operational credential under EXACT authority needs the `operator_secret` or `redacted` classification.
Authored fixture values remain valid under EXACT authority.

A grant binds one admitted pack, consumer node, variable, and exact source name.
Sources are `process-environment` or `project-env-file`.
The grant stores names, never values.
Project-tree scenarios have no pack identity; pack grants and pack startup adapters do not apply.
They need authored fixtures or declared generated outputs instead.

Startup adapters declare grants separately from fixtures and aliases.
Their grants can read only project `.env` keys supplied by that plan's fixtures or aliases.
Adapter selection must match the admitted pack's full identity.

A start captures its sources once; later starts refresh them.
Failed preflight discards previous bindings.
An unused grant causes a warning.
Errors identify nodes, variables, and source names without disclosing values.

## Service Isolation

Each sourced value is written to an owner-only service env file under `.aptl/realization/sourced-environment/`.
The generated override attaches that file to its consumer alone.
A value containing a single quote or an odd trailing backslash count cannot use that encoding.
Preflight refuses it before realization, as it does a missing or empty source.
Generated references must match the declared artifact, output, and consuming node.
Another output with the same variable name cannot satisfy that reference.

The Compose client inherits a restricted environment.
It retains Docker settings, client paths, certificate settings, proxies, Compose options, `APTL_*`, `BUILDKIT_*`, and `BUILDX_*` settings.
Other Compose substitutions read the project `.env` instead of arbitrary shell variables.
Changing a shell variable therefore does not override a project `INDEXER_PASSWORD` or `GRAFANA_ADMIN_PASSWORD` value.

LilRAE escapes authored `$` characters as `$$` in the generated Compose model.
Compose restores the literal dollar character.
This applies to commands, environment values, paths, content destinations, filenames, image references, and host addresses.
An authored `${INDEXER_PASSWORD}` therefore remains literal instead of receiving the project's credential.
A shell `"$@"` also reaches the container shell unchanged.

Every scenario uses the generated model, including project-tree scenarios.
The root `docker-compose.yml` does not supply that scenario model's services or environment.
Environment packs with a root `docker-compose.yml` are refused.
Raw Compose operation bypasses this admission and binding work.

## Evidence And Readback

Run evidence contains neither sourced values nor their digests.
Value-less `operator_secret` and `redacted` bindings are observed by presence only.
Value-less `secret_fixture` bindings are omitted from recorded realized environment data.
An unsalted digest would allow credential guessing.
Authored fixture values retain RAES's normal digest representation.
Generated values identify their artifact and consumer without a value commitment.

Generated operational credentials under EXACT authority require `operator_secret` or `redacted`.
Other generated classifications require OPEN authority because their required readback would expose a secret digest.
Preflight refuses incompatible declarations before mutation.
LilRAE also omits Docker's environment-derived `com.docker.compose.config-hash` inventory label.
Python and MCP serialization mask that label in older snapshots and text.

## Docker Socket Authority

A host Docker socket holder controls the daemon with root-equivalent authority.
LilRAE permits a socket only for a node admitted as Docker control authority.
In acquired TechVault, that node is `shuffle-orborus`, the workflow worker manager.
It receives exactly one read-write `/var/run/docker.sock` bind.
LilRAE prepares the exact worker and app images named by spawn templates.
The rendered service sets `SHUFFLE_AUTO_IMAGE_DOWNLOAD=false`.

Before startup, model validation rejects unauthorized socket binds or a control service with `DOCKER_HOST` or `DOCKER_CONTEXT` overrides.
LilRAE's capture sidecar and operator relays receive no Docker socket.
Containers subsequently created by the admitted socket holder are outside that model check.
The socket holder can create further containers because it already controls the daemon.
