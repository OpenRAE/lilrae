"""Read the managed database catalogs through their native SQL interfaces."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_realization_model import NodeRealization
    from raes.runtime_database import RuntimeDatabaseService

from copy import deepcopy

from aptl_techvault.readback_support import (
    ReadbackBackend,
    as_mapping,
    identifier,
    json_output,
    output,
    require,
    value,
    version_matches,
    observed_version,
)


def _postgres(
    backend: ReadbackBackend, container: str, sql: str, database: str = "postgres"
) -> str:
    """Run a bounded native PostgreSQL catalog query."""

    return output(
        backend,
        container,
        [
            "runuser",
            "-u",
            "postgres",
            "--",
            "psql",
            "-X",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-Atqc",
            sql,
        ],
    )


def _mariadb(backend: ReadbackBackend, container: str, sql: str) -> str:
    # Credentials stay inside the managed guest and never enter an observation.
    """Run a bounded native MariaDB query with guest-local credentials."""

    return output(
        backend,
        container,
        [
            "sh",
            "-ec",
            'MYSQL_PWD="${MARIADB_ROOT_PASSWORD:-${MYSQL_ROOT_PASSWORD:-}}"; '
            'export MYSQL_PWD; exec mariadb -uroot --batch --skip-column-names -e "$1"',
            "native-readback",
            sql,
        ],
    )


def _database_schema(
    backend: ReadbackBackend,
    container: str,
    engine: str,
    query: Callable[[ReadbackBackend, str, str], str],
    database: dict[str, object],
    schema: dict[str, object],
) -> None:
    """Read the selected schema's native table catalog."""

    name = database["name"]
    schema_name = identifier(schema["name"])
    statement = (
        "SELECT tablename FROM pg_tables "
        f"WHERE schemaname = '{schema_name}' ORDER BY tablename"
        if engine == "postgresql"
        else "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{schema_name}' ORDER BY table_name"
    )
    rows = (
        _postgres(backend, container, statement, name)
        if engine == "postgresql"
        else query(backend, container, statement)
    )
    observed = set(rows.splitlines())
    require(all(table["name"] in observed for table in schema["tables"]))
    for table in schema["tables"]:
        table["name"] = next(item for item in observed if item == table["name"])


def _database_catalogs(
    backend: ReadbackBackend,
    container: str,
    engine: str,
    query: Callable[[ReadbackBackend, str, str], str],
    row: dict[str, object],
) -> None:
    """Read selected native databases, schemas and table names."""

    for database in row["databases"]:
        name = identifier(database["name"])
        catalog = (
            "pg_database" if engine == "postgresql" else "information_schema.schemata"
        )
        column = "datname" if engine == "postgresql" else "schema_name"
        require(
            query(
                backend,
                container,
                f"SELECT {column} FROM {catalog} WHERE {column} = '{name}'",
            )
            == name
        )
        for schema in database["schemas"]:
            _database_schema(backend, container, engine, query, database, schema)


def _database_roles(
    backend: ReadbackBackend,
    container: str,
    engine: str,
    query: Callable[[ReadbackBackend, str, str], str],
    row: dict[str, object],
) -> None:
    """Corroborate native role presence and its login capability."""

    for role in row["roles"]:
        name = identifier(role["name"])
        statement = (
            f"SELECT rolname || '|' || rolcanlogin FROM pg_roles WHERE rolname = '{name}'"
            if engine == "postgresql"
            else f"SELECT user FROM mysql.user WHERE user = '{name}'"
        )
        observed = query(backend, container, statement).splitlines()
        require(bool(observed))
        if engine == "postgresql":
            require(
                len(observed) == 1
                and observed[0].split("|")
                == [name, str(bool(role["can_login"])).lower()]
            )
        else:
            require(
                all(item == name for item in observed) and role["can_login"] is True
            )


def _database_grants(
    backend: ReadbackBackend,
    container: str,
    engine: str,
    query: Callable[[ReadbackBackend, str, str], str],
    row: dict[str, object],
) -> None:
    """Corroborate selected MariaDB database privileges without grant authority."""

    for grant in row["grants"]:
        require(
            engine == "mariadb"
            and grant["object_type"] == "database"
            and not grant["with_grant_option"]
        )
        role = next(
            item
            for item in row["roles"]
            if item["role_id"] == grant["grantee_role_ref"]
        )
        database = next(
            item
            for item in row["databases"]
            if item["database_id"] == grant["object_ref"]
        )
        grants = query(
            backend, container, f"SHOW GRANTS FOR '{identifier(role['name'])}'@'%'"
        )
        require(
            grant["privileges"] == ["ALL"]
            and f"ALL PRIVILEGES ON `{identifier(database['name'])}`.*" in grants
            and "WITH GRANT OPTION" not in grants
        )


def _database_listeners(
    row: dict[str, object], actual_port: str, actual_address: str
) -> None:
    """Read the effective native listener port and admitted address."""

    for listener in row["listeners"]:
        require(int(actual_port) == listener["port"])
        require(
            listener["address"] in actual_address.split(",")
            or actual_address in {"*", "0.0.0.0"}
            and listener["address"] == "0.0.0.0"
        )
        listener["port"] = int(actual_port)


def _database_service(
    backend: ReadbackBackend, node: NodeRealization, service: RuntimeDatabaseService
) -> dict[str, object]:
    """Read one database service through its native SQL owner."""

    engine = value(service.engine)
    require(engine in {"postgresql", "mariadb"})
    query = _postgres if engine == "postgresql" else _mariadb
    container = node.container_name
    actual_version = query(
        backend,
        container,
        "SHOW server_version" if engine == "postgresql" else "SELECT VERSION()",
    )
    require(version_matches(str(service.version or ""), actual_version))
    actual_port = query(
        backend,
        container,
        "SHOW port" if engine == "postgresql" else "SELECT @@port",
    )
    actual_address = query(
        backend,
        container,
        "SHOW listen_addresses" if engine == "postgresql" else "SELECT @@bind_address",
    )
    row = service.model_dump(mode="json", by_alias=True)
    row["version"] = observed_version(str(service.version or ""), actual_version)
    row["protocol"] = "postgresql" if engine == "postgresql" else "mysql"
    _database_listeners(row, actual_port, actual_address)
    _database_catalogs(backend, container, engine, query, row)
    _database_roles(backend, container, engine, query, row)
    _database_grants(backend, container, engine, query, row)
    require(not row["settings"])
    return row


def database_services(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read native catalogs, login roles, grants and listener configuration."""

    return [
        _database_service(backend, node, service)
        for service in node.runtime.database_services
    ]


_SEARCH_QUERY = r"""set -eu
path=$1
if [ -f /usr/share/wazuh-indexer/certs/admin.pem ]; then
  exec curl -fsk --max-time 25 \
    --cert /usr/share/wazuh-indexer/certs/admin.pem \
    --key /usr/share/wazuh-indexer/certs/admin-key.pem "https://127.0.0.1:9200$path"
fi
exec curl -fsk --max-time 25 -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD:?}" "https://127.0.0.1:9200$path"
"""


def _search(backend: ReadbackBackend, container: str, path: str) -> object:
    """Read one authenticated native search-engine endpoint."""

    return json_output(
        backend, container, ["sh", "-ec", _SEARCH_QUERY, "native-readback", path]
    )


def _search_service(
    backend: ReadbackBackend, container: str, service: object
) -> dict[str, object]:
    """Read native search metadata and the selected engine version."""

    row = service.model_dump(mode="json", by_alias=True)
    info = as_mapping(_search(backend, container, "/"))
    version = as_mapping(info.get("version"))
    actual_version = str(version.get("number", ""))
    if row["datastore_service_id"] == "wazuh-indexer":
        actual_version = output(
            backend, container, ["rpm", "-q", "--qf", "%{VERSION}", "wazuh-indexer"]
        )
    require(version_matches(row["version"], actual_version))
    row["version"] = observed_version(row["version"], actual_version)
    metadata = as_mapping(
        as_mapping(_search(backend, container, "/_cluster/state/metadata")).get(
            "metadata"
        )
    )
    indices = as_mapping(metadata.get("indices"))
    for partition in row["partitions"]:
        require(partition["name"] in indices)
        settings = as_mapping(as_mapping(indices[partition["name"]]).get("settings"))
        settings = as_mapping(settings.get("index"))
        partition["shard_count"] = int(settings["number_of_shards"])
        partition["replica_count"] = int(settings["number_of_replicas"])
    templates = (
        as_mapping(_search(backend, container, "/_template"))
        if row["templates"]
        else {}
    )
    for template in row["templates"]:
        require(template["name"] in templates)
    mappings = (
        as_mapping(_search(backend, container, "/_mapping")) if row["mappings"] else {}
    )
    for mapping in row["mappings"]:
        properties = as_mapping(
            as_mapping(as_mapping(mappings.get(mapping["name"])).get("mappings")).get(
                "properties"
            )
        )
        mapping["top_level_field_count"] = len(properties)
    native_nodes = (
        as_mapping(as_mapping(_search(backend, container, "/_nodes")).get("nodes"))
        if row["nodes"]
        else {}
    )
    for selected in row["nodes"]:
        matching = [
            as_mapping(item)
            for item in native_nodes.values()
            if as_mapping(item).get("name") == selected["name"]
        ]
        require(len(matching) == 1)
        native = matching[0]
        selected["roles"] = sorted(native.get("roles", []))
        # Every OpenSearch node coordinates requests unless configured as a pure voting node.
        selected["is_coordinator"] = "voting_only" not in selected["roles"]
    require(
        not any(
            row[field]
            for field in (
                "aliases",
                "lifecycle_policies",
                "ingest_pipelines",
                "pubsub_channels",
                "queues_streams",
                "backup_targets",
                "settings",
            )
        )
    )
    return row


def datastore_services(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read search-engine inventories or the managed Redis cache state."""

    result = []
    for service in node.runtime.datastore_services:
        engine = value(service.engine)
        if engine in {"opensearch", "elasticsearch"}:
            result.append(_search_service(backend, node.container_name, service))
        else:
            require(engine == "redis")
            result.append(_redis_service(backend, node.container_name, service))
    return result


def _redis_service(
    backend: ReadbackBackend, container: str, service: object
) -> dict[str, object]:
    """Corroborate the native Redis cache version and loaded persistence policy."""

    from aptl_techvault.redis_acl_observation import _REDIS_ACL_READBACK_SCRIPT

    # This existing native probe checks the exact loaded persistence/eviction configuration too.
    output(backend, container, ["sh", "-ec", _REDIS_ACL_READBACK_SCRIPT])
    reported = output(backend, container, ["redis-server", "--version"])
    actual = reported.split("v=", 1)[1].split()[0] if "v=" in reported else ""
    row = service.model_dump(mode="json", by_alias=True)
    require(version_matches(row["version"], actual))
    row["version"] = observed_version(row["version"], actual)
    require(row["data_model"] == "key_value" and row["protocol"] == "redis")
    require(
        not any(
            row[field]
            for field in (
                "partitions",
                "templates",
                "aliases",
                "mappings",
                "settings",
                "queues_streams",
                "pubsub_channels",
            )
        )
    )
    require(
        row["persistence"]
        and row["persistence"]["aof"] is False
        and row["persistence"]["eviction"] == "noeviction"
    )
    return deepcopy(row)
