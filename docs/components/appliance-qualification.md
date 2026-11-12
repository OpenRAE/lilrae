# Qualify an appliance boundary

Use an approved isolated KVM host with the declared image resources and required tools.
The [boundary reference](appliance-boundary.md#qualification-and-start-gate) defines evidence, versions, failure conditions, and trust requirements.

## Qualification And Start Gate

1. Select the exact source revision and signed immutable image reference.
2. Get the publisher's public key through the approved trust process.
3. Install a fresh LilRAE CLI and use an empty private image cache.
4. Run the normal image qualifier on the approved host:

```shell
APTL_SEAT_QUALIFY_KEEP_WORK=1 scripts/appliance/qualify-seat-image.sh \
  ghcr.io/owner/seat@sha256:<published-manifest-digest>
```

The command prints its retained private workspace path.
Keep that workspace within the approved evidence boundary.

5. For another publisher, pass its independently obtained public key as the second argument.
6. Keep the source, disk, configuration, policy, host, guest, and observed result identities.
7. Make sure that normal first boot, readiness, warm restart, reset, and second clean start completed.
8. Examine failed boundary inventory entries and positive/negative reachability probes.
9. Stop qualification if evidence is missing, stale, incomplete, or inconsistent.
10. Examine browser access through Guacamole and xrdp.
11. Record the scenario's attack, detection, Shuffle, repair, and retest observations separately.
12. Run the privilege qualifier for event mode and both administrative password modes:

```shell
scripts/appliance/qualify-seat-privileges.sh ghcr.io/owner/seat@sha256:<published-manifest-digest>
```

13. Examine browser login separately from automated privilege checks.
14. Keep the public image channel unchanged until the required qualification record is accepted.

Do not replace normal first boot with the retired smoke service.
A unit-test pass does not replace the required live observations.
See [build and publish a seat](../reference/appliance-seat-operations.md#building-the-image) for the full procedure.
