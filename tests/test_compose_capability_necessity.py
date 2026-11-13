"""Why the Samba provider needs no CAP_SYS_ADMIN (#955, #976).

Issue #955 removed `CAP_SYS_ADMIN` from every node on the generic systemd
substrate. The Samba provider kept the grant on a measurement: `samba-tool
domain provision` wrote the sysvol's NT ACLs into the `security.NTACL` extended
attribute, and the kernel gates writes to the whole `security.*` xattr
namespace behind CAP_SYS_ADMIN. Without the grant, provisioning failed at
`setsysvolacl` with NT_STATUS_ACCESS_DENIED.

Issue #976 moved the NT ACLs to Samba's `xattr_tdb` store: a root-only TDB on
the persistent volume, beside sysvol. Samba's own AD DC test environments use
the same VFS stack. The provider now adds no capability. The tests below keep
the original kernel measurement and prove the replacement on a real daemon:
provisioning, winbind, Kerberos, LDAP, SYSVOL access control, container
recreation, and conversion of a volume provisioned before #976.

The behavioural tests are marked `integration` (per-test, not module-level, so
the default `-k "not integration"` run does not zero this module's coverage)
because they need a real Docker daemon and the built Samba provider images. CI
builds both images and runs them in the python-qualification job.
"""

from __future__ import annotations

import re
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from aptl.backends import _raes_backend_implementation_profiles as profiles
from aptl.backends._raes_backend_implementation_images import (
    SAMBA_AD_BASE_IMAGE,
    WAZUH_SAMBA_AD_BASE_IMAGE,
)

PROJECT_ROOT = Path(__file__).parents[1]
_PROVISION_SCRIPT = PROJECT_ROOT / "containers/generic-samba-ad-base/provision-domain.sh"
_XATTR_STORE = "/var/lib/samba/private/xattr.tdb"
_READY_MARKER = "/run/aptl-samba-provider.ready"
_DOMAIN, _REALM = "LABTEST", "LABTEST.LOCAL"
_SHARE_ROOT = "/var/lib/samba/sysvol"
_SYSVOL = f"{_SHARE_ROOT}/{_REALM.lower()}"
# Generated per run for a throwaway test domain; meets Samba's complexity rule.
_PASSWORD = f"Lab-{secrets.token_hex(12)}-Aa1!"
_CAP_SYS_ADMIN_BIT = 21


def _domain_runtime() -> SimpleNamespace:
    """A portable runtime that selects the Samba provider."""

    return SimpleNamespace(
        service_listeners=tuple(
            SimpleNamespace(service=name) for name in ("kerberos", "ldap", "smb")
        ),
        identity_authorities=(
            SimpleNamespace(
                kind="domain", realm=_REALM.lower(), domain_name=_REALM.lower()
            ),
        ),
        forwarding_agents=(),
    )


def test_the_samba_provider_selects_no_capability():
    """The provider adds nothing; an authored grant stays a scenario decision."""

    selection = profiles._active_directory_base(_domain_runtime())

    assert selection is not None
    assert selection.provider_kind == "samba-active-directory"
    assert selection.run_capabilities == ()


def test_provisioning_writes_nt_acls_to_the_root_only_tdb_store():
    """Fresh provisioning and the restart path both select the xattr_tdb store."""

    script = _PROVISION_SCRIPT.read_text()

    assert 'xattr_store="$private_root/xattr.tdb"' in script
    assert 'vfs_option="vfs objects = dfs_samba4 acl_xattr xattr_tdb"' in script
    assert script.count('--option="$vfs_option"') == 1
    assert script.count('--option="$store_option"') == 1
    # Conversion copies the old descriptors; it never resets them to defaults.
    assert '$acl_store_tool convert "$xattr_store" "$sysvol_tree"' in script
    commands = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in commands if "sysvolreset" in line]
    # Every path verifies the store before it releases readiness.
    verify = script.index('$acl_store_tool verify "$xattr_store" "$sysvol_tree"')
    assert verify < script.index("touch /run/aptl-samba-provider.ready")


# `docker run` flags that would give the container more than its added capability.
_PRIVILEGE_FLAGS = frozenset(
    {"--privileged", "--security-opt", "--cgroupns", "--userns", "--pid", "--ipc"}
)


class _StartRecorder:
    """A backend that records the base container the materializer starts.

    Raising from the start stops materialization there, so nothing else runs
    and no Docker daemon is needed.
    """

    def __init__(self) -> None:
        self.started = []
        self.copied = []

    def start_base_container(self, spec) -> None:
        self.started.append(spec)
        raise RuntimeError("recorded, not started")

    def copy_into_container(self, *args, **kwargs) -> None:
        self.copied.append((args, kwargs))


def _docker(*args: str, timeout: int = 300, stdin: str | None = None):
    return subprocess.run(
        ["docker", *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _require_image(image: str) -> None:
    if _docker("image", "inspect", image).returncode != 0:
        pytest.skip(f"{image} is not built on this host")


requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="needs a Docker daemon"
)


def _write_security_xattr(*cap_flags: str) -> subprocess.CompletedProcess:
    """Attempt a `security.*` xattr write with the given grants."""

    return _docker(
        "run", "--rm",
        "--entrypoint", "python3",
        *cap_flags,
        SAMBA_AD_BASE_IMAGE,
        "-c",
        # The kernel permission the default NT ACL store depends on.
        "import os; os.makedirs('/tmp/acl', exist_ok=True); "
        "os.setxattr('/tmp/acl', 'security.NTACL', b'\\x01\\x00\\x00')",
    )


@pytest.mark.integration
@requires_docker
def test_security_xattr_write_requires_sys_admin_in_the_samba_provider_image():
    """The #955 measurement: the kernel store needs SYS_ADMIN for each write.

    This is why the provider must not use `security.NTACL`.
    """

    _require_image(SAMBA_AD_BASE_IMAGE)

    without = _write_security_xattr()
    assert without.returncode != 0
    assert "Operation not permitted" in (without.stderr + without.stdout)

    with_sys_admin = _write_security_xattr("--cap-add", "SYS_ADMIN")
    assert with_sys_admin.returncode == 0, with_sys_admin.stderr


class _DomainController:
    """One provider container on one named volume, started like the backend does."""

    def __init__(self, image: str) -> None:
        self.image = image
        self.name = f"lilrae-976-{uuid.uuid4().hex[:12]}"
        self.volume = f"{self.name}-data"

    def start(self) -> None:
        """Start the image's own entrypoint with no added capability."""

        result = _docker(
            "run", "-d", "--name", self.name,
            "-v", f"{self.volume}:/var/lib/samba",
            self.image,
        )
        assert result.returncode == 0, result.stderr

    def remove_container(self) -> None:
        _docker("rm", "-f", self.name)

    def run(self, *argv: str, stdin: str | None = None):
        return _docker("exec", "-i", self.name, *argv, stdin=stdin)

    def sh(self, script: str):
        return self.run("sh", "-c", script)

    def provision_step(self):
        return self.run("aptl-provision-samba-domain", _DOMAIN, _REALM)

    def provision(self) -> None:
        """Run the provider's provisioning step and wait for the domain."""

        result = self.provision_step()
        assert result.returncode == 0, result.stdout + result.stderr
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.run("samba-tool", "domain", "info", "127.0.0.1").returncode == 0:
                return
            time.sleep(2)
        pytest.fail("Samba did not answer domain info within 180 s")

    def cleanup(self) -> None:
        self.remove_container()
        _docker("volume", "rm", "-f", self.volume)


@pytest.fixture
def domain_controller():
    created: list[_DomainController] = []

    def make(image: str) -> _DomainController:
        _require_image(image)
        controller = _DomainController(image)
        created.append(controller)
        return controller

    yield make
    for controller in created:
        controller.cleanup()


def _pid1_holds_sys_admin(dc: _DomainController) -> bool:
    status = dc.run("cat", "/proc/1/status").stdout
    cap_eff = int(re.search(r"^CapEff:\s*([0-9a-f]+)$", status, re.M).group(1), 16)
    return bool(cap_eff & (1 << _CAP_SYS_ADMIN_BIT))


def _create_accounts(dc: _DomainController) -> None:
    """`alice` is an ordinary user; `bob` is over-privileged in Domain Admins."""

    for user in ("alice", "bob"):
        result = dc.run("samba-tool", "user", "create", user, _PASSWORD)
        assert result.returncode == 0, result.stderr
    result = dc.run("samba-tool", "group", "addmembers", "Domain Admins", "bob")
    assert result.returncode == 0, result.stderr


def _smb(dc: _DomainController, user: str, command: str):
    return dc.run(
        "smbclient", "//127.0.0.1/sysvol",
        "-U", f"{_DOMAIN}\\{user}%{_PASSWORD}",
        "-c", command,
    )


def _assert_sysvol_acls_are_enforced(dc: _DomainController, new_file: str) -> str:
    """Ordinary users read sysvol; only administrators write. Return the new ACL."""

    listing = _smb(dc, "alice", f"ls {_REALM.lower()}/*")
    assert listing.returncode == 0, listing.stdout + listing.stderr
    assert "Policies" in listing.stdout

    denied = _smb(dc, "alice", f"put /etc/hostname {_REALM.lower()}/{new_file}-alice")
    assert "NT_STATUS_ACCESS_DENIED" in denied.stdout + denied.stderr

    allowed = _smb(dc, "bob", f"put /etc/hostname {_REALM.lower()}/{new_file}")
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    return _sddl(dc, f"{_SYSVOL}/{new_file}")


def _sddl(dc: _DomainController, path: str) -> str:
    result = dc.run("samba-tool", "ntacl", "get", path, "--as-sddl", "--use-s3fs")
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _assert_sysvol_matches_the_provisioned_acls(dc: _DomainController) -> None:
    """Samba's own check reads every sysvol ACL directly and through smbd."""

    result = dc.run("samba-tool", "ntacl", "sysvolcheck")
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_identity_services(dc: _DomainController) -> None:
    assert dc.run("wbinfo", "-p").returncode == 0
    assert f"{_DOMAIN}\\alice" in dc.run("wbinfo", "-u").stdout
    auth = dc.run("wbinfo", "-a", f"{_DOMAIN}\\alice%{_PASSWORD}")
    assert "authentication succeeded" in auth.stdout, auth.stdout + auth.stderr
    assert dc.run("wbinfo", "-i", f"{_DOMAIN}\\alice").returncode == 0

    # The provisioned krb5.conf locates the KDC through DNS, which this
    # standalone container does not serve; name the KDC directly.
    krb5 = (
        f"[libdefaults]\n default_realm = {_REALM}\n dns_lookup_kdc = false\n"
        f"[realms]\n {_REALM} = {{\n  kdc = 127.0.0.1\n }}\n"
    )
    assert dc.run("sh", "-c", "cat > /tmp/krb5.conf", stdin=krb5).returncode == 0
    kinit = dc.run(
        "env", "KRB5_CONFIG=/tmp/krb5.conf", "kinit", f"alice@{_REALM}",
        stdin=f"{_PASSWORD}\n",
    )
    assert kinit.returncode == 0, kinit.stdout + kinit.stderr

    ldap = dc.run(
        "ldbsearch", "-H", "ldap://127.0.0.1",
        "-U", f"{_DOMAIN}\\alice%{_PASSWORD}",
        "-b", f"DC={_REALM.split('.')[0]},DC=local",
        "(sAMAccountName=alice)", "dn",
    )
    assert "dn: CN=alice,CN=Users" in ldap.stdout, ldap.stdout + ldap.stderr


def _assert_acl_store_is_root_only(dc: _DomainController) -> None:
    """The NT ACLs live in a root-only TDB, not in a user-writable xattr."""

    mode = dc.run("stat", "-c", "%a %U %G", _XATTR_STORE).stdout.split()
    assert mode == ["600", "root", "root"]
    names = dc.run(
        "python3", "-c", f"import os; print(os.listxattr('{_SYSVOL}'))"
    ).stdout
    assert "NTACL" not in names


@pytest.mark.integration
@requires_docker
@pytest.mark.parametrize("image", [SAMBA_AD_BASE_IMAGE, WAZUH_SAMBA_AD_BASE_IMAGE])
def test_the_domain_works_without_sys_admin_and_survives_recreation(
    domain_controller, image
):
    dc = domain_controller(image)
    dc.start()
    assert not _pid1_holds_sys_admin(dc)

    dc.provision()
    _assert_sysvol_matches_the_provisioned_acls(dc)
    _assert_acl_store_is_root_only(dc)
    _create_accounts(dc)
    _assert_identity_services(dc)
    new_acl = _assert_sysvol_acls_are_enforced(dc, "admin-before.txt")

    # Recreate the container on the same volume: the restart path.
    dc.remove_container()
    dc.start()
    dc.provision()
    _assert_sysvol_matches_the_provisioned_acls(dc)
    assert _sddl(dc, f"{_SYSVOL}/admin-before.txt") == new_acl
    _assert_sysvol_acls_are_enforced(dc, "admin-after.txt")


# A protected ACL that admits only BUILTIN\\Administrators and SYSTEM: Domain
# Admins members may read; an ordinary authenticated user may not.
_RESTRICTED_SDDL = {
    "restricted": "O:BAG:BAD:P(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)",
    "restricted/secret.txt": "O:BAG:BAD:P(A;;FA;;;BA)(A;;FA;;;SY)",
}
# A custom descriptor on the SYSVOL share root, which sits above the realm.
_SHARE_ROOT_SDDL = "O:BAG:BAD:P(A;;FA;;;BA)(A;;FA;;;SY)(A;;0x1200a9;;;AU)"


def _legacy_provision_script() -> str:
    """The pre-#976 provisioning, plus one custom restrictive sysvol ACL."""

    restricted = f"{_SYSVOL}/restricted"
    acls = " && ".join(
        f"samba-tool ntacl set '{sddl}' {path} --use-s3fs"
        for path, sddl in (
            *((f"{_SYSVOL}/{path}", sddl) for path, sddl in _RESTRICTED_SDDL.items()),
            (_SHARE_ROOT, _SHARE_ROOT_SDDL),
        )
    )
    return (
        "rm -f /etc/samba/smb.conf && samba-tool domain provision --server-role=dc "
        f"--use-rfc2307 --dns-backend=SAMBA_INTERNAL --realm={_REALM} "
        f"--domain={_DOMAIN} --adminpass='{_PASSWORD}' > /dev/null "
        "&& cp /etc/samba/smb.conf /var/lib/samba/smb.conf.provisioned "
        "&& touch /var/lib/samba/private/.provisioned "
        f"&& mkdir {restricted} && echo restricted > {restricted}/secret.txt "
        f"&& {acls} "
        f"&& python3 -c \"import os; print(os.listxattr('{restricted}'))\""
    )


@pytest.mark.integration
@requires_docker
def test_a_volume_provisioned_before_976_is_converted(domain_controller):
    """A retained volume holds kernel `security.NTACL` ACLs and a marker.

    Conversion must keep every descriptor, including a custom restrictive one.
    """

    dc = domain_controller(SAMBA_AD_BASE_IMAGE)
    # Test setup only: reproduce the pre-#976 provisioning, which needed the grant.
    legacy = _docker(
        "run", "--rm", "--cap-add", "SYS_ADMIN",
        "-v", f"{dc.volume}:/var/lib/samba",
        "--entrypoint", "sh", SAMBA_AD_BASE_IMAGE, "-c", _legacy_provision_script(),
    )
    assert legacy.returncode == 0, legacy.stdout + legacy.stderr
    assert "security.NTACL" in legacy.stdout

    dc.start()
    assert not _pid1_holds_sys_admin(dc)
    dc.provision()
    _assert_sysvol_matches_the_provisioned_acls(dc)
    saved = dc.run(
        "testparm", "-s", "--parameter-name=xattr_tdb:file",
        "/var/lib/samba/smb.conf.provisioned",
    )
    assert saved.stdout.strip() == _XATTR_STORE
    for path, sddl in _RESTRICTED_SDDL.items():
        assert _sddl(dc, f"{_SYSVOL}/{path}") == sddl
    assert _sddl(dc, _SHARE_ROOT) == _SHARE_ROOT_SDDL
    _create_accounts(dc)
    _assert_sysvol_acls_are_enforced(dc, "admin-converted.txt")
    secret = f"{_REALM.lower()}/restricted/secret.txt"
    denied = _smb(dc, "alice", f"get {secret} /dev/null")
    assert "NT_STATUS_ACCESS_DENIED" in denied.stdout + denied.stderr
    allowed = _smb(dc, "bob", f"get {secret} /dev/null")
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr

    # The conversion runs once; the next start keeps one copy of each option.
    dc.remove_container()
    dc.start()
    dc.provision()
    config = dc.run("cat", "/etc/samba/smb.conf").stdout
    assert config.count("xattr_tdb:file") == 1
    assert config.count("vfs objects") == 1


def _damage_store(dc: _DomainController, damage: str) -> None:
    damaged = _docker(
        "run", "--rm", "-v", f"{dc.volume}:/var/lib/samba",
        "--entrypoint", "sh", SAMBA_AD_BASE_IMAGE, "-c", damage,
    )
    assert damaged.returncode == 0, damaged.stderr


_DAMAGE = [
    pytest.param(f"rm {_XATTR_STORE}", id="missing"),
    pytest.param(f"head -c 4096 /dev/urandom > {_XATTR_STORE}", id="corrupt"),
]


@pytest.mark.integration
@requires_docker
@pytest.mark.parametrize("damage", _DAMAGE)
def test_a_damaged_acl_store_blocks_readiness_in_a_new_container(
    domain_controller, damage
):
    """A retained marker and configuration do not prove the ACL store is usable."""

    dc = domain_controller(SAMBA_AD_BASE_IMAGE)
    dc.start()
    dc.provision()
    dc.remove_container()
    _damage_store(dc, damage)

    dc.start()
    result = dc.provision_step()

    assert result.returncode != 0
    assert _XATTR_STORE in result.stdout + result.stderr
    assert dc.run("test", "-e", _READY_MARKER).returncode != 0


@pytest.mark.integration
@requires_docker
@pytest.mark.parametrize("damage", _DAMAGE)
def test_a_damaged_acl_store_stops_a_restarted_container(domain_controller, damage):
    """The readiness marker survives a restart; the entrypoint checks the store."""

    dc = domain_controller(SAMBA_AD_BASE_IMAGE)
    dc.start()
    dc.provision()
    assert _docker("stop", dc.name).returncode == 0
    _damage_store(dc, damage)

    assert _docker("start", dc.name).returncode == 0
    deadline = time.monotonic() + 60
    state = ""
    while time.monotonic() < deadline:
        state = _docker("inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", dc.name)
        state = state.stdout.strip()
        if state.startswith("exited"):
            break
        time.sleep(1)

    status, exit_code = state.split()
    assert status == "exited", state
    assert exit_code != "0", state
    assert _XATTR_STORE in _docker("logs", dc.name).stderr


def test_retired_reverse_workstation_has_no_shipped_capability_grant():
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text())
    assert "reverse" not in compose["services"]
    assert not (PROJECT_ROOT / "containers/reverse/Dockerfile").exists()
