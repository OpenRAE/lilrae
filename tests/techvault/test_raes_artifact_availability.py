"""The released TechVault pack declares artifact demand (#1700)."""

from __future__ import annotations

from raes.parser import parse_sdl_file

from aptl.backends.raes_artifact_availability import artifact_availability_for_scenario
from tests.test_raes_artifact_availability import _Probe


def test_shipped_scenario_declares_artifact_demand_for_every_imaged_node(tmp_path):
    """The shipped scenario pins each artifact-bearing address to an exact artifact."""

    from raes import instantiate_scenario

    from tests.techvault.pack import techvault_scenario_path

    scenario = parse_sdl_file(techvault_scenario_path(tmp_path))
    scenario = instantiate_scenario(
        scenario,
        parameters={
            f"flag_{host}_{level}": f"{host}-{level}"
            for host in ("victim", "workstation", "webapp", "fileshare", "ad")
            for level in ("user", "root")
        },
    )
    probe = _Probe(set())

    context = artifact_availability_for_scenario(scenario, probe)

    # One address per artifact-bearing address — every image-backed node and
    # every digest-pinned content placement in the full TechVault env-pack. The
    # 7.0.0 pack's backend-neutral inventory contains 29 exact content demands:
    # it removed the two Cortex analyzer artifacts with TheHive and Cortex.
    # Compute substrates are selected separately under OPEN authority.
    assert len(context.requirements) == 29
    addresses = {requirement.address for requirement in context.requirements}
    assert {
        "provision.content.ad-rules",
        "provision.content.database-rules",
        "provision.content.falco-rules",
        "provision.content.postgresql-decoders",
        "provision.content.samba-decoders",
        "provision.content.suricata-rules",
        "provision.content.wazuh-integrations",
        "provision.content.webapp-rules",
    } <= addresses
    # Exact pins are probed by digest-pinned reference; materialized components
    # probe their locked base input the same way.
    assert all(ref.count("@sha256:") == 1 for ref, _ in probe.calls)
    # Nothing was obtainable for this probe, so nothing is claimed available.
    assert all(not e.available_artifact_digests for e in context.requirements)
