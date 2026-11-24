"""Verify Wazuh active-response wiring + carve-outs (issue #249).

Pre-#249 the manager declared seven `<command>` blocks but only one
`<active-response>` block (rule 5763 SSH brute-force → bare `firewall-
drop`, 600s, enabled). Every other detection rule fired and nothing
happened. The framework was present but inert.

After #249, the manager:
  - Adds an `<aptl-firewall-drop>` `<command>` that wraps the upstream
    `firewall-drop` and consults a kali-IP whitelist.
  - Adds `<active-response>` blocks for representative high-severity
    rules (webapp / AD / database).
  - Ships every `<active-response>` block commented out, with
    `<timeout>` between 60 and 300, and `<level>` >= 10. Blue
    uncomments a block per iteration.
  - Bind-mounts a flat-file whitelist at /var/ossec/etc/lists/active-
    response-whitelist with kali's three lab IPs preloaded.
  - Installs the wrapper script at /var/ossec/active-response/bin/aptl-
    firewall-drop on every Wazuh agent in the lab.

These are integration tests gated by `APTL_SMOKE=1`. CI without the lab
skips the file cleanly.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.helpers import (
    dockerfile_copies,
)

# The three kali-side IPs (kali multi-homed across redteam, dmz, internal).
# All three must be in the whitelist file so AR refuses to drop kali on
# any interface it might present.
KALI_IPS: tuple[str, ...] = ("172.20.4.30", "172.20.1.30", "172.20.2.35")


WAZUH_MANAGER = "aptl-wazuh-manager"
WHITELIST_PATH = "/var/ossec/etc/lists/active-response-whitelist"
WRAPPER_PATH = "/var/ossec/active-response/bin/aptl-firewall-drop"
MANAGER_OSSEC = "/var/ossec/etc/ossec.conf"

# Repo paths for source-level tests that don't require the lab to be
# up. These let CI catch regressions in the source files without
# spinning up Docker.
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_MANAGER_CONF = REPO_ROOT / "config" / "wazuh_cluster" / "wazuh_manager.conf"
SRC_WHITELIST = (
    REPO_ROOT
    / "config"
    / "wazuh_cluster"
    / "etc"
    / "lists"
    / "active-response-whitelist"
)
SRC_WRAPPER = REPO_ROOT / "containers" / "_wazuh-agent" / "aptl-firewall-drop.sh"
SRC_INSTALL = REPO_ROOT / "containers" / "_wazuh-agent" / "install.sh"
SRC_INSTALL_RHEL = REPO_ROOT / "containers" / "_wazuh-agent" / "install-rhel.sh"
SRC_AR_STEP = REPO_ROOT / "containers" / "_wazuh-agent" / "install-active-response.sh"


def _ar_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create scratch AR inputs and an output root for the shared step."""
    wrapper = tmp_path / "aptl-firewall-drop.sh"
    wrapper.write_text("#!/bin/sh\n")
    whitelist = tmp_path / "active-response-whitelist"
    whitelist.write_text("172.20.4.30\n")
    return wrapper, whitelist, tmp_path / "ossec"


def _run_ar_step(
    tmp_path: Path, wrapper: Path, whitelist: Path, root: Path, calls: Path
) -> subprocess.CompletedProcess:
    """Run the real AR step with `install` shimmed so no root is needed.

    The shim records its exact arguments; ownership is part of the contract
    being asserted, and changing it would require privileges a test lacks.
    """
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "install"
    shim.write_text(f'#!/bin/sh\necho "$*" >> {calls}\n')
    shim.chmod(0o755)
    return subprocess.run(
        ["sh", str(SRC_AR_STEP)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{shim_dir}:/usr/bin:/bin",
            "APTL_AR_WRAPPER_SRC": str(wrapper),
            "APTL_AR_WHITELIST_SRC": str(whitelist),
            "APTL_AR_OSSEC_ROOT": str(root),
        },
        check=False,
    )


# Dockerfiles that must each install the wrapper + whitelist via the
# install.sh /tmp pre-COPY pattern. webapp/fileshare/dns moved to SDL
# `runtime:` realization (issue #581) and no longer have a Dockerfile —
# they have no in-process Wazuh agent (and so no AR wrapper) at all until
# aces#847 (no typed way to declare a third-party apt repository, which
# install.sh's wazuh-agent package needs) is resolved; tracked as #809.
# Every image that installs the Wazuh agent. The sidecar and the `ad` image
# that used to carry the agent are gone (issue #1006): a scenario declares a
# forwarding agent on the node, and APTL realizes it on these generic agent
# substrates instead. The active-response contract moved with the agent.
AGENT_DOCKERFILES: tuple[Path, ...] = (
    REPO_ROOT / "containers" / "generic-wazuh-agent-base-debian" / "Dockerfile",
    REPO_ROOT / "containers" / "generic-systemd-wazuh-agent-base" / "Dockerfile",
    REPO_ROOT / "containers" / "generic-systemd-wazuh-agent-base-debian" / "Dockerfile",
    REPO_ROOT / "containers" / "generic-samba-ad-wazuh-agent-base" / "Dockerfile",
    REPO_ROOT / "containers" / "suricata-wazuh-agent" / "Dockerfile",
)


# =============================================================================
# Source-level tests — no lab required.
#
# These run in CI without Docker; they parse the repo's source files to
# catch regressions that the live-lab integration tests would miss when
# the lab is down. The wrapper unit-tests use a temp whitelist and a
# /bin/true mock upstream so we exercise the script logic locally.
# =============================================================================


class TestWazuhActiveResponseSource:
    """Source-file integrity. No Docker, no lab — these are pytest's
    floor of safety: if these fail, the next live-lab run won't even
    have a chance of being correct."""

    def test_manager_conf_declares_wrapper_command(self) -> None:
        """The repo's manager config must declare the `aptl-firewall-
        drop` `<command>` block, including `<expect>srcip</expect>` so
        the manager skips dispatch when an alert carries no srcip."""
        content = SRC_MANAGER_CONF.read_text()
        assert "<name>aptl-firewall-drop</name>" in content, (
            "Manager config missing aptl-firewall-drop <command> block."
        )
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
            "aptl-firewall-drop <command> missing <expect>srcip</expect>"
        )

    def test_manager_conf_active_response_blocks_disabled_by_default(self) -> None:
        """Source-level mirror of test_active_response_blocks_have_required_
        carve_outs — runs without the lab. Anchored regex avoids
        matching the `<active-response>` text inside XML comments."""
        content = SRC_MANAGER_CONF.read_text()
        blocks = re.findall(
            r"^\s*<active-response>.*?</active-response>",
            content,
            re.DOTALL | re.MULTILINE,
        )
        assert len(blocks) >= 3, (
            f"Source manager config has {len(blocks)} <active-response> "
            f"blocks; expected >= 3"
        )
        violations: list[str] = []
        for i, block in enumerate(blocks):
            if "<timeout>" not in block:
                violations.append(f"block #{i}: missing <timeout>")
            if not re.search(r"<rules_id>\d+</rules_id>", block):
                violations.append(f"block #{i}: missing <rules_id>")
            # Wazuh OR's matchers — `<level>` next to `<rules_id>` broadens
            # the block. Reject the combination.
            if "<level>" in block and "<rules_id>" in block:
                violations.append(
                    f"block #{i}: `<level>` AND `<rules_id>` together — "
                    f"Wazuh OR's matchers; drop the `<level>`",
                )
        # A per-block <disabled>yes</disabled> stops the manager's
        # wazuh-execd, which reads the first <disabled> as a global switch.
        if "<active-response>" in re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL):
            violations.append("an <active-response> block is not commented out by default")
        assert not violations, "Carve-outs not enforced in source:\n  " + "\n  ".join(
            violations,
        )

    def test_manager_conf_uses_wrapper_for_firewall_drop_blocks(self) -> None:
        """No <active-response> block in source may reference bare
        `firewall-drop` — every block that wants firewall-drop semantics
        must use the `aptl-firewall-drop` wrapper."""
        content = SRC_MANAGER_CONF.read_text()
        blocks = re.findall(
            r"^\s*<active-response>.*?</active-response>",
            content,
            re.DOTALL | re.MULTILINE,
        )
        leaks: list[str] = []
        for i, block in enumerate(blocks):
            cmd = re.search(r"<command>([^<]+)</command>", block)
            if cmd and cmd.group(1).strip() == "firewall-drop":
                leaks.append(
                    f"block #{i}: bare firewall-drop (use aptl-firewall-drop)",
                )
        assert not leaks, "\n  ".join(leaks)

    def test_whitelist_file_format(self) -> None:
        """The repo's whitelist file must contain kali's three IPs as
        bare IPv4 addresses, one per line — `grep -Fxq` semantics
        require whole-line matching with no inline content."""
        content = SRC_WHITELIST.read_text()
        ip_lines = [
            ln.strip()
            for ln in content.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        # Each non-comment line must be a bare IPv4. Inline comments
        # like "172.20.4.30  # kali" would be a silent regression.
        bare_ipv4 = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
        bad = [ln for ln in ip_lines if not bare_ipv4.match(ln)]
        assert not bad, (
            f"Whitelist source file contains non-bare-IPv4 lines: {bad}. "
            f"`grep -Fxq` matches the entire line, so `172.20.4.30  # kali` "
            f"on one line silently fails to match."
        )
        missing = [ip for ip in KALI_IPS if ip not in ip_lines]
        assert not missing, f"Kali IPs missing from source whitelist: {missing}"

    def test_wrapper_script_is_compatible_with_macos_system_bash(self) -> None:
        """The wrapper must avoid Bash 4+ parameter transformations.

        macOS ships /bin/bash 3.2 by default, and the hosted macOS
        smoke job runs this source-level suite before any lab
        containers are involved.
        """
        content = SRC_WRAPPER.read_text()
        assert "@Q}" not in content, (
            "Wrapper uses Bash 4+ ${var@Q} quoting; use printf %q so "
            "source-level tests run under macOS /bin/bash 3.2."
        )

    def _run_wrapper(
        self, tmp_path: Path, payload: str, iptables: str = "/bin/true"
    ) -> tuple[subprocess.CompletedProcess, Path]:
        """Helper: run the source wrapper with a temp whitelist + log
        and a mock iptables. Returns (result, log_path)."""
        wl = tmp_path / "whitelist"
        wl.write_text("172.20.4.30\n")
        log = tmp_path / "log"
        env = {
            **os.environ,
            "APTL_AR_WHITELIST": str(wl),
            "APTL_AR_IPTABLES": iptables,
            "APTL_AR_LOG": str(log),
        }
        result = subprocess.run(
            ["bash", str(SRC_WRAPPER)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return result, log

    def test_wrapper_script_rejects_invalid_ipv4(self, tmp_path: Path) -> None:
        """The wrapper's IPv4 validation must reject a srcip with an
        embedded newline + whitelisted IP. Without validation,
        `grep -Fxq` would match the embedded whitelisted line and
        short-circuit. With validation, the wrapper logs the rejection
        and exits 0 without invoking iptables — so /bin/false mock for
        iptables doesn't matter; we just verify no SKIPPED log line
        and a 'rejecting invalid srcip' line is present."""
        payload = json.dumps(
            {
                "command": "add",
                "parameters": {
                    "alert": {"data": {"srcip": "evil\n172.20.4.30"}},
                },
            },
        )
        result, log = self._run_wrapper(tmp_path, payload, iptables="/bin/false")
        # Wrapper returns 0 on rejection (no work to do, no error).
        log_content = log.read_text() if log.exists() else ""
        assert "SKIPPED for whitelisted" not in log_content, (
            "Wrapper short-circuited on a malformed srcip with an "
            "embedded newline — IPv4 validation regression."
        )
        assert "rejecting invalid srcip" in log_content, (
            f"Wrapper did not log a srcip rejection; log content: {log_content!r}"
        )

    def test_wrapper_script_short_circuits_valid_whitelisted(
        self, tmp_path: Path
    ) -> None:
        """Source-level happy-path: a whitelisted IPv4 must short-
        circuit. With APTL_AR_IPTABLES=/bin/false, any iptables call
        propagates a non-zero exit; rc=0 means the wrapper never
        invoked iptables."""
        payload = json.dumps(
            {
                "command": "add",
                "parameters": {"alert": {"data": {"srcip": "172.20.4.30"}}},
            },
        )
        result, log = self._run_wrapper(tmp_path, payload, iptables="/bin/false")
        assert result.returncode == 0, (
            f"Wrapper failed to short-circuit on whitelisted 172.20.4.30; "
            f"rc={result.returncode}, stderr={result.stderr[:200]}"
        )
        assert log.exists()
        assert "SKIPPED for whitelisted 172.20.4.30" in log.read_text(), (
            f"Log file missing or no SKIPPED entry; contents: "
            f"{log.read_text() if log.exists() else '<no file>'}"
        )

    def test_wrapper_script_runs_delete_unconditionally(self, tmp_path: Path) -> None:
        """delete + whitelisted IP must still proceed to the iptables
        delete branch (cleanup is unconditional). With /bin/false
        iptables mock, `iptables -C` returns 1 ('rule not present')
        and the wrapper exits 0 — but the log shows 'removed 0 DROP
        rule(s)', proving the delete branch ran."""
        payload = json.dumps(
            {
                "command": "delete",
                "parameters": {"alert": {"data": {"srcip": "172.20.4.30"}}},
            },
        )
        result, log = self._run_wrapper(tmp_path, payload, iptables="/bin/false")
        assert result.returncode == 0, (
            f"Wrapper rc={result.returncode} on delete; expected 0 "
            f"(no rule to delete is OK). stderr={result.stderr[:200]}"
        )
        log_content = log.read_text() if log.exists() else ""
        assert "removed 0 DROP rule(s) for 172.20.4.30" in log_content, (
            f"Wrapper short-circuited on delete + whitelisted srcip "
            f"(no 'removed' log line). cleanup must always run. "
            f"Log: {log_content!r}"
        )

    def test_every_installer_runs_the_shared_active_response_step(self) -> None:
        """Debian and RHEL installers must both place the AR assets.

        The placement used to live only inside install.sh, as an optional
        "if the file exists" step. install-rhel.sh never had it, so RHEL-based
        agents shipped without the wrapper while every source-level check still
        passed (issue #1006). Both installers now run one shared step
        unconditionally.
        """
        for installer in (SRC_INSTALL, SRC_INSTALL_RHEL):
            lines = [
                line.strip()
                for line in installer.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            assert "sh /tmp/install-active-response.sh" in lines, (
                f"{installer.name} does not run the shared active-response step"
            )

    def test_active_response_step_places_both_assets(self, tmp_path) -> None:
        """Run the real script against a scratch root, not a grep of its text."""
        wrapper, whitelist, root = _ar_sources(tmp_path)
        calls = tmp_path / "install-calls"

        result = _run_ar_step(tmp_path, wrapper, whitelist, root, calls)

        assert result.returncode == 0, result.stderr
        recorded = calls.read_text().splitlines()
        assert (
            f"-D -m 0755 -o root -g wazuh {wrapper} "
            f"{root}/active-response/bin/aptl-firewall-drop"
        ) in recorded
        assert (
            f"-D -m 0640 -o root -g wazuh {whitelist} "
            f"{root}/etc/lists/active-response-whitelist"
        ) in recorded

    @pytest.mark.parametrize("missing", ["wrapper", "whitelist"])
    def test_active_response_step_fails_on_a_missing_asset(
        self, tmp_path, missing
    ) -> None:
        """A missing asset fails the build instead of shipping a mute agent."""
        wrapper, whitelist, root = _ar_sources(tmp_path)
        (wrapper if missing == "wrapper" else whitelist).unlink()
        calls = tmp_path / "install-calls"

        result = _run_ar_step(tmp_path, wrapper, whitelist, root, calls)

        assert result.returncode != 0
        assert "active-response asset missing" in result.stderr
        assert not calls.exists()

    def test_every_agent_dockerfile_pre_copies_ar_extras(self) -> None:
        """Every agent image must COPY each AR input to where its installer reads it.

        Checked on parsed COPY instructions, not independent substrings: a
        source and destination in different instructions, or a comment naming
        one of them, used to satisfy the check while the real COPY was wrong.
        """
        required = (
            (
                "containers/_wazuh-agent/aptl-firewall-drop.sh",
                "/tmp/aptl-firewall-drop.sh",
            ),
            (
                "config/wazuh_cluster/etc/lists/active-response-whitelist",
                "/tmp/active-response-whitelist",
            ),
            (
                "containers/_wazuh-agent/install-active-response.sh",
                "/tmp/install-active-response.sh",
            ),
        )
        violations = [
            f"{dockerfile.relative_to(REPO_ROOT)}: missing COPY {source} {destination}"
            for dockerfile in AGENT_DOCKERFILES
            for source, destination in required
            if (source, destination) not in dockerfile_copies(dockerfile)
        ]
        assert not violations, (
            "Dockerfile AR-extras contract violated:\n  " + "\n  ".join(violations)
        )


class _RuntimeAgentBackend:
    """Container surface for an agent installed at realization time."""

    def __init__(self, project_dir: Path, *, present: dict[str, str] | None = None):
        self._project_dir = project_dir
        self.files: dict[str, str] = dict(present or {})
        self.commands: list[list[str]] = []

    def container_exec(self, name, cmd, *, timeout=None):
        import hashlib

        self.commands.append(list(cmd))
        if cmd[0] == "sha256sum":
            body = self.files.get(cmd[1])
            if body is None:
                return subprocess.CompletedProcess(cmd, 1, "", "")
            digest = hashlib.sha256(body.encode()).hexdigest()
            return subprocess.CompletedProcess(cmd, 0, f"{digest}  {cmd[1]}\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def container_exec_with_input(self, name, cmd, payload, *, timeout=None):
        path = cmd[-1].split("> ", 1)[1]
        self.files[path] = payload
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_runtime_installed_agent_gets_the_active_response_assets():
    """An agent installed at realization time carries the same AR contract."""
    from aptl.core.deployment._wazuh_agent_realization import (
        ensure_active_response_assets,
    )

    backend = _RuntimeAgentBackend(REPO_ROOT)

    assert ensure_active_response_assets(backend, "aptl-node") is None

    assert backend.files[WRAPPER_PATH] == SRC_WRAPPER.read_text()
    assert backend.files[WHITELIST_PATH] == SRC_WHITELIST.read_text()
    assert ["chmod", "0755", WRAPPER_PATH] in backend.commands
    assert ["chmod", "0640", WHITELIST_PATH] in backend.commands
    assert ["chown", "root:wazuh", WRAPPER_PATH] in backend.commands


def test_image_staged_assets_are_verified_not_rewritten():
    """An agent image already carrying the exact assets is left untouched."""
    from aptl.core.deployment._wazuh_agent_realization import (
        ensure_active_response_assets,
    )

    backend = _RuntimeAgentBackend(
        REPO_ROOT,
        present={
            WRAPPER_PATH: SRC_WRAPPER.read_text(),
            WHITELIST_PATH: SRC_WHITELIST.read_text(),
        },
    )

    assert ensure_active_response_assets(backend, "aptl-node") is None

    assert not [c for c in backend.commands if c[0] in {"chmod", "chown"}]
