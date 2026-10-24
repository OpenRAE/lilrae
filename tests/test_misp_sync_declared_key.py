"""The MISP sync agent presents the key the scenario declares (#1273).

TechVault declares the sync identity as a ``key`` account on the MISP node with
an authored ``secret_fixture`` value. The agent pulls from MISP's authored
canonical URL, so the backend maps that host to the single declared key, writes
it to a ``0600`` file the agent configuration names, and never puts it in the
configuration whose digest runtime observation re-derives.
"""

from __future__ import annotations

import hashlib
import subprocess
from types import SimpleNamespace

import pytest

from aptl.core.deployment import _forwarding_agent_realization as agents
from aptl.core.deployment.realization import (
    DeclaredAccountCredential,
    DeploymentAccountRealization,
)
from aptl.services.misp_suricata_sync.config import ServiceConfig

_KEY = "7ea54cbe19564f9893940770bbc659f890726557"


def _misp_node(address="provision.node.misp"):
    setting = SimpleNamespace(setting_id="misp-canonical-url", value="https://misp.example.test")
    runtime = SimpleNamespace(
        platform_applications=[SimpleNamespace(settings=[setting])]
    )
    return SimpleNamespace(address=address, runtime=runtime)


def _key_account(value=_KEY, *, address="provision.node.misp", name="sync"):
    return DeploymentAccountRealization(
        address=f"provision.account-placement.{name}",
        target_address=address,
        username=f"{name}-reader",
        auth_method="key",
        credential=DeclaredAccountCredential(credential_id=f"{name}-primary", value=value),
    )


def _agent():
    source = SimpleNamespace(location="https://misp.example.test", selector="tag")
    return SimpleNamespace(
        implementation="misp_suricata_sync",
        sources=[source],
        transforms=[],
        settings=[],
    )


def test_the_declared_key_is_mapped_to_its_service_host():
    keys = agents.agent_api_keys([_misp_node()], [_key_account()])

    assert keys == {"misp.example.test": _KEY}


def test_an_ambiguous_or_undeclared_key_maps_to_nothing():
    two = [_key_account(name="one"), _key_account("b" * 40, name="two")]

    assert agents.agent_api_keys([_misp_node()], two) == {}
    assert agents.agent_api_keys([_misp_node()], []) == {}


class _Container:
    def __init__(self):
        self.files: dict[str, tuple[str, str]] = {}
        self.argv: list[list[str]] = []

    def container_exec(self, _name, cmd, *, timeout=None):
        self.argv.append(list(cmd))
        if cmd[0] == "sha256sum":
            text = self.files.get(cmd[1], ("", ""))[0]
            digest = hashlib.sha256(text.encode()).hexdigest()
            return subprocess.CompletedProcess(cmd, 0, f"{digest}  {cmd[1]}\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def container_exec_with_input(self, _name, cmd, payload, *, timeout=None):
        self.argv.append(list(cmd))
        if cmd[0] == "cmp":
            assert cmd == ["cmp", "-s", "--", agents._MISP_SYNC_KEY, "-"]
            matches = self.files.get(cmd[3], (None, ""))[0] == payload
            return subprocess.CompletedProcess(cmd, 0 if matches else 1, "", "")
        script = cmd[-1]
        assert script.startswith("umask 077 && cat > ")
        self.files[script.rsplit("> ", 1)[1]] = (payload, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_the_key_file_is_written_apart_from_the_observed_configuration():
    container = _Container()

    reason = agents._write_declared_key(
        container, "aptl-sync", _agent(), {"misp.example.test": _KEY}
    )

    assert reason is None
    assert container.files[agents._MISP_SYNC_KEY][0] == f"{_KEY}\n"
    assert all(_KEY not in token for argv in container.argv for token in argv)
    assert ["cmp", "-s", "--", agents._MISP_SYNC_KEY, "-"] in container.argv
    assert not any(argv[0] == "sha256sum" for argv in container.argv)
    config = agents._misp_sync_config(_agent())
    assert _KEY not in config
    assert f"MISP_API_KEY_FILE={agents._MISP_SYNC_KEY}\n" in config


def test_key_verification_refuses_changed_content_without_emitting_a_digest():
    class ChangedKey(_Container):
        def container_exec_with_input(self, name, cmd, payload, *, timeout=None):
            if cmd[0] == "cmp":
                self.files[agents._MISP_SYNC_KEY] = ("different\n", "")
            return super().container_exec_with_input(name, cmd, payload, timeout=timeout)

    container = ChangedKey()
    assert agents._write_declared_key(
        container, "aptl-sync", _agent(), {"misp.example.test": _KEY}
    ) == "MISP sync key did not verify"
    assert not any(argv[0] == "sha256sum" for argv in container.argv)


def test_no_key_file_is_written_when_the_scenario_declares_none():
    container = _Container()

    assert agents._write_declared_key(container, "aptl-sync", _agent(), {}) is None
    assert container.files == {}


def test_the_sync_service_reads_its_key_from_the_named_file(tmp_path, monkeypatch):
    key_file = tmp_path / "sync.key"
    key_file.write_text(f"{_KEY}\n", encoding="utf-8")
    monkeypatch.delenv("MISP_API_KEY", raising=False)
    monkeypatch.setenv("MISP_API_KEY_FILE", str(key_file))

    assert ServiceConfig.from_env().misp_api_key == _KEY


def test_the_sync_service_refuses_to_start_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("MISP_API_KEY", raising=False)
    monkeypatch.setenv("MISP_API_KEY_FILE", str(tmp_path / "absent"))

    with pytest.raises(ValueError, match="MISP_API_KEY"):
        ServiceConfig.from_env()
