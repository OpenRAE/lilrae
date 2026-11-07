"""Initial application route and platform configuration readback."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aptl.backends.raes_realization_model import NodeRealization
    from aptl.core.deployment.backend import DeploymentBackend

import json
import re

from aptl.backends._runtime_concern_disclosure import _disclose
from aptl.backends.database_inventory import version_matches
from aptl.backends.service_inventory import (
    container_environment,
    native_text,
)
from aptl.core.deployment._application_account_requests import (
    CurlStep,
    curl_config,
    status_codes,
)
from aptl.core.deployment._compose_application_accounts import product_ingress


def _status(backend, container, url, path):
    result = backend.container_exec_with_input(
        container,
        ["curl", "--config", "-"],
        curl_config(url, [CurlStep("GET", path)]),
        timeout=35,
    )
    codes = status_codes(result.stdout) if result.returncode == 0 else ()
    return codes[0] if len(codes) == 1 else 0


_FLASK_ROUTES = r"""
import importlib,json,os,sys
parameters=json.load(sys.stdin)
os.chdir(parameters['workdir']);sys.path.insert(0,os.getcwd())
module,attribute=parameters['module'].split(':',1)
app=getattr(importlib.import_module(module),attribute)
result=[]
with app.test_client() as client:
 for rule in app.url_map.iter_rules():
  path=rule.rule
  methods=sorted(set(rule.methods)-{'OPTIONS','HEAD'})
  kwargs={name: 1 if converter.__class__.__name__=='IntegerConverter' else 'probe' for name,converter in rule._converters.items()}
  probe=rule.build(kwargs)[1]
  response=client.get(probe) if 'GET' in methods else None
  required=None
  if response is not None:
   required=response.status_code in (401,403) or response.status_code in (301,302,303,307,308) and '/login' in response.headers.get('Location','')
  result.append({'path':path,'methods':methods,'auth_required':required})
print(json.dumps(result))
"""


def observe_applications(
    backend: DeploymentBackend, node: NodeRealization, nodes: Sequence[NodeRealization]
) -> object | None:
    records = node.runtime.applications
    if not records:
        return None
    reader = (
        _flask_matches
        if node.backend_provider_kind == "python-flask-application"
        else _product_routes_match
    )
    if not reader(backend, node, nodes, records):
        return None
    return _disclose(
        "runtime-applications", [r.model_dump(mode="json") for r in records]
    )


def _flask_matches(backend, node, nodes, records):
    parameters = dict(node.backend_provider_parameters)
    result = backend.container_exec_with_input(
        node.container_name,
        ["/usr/bin/python3", "-c", _FLASK_ROUTES],
        json.dumps(parameters),
        timeout=30,
    )
    actual = json.loads(result.stdout) if result.returncode == 0 else []
    for app in records:
        if app.framework not in {"", "flask"}:
            return False
        for route in app.routes:
            found = next((r for r in actual if r["path"] == route.path), None)
            if found is None or not set(route.methods).issubset(found["methods"]):
                return False
            if (
                route.auth_required is not None
                and found["auth_required"] != route.auth_required
            ):
                return False
    return True


def _product_routes_match(backend, node, nodes, records):
    image = node.image.source_name if node.image else ""
    providers = {
        "wazuh/wazuh-dashboard": "wazuh-api",
        "ghcr.io/misp/misp-docker/misp-core": "misp",
        "ghcr.io/shuffle/shuffle-backend": "shuffle",
        "ghcr.io/shuffle/shuffle-frontend": "shuffle",
    }
    provider = providers.get(image)
    if provider is None:
        return False
    ingress = product_ingress(provider, node, nodes)
    if ingress is None:
        # The dashboard/frontend serve their own declared listener.
        app = records[0]
        port = next((s.port for s in node.services if s.name == app.service), None)
        if port is None:
            return False
        container, url = node.container_name, f"{app.protocol.value}://localhost:{port}"
    else:
        container, url = ingress.container, ingress.base_url
    for app in records:
        for route in app.routes:
            probe = (
                "/api/v1/workflows"
                if image.startswith("ghcr.io/shuffle/")
                else route.path
            )
            status = _status(backend, container, url, probe)
            if route.auth_required is True and status not in {
                301,
                302,
                303,
                307,
                308,
                401,
                403,
            }:
                return False
            if status == 0 or status >= 500:
                return False
            if route.upstream_target is not None:
                config = native_text(backend, node.container_name, ["nginx", "-T"])
                target = route.upstream_target
                upstream = next(
                    (n for n in nodes if n.name == target.target_node_ref), None
                )
                port = (
                    next(
                        (
                            s.port
                            for s in upstream.services
                            if s.name == target.target_service
                        ),
                        None,
                    )
                    if upstream
                    else None
                )
                if (
                    config is None
                    or port is None
                    or f"{target.target_node_ref}:{port}" not in config
                ):
                    return False
    return True


def observe_platform_applications(
    backend: DeploymentBackend, node: NodeRealization, nodes: Sequence[NodeRealization]
) -> object | None:
    records = node.runtime.platform_applications
    if not records:
        return None
    info = backend.container_inspect(node.container_name)
    env = container_environment(info)
    image = node.image.source_name if node.image else ""
    for app in records:
        if image == "ghcr.io/misp/misp-docker/misp-core" and app.product == "MISP":
            payload = native_text(
                backend,
                node.container_name,
                ["php", "-r", "echo file_get_contents('/var/www/MISP/VERSION.json');"],
            )
            version = json.loads(payload) if payload else {}
            if not version_matches(
                ".".join(str(version.get(k, "")) for k in ("major", "minor", "hotfix")),
                app.version,
            ):
                return None
            allowed = {"threat_intelligence_management", "intelligence_exchange"}
            for setting in app.settings:
                if (
                    setting.setting_id != "misp-canonical-url"
                    or env.get("BASE_URL") != setting.value
                ):
                    return None
            bindings = {env.get("MYSQL_HOST"), env.get("REDIS_HOST")}
        elif image == "wazuh/wazuh-dashboard" and app.product == "Wazuh Dashboard":
            data = backend.container_file_read(
                node.container_name,
                "/usr/share/wazuh-dashboard/package.json",
                max_bytes=1048576,
            )
            package = json.loads(data) if data else {}
            if not version_matches(package.get("version", ""), app.version):
                return None
            allowed = {"analytics_presentation"}
            # Read the effective backend URLs, rather than the profile's inputs.
            data = backend.container_file_read(
                node.container_name,
                "/usr/share/wazuh-dashboard/config/opensearch_dashboards.yml",
                max_bytes=1048576,
            )
            wazuh = backend.container_file_read(
                node.container_name,
                "/usr/share/wazuh-dashboard/data/wazuh/config/wazuh.yml",
                max_bytes=1048576,
            )
            text = (data or b"").decode() + (wazuh or b"").decode()
            bindings = {
                b.target_node_ref
                for b in app.upstream_bindings
                if b.target_node_ref in text
            }
        elif (
            image == "ghcr.io/shuffle/shuffle-backend"
            and app.product == "Shuffle"
            and app.version == "unversioned"
        ):
            allowed = {"workflow_automation"}
            bindings = {
                re.sub(
                    r"^https?://([^:/]+).*",
                    r"\1",
                    env.get("SHUFFLE_OPENSEARCH_URL", ""),
                )
            }
        else:
            return None
        if any(c.kind not in allowed for c in app.capabilities) or any(
            b.target_node_ref not in bindings for b in app.upstream_bindings
        ):
            return None
    return _disclose(
        "runtime-platform-applications", [r.model_dump(mode="json") for r in records]
    )
