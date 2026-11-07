"""Initial service readback must reject missing or conflicting native state."""

from types import SimpleNamespace

from raes.runtime_configuration import RuntimeConfiguration

from aptl.backends.database_inventory import observe_database_services
from aptl.backends.service_inventory import (
    observe_dns_services,
    observe_file_services,
    observe_identity_authorities,
)
from aptl.core.deployment._proc_net_listeners import ContainerListeners


class NativeBackend:
    def __init__(self, replies, sockets=()):
        self.replies = replies
        self.sockets = sockets
        self.commands = []

    def container_exec(self, container, argv, timeout):
        self.commands.append(argv)
        for match, value in self.replies.items():
            if match in " ".join(argv):
                return SimpleNamespace(returncode=0, stdout=value)
        return SimpleNamespace(returncode=1, stdout="")

    def observe_container_listeners(self, container):
        return ContainerListeners(sockets=self.sockets)


def test_directory_requires_live_domain_and_listener():
    runtime = RuntimeConfiguration.model_validate(
        {
            "identity_authorities": [
                {
                    "identity_authority_id": "domain",
                    "kind": "domain",
                    "domain_name": "example.test",
                    "realm": "EXAMPLE.TEST",
                    "base_dn": "DC=example,DC=test",
                    "services": [
                        {"service_id": "ldap", "protocol": "ldap", "port": 389}
                    ],
                }
            ]
        }
    )
    backend = NativeBackend(
        {
            "samba-tool": "Domain : example.test\nNetbios domain : EXAMPLE\nDC name : ad.example.test\n"
        },
        (("tcp", "0.0.0.0", 389),),
    )
    assert observe_identity_authorities(backend, "ad", runtime) is not None
    backend.sockets = ()
    assert observe_identity_authorities(backend, "ad", runtime) is None
    backend.sockets = (("tcp", "0.0.0.0", 389),)
    backend.replies["samba-tool"] = (
        "Domain : other.test\nNetbios domain : OTHER\nDC name : ad.other.test\n"
    )
    assert observe_identity_authorities(backend, "ad", runtime) is None


def test_samba_effective_share_permissions_and_group_presence():
    runtime = RuntimeConfiguration.model_validate(
        {
            "file_services": [
                {
                    "file_service_id": "shares",
                    "protocol": "smb",
                    "shares": [
                        {
                            "share_id": "engineering",
                            "name": "Engineering",
                            "backing_path": "/srv/engineering",
                            "read_only": False,
                            "guest_ok": False,
                            "valid_groups": ["Engineering"],
                        }
                    ],
                    "principals": [
                        {
                            "principal_id": "eng",
                            "kind": "group",
                            "name": "Engineering",
                            "origin": "provisioned",
                        }
                    ],
                }
            ]
        }
    )
    backend = NativeBackend(
        {
            "testparm": "[Engineering]\npath = /srv/engineering\nread only = No\nvalid users = @Engineering\n",
            "getent": "Engineering:x:1001:\n",
        }
    )
    assert observe_file_services(backend, "smb", runtime) is not None
    backend.replies["testparm"] += "guest ok = Yes\n"
    assert observe_file_services(backend, "smb", runtime) is None
    backend.replies["testparm"] = (
        "[Engineering]\npath = /srv/engineering\nread only = No\nvalid users = @Engineering\n"
    )
    del backend.replies["getent"]
    assert observe_file_services(backend, "smb", runtime) is None


def test_bind_zone_type_must_come_from_native_inventory():
    runtime = RuntimeConfiguration.model_validate(
        {
            "dns_services": [
                {
                    "dns_service_id": "dns",
                    "implementation": "bind",
                    "roles": ["authoritative"],
                    "zones": [
                        {
                            "zone_id": "forward",
                            "name": "example.test",
                            "kind": "primary",
                        }
                    ],
                }
            ]
        }
    )
    backend = NativeBackend({"named-checkconf": "example.test IN _default master\n"})
    assert observe_dns_services(backend, "dns", runtime) is not None
    backend.replies["named-checkconf"] = "example.test IN _default forward\n"
    assert observe_dns_services(backend, "dns", runtime) is None


def test_postgresql_checks_tables_and_login_role():
    runtime = RuntimeConfiguration.model_validate(
        {
            "database_services": [
                {
                    "database_service_id": "db",
                    "engine": "postgresql",
                    "protocol": "postgresql",
                    "listeners": [{"address": "0.0.0.0", "port": 5432}],
                    "databases": [
                        {
                            "database_id": "app",
                            "name": "app",
                            "schemas": [
                                {
                                    "schema_id": "public",
                                    "name": "public",
                                    "tables": [{"table_id": "users", "name": "users"}],
                                }
                            ],
                        }
                    ],
                    "roles": [
                        {"role_id": "app-role", "name": "app", "can_login": True}
                    ],
                }
            ]
        }
    )
    backend = NativeBackend(
        {
            "SHOW server_version": "17.4\n",
            "SELECT datname": "app\npostgres\n",
            "SELECT schema_name": "public\n",
            "SELECT table_name": "users\n",
            "SELECT rolcanlogin": "t\n",
        },
        (("tcp", "0.0.0.0", 5432),),
    )
    assert observe_database_services(backend, "db", runtime) is not None
    backend.replies["SELECT table_name"] = "other\n"
    assert observe_database_services(backend, "db", runtime) is None
    backend.replies["SELECT table_name"] = "users\n"
    backend.replies["SELECT rolcanlogin"] = "f\n"
    assert observe_database_services(backend, "db", runtime) is None


def test_mariadb_checks_database_grant_without_credential_in_argv():
    runtime = RuntimeConfiguration.model_validate(
        {
            "database_services": [
                {
                    "database_service_id": "db",
                    "engine": "mariadb",
                    "version": "10.11",
                    "protocol": "mysql",
                    "databases": [{"database_id": "app", "name": "app"}],
                    "roles": [{"role_id": "role", "name": "app", "can_login": True}],
                    "grants": [
                        {
                            "grantee_role_ref": "role",
                            "object_type": "database",
                            "object_ref": "app",
                            "privileges": ["ALL"],
                            "with_grant_option": False,
                        }
                    ],
                }
            ]
        }
    )
    backend = NativeBackend(
        {
            "SELECT VERSION()": "10.11.14-MariaDB\n",
            "SELECT SCHEMA_NAME": "app\n",
            "SELECT IF(plugin": "t\n",
            "SHOW GRANTS": "GRANT ALL PRIVILEGES ON `app`.* TO `app`@`%`\n",
        }
    )
    assert observe_database_services(backend, "db", runtime) is not None
    assert all("MYSQL_ROOT_PASSWORD" in argv[2] for argv in backend.commands)
    backend.replies["SHOW GRANTS"] += (
        ""  # grant delegation changes the selected posture
    )
    backend.replies["SHOW GRANTS"] = (
        "GRANT ALL PRIVILEGES ON `app`.* TO `app`@`%` WITH GRANT OPTION\n"
    )
    assert observe_database_services(backend, "db", runtime) is None
