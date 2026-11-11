"""Native package, dependency-manifest and executable component identities."""

from __future__ import annotations

from aptl_techvault.readback_support import (
    ReadbackBackend,
    as_mapping,
    json_output,
    output,
    require,
    version_matches,
)


def software_components(
    backend: ReadbackBackend, node: object
) -> list[dict[str, object]]:
    """Read adapter-owned components; core retains ownership of its Wazuh agent."""

    result = []
    for component in node.runtime.software_components:
        if component.component_id == "wazuh-agent":
            continue
        row = component.model_dump(mode="json", by_alias=True)
        require(not row["hashes"] and not row["repository_refs"])
        actual = ""
        if row["manifest_path"]:
            manifest = as_mapping(
                json_output(backend, node.container_name, ["cat", row["manifest_path"]])
            )
            require(manifest.get("name") == row["name"])
            actual = str(manifest.get("version", ""))
            packages = as_mapping(manifest.get("packages"))
            root = as_mapping(packages.get(""))
            require(
                root.get("name", row["name"]) == row["name"]
                and root.get("version", actual) == actual
            )
        elif row["component_id"] == "nodejs":
            actual = output(
                backend, node.container_name, ["node", "--version"]
            ).removeprefix("v")
        elif row["component_id"] == "shuffle-frontend":
            text = output(
                backend,
                node.container_name,
                ["cat", "/usr/share/nginx/html/index.html"],
            )
            require("shuffle" in text.lower())
            actual = "unversioned"
        elif row["component_id"] == "shuffle-orborus":
            # Go's embedded module identity comes from the running executable.
            output(
                backend,
                node.container_name,
                [
                    "sh",
                    "-ec",
                    "grep -aqi 'github.com/[Ss]huffle' /proc/1/exe && grep -aqi orborus /proc/1/exe",
                ],
            )
            actual = "unversioned"
        require(version_matches(row["version"], actual))
        result.append(row)
    return result
