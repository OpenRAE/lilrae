"""Read application routes and platform identity through native interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_realization_model import NodeRealization
    from raes.runtime_platform_application import RuntimePlatformApplication

from urllib.parse import urlsplit

from aptl_techvault.readback_support import (
    ReadbackBackend,
    as_mapping,
    json_output,
    output,
    require,
    version_matches,
)

_FLASK_ROUTES = r"""
import ast, inspect, json, sys, textwrap
sys.path.insert(0, '/app')
import app
rows = []
for rule in app.app.url_map.iter_rules():
    if rule.endpoint == 'static':
        continue
    function = app.app.view_functions[rule.endpoint]
    source = textwrap.dedent(inspect.getsource(inspect.unwrap(function)))
    tree = ast.parse(source)
    guarded = any(
        isinstance(branch, ast.If)
        and any(isinstance(test, (ast.NotIn, ast.Not)) for test in ast.walk(branch.test))
        and any(isinstance(test, ast.Name) and test.id in {'session', 'api_key'} for test in ast.walk(branch.test))
        and any(isinstance(effect, ast.Return) for statement in branch.body for effect in ast.walk(statement))
        for branch in ast.walk(tree)
    )
    rows.append({
        'path': rule.rule,
        'methods': sorted(set(rule.methods) - {'OPTIONS', 'HEAD'}),
        'auth_required': guarded,
    })
print(json.dumps(rows))
"""


def _port(node: object, service: str) -> int:
    """Select the one admitted native service port."""

    ports = [int(item.port) for item in node.services if item.name == service]
    require(len(ports) == 1 and 0 < ports[0] < 65536)
    return ports[0]


def _flask_routes(
    backend: ReadbackBackend, node: NodeRealization, row: dict[str, object]
) -> None:
    """Read live Flask route methods and authentication guards."""

    observed = json_output(
        backend, node.container_name, ["python3", "-c", _FLASK_ROUTES]
    )
    require(isinstance(observed, list))
    by_path = {item["path"]: item for item in observed}
    for route in row["routes"]:
        require(route["path"] in by_path)
        native = by_path[route["path"]]
        route["methods"] = native["methods"]
        route["auth_required"] = native["auth_required"]


def _http_authentication(
    backend: ReadbackBackend,
    node: NodeRealization,
    row: dict[str, object],
    route: dict[str, object],
    port: int,
) -> bool:
    """Read unauthenticated HTTP status and recognized login redirects."""

    require(
        route["path"].startswith("/")
        and not any(char in route["path"] for char in "\r\n?#")
    )
    address = f"{row['protocol']}://127.0.0.1:{port}{route['path']}"
    # Read the unauthenticated surface; never submit an authored POST.
    response = output(
        backend,
        node.container_name,
        [
            "curl",
            "-sk",
            "--max-time",
            "20",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}\\n%{redirect_url}",
            address,
        ],
    )
    status, _, redirect = response.partition("\n")
    require(
        status.isdigit()
        and (
            200 <= int(status) < 300
            or int(status) in {301, 302, 303, 307, 308, 401, 403}
        )
    )
    if 300 <= int(status) < 400:
        require(
            any(
                part in urlsplit(redirect).path.lower().split("/")
                for part in {"login", "signin", "authenticate"}
            )
        )
    return int(status) >= 300


def _http_routes(
    backend: ReadbackBackend, node: NodeRealization, row: dict[str, object]
) -> None:
    """Read HTTP authentication and corroborate a configured reverse proxy."""

    require(row["protocol"] in {"http", "https"})
    port = _port(node, row["service"])
    for route in row["routes"]:
        route["auth_required"] = _http_authentication(backend, node, row, route, port)
        if route["upstream_target"]:
            config = output(backend, node.container_name, ["nginx", "-T"])
            upstream = route["upstream_target"]
            require(
                upstream["target_node_ref"] in config
                and f"{upstream['scheme']}://" in config
            )


def applications(backend: ReadbackBackend, node: object) -> list[dict[str, object]]:
    """Read the selected web product through its native route surface."""

    result = []
    for application in node.runtime.applications:
        row = application.model_dump(mode="json", by_alias=True)
        reader = _flask_routes if row["framework"] == "flask" else _http_routes
        reader(backend, node, row)
        result.append(row)
    return result


def _misp_platform(
    backend: ReadbackBackend,
    node: NodeRealization,
    application: RuntimePlatformApplication,
) -> tuple[dict[str, object], str]:
    """Corroborate the product identity and read its configured upstreams."""

    row = application.model_dump(mode="json", by_alias=True)

    native = as_mapping(
        json_output(
            backend,
            node.container_name,
            [
                "php",
                "-r",
                "$d=json_decode(file_get_contents('/var/www/MISP/VERSION.json'),true); echo json_encode($d);",
            ],
        )
    )
    actual_version = ".".join(str(native[key]) for key in ("major", "minor", "hotfix"))
    config = output(
        backend,
        node.container_name,
        [
            "/var/www/MISP/app/Console/cake",
            "Admin",
            "getSetting",
            "MISP.baseurl",
        ],
    )
    require(version_matches(row["version"], actual_version))
    # The owner command returns a setting name and its effective value.
    for setting in application.settings:
        require(str(setting.value) in config and setting.provenance is not None)
    dependencies = output(
        backend,
        node.container_name,
        [
            "php",
            "-r",
            "require '/var/www/MISP/app/Config/database.php'; "
            "$d=new DATABASE_CONFIG(); echo $d->default['host'];",
        ],
    )
    dependencies += "\n" + output(
        backend, node.container_name, ["printenv", "REDIS_HOST"]
    )
    return row, dependencies


def _wazuh_dashboard_platform(
    backend: ReadbackBackend,
    node: NodeRealization,
    application: RuntimePlatformApplication,
) -> tuple[dict[str, object], str]:
    """Corroborate the product identity and read its configured upstreams."""

    row = application.model_dump(mode="json", by_alias=True)

    native = as_mapping(
        json_output(
            backend,
            node.container_name,
            ["cat", "/usr/share/wazuh-dashboard/package.json"],
        )
    )
    actual_version = str(native.get("version", ""))
    require(version_matches(row["version"], actual_version))
    dependencies = output(
        backend,
        node.container_name,
        [
            "cat",
            "/usr/share/wazuh-dashboard/config/opensearch_dashboards.yml",
            "/usr/share/wazuh-dashboard/data/wazuh/config/wazuh.yml",
        ],
    )
    return row, dependencies


def _shuffle_platform(
    backend: ReadbackBackend,
    node: NodeRealization,
    application: RuntimePlatformApplication,
) -> tuple[dict[str, object], str]:
    """Corroborate the product identity and read its configured upstreams."""

    row = application.model_dump(mode="json", by_alias=True)

    require(row["version"] == "unversioned")
    native = as_mapping(
        json_output(
            backend,
            node.container_name,
            [
                "curl",
                "-fsS",
                "--max-time",
                "20",
                "http://127.0.0.1:5001/api/v1/health",
            ],
        )
    )
    require(native.get("success") is True or native.get("status") in {"ok", "healthy"})
    dependencies = output(
        backend, node.container_name, ["printenv", "SHUFFLE_OPENSEARCH_URL"]
    )
    return row, dependencies


def platform_applications(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read product identity, native settings and configured upstream bindings."""

    readers = {
        "misp": _misp_platform,
        "wazuh dashboard": _wazuh_dashboard_platform,
        "shuffle": _shuffle_platform,
    }
    result = []
    for application in node.runtime.platform_applications:
        reader = readers.get(application.product.lower())
        require(reader is not None)
        row, dependencies = reader(backend, node, application)
        for binding in row["upstream_bindings"]:
            target = binding["target_node_ref"]
            require(target in dependencies or target.replace("-", ".") in dependencies)
        require(
            not any(
                row[field]
                for field in (
                    "organizations",
                    "tenants",
                    "content_objects",
                    "markings",
                    "connectors",
                    "secrets",
                    "cloud_limits",
                )
            )
        )
        result.append(row)
    return result


_MISP_AUTHORIZATION = r"""
require '/var/www/MISP/app/Config/database.php';
$c = (new DATABASE_CONFIG())->default;
$db = new PDO('mysql:host='.$c['host'].';dbname='.$c['database'],
    $c['login'], $c['password'], [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$users=$db->query('SELECT u.id, u.email, r.perm_site_admin, r.perm_admin, r.perm_add, '
    . ' r.perm_modify, r.perm_publish, r.perm_auth '
    . 'FROM users u JOIN roles r ON u.role_id=r.id')->fetchAll(PDO::FETCH_ASSOC);
$keys=$db->query('SELECT user_id, comment, read_only FROM auth_keys '
    . 'WHERE expiration=0 OR expiration>UNIX_TIMESTAMP()')->fetchAll(PDO::FETCH_ASSOC);
echo json_encode(['users'=>$users,'keys'=>$keys]);
"""


def _misp_principal(
    principal: dict[str, object],
    users: list[dict[str, object]],
    keys: list[dict[str, object]],
) -> tuple[dict[str, object], bool]:
    """Resolve a native MISP user or live read-only API key to its owner."""

    if principal["kind"] == "user":
        matching = [user for user in users if user.get("email") == principal["name"]]
    else:
        require(principal["kind"] == "api_key")
        # The pack's account realization uses the account username as
        # the native key comment; its authorization id is a logical id.
        comment = principal["name"] or {
            "misp-suricata-sync-api-key": "techvault-suricata-sync",
        }.get(principal["principal_id"])
        require(comment)
        matching_keys = [key for key in keys if key.get("comment") == comment]
        require(len(matching_keys) == 1 and int(matching_keys[0]["read_only"]) == 1)
        matching = [
            user
            for user in users
            if str(user.get("id")) == str(matching_keys[0]["user_id"])
        ]
    require(len(matching) == 1)
    return matching[0], principal["kind"] == "api_key"


def _misp_grant_principal(
    row: dict[str, object],
    grant: dict[str, object],
    observed_principals: dict[str, tuple[dict[str, object], bool]],
) -> tuple[dict[str, object], bool]:
    """Bind one logical authorization role to its observed native principal."""

    mappings = [
        item for item in row["role_mappings"] if item["role_ref"] == grant["role_ref"]
    ]
    require(
        len(mappings) == 1
        and len(mappings[0]["users"]) == 1
        and not mappings[0]["backend_roles"]
        and not mappings[0]["hosts"]
    )
    return observed_principals[mappings[0]["users"][0]]


def _misp_grant(
    principal: dict[str, object], read_only_key: bool, grant: dict[str, object]
) -> None:
    """Check effective MISP permissions, including a key restriction on its owner."""

    require(grant["effect"] == "allow" and grant["resource_kind"] == "app_resource")
    if grant["actions"] == ["manage"]:
        require(
            not read_only_key
            and int(principal["perm_site_admin"]) == 1
            and grant["resource_patterns"] == ["*"]
        )
    else:
        require(
            grant["actions"] == ["read"]
            and set(grant["resource_patterns"]) == {"events/*", "attributes/*"}
        )
        require(
            int(principal["perm_auth"]) == 1
            and (
                read_only_key
                or not any(
                    int(principal[key])
                    for key in (
                        "perm_site_admin",
                        "perm_admin",
                        "perm_add",
                        "perm_modify",
                        "perm_publish",
                    )
                )
            )
        )


def _misp_authorization(
    backend: ReadbackBackend, node: NodeRealization, row: dict[str, object]
) -> None:
    """Read only native authorization metadata, keeping credentials inside the guest."""

    require(
        row["resource_vocabulary"] == "app_resource" and row["auth_enabled"] is True
    )
    native = as_mapping(
        json_output(backend, node.container_name, ["php", "-r", _MISP_AUTHORIZATION])
    )
    principals = {
        item["principal_id"]: _misp_principal(
            item, native.get("users", []), native.get("keys", [])
        )
        for item in row["principals"]
    }
    for grant in row["permission_grants"]:
        principal, read_only_key = _misp_grant_principal(row, grant, principals)
        _misp_grant(principal, read_only_key, grant)
    require(not row["tenants"])


def app_authorizations(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read MISP roles and mappings or the existing native Redis ACL probe."""

    from aptl_techvault.redis_acl_observation import observe_redis_app_authorizations

    result = []
    for authorization in node.runtime.app_authorizations:
        row = authorization.model_dump(mode="json", by_alias=True)
        if row["resource_vocabulary"] == "redis_acl":
            observed = observe_redis_app_authorizations(
                backend, node.container_name, node.runtime
            )
            require(observed is not None)
            result.extend(observed)
        else:
            _misp_authorization(backend, node, row)
            result.append(row)
    return result
