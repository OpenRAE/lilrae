<a id="hosted-backup-seats-for-a-workshop"></a>

# Prepare Historical Hosted Backup Seats

Use this guide only for a separately approved reconstruction of the July 28, 2026 contingency.
You need the exact pinned payload, an approved AWS account, private operator storage, and authorized cloud budget.
Do not provision hosts, transfer payloads, or create public endpoints without approval for that deployment.
Run lab operations and semantic checks only in approved isolated hosts or CI.

The result is one independently admitted browser seat per participant, up to twelve seats.
This procedure does not qualify the current LilRAE appliance or development branch.
Read the [pinned trial reference](hosted-backup-reference.md) before selecting it.
Its legacy `aptl` commands belong to the pinned payload; do not replace them mechanically with current selectors.
For the supported desktop-seat route, use [Workshop setup](setup.md).

## Current Go/No-Go Truth

Review the [trial outcome and limitations](hosted-backup-reference.md#trial-outcome).
Obtain an explicit event decision for provider authentication and the historical payload.
Do not infer readiness from the existence of these commands.

## Tested Recipe

Use the exact [proof inputs](hosted-backup-reference.md#proof-inputs) when reconstructing this trial.
Validate their availability and integrity before launching an event seat.

## Two Days Before The Event

Complete these gates while there is still time to change course:

1. Confirm the AWS account, region, quota, subnet, and operator source IP.
2. Build one canary from the tested recipe.
3. Put a real event-domain A record on the canary and rerun the TLS and browser
   checks. The proof used `sslip.io` only because no owned hosted zone was
   available in the test account.
4. Authenticate the chosen coding agent as the participant will and make one
   harmless model call through the intended credential boundary.
5. Run the four semantic MCP checks.
6. Stop and start the lab once using the recovery gate in this runbook.
7. Preserve the canary and its Docker cache.
   An event AMI can reduce launch time.
   It remains a mutable contingency image, not a sealed appliance.
8. Check that 192 Standard On-Demand vCPUs, plus replacement headroom, are
   available if all twelve `m6i.4xlarge` seats may run at once.

Do not launch twelve seats merely to prove that one repeatable seat works.

## Operator Inputs

Use a private operator directory outside the repository:

```bash
umask 077
export AWS_PROFILE=catalyst-dev
export AWS_REGION=us-east-2
export TRIAL_ID=blackhat-arsenal
export EVENT_DOMAIN=labs.example.org
export OPERATOR_CIDR=203.0.113.10/32
export EXPECTED_AWS_ACCOUNT=123456789012
export AMI_ID=ami-0dc6aa44dbcdd872e
export SUBNET_ID=subnet-replace-me
export STATE_DIR=/secure/operator-state/blackhat-arsenal
export PAYLOAD_DIR=/secure/operator-state/hosted-seat-payload
mkdir -m 0700 "$STATE_DIR"
```

Replace every example value. Do not put these exports in shell startup files.
The event domain must be one you control. `OPERATOR_CIDR` must be one exact
public IPv4 address, not a venue or corporate network range.

Reject SSO configuration and confirm the caller before mutation:

```bash
test -z "$(aws configure get sso_session --profile "$AWS_PROFILE")"
test -z "$(aws configure get sso_start_url --profile "$AWS_PROFILE")"
test -z "$(aws configure get sso_region --profile "$AWS_PROFILE")"
test "$(aws sts get-caller-identity \
  --profile "$AWS_PROFILE" \
  --query Account \
  --output text)" = "$EXPECTED_AWS_ACCOUNT"
```

Check the Standard On-Demand quota:

```bash
aws service-quotas get-service-quota \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --service-code ec2 \
  --quota-code L-1216C47A \
  --query 'Quota.{Value:Value,Unit:Unit}' \
  --output table
```

Stage the exact source inputs once from the APTL repository. This bundle has
no credentials, generated `.env`, or runtime state:

```bash
uv run python tools/workshop/stage_hosted_seat_payload.py \
  --repo-root . \
  --output-dir "$PAYLOAD_DIR"

sha256sum "$PAYLOAD_DIR/manifest.json"
```

The stager resolves the three pinned Git commits and replaces the certificate helper.
It checks and applies the admitted Kali patch, copies the smoke helper, and writes a manifest. It refuses to overwrite a prior payload.
Build it before the event and keep that exact directory for every seat.

## Create The Shared Event Security Group

One event security group may be attached to all twelve otherwise independent
VMs. Create it once in the selected VPC:

```bash
VPC_ID="$(aws ec2 describe-subnets \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --subnet-ids "$SUBNET_ID" \
  --query 'Subnets[0].VpcId' \
  --output text)"

SG_ID="$(aws ec2 create-security-group \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-name "$TRIAL_ID-seats" \
  --description "$TRIAL_ID hosted desktop seats" \
  --vpc-id "$VPC_ID" \
  --tag-specifications \
    "ResourceType=security-group,Tags=[{Key=aptl-trial,Value=$TRIAL_ID}]" \
  --query GroupId \
  --output text)"

aws ec2 authorize-security-group-ingress \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --group-id "$SG_ID" \
  --ip-permissions \
    "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$OPERATOR_CIDR,Description=event-operator}]" \
    'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description=acme-and-redirect}]' \
    'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=participant-dcv}]'
```

There must be no ingress for UDP 443, TCP/UDP 8443, RDP, Docker, the victim,
Wazuh, or another APTL service. Do not assign public IPv6 for this event
recipe.

## Prepare One Seat

The helper accepts only `seat01` through `seat12`, binds the username to the
exact hostname, generates an independent 256-bit passphrase, and creates every
file once with owner-only permissions:

```bash
export SEAT_ID=seat01
export SEAT_HOSTNAME="$SEAT_ID.$EVENT_DOMAIN"

uv run python tools/workshop/hosted_seat.py prepare \
  --state-dir "$STATE_DIR" \
  --trial-id "$TRIAL_ID" \
  --seat-id "$SEAT_ID" \
  --hostname "$SEAT_HOSTNAME"
```

The command prints paths but never the passphrase. It refuses to overwrite an
existing credential or follow a symlink. The only participant secret is:

```text
$STATE_DIR/credentials/seat01.json
```

Do not open all credential files on a projected screen. Give each participant
only their URL, username, and passphrase.

## Launch One VM

The following launches exactly the selected seat. It does not loop:

```bash
INSTANCE_ID="$(aws ec2 run-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --image-id "$AMI_ID" \
  --instance-type m6i.4xlarge \
  --subnet-id "$SUBNET_ID" \
  --security-group-ids "$SG_ID" \
  --associate-public-ip-address \
  --metadata-options \
    HttpEndpoint=enabled,HttpTokens=required,HttpPutResponseHopLimit=1 \
  --block-device-mappings \
    'DeviceName=/dev/sda1,Ebs={VolumeSize=200,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --tag-specifications \
    "ResourceType=instance,Tags=[{Key=Name,Value=$TRIAL_ID-$SEAT_ID},{Key=aptl-trial,Value=$TRIAL_ID},{Key=aptl-seat,Value=$SEAT_ID}]" \
    "ResourceType=volume,Tags=[{Key=aptl-trial,Value=$TRIAL_ID},{Key=aptl-seat,Value=$SEAT_ID}]" \
  --count 1 \
  --query 'Instances[0].InstanceId' \
  --output text)"

aws ec2 wait instance-status-ok \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID"

PUBLIC_IP="$(aws ec2 describe-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)"
```

Record the instance and resulting volume IDs in the private seat ledger. Check
that the AMI is still available, x86-64, and owned by Canonical before every
event launch. Check the volume reports `Encrypted=true` and
`DeleteOnTermination=true`.

Create or update the exact DNS A record:

```text
seat01.labs.example.org.  60  IN  A  <PUBLIC_IP>
```

Wait until the public resolver used by participants returns that address.

For temporary operator access, use EC2 Instance Connect instead of creating an
AWS key-pair resource:

```bash
KEY_DIR="$(mktemp -d)"
chmod 0700 "$KEY_DIR"
ssh-keygen -q -t ed25519 -N '' -f "$KEY_DIR/operator"

AZ="$(aws ec2 describe-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' \
  --output text)"

aws ec2-instance-connect send-ssh-public-key \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-id "$INSTANCE_ID" \
  --availability-zone "$AZ" \
  --instance-os-user ubuntu \
  --ssh-public-key "file://$KEY_DIR/operator.pub"
```

Repeat the `send-ssh-public-key` call immediately before each SSH connection;
the admission is short-lived.

## Provision The Host

Use a clean Ubuntu host or a prebuilt event image that passed this exact
procedure. Do not provision over an unrelated working checkout.

First record the cloud Netplan baseline and reserve APTL's UDP 5353 before
installing the desktop:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" '
  set -e
  sudo install -d -m 0700 /root/aptl-network-baseline
  sudo cp -a /etc/netplan/. /root/aptl-network-baseline/
  sudo systemctl mask avahi-daemon.service avahi-daemon.socket
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ubuntu-desktop-minimal gdm3 curl ca-certificates gnupg jq openssl \
    python3 python3-venv pipx
'
```

The desktop installs NetworkManager. Make its ownership explicit instead of
letting it race the cloud image's `systemd-networkd` configuration:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" '
  set -e
  PRIMARY_MAC="$(cat /sys/class/net/ens5/address)"
  printf "%s\n" \
    "network:" \
    "  version: 2" \
    "  renderer: NetworkManager" \
    "  ethernets:" \
    "    ens5:" \
    "      match:" \
    "        macaddress: \"$PRIMARY_MAC\"" \
    "      dhcp4: true" \
    "      dhcp6: false" \
    "      set-name: \"ens5\"" |
    sudo tee /etc/netplan/50-cloud-init.yaml >/dev/null
  sudo chmod 0600 /etc/netplan/50-cloud-init.yaml
  sudo systemctl unmask \
    NetworkManager.service NetworkManager-wait-online.service
  sudo systemctl enable \
    NetworkManager.service NetworkManager-wait-online.service
  sudo netplan apply
  sudo systemctl disable systemd-networkd.service \
    systemd-networkd-wait-online.service
  sudo systemctl enable --now systemd-resolved.service gdm3.service
'
```

The transition may close the current SSH connection. Send the EC2 Instance
Connect key again, reconnect, and require `NetworkManager` to be active with
the expected private address. Reboot the canary once and require both EC2
status checks plus SSH to recover before installing the lab. The live proof's
original network outage occurred because this renderer/owner decision was
left implicit.

Install the tested Docker Engine, Compose plugin, Node.js, and npm before
staging APTL. The Docker package versions below are the proof versions:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" '
  set -e
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  printf "Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nSigned-By: /etc/apt/keyrings/docker.asc\n" \
    "$VERSION_CODENAME" |
    sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null
  sudo apt-get update
  sudo apt-get install -y \
    docker-ce=5:29.6.2-1~ubuntu.24.04~noble \
    docker-ce-cli=5:29.6.2-1~ubuntu.24.04~noble \
    containerd.io=2.2.6-1~ubuntu.24.04~noble \
    docker-buildx-plugin=0.35.0-1~ubuntu.24.04~noble \
    docker-compose-plugin=5.3.1-1~ubuntu.24.04~noble
  sudo usermod -aG docker ubuntu
'
```

The participant is intentionally not added to the Docker group. Install the
proof Node.js archive for the operator-owned APTL build:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" '
  set -e
  cd /tmp
  curl -fLO \
    https://nodejs.org/dist/v22.23.4/node-v22.23.4-linux-x64.tar.xz
  printf "%s  %s\n" \
    1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce \
    node-v22.23.4-linux-x64.tar.xz | sha256sum --check
  sudo tar -xJf node-v22.23.4-linux-x64.tar.xz -C /opt
  sudo ln -s /opt/node-v22.23.4-linux-x64/bin/node /usr/local/bin/node
  sudo ln -s /opt/node-v22.23.4-linux-x64/bin/npm /usr/local/bin/npm
  sudo ln -s /opt/node-v22.23.4-linux-x64/bin/npx /usr/local/bin/npx
  node --version
  npm --version
'
```

Install the pinned Amazon DCV packages:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" '
  set -e
  install -d -m 0700 /tmp/dcv-install
  cd /tmp/dcv-install
  curl -fLO https://d1uj6qtbmh3dt5.cloudfront.net/NICE-GPG-KEY
  curl -fLO \
    https://d1uj6qtbmh3dt5.cloudfront.net/2025.0/Servers/nice-dcv-2025.0-20103-ubuntu2404-x86_64.tgz
  printf "%s  %s\n" \
    a39374d39f2d849bd13ee101970bb9eea15a8c5ec743799b7cbb7f562ece9e17 \
    nice-dcv-2025.0-20103-ubuntu2404-x86_64.tgz | sha256sum --check
  gpg --import NICE-GPG-KEY
  tar -xzf nice-dcv-2025.0-20103-ubuntu2404-x86_64.tgz
  cd nice-dcv-2025.0-20103-ubuntu2404-x86_64
  sudo apt-get install -y \
    ./nice-dcv-server_2025.0.20103-1_amd64.ubuntu2404.deb \
    ./nice-dcv-web-viewer_2025.0.20103-1_amd64.ubuntu2404.deb
  sudo usermod -aG video dcv
'
```

Install Caddy from its signed stable Debian repository and confirm the
resulting version is the canary version before continuing:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" '
  set -e
  sudo apt-get install -y \
    debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key |
    sudo gpg --dearmor -o \
      /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt |
    sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
  sudo apt-get update
  sudo apt-get install -y caddy=2.11.4
  caddy version
'
```

Copy the generated non-secret configurations:

```bash
scp -i "$KEY_DIR/operator" \
  "$STATE_DIR/generated/$SEAT_ID/dcv.conf" \
  "$STATE_DIR/generated/$SEAT_ID/$SEAT_ID.perm" \
  "$STATE_DIR/generated/$SEAT_ID/Caddyfile" \
  "$STATE_DIR/generated/$SEAT_ID/aptl-host-ports.env" \
  ubuntu@"$PUBLIC_IP":/tmp/

ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" "
  set -e
  sudo install -m 0644 /tmp/dcv.conf /etc/dcv/dcv.conf
  sudo install -m 0644 /tmp/$SEAT_ID.perm /etc/dcv/$SEAT_ID.perm
  sudo install -m 0644 /tmp/Caddyfile /etc/caddy/Caddyfile
  sudo install -d -m 0755 /opt/aptl-event
  sudo install -o ubuntu -g ubuntu -m 0600 /tmp/aptl-host-ports.env \
    /opt/aptl-event/aptl-host-ports.env
  rm -f /tmp/dcv.conf /tmp/$SEAT_ID.perm /tmp/Caddyfile \
    /tmp/aptl-host-ports.env
"
```

Create a private CA and exact-host leaf certificate for Caddy's verified
loopback connection to DCV. This is not the public browser certificate; Caddy
obtains that automatically:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" "
  set -e
  sudo install -d -m 0700 /root/aptl-dcv-pki
  sudo openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
    -out /root/aptl-dcv-pki/ca.key
  sudo openssl req -x509 -new -sha256 -days 14 \
    -key /root/aptl-dcv-pki/ca.key \
    -subj '/CN=APTL DCV upstream CA' \
    -out /root/aptl-dcv-pki/ca.pem
  sudo openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out /root/aptl-dcv-pki/dcv.key
  sudo openssl req -new \
    -key /root/aptl-dcv-pki/dcv.key \
    -subj '/CN=$SEAT_HOSTNAME' \
    -addext 'subjectAltName=DNS:$SEAT_HOSTNAME' \
    -out /root/aptl-dcv-pki/dcv.csr
  sudo openssl x509 -req -sha256 -days 14 \
    -in /root/aptl-dcv-pki/dcv.csr \
    -CA /root/aptl-dcv-pki/ca.pem \
    -CAkey /root/aptl-dcv-pki/ca.key \
    -CAcreateserial -copy_extensions copy \
    -out /root/aptl-dcv-pki/dcv.pem
  sudo install -o dcv -g dcv -m 0600 \
    /root/aptl-dcv-pki/dcv.key /etc/dcv/dcv.key
  sudo install -o dcv -g dcv -m 0600 \
    /root/aptl-dcv-pki/dcv.pem /etc/dcv/dcv.pem
  sudo install -o root -g caddy -m 0640 \
    /root/aptl-dcv-pki/ca.pem /etc/dcv/dcv-upstream-ca.pem
"
```

Create the participant without sudo, Docker, or SSH access, and send the
password only through the encrypted SSH channel and `chpasswd` stdin:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" "
  set -e
  sudo useradd --create-home --shell /bin/bash '$SEAT_ID'
  sudo install -d -o '$SEAT_ID' -g '$SEAT_ID' -m 0700 \
    '/home/$SEAT_ID/.config'
  sudo install -o '$SEAT_ID' -g '$SEAT_ID' -m 0600 /dev/null \
    '/home/$SEAT_ID/.config/gnome-initial-setup-done'
"

jq -r '"\(.username):\(.passphrase)"' \
  "$STATE_DIR/credentials/$SEAT_ID.json" |
  ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" 'sudo chpasswd'
```

Keep shell tracing disabled around that pipeline. Do not pass the password or
its hash in argv, an environment variable, user data, a tag, or a log.

Transfer the previously staged payload and install it in `/opt/aptl-event`,
not in the participant's home:

```bash
tar -C "$PAYLOAD_DIR" -czf "$STATE_DIR/hosted-seat-payload.tar.gz" .
scp -i "$KEY_DIR/operator" \
  "$STATE_DIR/hosted-seat-payload.tar.gz" \
  ubuntu@"$PUBLIC_IP":/tmp/

ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" '
  set -e
  sudo install -d -o ubuntu -g ubuntu -m 0750 /opt/aptl-event
  sudo -u ubuntu tar -C /opt/aptl-event -xzf \
    /tmp/hosted-seat-payload.tar.gz
  rm -f /tmp/hosted-seat-payload.tar.gz
  python3 -m venv /opt/aptl-event/lab-runtime
  /opt/aptl-event/lab-runtime/bin/pip install \
    /opt/aptl-event/lab-source
  python3 -m venv /opt/aptl-event/profile-runtime
  /opt/aptl-event/profile-runtime/bin/pip install \
    /opt/aptl-event/profile-source
  install -d -m 0750 /opt/aptl-event/workshop
  cp -a /opt/aptl-event/lab-source/. /opt/aptl-event/workshop/
'
```

Initialize the lab in the separate working directory and retain its generated
`.env` only on the host with owner-only permissions. Do not run either APTL
runtime from an arbitrary checkout.

The payload's Kali build must be cold-built at least once before the event.
The patch intentionally replaces the stale NodeSource step only inside the
Kali image with Kali's signed `nodejs` and `npm` packages.

Install the coding agent using its supported per-user installer as
`$SEAT_ID`. Do not use `sudo npm install -g`, do not share another user's
authentication directory, and do not authenticate until the event's model
credential decision is approved.

Start DCV and create exactly one owner session:

```bash
ssh -i "$KEY_DIR/operator" ubuntu@"$PUBLIC_IP" "
  set -e
  sudo systemctl enable --now dcvserver caddy
  sudo dcv create-session \
    --type=console \
    --owner '$SEAT_ID' \
    --user '$SEAT_ID' \
    --permissions-file '/etc/dcv/$SEAT_ID.perm' \
    --max-concurrent-clients 1 \
    --disable-login-monitor \
    '$SEAT_ID'
  sudo dcv set-display-layout --session '$SEAT_ID' 1440x900
"
```

The explicit single-display command is required. The proof initially produced
a black browser canvas when DCV exposed GNOME as four 800 by 600 outputs.

## Start And Prove The Lab

In the APTL working directory, load only the two host-port overrides and start
the pinned scenario through the APTL CLI:

```bash
set -a
. /opt/aptl-event/aptl-host-ports.env
set +a
/opt/aptl-event/lab-runtime/bin/aptl lab start \
  --scenario techvault-attacker-target
/opt/aptl-event/lab-runtime/bin/aptl lab status
```

Run the repository helper with the working project and the separately pinned
profile root:

```bash
/opt/aptl-event/profile-runtime/bin/python \
  /opt/aptl-event/hosted_seat.py smoke \
  --project-dir /opt/aptl-event/workshop \
  --profile-root /opt/aptl-event/profile-source
```

It must report all four stable IDs as `passed`:

```text
mcp.red.kali-command
mcp.red.ssh-authentication-attack
mcp.blue.indexer-investigation
mcp.blue.wazuh-investigation
```

The helper selects only `aptl-red`, `aptl-indexer`, and `aptl-wazuh` from the
profile. It does not load facilitator-only MCP registrations and prints
redacted outcomes rather than backend payloads.

## Seat Admission Checklist

A seat is assignable only when every item passes:

- `https://seatNN.<event-domain>` has a valid certificate for the exact name;
- HTTP redirects to that HTTPS URL;
- a wrong password is rejected and the seat's password succeeds;
- the browser shows a usable GNOME desktop at 1440 by 900;
- the terminal identity is the matching `seatNN`;
- `id -nG seatNN` contains only `seatNN`;
- the coding-agent version is the admitted version and the approved
  authentication path completes;
- the pinned runtime's lab status reports the required containers healthy;
- all four semantic MCP checks pass;
- public 80 and 443 are reachable;
- public 8443, 3389, 8080, 9200, 9443, 9444, and 55000 are not reachable;
- `ss` shows DCV 8443 only on `127.0.0.1` and `::1`;
- Caddy is the only public listener on 80 and 443;
- SSH is reachable only from the operator CIDR;
- the instance has no public IPv6 address.

Do not admit a seat based on a login page, `docker ps`, MCP `tools/list`, or
HTTP 200 alone.

## Repeat For Twelve

Keep a private assignment table:

| Seat | Hostname | Instance ID | Volume ID | Public IP | DNS checked | Admission checked | Assigned |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `seat01` | `seat01.<event-domain>` |  |  |  |  |  |  |
| ... | ... |  |  |  |  |  |  |
| `seat12` | `seat12.<event-domain>` |  |  |  |  |  |  |

For each row, change only `SEAT_ID`, derive `SEAT_HOSTNAME`, and repeat
**Prepare One Seat** through **Seat Admission Checklist**. Never run an
unreviewed launch loop. Two operators can divide the rows, but one operator
must audit the final instance, DNS, credential, and admission mappings.

If time is short, use the proven event image.
Rotate the seat password.
Create its exact DCV certificate and configuration.
Update DNS, then repeat every admission check.
An image alone does not make a copied seat ready.

## Recovery During The Event

For an inner lab restart:

```bash
/opt/aptl-event/lab-runtime/bin/aptl lab stop

until ! ss -lntH 'sport = :9200' | grep -q .; do
  sleep 1
done

set -a
. /opt/aptl-event/aptl-host-ports.env
set +a
/opt/aptl-event/lab-runtime/bin/aptl lab start \
  --scenario techvault-attacker-target
/opt/aptl-event/profile-runtime/bin/python \
  /opt/aptl-event/hosted_seat.py smoke \
  --project-dir /opt/aptl-event/workshop \
  --profile-root /opt/aptl-event/profile-source
```

The wait is mandatory. In the proof, one immediate restart saw Docker's old
9200 listener, automatically remapped the indexer to 20000, and correctly
failed both blue MCP checks. The gated retry kept 9200, reached APTL ready in
79 seconds, and passed all four operations.

If the VM is suspect, withdraw its assignment and terminate that event VM.
Launch the same recipe under the same logical seat ID.
Issue a new passphrase, update DNS, and repeat admission.
Do not preserve or repair participant state under event pressure.

## Teardown

First withdraw the participant assignment. Then, for every exact instance ID
in the private ledger:

```bash
aws ec2 terminate-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID"

aws ec2 wait instance-terminated \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID"
```

Delete the twelve DNS records, then delete the exact event security group.
Remove the temporary EC2 Instance Connect key directory and the owner-only
credential/state directory with an explicit, reviewed path.

Independently search the expected account and region for the `aptl-trial` value.
Check for running or stopped instances, available volumes, snapshots, AMIs, ENIs, and elastic IPs.
Also check security groups, DNS, temporary IAM resources, and AWS key pairs.
Remove participant credentials, model authentication state, and operator SSH material created for the trial.
The final audit must find none of these event resources.

For a reused host, do not terminate it.
Use the pinned runtime's destructive project stop after retaining required data.
Close its DCV session and remove the event participant account and home.
Restore DCV, Caddy, services, and packages from the change ledger.
Remove only the reviewed event directories.
Verify the original public listeners, accounts, security-group rules, and unrelated checkout against that ledger.

## Vendor References

Use the [vendor references](hosted-backup-reference.md#vendor-references) for the pinned recipe's external interfaces.
