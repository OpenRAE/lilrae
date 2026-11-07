"""Static consistency tests for APTL configuration files.

These tests check the live project-tree configuration. No running Docker
environment is needed; the released-pack cases live with the adapter tests. The former profile
comparison relied on inactive stubs, and the docker-exec scan matched no real
references; both were removed for #954. Pack profile/dependency validation is
covered by test_env_pack_realization.py and test_raes_backend.py.
"""

from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def compose_config():
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    with open(compose_path) as f:
        return yaml.safe_load(f)


class TestComposeConsistency:
    """Validate docker-compose.yml internal consistency."""

    def test_all_services_have_container_name(self, compose_config):
        """Every service must have an explicit container_name."""
        services = compose_config.get("services", {})
        missing = []
        for name, svc in services.items():
            if "container_name" not in svc:
                missing.append(name)
        assert not missing, (
            f"Services missing container_name: {missing}. "
            "Auto-generated names break when repo is cloned to a different directory."
        )

    def test_container_names_are_unique(self, compose_config):
        """All container_name values must be unique."""
        services = compose_config.get("services", {})
        names = [
            svc["container_name"]
            for svc in services.values()
            if "container_name" in svc
        ]
        dupes = [n for n in names if names.count(n) > 1]
        assert not dupes, f"Duplicate container_name values: {set(dupes)}"

    def test_static_ipv4_addresses_are_unique_per_network(self, compose_config):
        """Static container IPs must not collide within the same Docker network."""
        services = compose_config.get("services", {})
        seen: dict[tuple[str, str], str] = {}
        dupes: list[tuple[str, str, str, str]] = []

        for service_name, svc in services.items():
            networks = svc.get("networks", {})
            if not isinstance(networks, dict):
                continue

            for network_name, network_cfg in networks.items():
                if not isinstance(network_cfg, dict):
                    continue

                ip = network_cfg.get("ipv4_address")
                if not ip:
                    continue

                key = (network_name, ip)
                if key in seen:
                    dupes.append((network_name, ip, seen[key], service_name))
                else:
                    seen[key] = service_name

        assert not dupes, "Duplicate static ipv4_address assignments:\n" + "\n".join(
            f"  {network}: {ip} used by {first} and {second}"
            for network, ip, first, second in dupes
        )

    def test_misp_suricata_rules_mount_named_volume(self, compose_config):
        """ADR-043: MISP rules ride a shared named volume, never a host bind.

        Nothing checked-in or under ``.aptl/`` may be bind-mounted onto a
        path the Suricata image entrypoint chowns (that rewrote host-side
        ownership, issue #325). ``suricata`` (still Compose-managed) and
        ``misp-suricata-sync`` (realized generically from the SDL, issue
        #581, via a declared persistent-volume consumer — never a Compose
        volume mount) share the ``suricata_misp_rules`` named volume instead. The env-var side
        of misp-suricata-sync's config (RULES_OUT_PATH, MISP_API_KEY, ...)
        is a separate, not-yet-built secrets-injection concern for
        base-container-materialized nodes (tracked alongside #809) and is not asserted here.
        """
        services = compose_config["services"]
        suricata_volumes = services["suricata"]["volumes"]

        misp_mount = "suricata_misp_rules:/var/lib/suricata/rules/misp:rw"
        assert misp_mount in suricata_volumes

        # No host bind (checked-in or .aptl) onto the chowned rules tree.
        assert not any(
            volume.startswith("./") and "/var/lib/suricata/rules/misp" in volume
            for volume in suricata_volumes
        )
        # The seed volumes are declared at top level (project-scoped, no
        # explicit global name).
        top_level = compose_config.get("volumes", {})
        assert "suricata_misp_rules" in top_level
        assert "suricata_config_seed" in top_level

    def test_suricata_config_seeded_not_bind_mounted(self, compose_config):
        """ADR-043: suricata.yaml / local.rules are seeded via a named volume
        and staged by the wrapper entrypoint, never bind-mounted from the
        checked-in tree onto the chowned /etc/suricata path."""
        suricata = compose_config["services"]["suricata"]
        volumes = suricata["volumes"]

        assert "suricata_config_seed:/seed:ro" in volumes
        assert not any(volume.startswith("./config/suricata/") for volume in volumes)
        # Wrapper entrypoint stages the seed into image-owned /etc/suricata
        # then delegates to the upstream entrypoint.
        entrypoint = "\n".join(suricata["entrypoint"])
        assert "/seed/suricata.yaml" in entrypoint
        assert "exec /docker-entrypoint.sh" in entrypoint

    def test_legacy_suricata_config_disables_container_checksum_validation(self):
        """The in-tree legacy scenario keeps its live-capture checksum policy."""

        config = yaml.safe_load(
            (PROJECT_ROOT / "config/suricata/suricata.yaml").read_text(
                encoding="utf-8"
            )
        )

        assert config["pcap"] == [{"interface": "any", "checksum-checks": False}]

        seed = (PROJECT_ROOT / "scripts/seed-prime.sh").read_text(encoding="utf-8")
        assert "envpack-suricata-fixups" not in seed

    def test_otel_collector_healthcheck_uses_image_binary(self):
        """The OTEL collector image is distroless, so the healthcheck cannot
        depend on shell utilities such as wget or curl."""
        apparatus = yaml.safe_load(
            (PROJECT_ROOT / "docker-compose.observability.yml").read_text()
        )
        collector = apparatus["services"]["aptl-otel-collector"]
        test = collector.get("healthcheck", {}).get("test")

        assert test == [
            "CMD",
            "/otelcol-contrib",
            "validate",
            "--config",
            "/etc/otelcol-contrib/config.yaml",
        ]

    def test_shuffle_opensearch_stays_writable_on_full_host(self, compose_config):
        """Shuffle's lab datastore must not use host percentage watermarks.

        A container can share a large, mostly-full host filesystem and still
        have ample absolute free space. OpenSearch's default flood-stage
        watermark then makes indices read-only while its healthcheck remains
        green, so the first-load Shuffle workflow silently fails to seed.
        """
        environment = compose_config["services"]["shuffle-opensearch"]["environment"]

        assert "cluster.routing.allocation.disk.threshold_enabled=false" in environment

    def test_web_api_token_does_not_block_inactive_profiles(self, compose_config):
        """Compose expands environment substitutions for inactive profiles, so
        the optional web token must be validated by the web runtime instead of
        by `${VAR:?}` interpolation in docker-compose.yml."""
        api_env = compose_config["services"]["aptl-web-api"]["environment"]
        token_lines = [line for line in api_env if line.startswith("APTL_API_TOKEN=")]

        assert token_lines == ["APTL_API_TOKEN=${APTL_API_TOKEN:-}"]
        assert not any(":?" in line for line in token_lines)

    def test_web_ui_does_not_carry_control_plane_token(self, compose_config):
        """UI-008a: the control-plane token is custodied only by the FastAPI BFF
        (aptl-web-api). The static-SPA + reverse-proxy UI container must not
        receive APTL_API_TOKEN — it holds no secret and enforces no auth."""
        ui = compose_config["services"]["aptl-web-ui"]
        env_lines = ui.get("environment", []) or []
        assert not any("APTL_API_TOKEN" in line for line in env_lines), (
            "aptl-web-ui must not carry the control-plane token (UI-008a)"
        )


class TestNetworkEgressControls:
    """Validate SAF-002: attack networks must block internet egress.

    Checked on the in-tree Compose model. The released-pack tests reuse these
    checks on the networks the planner renders for a released pack (#954).
    """

    ATTACK_NETWORKS = ["aptl-dmz", "aptl-internal", "aptl-redteam"]

    @pytest.fixture
    def networks(self, compose_config):
        return compose_config.get("networks", {})

    def test_attack_networks_are_internal(self, networks):
        """Networks carrying attack traffic must use internal: true."""
        not_internal = []
        for name in self.ATTACK_NETWORKS:
            net = networks.get(name, {})
            if not net.get("internal", False):
                not_internal.append(name)
        assert not not_internal, (
            f"SAF-002 violation: attack networks missing internal: true: "
            f"{not_internal}. Containers on these networks can reach the "
            f"internet, risking autonomous agent attacks on external targets."
        )

    def test_security_network_allows_egress(self, networks):
        """Security/management network must NOT be internal (SOC tools need internet)."""
        assert "aptl-security" in networks
        security = networks["aptl-security"]
        assert not security.get("internal", False), (
            "aptl-security must not be internal: true. "
            "SOC tools (MISP, Wazuh, Shuffle) require internet for "
            "threat feeds and rule updates."
        )


class TestBuildScriptCoverage:
    """Validate build-all-mcps.sh covers all MCP server directories."""

    def test_all_mcp_servers_in_build_script(self):
        """Every mcp-* directory should be built by build-all-mcps.sh."""
        mcp_dir = PROJECT_ROOT / "mcp"
        build_script = mcp_dir / "build-all-mcps.sh"

        server_dirs = {
            d.name
            for d in mcp_dir.iterdir()
            if d.is_dir() and d.name.startswith("mcp-")
        }

        script_text = build_script.read_text()

        missing = {s for s in server_dirs if s not in script_text}
        assert not missing, f"MCP servers not in build-all-mcps.sh: {missing}"
