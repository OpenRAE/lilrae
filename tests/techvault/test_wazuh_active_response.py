"""The live Wazuh active-response suite targets TechVault agents (#1700)."""

from __future__ import annotations

import json
import re
import shlex
import textwrap

import pytest

from tests.helpers import (
    LIVE_LAB,
    docker_exec,
)
from tests.test_wazuh_active_response import (
    KALI_IPS,
    MANAGER_OSSEC,
    WAZUH_MANAGER,
    WHITELIST_PATH,
    WRAPPER_PATH,
)


def test_continuity_audit_targets_declare_iptables(tmp_path):
    """Closed capability scopes leave no implicit continuity targets."""
    from raes.parser import parse_sdl_file

    from aptl.core.continuity import default_targets
    from tests.techvault.pack import techvault_scenario_path

    scenario = parse_sdl_file(techvault_scenario_path(tmp_path))

    assert set(default_targets()) == set(IN_PROCESS_TARGETS)
    assert all(
        scenario.nodes[node].runtime.linux_capabilities is None
        for node in ("webapp", "fileshare", "dns", "ad")
    )


def test_live_agent_roster_matches_the_declared_forwarding_agents(tmp_path):
    """The live suite must target the agents the scenario actually declares.

    It used to require the retired db/suricata sidecars, so a lab with the new
    topology skipped the whole live active-response suite instead of testing
    the realized agents (issue #1006).
    """
    from raes.parser import parse_sdl_file

    from tests.techvault.pack import techvault_scenario_path

    scenario = parse_sdl_file(techvault_scenario_path(tmp_path))
    declared = {
        f"aptl-{name}"
        for name, node in scenario.nodes.items()
        if node.runtime is not None
        and any(
            str(getattr(agent.implementation, "value", agent.implementation))
            == "wazuh_agent"
            for agent in node.runtime.forwarding_agents
        )
    }

    assert set(ALL_AGENTS) == declared


# Containers running an in-process Wazuh agent (per #248).
IN_PROCESS_TARGETS: tuple[str, ...] = (
    "aptl-webapp",
    "aptl-fileshare",
    "aptl-ad",
    "aptl-dns",
)


# The other realized nodes TechVault declares a Wazuh forwarding agent on. The
# old db/suricata sidecars are gone (issue #1006): each declared agent now runs
# on its own node, so the live suite targets those nodes, not retired sidecars.
IN_NODE_FORWARDING_AGENTS: tuple[str, ...] = (
    "aptl-db",
    "aptl-suricata",
    "aptl-victim",
    # raes-env-packs 6.1.0 gives the workstation its own enrolled endpoint
    # agent for /var/log/secure and /var/log/messages, so the AR contract has
    # to hold there too (issue #912).
    "aptl-workstation",
)


# Every Wazuh agent in the lab — used for "the AR contract is honored
# everywhere" assertions. The wrapper script and whitelist file ship
# on each.
ALL_AGENTS: tuple[str, ...] = IN_PROCESS_TARGETS + IN_NODE_FORWARDING_AGENTS


def _container_running(name: str) -> bool:
    """Return True if the named container is in `docker ps` output."""
    from tests.helpers import run_cmd

    result = run_cmd(["docker", "ps", "--format", "{{.Names}}"], timeout=10)
    if result.returncode != 0:
        return False
    return name in result.stdout.split()


def _require_lab_up() -> None:
    """Skip the test if the manager OR any agent (in-process or sidecar)
    is missing. These tests exercise live-lab integration; without all
    required containers present, a failure is environmental, not a real
    regression."""
    needed = (WAZUH_MANAGER, *ALL_AGENTS)
    missing = [c for c in needed if not _container_running(c)]
    if missing:
        pytest.skip(
            f"Lab not fully up; missing containers: {missing}. "
            f"Run `aptl lab start` first.",
        )


def _read_manager_ossec() -> str:
    """Read the deployed manager ossec.conf content. Skips if the lab
    or manager is not running."""
    _require_lab_up()
    result = docker_exec(WAZUH_MANAGER, f"cat {MANAGER_OSSEC}")
    if result.returncode != 0:
        pytest.skip(
            f"{WAZUH_MANAGER} not reachable or ossec.conf missing "
            f"(rc={result.returncode}, stderr={result.stderr[:200]})",
        )
    return result.stdout


def _all_active_response_blocks(content: str) -> list[str]:
    """Return every `<active-response>...</active-response>` block as
    raw XML. Anchor on a line-start `<active-response>` to avoid
    matching the literal text inside `<!-- ... <active-response> ... -->`
    comments (which our manager config has — the comments describe the
    framework above the actual AR blocks)."""
    return re.findall(
        r"^\s*<active-response>.*?</active-response>",
        content,
        re.DOTALL | re.MULTILINE,
    )


@pytest.fixture
def _check_lab_up() -> None:
    """Skip a test when the lab is not up. Applied via
    `@pytest.mark.usefixtures("_check_lab_up")` on live-lab classes
    only (not on TestWazuhActiveResponseSource, which runs without
    Docker)."""
    _require_lab_up()


@LIVE_LAB
@pytest.mark.usefixtures("_check_lab_up")
class TestWazuhActiveResponseConfig:
    """Manager-side AR config: command, AR blocks, and whitelist."""

    def test_aptl_firewall_drop_command_is_declared(self) -> None:
        """The wrapper command must be registered with the manager so
        `<active-response>` blocks can reference it. Required directives:
        `<name>` = `aptl-firewall-drop`, `<executable>` = same,
        `<expect>srcip</expect>` (manager skips dispatch when the alert
        doesn't carry srcip), `<timeout_allowed>yes`."""
        content = _read_manager_ossec()
        # Find the <command> block by name; check each required child.
        m = re.search(
            r"<command>(?P<body>.*?</command>)",
            content[content.find("<name>aptl-firewall-drop</name>") - 50 :]
            if "<name>aptl-firewall-drop</name>" in content
            else "",
            re.DOTALL,
        )
        assert "<name>aptl-firewall-drop</name>" in content, (
            "Manager ossec.conf has no <command> block named "
            "aptl-firewall-drop. Without this registration, every "
            "<active-response> block referencing aptl-firewall-drop "
            "is a no-op."
        )
        # Pull the surrounding <command>...</command> block by name match.
        m = re.search(
            r"<command>[^<]*<name>aptl-firewall-drop</name>.*?</command>",
            content,
            re.DOTALL,
        )
        assert m is not None, "could not locate aptl-firewall-drop <command> block"
        block = m.group(0)
        assert "<executable>aptl-firewall-drop</executable>" in block, (
            "aptl-firewall-drop <command> missing matching <executable>"
        )
        assert "<expect>srcip</expect>" in block, (
            "aptl-firewall-drop <command> missing <expect>srcip</expect>; "
            "without this, the manager dispatches AR for alerts that "
            "don't carry srcip and the script no-ops without surfacing "
            "the misfire to the manager."
        )
        assert "<timeout_allowed>yes</timeout_allowed>" in block, (
            "aptl-firewall-drop <command> missing <timeout_allowed>yes</timeout_allowed>"
        )

    def test_active_response_blocks_have_required_carve_outs(self) -> None:
        """Every `<active-response>` block in the manager config must
        ship commented out (default OFF), a finite
        `<timeout>` in [60, 300] (auto-rollback), and a specific
        `<rules_id>` (per-rule scoping).

        We deliberately do NOT require `<level>`. Wazuh AR's matchers
        (`<rules_id>`, `<rules_group>`, `<level>`) are OR'd, not AND'd
        — adding `<level>10</level>` to a block that already has
        `<rules_id>` BROADENS the block to fire on every level-10+
        alert. The severity gate is enforced implicitly by selecting
        level-10+ rules in `<rules_id>`."""
        content = _read_manager_ossec()
        blocks = _all_active_response_blocks(content)
        assert len(blocks) >= 3, (
            f"Expected >= 3 `<active-response>` blocks (the rule-5763 "
            f"original plus at least 2 representative new ones). Found "
            f"{len(blocks)}."
        )
        violations: list[str] = []
        for i, block in enumerate(blocks):
            timeout_match = re.search(r"<timeout>(\d+)</timeout>", block)
            if not timeout_match:
                violations.append(f"block #{i}: missing `<timeout>` directive")
            else:
                timeout = int(timeout_match.group(1))
                if not (60 <= timeout <= 300):
                    violations.append(
                        f"block #{i}: timeout={timeout}s outside [60, 300] "
                        f"(carve-out: timeout-bounded so drops auto-rollback)",
                    )
            if not re.search(r"<rules_id>\d+</rules_id>", block):
                violations.append(
                    f"block #{i}: missing `<rules_id>` (per-rule scoping is "
                    f"the only correct severity-gate pattern in Wazuh AR)",
                )
            # Reject `<level>` next to `<rules_id>` — Wazuh OR's them.
            if "<level>" in block and "<rules_id>" in block:
                violations.append(
                    f"block #{i}: `<level>` AND `<rules_id>` together — "
                    f"Wazuh OR's matchers, broadening the block to every "
                    f"level-N+ alert. Drop the `<level>`.",
                )
        # Default posture is OFF: blue uncomments a block per iteration. A
        # per-block <disabled>yes</disabled> stops the manager's wazuh-execd,
        # which reads the first <disabled> as a global switch.
        if "<active-response>" in re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL):
            violations.append("an <active-response> block is not commented out by default")
        assert not violations, (
            "Per-target carve-outs not enforced on every block:\n  "
            + "\n  ".join(violations)
        )

    def test_active_response_uses_wrapper_not_bare_firewall_drop(self) -> None:
        """No `<active-response>` block may reference bare `firewall-
        drop`. Every block must use the `aptl-firewall-drop` wrapper so
        the kali whitelist is consulted at exec time. (Other commands
        like `host-deny` are fine and may appear.)"""
        content = _read_manager_ossec()
        blocks = _all_active_response_blocks(content)
        leaks: list[str] = []
        for i, block in enumerate(blocks):
            cmd_match = re.search(r"<command>([^<]+)</command>", block)
            if not cmd_match:
                continue
            cmd = cmd_match.group(1).strip()
            if cmd == "firewall-drop":
                leaks.append(
                    f"block #{i} uses bare `firewall-drop` instead of "
                    f"`aptl-firewall-drop` — kali whitelist will be "
                    f"bypassed",
                )
        assert not leaks, "AR blocks must use the wrapper:\n  " + "\n  ".join(
            leaks,
        )


@LIVE_LAB
@pytest.mark.usefixtures("_check_lab_up")
class TestWazuhActiveResponseWhitelist:
    """The kali-IP whitelist file is installed on every in-process
    agent and populated with kali's three lab IPs. The wrapper script
    runs on the agent, so the file ships in each agent's image at
    build time."""

    def test_whitelist_file_present_on_every_agent(self) -> None:
        """Whitelist file must exist at the canonical path inside every
        Wazuh agent — both the in-process targets (4) AND the remaining
        sidecars (db, suricata). The wrapper consults it at exec time;
        ADR-021's contract is that the file ships on EVERY agent so
        any AR rule that fires honors the carve-out."""
        missing: list[str] = []
        for target in ALL_AGENTS:
            result = docker_exec(target, f"test -f {WHITELIST_PATH}")
            if result.returncode != 0:
                missing.append(target)
        assert not missing, (
            f"{WHITELIST_PATH} missing inside agents: {missing}. The "
            f"Dockerfile's COPY + install of the whitelist may have "
            f"been removed."
        )

    def test_whitelist_contains_kali_ips(self) -> None:
        """Each of kali's three lab IPs must appear in the whitelist
        on its own line (the wrapper uses `grep -Fxq` to match). Sample
        from one agent — file content is identical across all agents
        because they all COPY the same source file."""
        result = docker_exec("aptl-webapp", f"cat {WHITELIST_PATH}")
        assert result.returncode == 0, (
            f"could not read {WHITELIST_PATH} on aptl-webapp: {result.stderr[:200]}"
        )
        # Strip comments and blank lines for the membership check.
        lines = [
            ln.strip()
            for ln in result.stdout.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        missing = [ip for ip in KALI_IPS if ip not in lines]
        assert not missing, (
            f"Kali IPs missing from whitelist: {missing}. Without all "
            f"three present, the wrapper will allow `firewall-drop` to "
            f"fire on the missing kali interface, ending the purple loop."
        )


@LIVE_LAB
@pytest.mark.usefixtures("_check_lab_up")
class TestWazuhActiveResponseWrapper:
    """The wrapper script is installed on every Wazuh agent and behaves
    correctly for both whitelisted and non-whitelisted source IPs."""

    def test_wrapper_installed_on_every_agent(self) -> None:
        """Every Wazuh agent — in-process targets (4) AND sidecars (db,
        suricata) — must have the wrapper at the canonical path with
        execute bit set. The agent's wazuh-execd runs scripts from this
        directory by name; missing on a sidecar means AR fired against
        that agent would bypass the kali whitelist."""
        broken: list[str] = []
        for target in ALL_AGENTS:
            result = docker_exec(target, f"test -x {WRAPPER_PATH}")
            if result.returncode != 0:
                broken.append(
                    f"{target}: {WRAPPER_PATH} missing or not executable "
                    f"(rc={result.returncode})",
                )
        assert not broken, (
            "Wrapper script missing on one or more agents:\n  " + "\n  ".join(broken)
        )

    def test_wrapper_skips_whitelisted_srcip(self) -> None:
        """When invoked with a Wazuh AR `add` command and a srcip
        present in the whitelist, the wrapper exits 0 without running
        any iptables operation. Mock the iptables binary with
        `APTL_AR_IPTABLES=/bin/false` — if the wrapper invokes
        iptables for an `add`, the process exits non-zero. Whitelist
        short-circuit means it never reaches iptables."""
        ar_payload = json.dumps(
            {
                "version": 1,
                "command": "add",
                "parameters": {
                    "extra_args": [],
                    "alert": {"data": {"srcip": KALI_IPS[0]}},
                    "program": "firewall-drop",
                },
            },
        )
        cmd = (
            f"printf %s {shlex.quote(ar_payload)} | "
            f"APTL_AR_IPTABLES=/bin/false {WRAPPER_PATH}"
        )
        result = docker_exec("aptl-webapp", cmd)
        assert result.returncode == 0, (
            f"Wrapper did not short-circuit for whitelisted srcip "
            f"{KALI_IPS[0]}. rc={result.returncode}, stderr="
            f"{result.stderr[:200]}"
        )

    def test_wrapper_runs_iptables_for_non_whitelisted_srcip(self) -> None:
        """When invoked with a non-whitelisted srcip on `add`, the
        wrapper must call iptables `-I` (insert). A naive `/bin/true`
        mock makes `iptables -C` succeed (rule "already present") and
        the wrapper short-circuits with a no-op — never exercising the
        insert. Use a smarter mock that returns 1 for `-C` (rule not
        present) and 0 for `-I` (insert succeeded), then assert the
        wrapper logged 'added DROP' for the srcip — proving the
        insert branch ran."""
        ar_payload = json.dumps(
            {
                "version": 1,
                "command": "add",
                "parameters": {
                    "extra_args": [],
                    "alert": {"data": {"srcip": "10.99.99.99"}},
                    "program": "firewall-drop",
                },
            },
        )
        # Install a fake iptables in /tmp/aptl-fake-iptables that:
        #   -C → exit 1 (rule not present)
        #   -I → exit 0 (insert succeeds)
        #   -D → exit 0
        fake_iptables = "/tmp/aptl-fake-iptables.sh"
        fake_script = textwrap.dedent("""\
            #!/bin/bash
            for arg in "$@"; do
                case "$arg" in
                    -C) exit 1 ;;
                    -I) exit 0 ;;
                    -D) exit 0 ;;
                esac
            done
            exit 0
        """)
        # Write the fake iptables script in a single docker exec —
        # printf then chmod, both inside one bash -c so the file is
        # executable when the wrapper invokes it below.
        write = docker_exec(
            "aptl-webapp",
            f"bash -c {shlex.quote(f'printf %s {shlex.quote(fake_script)} > {fake_iptables} && chmod +x {fake_iptables}')}",
        )
        assert write.returncode == 0, (
            f"could not install fake iptables: rc={write.returncode}, "
            f"stderr={write.stderr[:200]}"
        )

        cmd = (
            f"printf %s {shlex.quote(ar_payload)} | "
            f"APTL_AR_IPTABLES={fake_iptables} {WRAPPER_PATH}"
        )
        result = docker_exec("aptl-webapp", cmd)
        assert result.returncode == 0, (
            f"Wrapper rc={result.returncode} with smart mock; expected "
            f"0 (insert succeeded). stderr={result.stderr[:200]}"
        )
        # Verify the insert branch actually ran via the audit log.
        log_check = docker_exec(
            "aptl-webapp",
            "grep -F 'added DROP for 10.99.99.99' /var/ossec/logs/active-responses.log",
        )
        assert log_check.returncode == 0, (
            "Wrapper did not log 'added DROP for 10.99.99.99' — the "
            "insert branch did not run. With the smart mock returning "
            "1 for -C and 0 for -I, the wrapper should have called -I "
            "and logged the addition."
        )

    def test_wrapper_runs_delete_even_for_whitelisted(self) -> None:
        """The `delete` phase (timeout cleanup) must always run iptables
        delete, even for whitelisted IPs — otherwise drops installed
        before an IP joined the whitelist would never be reaped. With
        `/bin/false` mock for iptables, the wrapper's delete path
        attempts `iptables -C` (returns 1, "not present") and exits 0
        — that's correct delete-cleanup behavior."""
        ar_payload = json.dumps(
            {
                "version": 1,
                "command": "delete",
                "parameters": {
                    "extra_args": [],
                    "alert": {"data": {"srcip": KALI_IPS[0]}},
                    "program": "firewall-drop",
                },
            },
        )
        # Mock with /bin/false — iptables -C returns 1, the wrapper
        # treats that as "no matching rule to delete" and exits 0.
        # The CRITICAL check: wrapper did NOT short-circuit on the
        # whitelist. We verify by checking the log for a 'removed N
        # DROP rule(s)' line — only present if the delete branch ran.
        cmd = (
            f"printf %s {shlex.quote(ar_payload)} | "
            f"APTL_AR_IPTABLES=/bin/false {WRAPPER_PATH}"
        )
        result = docker_exec("aptl-webapp", cmd)
        assert result.returncode == 0, (
            f"Wrapper rc={result.returncode} on delete with /bin/false "
            f"mock; expected 0 (no rule to delete is OK). "
            f"stderr={result.stderr[:200]}"
        )
        log_check = docker_exec(
            "aptl-webapp",
            f"grep -F 'removed' /var/ossec/logs/active-responses.log "
            f"| grep -F '{KALI_IPS[0]}'",
        )
        assert log_check.returncode == 0, (
            f"Wrapper short-circuited on `command=delete` for whitelisted "
            f"{KALI_IPS[0]}. The delete branch must always run."
        )

    def test_wrapper_logs_skip_to_active_responses_log(self) -> None:
        """When the wrapper short-circuits, it must log a `SKIPPED for
        whitelisted <ip>` line to /var/ossec/logs/active-responses.log
        so blue can audit which AR invocations were suppressed by the
        whitelist."""
        sentinel_ip = KALI_IPS[1]  # different IP from skip test for clarity
        ar_payload = json.dumps(
            {
                "version": 1,
                "command": "add",
                "parameters": {
                    "extra_args": [],
                    "alert": {"data": {"srcip": sentinel_ip}},
                    "program": "firewall-drop",
                },
            },
        )
        # Trigger the skip. iptables mock /bin/false ensures the wrapper
        # doesn't actually mutate iptables; if the wrapper failed to
        # short-circuit, /bin/false would propagate non-zero.
        cmd = (
            f"printf %s {shlex.quote(ar_payload)} | "
            f"APTL_AR_IPTABLES=/bin/false {WRAPPER_PATH}"
        )
        trigger = docker_exec("aptl-webapp", cmd)
        assert trigger.returncode == 0, (
            f"wrapper failed to short-circuit (rc={trigger.returncode})"
        )
        # Verify log entry.
        log_check = docker_exec(
            "aptl-webapp",
            f"grep -F 'SKIPPED for whitelisted {sentinel_ip}' "
            f"/var/ossec/logs/active-responses.log",
        )
        assert log_check.returncode == 0, (
            f"Wrapper did not log the skip for {sentinel_ip} to "
            f"/var/ossec/logs/active-responses.log. Without an audit "
            f"trail, blue can't tell which AR invocations the whitelist "
            f"suppressed."
        )
