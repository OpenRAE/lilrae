# Operate an appliance seat

Use an approved isolated host with the selected image's declared resources.
The [seat reference](appliance-seat-launcher.md) owns modes, fields, defaults, trust rules, and failure conditions.

## Prerequisites

1. Examine the [host prerequisites](appliance-seat-launcher.md#host-prerequisites).
2. Get the required KVM permissions from the host administrator.
3. Start another login session after a group-membership change.
4. Install the declared tools through the approved host package procedure.

For Debian or Ubuntu, the existing package command is:

```shell
sudo apt-get install qemu-system-x86 qemu-utils ovmf bubblewrap util-linux slirp4netns
```

5. Make sure that available resources meet the selected image's declared minimums.
6. Keep seat state in the private directory of the user who starts the seat.

## Choose desktop privileges and start a seat

1. Read the [privilege-mode contract](appliance-seat-launcher.md#desktop-privilege-modes).
2. When the participant must have no guest administration, select event mode:

```shell
lilrae seat start --desktop-mode event
```

3. Before you authorize a registry lookup or download, examine the acquisition prompt.
4. Examine the reported readiness and mapping before participant use.

For an approved administrative seat, select the mode on first start:

```shell
lilrae seat start --desktop-mode administrative
```

Enter the guest password through the private prompt.
Choose an empty answer only when passwordless guest sudo is intended.
For automation, use an approved private password file:

```shell
lilrae seat start --desktop-mode administrative --sudo-password-file /private/path/password
```

To change the generation's mode, stop and reset the seat:

```shell
lilrae seat stop
lilrae seat reset --desktop-mode event
lilrae seat start
```

Reset destroys the existing overlay.
Before you apply the new mode contract to an older image, use an explicit update and reset.

### Rescue a stopped guest

Install `virt-rescue` through the approved host procedure before recovery.
Stop the seat as its host owner:

```shell
lilrae seat stop --seat-root /home/seat-user/.local/state/aptl/seat
```

Run rescue as the host administrator:

```shell
sudo lilrae seat rescue --seat-root /home/seat-user/.local/state/aptl/seat
```

Examine or repair the guest files within the rescue shell.
Before you start the seat again, exit that shell.
Before you use this route, read the [rescue constraints](appliance-seat-launcher.md#desktop-privilege-modes).

### Select another publisher

Get the publisher's key through an independent approved channel.
Select its immutable image reference and key:

```shell
lilrae seat start --image ghcr.io/your-org/your-seat@sha256:<digest> --public-key publisher.pub
```

Use `--yes` only when automation explicitly authorizes acquisition.
Before you retry, examine signature and admission failures.
Do not replace verification with a mutable local image tag.

### Participant desktop

Open the desktop after readiness:

```shell
lilrae seat open-kiosk
```

Sign into the provider inside the guest if required.
Use the scenario application's own login when requested.
Use `lilrae lab info` inside the guest for current access details.
See [desktop endpoints](appliance-seat-launcher.md#desktop-endpoints) for namespace and certificate constraints.

## Updates are never forced

Read the [image-update contract](appliance-seat-launcher.md#image-selection-and-verification) before replacement.
Stop the seat, request the update, and start the accepted selection:

```shell
lilrae seat stop
lilrae seat update
lilrae seat start
```

Use `lilrae seat update --yes` only for explicitly authorized automation.
After an interrupted reset, stop the seat and repeat reset before use.
Before you confirm removal, examine cached images:

```shell
lilrae seat images
lilrae seat images --prune
```

For rollback, use a retained verified disk or acquire the intended immutable reference.
Do not assume that a superseded image remains cached.

## Reserving operator-selected ports

1. Read the [mapping fields and capacity rules](appliance-seat-launcher.md#port-mappings-and-capacity).
2. Pass one mapping for every declared publication:

```shell
lilrae seat stage \
  --seat-id seat-01 \
  --mapping participant,tcp,127.0.0.1,18080,127.0.0.1,8080
```

3. Resolve staging errors before startup.
4. Use the reported mapping with `lilrae seat open-kiosk`.
5. Examine coarse health with `lilrae seat status`.

Do not paste the private-namespace URL into an ordinary host browser.

## Reset and recovery

Reset destroys the overlay and creates another over the selected image:

```shell
lilrae seat reset --seat-id seat-01
```

Use recovery when reset followed by startup is intended:

```shell
lilrae seat recover --seat-id seat-01
```

After a physical-host reboot, reconcile persisted state:

```shell
lilrae seat reconcile
```

If reconciliation reports `host-reboot-detected` or `vm-not-running`, recover the seat before participant use.
A reset does not restore trust in a compromised physical host.

## Building the image

1. Read the [build and publication contracts](appliance-seat-launcher.md#image-build-and-publication-contracts).
2. Use a clean checkout of the selected source revision on the approved build host.
3. Examine build tools, KVM access, disk capacity, and the installed project environment.
4. Select the approved build directory.
Run this command:

```shell
APTL_SEAT_BUILD_ROOT="$PWD/build/seat-cut" scripts/appliance/build-seat-image.sh
```

5. Examine sanitization results and `seat-build.json` before publication.
6. Get explicit approval for the publication destination and signing authority.
7. Pass the approved credentials through the existing environment or key provider.
8. Keep signing values out of command arguments and shell history.
9. Keep the public channel unchanged during immutable publication:

```shell
scripts/appliance/publish-seat-image.sh build/seat-cut/out
```

10. Qualify that exact signed reference with a fresh CLI and empty private cache.
11. Use the [boundary qualification procedure](../components/appliance-qualification.md).
12. Record manual browser, scenario, and privilege observations separately.
13. Before you retry publication, resolve registry-permission failures.
14. After accepted qualification and authorized channel promotion, rerun publication with `APTL_SEAT_PUBLISH_LATEST=1`.

For a new public GHCR package, ask its owner to enable the approved public visibility before anonymous acquisition.
Do not rebuild the image merely to retry a permission failure.
