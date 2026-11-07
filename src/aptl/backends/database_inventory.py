"""Initial PostgreSQL and MariaDB logical inventory through native clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes.runtime_configuration import RuntimeConfiguration

from aptl.backends._runtime_concern_disclosure import _disclose
from aptl.backends.service_inventory import native_text

if TYPE_CHECKING:
    from aptl.core.deployment.backend import DeploymentBackend


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def version_matches(actual: str, declared: str) -> bool:
    """Allow a declared release family as well as an exact native version."""
    return (
        not declared
        or actual == declared
        or actual.startswith(declared + ".")
        or actual.startswith(declared + "-")
    )


def _query(
    backend, container: str, engine: str, sql: str, database: str = "postgres"
) -> str | None:
    if engine == "postgresql":
        argv = [
            "runuser",
            "-u",
            "postgres",
            "--",
            "psql",
            "-XAt",
            "--dbname",
            database,
            "--command",
            sql,
        ]
    else:
        # Use standard SQL quoting regardless of the server's default mode.
        # This setting affects only this short-lived readback connection.
        sql = "SET SESSION sql_mode = 'NO_BACKSLASH_ESCAPES'; " + sql
        # Only the environment variable name enters argv; the credential stays
        # inside the service process environment and is never logged here.
        argv = [
            "sh",
            "-ec",
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mariadb --batch --skip-column-names --user=root --execute "$1"',
            "--",
            sql,
        ]
    return native_text(backend, container, argv)


def observe_database_services(
    backend: DeploymentBackend, container: str, runtime: RuntimeConfiguration
) -> object | None:
    """Check selected listeners, logical objects, roles and database grants."""
    records = runtime.database_services
    if not records:
        return None
    sockets = backend.observe_container_listeners(container)
    for record in records:
        if record.engine not in {"postgresql", "mariadb"} or record.settings:
            return None
        if sockets is None or any(
            not any(
                protocol == "tcp"
                and port == listener.port
                and (
                    host == listener.address
                    or host == "::"
                    and listener.address == "0.0.0.0"
                )
                for protocol, host, port in sockets.sockets
            )
            for listener in record.listeners
        ):
            return None
        version = _query(
            backend,
            container,
            record.engine,
            "SHOW server_version"
            if record.engine == "postgresql"
            else "SELECT VERSION()",
        )
        if version is None or not version_matches(version.strip(), record.version):
            return None
        if not _logical_objects_match(backend, container, record) or not _roles_match(
            backend, container, record
        ):
            return None
    return _disclose(
        "runtime-database-services", [r.model_dump(mode="json") for r in records]
    )


def _logical_objects_match(backend, container, record) -> bool:
    engine = record.engine
    sql = (
        "SELECT datname FROM pg_database"
        if engine == "postgresql"
        else "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA"
    )
    text = _query(backend, container, engine, sql)
    if text is None:
        return False
    present = set(text.splitlines())
    for database in record.databases:
        if database.name not in present:
            return False
        if engine != "postgresql" and database.schemas:
            return False
        for schema in database.schemas:
            text = _query(
                backend,
                container,
                engine,
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name="
                + _literal(schema.name),
                database.name,
            )
            if text is None or schema.name not in text.splitlines():
                return False
            text = _query(
                backend,
                container,
                engine,
                "SELECT table_name FROM information_schema.tables WHERE table_schema="
                + _literal(schema.name),
                database.name,
            )
            if text is None or not {table.name for table in schema.tables}.issubset(
                text.splitlines()
            ):
                return False
    return True


def _roles_match(backend, container, record) -> bool:
    engine = record.engine
    for role in record.roles:
        if engine == "postgresql":
            sql = "SELECT rolcanlogin FROM pg_roles WHERE rolname=" + _literal(
                role.name
            )
        else:
            sql = (
                "SELECT IF(plugin IN ('mysql_no_login','auth_socket'), 'f', 't') FROM mysql.user WHERE User="
                + _literal(role.name)
            )
        text = _query(backend, container, engine, sql)
        expected = "t" if role.can_login else "f"
        if (
            text is None
            or not text.strip()
            or role.can_login is not None
            and any(row != expected for row in text.splitlines())
        ):
            return False
    if engine == "postgresql":
        return not record.grants
    roles = {role.role_id: role.name for role in record.roles}
    databases = {database.database_id: database.name for database in record.databases}
    for grant in record.grants:
        if grant.object_type != "database":
            return False
        sql = "SHOW GRANTS FOR " + _literal(roles[grant.grantee_role_ref]) + "@'%'"
        text = _query(backend, container, engine, sql)
        name = databases.get(grant.object_ref, "").replace("`", "``")
        target = f" ON `{name}`.* TO "
        expected = {p.upper() for p in grant.privileges}
        if text is None or not any(
            target in row
            and ("WITH GRANT OPTION" in row) == grant.with_grant_option
            and expected.issubset(
                {
                    p.strip()
                    for p in row.removeprefix("GRANT ")
                    .split(" ON ", 1)[0]
                    .replace("ALL PRIVILEGES", "ALL")
                    .split(",")
                }
            )
            for row in text.splitlines()
        ):
            return False
    return True
