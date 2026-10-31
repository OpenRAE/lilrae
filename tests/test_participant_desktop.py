"""The participant desktop comes from the pack SDL, not from LilRAE (#1273).

The provider returns references; core resolves consoles, hostnames, logins and
the guide against the admitted SDL and the realized lab, then publishes a
non-secret hostname list and the participant's private desktop files.
"""

from __future__ import annotations

import json
import os
import pwd
import stat
from types import SimpleNamespace

import pytest

from aptl.backends import participant_desktop as seam
from aptl.backends.participant_desktop import (
    DesktopConsole,
    DesktopCredential,
    ParticipantDesktopSpec,
)
from aptl.core import _participant_desktop_files as files
from aptl.core import participant_desktop as desktop
from aptl.core import participant_hosts
from aptl.core.deployment.realization import DeploymentServicePort

_SECRET = "Console-Fixture-2026!"


def _setting(url):
    return SimpleNamespace(setting_id="console-canonical-url", value=url)


def _node(
    name, *, service, port, protocol="https", canonical=None, address="172.20.0.9"
):
    applications = [SimpleNamespace(service=service, protocol=protocol)]
    platform = (
        [SimpleNamespace(service=service, settings=[_setting(canonical)])]
        if canonical
        else []
    )
    return SimpleNamespace(
        name=name,
        container_name=f"aptl-{name}",
        services=(DeploymentServicePort(service, port),),
        runtime=SimpleNamespace(
            applications=applications, platform_applications=platform
        ),
        address=address,
    )


def _inspect_for(nodes, published):
    def inspect(container):
        node = next(item for item in nodes if item.container_name == container)
        port = node.services[0].port
        ports = {
            f"{port}/tcp": [
                {"HostIp": "127.0.0.1", "HostPort": str(published.get(node.name, 0))},
                {"HostIp": "::1", "HostPort": str(published.get(node.name, 0))},
            ]
        }
        return {
            "State": {"Running": True},
            "NetworkSettings": {
                "Ports": ports,
                "Networks": {"lab_security": {"IPAddress": node.address}},
            },
        }

    return inspect


def _account(username, value=_SECRET, classification="secret_fixture"):
    material = SimpleNamespace(classification=classification, value=value)
    binding = SimpleNamespace(
        credential_id="primary", material=material, auth_method="password"
    )
    return SimpleNamespace(username=username, credential_bindings=[binding])


def _spec(**overrides):
    values = {
        "consoles": (
            DesktopConsole("Dashboard", "dashboard", "dashboard"),
            DesktopConsole("Intel", "intel", "https"),
            DesktopConsole("Cases", "cases", "api"),
        ),
        "credentials": (DesktopCredential("Intel", "intel-admin", "primary"),),
        "guide": "docs/guide.md",
        "hostnames": ("intel",),
    }
    values.update(overrides)
    return ParticipantDesktopSpec(**values)


def _lab(*, canonical="https://intel.example.test", served=frozenset({"dash.lab"})):
    nodes = [
        _node("dashboard", service="dashboard", port=5601),
        _node("intel", service="https", port=443, canonical=canonical),
        _node("cases", service="api", port=9001, protocol="http"),
    ]
    inspect = _inspect_for(nodes, {"dashboard": 8443, "cases": 9001})
    return nodes, inspect, (lambda _port: served)


def _resolve(spec=None, accounts=None, lab=None):
    nodes, inspect, served = lab or _lab()
    return desktop.resolve_participant_desktop(
        spec or _spec(),
        read_asset=lambda path: f"guide at {path}".encode(),
        accounts=accounts
        if accounts is not None
        else {"intel-admin": _account("admin@example.test")},
        nodes=nodes,
        inspect=inspect,
        served_names=lambda _node, port: served(port),
    )


def test_every_field_is_resolved_from_the_sdl_and_the_realized_lab():
    resolved = _resolve()

    assert resolved.consoles == (
        ("Dashboard", "https://dash.lab:8443/"),
        ("Intel", "https://intel.example.test/"),
        ("Cases", "http://localhost:9001/"),
    )
    assert resolved.hosts == (
        ("127.0.0.1", "dash.lab"),
        ("172.20.0.9", "intel.example.test"),
    )
    assert [(item.label, item.username, item.secret) for item in resolved.logins] == [
        ("Intel", "admin@example.test", _SECRET)
    ]
    assert resolved.guide == b"guide at docs/guide.md"
    assert _SECRET not in repr(resolved)


def test_a_certificate_that_covers_localhost_needs_no_hostname():
    resolved = _resolve(lab=_lab(served=frozenset({"localhost", "dash.lab"})))

    assert resolved.consoles[0] == ("Dashboard", "https://localhost:8443/")
    assert ("127.0.0.1", "dash.lab") not in resolved.hosts


def test_a_changed_sdl_hostname_and_credential_change_the_output():
    first = _resolve()
    second = _resolve(
        accounts={"intel-admin": _account("analyst@example.test", "Rotated-2027!")},
        lab=_lab(canonical="https://threat.example.test"),
    )

    assert ("172.20.0.9", "threat.example.test") in second.hosts
    assert second.consoles[1] == ("Intel", "https://threat.example.test/")
    assert (second.logins[0].username, second.logins[0].secret) == (
        "analyst@example.test",
        "Rotated-2027!",
    )
    assert first != second


@pytest.mark.parametrize(
    ("accounts", "code"),
    [
        ({}, "login-account-unknown"),
        (
            {"intel-admin": _account("a", classification="operator_secret")},
            "login-credential-not-secret-fixture",
        ),
    ],
)
def test_a_login_that_is_not_an_authored_fixture_is_refused(accounts, code):
    with pytest.raises(desktop.ParticipantDesktopError) as caught:
        _resolve(accounts=accounts)

    assert caught.value.code == code


def test_an_unpublished_console_port_is_refused():
    nodes, _inspect, served = _lab()
    inspect = _inspect_for(nodes, {})

    with pytest.raises(desktop.ParticipantDesktopError) as caught:
        _resolve(lab=(nodes, inspect, served))

    assert caught.value.code == "console-port-unpublished"


def test_an_ambiguous_node_address_is_refused():
    nodes, inspect, served = _lab()

    def two_networks(container):
        info = inspect(container)
        info["NetworkSettings"]["Networks"]["lab_other"] = {"IPAddress": "10.9.0.2"}
        return info

    with pytest.raises(desktop.ParticipantDesktopError) as caught:
        _resolve(lab=(nodes, two_networks, served))

    assert caught.value.code == "node-address-ambiguous"


def test_a_served_name_that_could_inject_a_hosts_line_is_refused():
    lab = _lab(served=frozenset({"evil.lab\n10.0.0.1 bank.test"}))
    with pytest.raises(desktop.ParticipantDesktopError) as caught:
        _resolve(lab=lab)

    assert caught.value.code == "hostname-invalid"


def test_publication_keeps_only_hostnames_in_lab_state(tmp_path):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    resolved = _resolve()
    entry = pwd.getpwuid(os.geteuid())
    account = SimpleNamespace(
        **{name: getattr(entry, name) for name in dir(entry) if name.startswith("pw_")}
    )
    account.pw_dir = str(home)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(desktop.pwd, "getpwnam", lambda _name: account)
        desktop.publish_participant_desktop(tmp_path, resolved, entry.pw_name)

    hosts = (tmp_path / desktop.HOSTS_RELPATH).read_text(encoding="utf-8")
    assert _SECRET not in hosts
    assert participant_hosts.validated_entries(json.loads(hosts)) == list(
        resolved.hosts
    )
    directory = home / files.DESKTOP_DIR
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for name in (files.CREDENTIALS_FILE, files.CONSOLES_FILE, files.GUIDE_FILE):
        path = directory / name
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.stat().st_uid == os.geteuid()
    assert _SECRET in (directory / files.CREDENTIALS_FILE).read_text(encoding="utf-8")
    assert (directory / files.CONSOLES_FILE).read_text().splitlines()[0] == (
        "https://dash.lab:8443/"
    )


def test_a_non_root_start_cannot_publish_for_another_account(tmp_path, monkeypatch):
    other = SimpleNamespace(pw_uid=os.geteuid() + 1, pw_gid=0, pw_dir=str(tmp_path))
    monkeypatch.setattr(desktop.pwd, "getpwnam", lambda _name: other)
    monkeypatch.setattr(desktop, "_effective_uid", lambda: os.geteuid())
    resolved = _resolve()

    with pytest.raises(desktop.ParticipantDesktopError) as caught:
        desktop.publish_participant_desktop(tmp_path, resolved, "participant")

    assert caught.value.code == "desktop-account-not-writable"


def test_a_root_start_writes_as_the_participant_with_files_on_stdin(
    tmp_path, monkeypatch
):
    other = SimpleNamespace(pw_uid=4242, pw_gid=4242, pw_dir=str(tmp_path / "p"))
    monkeypatch.setattr(desktop.pwd, "getpwnam", lambda _name: other)
    monkeypatch.setattr(desktop, "_effective_uid", lambda: 0)
    calls = []

    desktop.publish_participant_desktop(
        tmp_path,
        _resolve(),
        "participant",
        run_as_account=lambda entry, request: calls.append((entry, request)),
    )

    entry, request = calls[0]
    assert entry.pw_uid == 4242
    assert set(json.loads(request)["files"]) == {
        files.CREDENTIALS_FILE,
        files.CONSOLES_FILE,
        files.GUIDE_FILE,
    }


def test_the_credentials_page_escapes_every_value_and_runs_no_script():
    page = files.render_credentials([("<b>", "<script>x</script>", 'a"b')]).decode()

    assert "<script>x" not in page
    assert "&lt;script&gt;" in page
    assert "default-src 'none'" in page


def test_a_symlinked_desktop_directory_is_refused(tmp_path):
    home = tmp_path / "home"
    (home / ".config" / "aptl").mkdir(parents=True)
    (home / files.DESKTOP_DIR).symlink_to(tmp_path)

    with pytest.raises(desktop.PathContainmentError, match="rejected path component"):
        files.write_desktop_files(home, {files.CONSOLES_FILE: b"https://x/\n"})
    assert not (tmp_path / files.CONSOLES_FILE).exists()


# --- hosts publisher --------------------------------------------------------


def _hosts_json(tmp_path, entries):
    path = tmp_path / "hosts.json"
    path.write_text(
        json.dumps({"schema": participant_hosts.SCHEMA, "entries": entries})
    )
    path.chmod(0o600)
    return path


def test_the_hosts_publisher_replaces_only_its_own_and_legacy_lines(tmp_path):
    etc = tmp_path / "hosts"
    etc.write_text(
        "127.0.0.1 localhost\n"
        "10.0.0.5 old.lab # lilrae-participant-desktop\n"
        "10.0.0.6 misp.legacy # aptl-seat-browser\n"
    )
    etc.chmod(0o644)

    participant_hosts.publish(
        _hosts_json(
            tmp_path, [{"address": "172.20.0.9", "hostname": "intel.example.test"}]
        ),
        etc,
    )

    assert etc.read_text().splitlines() == [
        "127.0.0.1 localhost",
        "172.20.0.9 intel.example.test # lilrae-participant-desktop",
    ]
    assert stat.S_IMODE(etc.stat().st_mode) == 0o644


@pytest.mark.parametrize(
    "entry",
    [
        {"address": "not-an-ip", "hostname": "a.test"},
        {"address": "10.0.0.1", "hostname": "a.test 10.0.0.2 b.test"},
        {"address": "10.0.0.1", "hostname": "localhost"},
    ],
)
def test_the_hosts_publisher_refuses_unsafe_entries(tmp_path, entry):
    etc = tmp_path / "hosts"
    etc.write_text("127.0.0.1 localhost\n")

    assert (
        participant_hosts.main(["x", str(_hosts_json(tmp_path, [entry])), str(etc)])
        == 1
    )
    assert etc.read_text() == "127.0.0.1 localhost\n"


def test_the_hosts_publisher_refuses_a_linked_hosts_file(tmp_path):
    real = tmp_path / "real"
    real.write_text("")
    link = tmp_path / "hosts"
    link.symlink_to(real)

    assert participant_hosts.main(["x", str(_hosts_json(tmp_path, [])), str(link)]) == 1


def test_the_hosts_publisher_runs_without_lilrae_installed(tmp_path):
    import subprocess
    import sys

    etc = tmp_path / "hosts"
    etc.write_text("")
    etc.chmod(0o644)
    script = participant_hosts.__file__
    completed = subprocess.run(
        [sys.executable, "-I", "-S", script, str(_hosts_json(tmp_path, [])), str(etc)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


# --- seam -------------------------------------------------------------------


def test_the_techvault_provider_supplies_every_field():
    from aptl_techvault.participant_desktop import TECHVAULT_DESKTOP

    spec = seam.validated_spec(TECHVAULT_DESKTOP)

    assert [item.label for item in spec.consoles] == [
        "Wazuh",
        "Shuffle",
        "MISP",
    ]
    assert {item.account for item in spec.credentials} == {
        "wazuh-indexer-admin",
        "shuffle-administrator",
        "misp-administrator",
    }
    assert spec.guide == "docs/attack-path.md"
    assert spec.hostnames == ("misp",)


def test_the_techvault_references_resolve_against_the_released_pack(tmp_path):
    from tests.techvault_pack import _pack_root

    from aptl.backends.raes_declared_credentials import scenario_accounts
    from aptl.core.scenario_bundle import env_pack_bundle
    from aptl_techvault.participant_desktop import TECHVAULT_DESKTOP

    bundle = env_pack_bundle(tmp_path, identity="techvault", source_pack=_pack_root())
    accounts = scenario_accounts(bundle.sdl_path)
    for item in TECHVAULT_DESKTOP.credentials:
        desktop._login(accounts, item)
    assert bundle.read_asset(TECHVAULT_DESKTOP.guide)
    assert seam.select_participant_desktop(bundle) == TECHVAULT_DESKTOP


@pytest.mark.parametrize(
    "spec",
    [
        ParticipantDesktopSpec(consoles=(DesktopConsole("a\nb", "n", "s"),)),
        ParticipantDesktopSpec(consoles=(DesktopConsole("A", "../n", "s"),)),
        ParticipantDesktopSpec(guide="/etc/passwd"),
        ParticipantDesktopSpec(guide="docs/../../x"),
        ParticipantDesktopSpec(hostnames=("n", "n")),
    ],
)
def test_the_seam_refuses_a_malformed_reference(spec):
    with pytest.raises(seam.ParticipantDesktopProviderError):
        seam.validated_spec(spec)


# --- owned fixture pack: SDL changes reach the desktop ------------------------

_FIXTURE_ADDITIONS = """
accounts:
  console-admin:
    username: {username}
    node: smoke-box
    auth_method: password
    password_strength: weak
    credential_bindings:
      - credential_id: console-admin-primary
        purpose: primary_authentication
        auth_method: password
        material:
          classification: secret_fixture
          value: "{secret}"
"""

_FIXTURE_RUNTIME = """    services:
      - {{name: https, port: 443, protocol: tcp}}
    runtime:
      applications:
        - application_id: smoke-console
          service: https
          protocol: https
      platform_applications:
        - platform_application_id: smoke-console
          service: https
          platform_kind: analytics_dashboard
          product: Smoke Console
          settings:
            - setting_id: smoke-canonical-url
              name: Canonical console URL
              value: https://{hostname}
              provenance: runtime
              classification: plain
"""


def _authored_fixture_pack(root, *, hostname, username, secret):
    """Copy the owned fixture pack, author a console and login, re-manifest it."""

    import shutil

    from raes_env_packs import derive_pack_content_manifest

    from tests.fixture_pack import FIXTURE_PACK_IDENTITY, FIXTURE_PACK_SOURCE

    pack = root / FIXTURE_PACK_IDENTITY
    shutil.copytree(FIXTURE_PACK_SOURCE, pack)
    sdl = pack / "sdl" / f"{FIXTURE_PACK_IDENTITY}.sdl.yaml"
    text = sdl.read_text(encoding="utf-8").replace(
        "    os: linux\n    runtime:\n",
        "    os: linux\n" + _FIXTURE_RUNTIME.format(hostname=hostname),
        1,
    )
    sdl.write_text(
        text + _FIXTURE_ADDITIONS.format(username=username, secret=secret),
        encoding="utf-8",
    )
    manifest = derive_pack_content_manifest(str(pack))
    (pack / "associated-artifacts.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return pack


def _fixture_desktop(tmp_path, **authored):
    from aptl.backends.raes import parse_sdl_file
    from aptl.backends.raes_declared_credentials import scenario_accounts
    from aptl.core.scenario_bundle import env_pack_bundle

    from tests.fixture_pack import FIXTURE_PACK_IDENTITY

    source = _authored_fixture_pack(tmp_path / "source", **authored)
    bundle = env_pack_bundle(
        tmp_path / "staged", FIXTURE_PACK_IDENTITY, source_pack=source
    )
    node_sdl = parse_sdl_file(bundle.sdl_path).nodes["smoke-box"]
    node = SimpleNamespace(
        name="smoke-box",
        container_name="aptl-smoke-box",
        services=tuple(
            DeploymentServicePort(item.name, item.port) for item in node_sdl.services
        ),
        runtime=node_sdl.runtime,
        address="172.31.250.10",
    )
    spec = ParticipantDesktopSpec(
        consoles=(DesktopConsole("Console", "smoke-box", "https"),),
        credentials=(
            DesktopCredential("Console", "console-admin", "console-admin-primary"),
        ),
        hostnames=("smoke-box",),
    )
    return desktop.resolve_participant_desktop(
        spec,
        read_asset=bundle.read_asset,
        accounts=scenario_accounts(bundle.sdl_path),
        nodes=[node],
        inspect=_inspect_for([node], {}),
        served_names=lambda _node, _port: frozenset(),
    )


def test_the_owned_fixture_pack_sdl_drives_the_desktop_output(tmp_path):
    first = _fixture_desktop(
        tmp_path / "first",
        hostname="console.fixture.test",
        username="analyst@fixture.test",
        secret="Fixture-One-2026!",
    )
    second = _fixture_desktop(
        tmp_path / "second",
        hostname="ops.fixture.test",
        username="operator@fixture.test",
        secret="Fixture-Two-2027!",
    )

    assert first.consoles == (("Console", "https://console.fixture.test/"),)
    assert first.hosts == (("172.31.250.10", "console.fixture.test"),)
    assert (first.logins[0].username, first.logins[0].secret) == (
        "analyst@fixture.test",
        "Fixture-One-2026!",
    )
    assert second.consoles == (("Console", "https://ops.fixture.test/"),)
    assert second.hosts == (("172.31.250.10", "ops.fixture.test"),)
    assert (second.logins[0].username, second.logins[0].secret) == (
        "operator@fixture.test",
        "Fixture-Two-2027!",
    )


def test_a_lab_without_a_desktop_account_publishes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv(desktop.ACCOUNT_VARIABLE, raising=False)
    admitted = SimpleNamespace(bundle=object(), realization=object(), scenario=None)

    assert desktop.start_participant_desktop(tmp_path, admitted, object()) is None
    assert not (tmp_path / desktop.HOSTS_RELPATH).exists()


def test_a_failed_desktop_withdraws_the_previous_hostnames(tmp_path, monkeypatch):
    stale = tmp_path / desktop.HOSTS_RELPATH
    stale.parent.mkdir(parents=True, mode=0o700)
    stale.write_text("{}")
    monkeypatch.setenv(desktop.ACCOUNT_VARIABLE, "participant")
    monkeypatch.setattr(
        seam,
        "select_participant_desktop",
        lambda _bundle, **_kwargs: _spec(consoles=(), hostnames=("absent",)),
    )
    admitted = SimpleNamespace(
        bundle=SimpleNamespace(root=tmp_path, read_asset=lambda _p: b"guide"),
        realization=SimpleNamespace(nodes=()),
        scenario=SimpleNamespace(accounts={}),
    )

    backend = SimpleNamespace(container_inspect=lambda _container: {})
    failure = desktop.start_participant_desktop(tmp_path, admitted, backend)

    assert failure == "node-unrealized"
    assert not stale.exists()


# --- review findings: complete snapshot, conflicts, exact loopback identity ---


def test_publication_removes_a_file_the_new_surface_omits(tmp_path):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    files.write_desktop_files(
        home,
        {files.GUIDE_FILE: b"old guide", files.CONSOLES_FILE: b"https://old/\n"},
    )

    files.write_desktop_files(home, {files.CONSOLES_FILE: b"https://new/\n"})

    directory = home / files.DESKTOP_DIR
    assert not (directory / files.GUIDE_FILE).exists()
    assert (directory / files.CONSOLES_FILE).read_text() == "https://new/\n"


def test_withdrawal_removes_the_hostnames_and_every_desktop_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    files.write_desktop_files(home, {files.CREDENTIALS_FILE: b"old logins"})
    hosts = tmp_path / desktop.HOSTS_RELPATH
    hosts.parent.mkdir(parents=True, mode=0o700)
    hosts.write_text("{}")
    entry = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid(), pw_dir=str(home))
    monkeypatch.setattr(desktop.pwd, "getpwnam", lambda _name: entry)

    desktop.withdraw_participant_desktop(tmp_path, "participant")

    assert not hosts.exists()
    assert not (home / files.DESKTOP_DIR / files.CREDENTIALS_FILE).exists()


def test_a_pack_without_a_desktop_withdraws_the_previous_one(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv(desktop.ACCOUNT_VARIABLE, "participant")
    monkeypatch.setattr(
        seam, "select_participant_desktop", lambda _bundle, **_kwargs: None
    )
    monkeypatch.setattr(
        desktop,
        "withdraw_participant_desktop",
        lambda root, account: calls.append(account) or True,
    )
    admitted = SimpleNamespace(bundle=object(), realization=object(), scenario=None)
    backend = SimpleNamespace(container_inspect=lambda _c: {})

    assert desktop.start_participant_desktop(tmp_path, admitted, backend) is None
    assert calls == ["participant"]


def test_two_addresses_for_one_hostname_are_refused():
    nodes, inspect, served = _lab(served=frozenset({"intel.example.test"}))

    with pytest.raises(desktop.ParticipantDesktopError) as caught:
        _resolve(lab=(nodes, inspect, served))

    assert caught.value.code == "hostname-conflict"


@pytest.mark.parametrize(
    ("served", "url"),
    [
        (frozenset({"127.0.0.1"}), "https://127.0.0.1:8443/"),
        (frozenset({"::1"}), "https://[::1]:8443/"),
        (frozenset({"localhost", "127.0.0.1"}), "https://localhost:8443/"),
    ],
)
def test_the_url_uses_the_exact_loopback_identity_the_certificate_covers(served, url):
    resolved = _resolve(lab=_lab(served=served))

    assert resolved.consoles[0] == ("Dashboard", url)


def _desktop_provider_entry(provider):
    return SimpleNamespace(name="fixture", load=lambda: provider)


def test_present_but_incompatible_desktop_provider_fails_closed(monkeypatch):
    provider = SimpleNamespace(
        extension_api_version="1",
        supported_pack_id="fixture",
        supported_pack_versions=("old",),
        supported_pack_set_digests=("digest",),
        resolve=lambda _bundle: _spec(),
    )
    bundle = SimpleNamespace(
        pack_identity=SimpleNamespace(
            pack_id="fixture", pack_version="new", set_digest="digest"
        )
    )
    monkeypatch.setattr(
        seam, "_entry_points", lambda: [_desktop_provider_entry(provider)]
    )

    with pytest.raises(
        seam.ParticipantDesktopProviderError, match="provider-incompatible"
    ):
        seam.select_participant_desktop(bundle)


def test_a_required_desktop_provider_cannot_be_silently_absent(monkeypatch):
    bundle = SimpleNamespace(pack_identity=SimpleNamespace(pack_id="fixture"))
    monkeypatch.setattr(seam, "_entry_points", lambda: [])

    with pytest.raises(seam.ParticipantDesktopProviderError, match="provider-missing"):
        seam.select_participant_desktop(bundle, required=True)


def test_desktop_provider_ambiguity_is_refused_before_resolution(monkeypatch):
    def refuse(_bundle):
        pytest.fail("ambiguous provider was resolved")

    provider = SimpleNamespace(
        extension_api_version="1",
        supported_pack_id="fixture",
        supported_pack_versions=("1",),
        supported_pack_set_digests=("digest",),
        resolve=refuse,
    )
    bundle = SimpleNamespace(
        pack_identity=SimpleNamespace(
            pack_id="fixture", pack_version="1", set_digest="digest"
        )
    )
    monkeypatch.setattr(
        seam, "_entry_points", lambda: [_desktop_provider_entry(provider)] * 2
    )
    with pytest.raises(
        seam.ParticipantDesktopProviderError, match="provider-ambiguous"
    ):
        seam.select_participant_desktop(bundle)


def test_guide_publication_is_passive_escaped_text(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    entry = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid(), pw_dir=str(home))
    monkeypatch.setattr(desktop.pwd, "getpwnam", lambda _name: entry)
    resolved = desktop.ResolvedDesktop(
        (),
        (),
        b'<script>window.bad=1</script><img src="https://remote.test/pixel">',
        (),
    )

    desktop.publish_participant_desktop(tmp_path, resolved, "participant")

    published = (home / files.DESKTOP_DIR / files.GUIDE_FILE).read_text()
    assert "<script>" not in published
    assert "<img " not in published
    assert "&lt;script&gt;" in published
    assert "Content-Security-Policy" in published


@pytest.mark.parametrize(
    "canonical",
    [
        "https://user:private-fixture@intel.example.test/",
        "https://intel.example.test/?token=private-fixture",
        "https://intel.example.test/#private-fixture",
    ],
)
def test_canonical_console_urls_cannot_carry_credentials(canonical):
    lab = _lab(canonical=canonical)
    with pytest.raises(desktop.ParticipantDesktopError):
        _resolve(lab=lab)


def test_the_canonical_console_preserves_its_authored_path():
    resolved = _resolve(lab=_lab(canonical="https://intel.example.test/console/"))
    assert resolved.consoles[1] == ("Intel", "https://intel.example.test/console/")


def test_stopped_containers_cannot_supply_desktop_endpoints():
    nodes, inspect, served = _lab()

    def stopped(container):
        info = inspect(container)
        info["State"]["Running"] = False
        return info

    with pytest.raises(desktop.ParticipantDesktopError, match="node-not-ready"):
        _resolve(lab=(nodes, stopped, served))


def test_ambiguous_published_ports_cannot_select_the_first_binding():
    nodes, inspect, served = _lab()

    def ambiguous(container):
        info = inspect(container)
        for bindings in info["NetworkSettings"]["Ports"].values():
            bindings.append({"HostPort": "9443"})
        return info

    with pytest.raises(desktop.ParticipantDesktopError, match="console-port-ambiguous"):
        _resolve(lab=(nodes, ambiguous, served))


def test_ipv6_certificate_identity_requires_an_actual_ipv6_publication():
    nodes, inspect, served = _lab(served=frozenset({"::1"}))

    def ipv4_only(container):
        info = inspect(container)
        for port, bindings in info["NetworkSettings"]["Ports"].items():
            info["NetworkSettings"]["Ports"][port] = [bindings[0]]
        return info

    with pytest.raises(
        desktop.ParticipantDesktopError, match="console-port-unreachable"
    ):
        _resolve(lab=(nodes, ipv4_only, served))


def test_root_writer_drops_supplementary_groups_and_keeps_payload_on_stdin(
    tmp_path, monkeypatch
):
    calls = []
    entry = SimpleNamespace(pw_uid=4242, pw_gid=4242, pw_dir=str(tmp_path))

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(files.subprocess, "run", run)

    desktop._write_as_account(entry, "private-fixture-payload")

    argv, options = calls[0]
    assert options["user"] == options["group"] == 4242
    assert options.get("extra_groups") == []
    assert options["input"] == "private-fixture-payload"
    assert "private-fixture-payload" not in repr(argv)


def test_withdrawal_reports_a_private_path_refusal(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config/aptl").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / files.CREDENTIALS_FILE
    marker.write_text("untouched")
    (home / files.DESKTOP_DIR).symlink_to(outside, target_is_directory=True)
    entry = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid(), pw_dir=str(home))
    monkeypatch.setattr(desktop.pwd, "getpwnam", lambda _name: entry)

    assert desktop.withdraw_participant_desktop(tmp_path, "participant") is False
    assert marker.read_text() == "untouched"
