# ADR-001: Migrate from AWS/Terraform to Local Docker Compose

## Status

accepted

## Date

2025-08-06

## Context

APTL v1.x used AWS and Terraform for the whole lab.
The SIEM used qRadar on a c5.4xlarge EC2 instance.
Kali used a t3.micro instance, and the victim used RHEL 9.6.
A VPC, public subnet, security groups, and bastion supplied network access.
S3 and DynamoDB stored Terraform state; UUID-based bucket names reduced enumeration.

The recorded continuous cost was about $280 per month.
The qRadar instance accounted for about $250 per month.
qRadar Community Edition needed a manually transferred 5 GB ISO and 1–2 hours of installation.
Its limits were 5,000 events per second and a 30-day trial license.

Infrastructure preparation took 30–60 minutes before the qRadar installation.

These are historical costs and timings from the migration decision.
They are not current AWS prices or deployment guarantees.
Repeated setup and billing made the lab difficult to use for personal training.
AWS credentials, IAM permissions, and billing administration also made sharing harder.

### Alternatives Considered

1. Multi-cloud Terraform could reduce some costs but would keep cloud billing and increase maintenance across providers.
2. Vagrant and VirtualBox would provide local VMs but increase disk use and provisioning time.
3. Kubernetes through kind or minikube would add cluster administration for a lab that then needed about 5–15 containers.
4. Docker Compose offered local declarative deployment without cloud billing and supported offline use after image acquisition.

## Decision

Replace the AWS and Terraform deployment with local Docker Compose.
The original decision defined lab containers in one `docker-compose.yml`.
Startup used `docker compose up`, followed later by the historical `aptl lab start` interface.
Profiles selected subsets of containers under [ADR-005](adr-005-docker-compose-profiles.md).
Wazuh replaced qRadar under [ADR-002](adr-002-wazuh-siem.md).
Docker bridges replaced VPC networking under [ADR-006](adr-006-four-network-segmentation.md).

The initial v2.0.0 deployment had five containers.
They were Wazuh Manager, Wazuh Indexer, Wazuh Dashboard, a Rocky Linux victim, and Kali.
A later version of this record reported 19 containers across four networks.
That count is historical and does not describe every current Scenario Pack.

[ADR-046](adr-046-dynamic-raes-scenario-realization.md) and [ADR-051](adr-051-component-level-raes-realization.md) define later scenario realization.
The admitted plan now supplies scenario topology and content.
The [root topology reference](../reference/compose-topology.md) identifies compatibility declarations and stubs.
The supported current startup procedure belongs to the [deployment guide](../deployment.md).

### What Was Removed

The migration removed Terraform code under `infra/` and `vms/`.
It removed AWS VPC, security-group, and S3 state configuration.
It also removed qRadar integration, bastion access, and cloud-cost administration from the local deployment path.

### What Was Preserved

The lab still combined a SIEM, an attacker, and victim systems.
MCP continued to provide agent access, and SSH continued to provide container access.
The documentation retained its structure while moving from VitePress to MkDocs.

## Consequences

### Positive

- Local deployment removed recurring cloud billing.
- The decision expected container startup in seconds instead of 30–60 minutes for infrastructure preparation.
- Previously acquired images supported offline use.
- Declarative deployment removed Terraform state and cloud drift from the local path.
- The original `git clone && aptl lab start` example represented a simpler setup than the AWS workflow.
- Docker support made local deployment possible on Linux, macOS, and WSL2, subject to each supported backend's limits.

### Negative

- Containers compete for one host's resources and do not provide horizontal scaling.
- The record estimated about 20 GB RAM for the then-current full stack.
- Docker bridge latency differs from enterprise networks.
- Linux Docker cannot run Windows containers natively; Windows endpoints need a separate VM.
- Vulnerable containers share the host kernel, so escape can affect the host.
- Resource limits and non-root execution reduce some risks but do not provide a VM boundary.

[ADR-060](adr-060-vm-only-seat-containment.md) defines the later disposable-seat containment decision.
The original local-container decision does not supersede that requirement.

### Risks

- The record identified resource contention below 16 GB RAM; profiles allowed smaller deployments.
- Docker Desktop license changes could affect commercial use; Linux Docker Engine remained an alternative.
- The Compose v1-to-v2 migration required `docker compose` instead of `docker-compose` commands.
