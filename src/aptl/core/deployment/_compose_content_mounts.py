"""Deliver declared content to image (Compose) nodes as bind mounts (#875).

Content for a base-container-materialized node is placed into its container by the generic
materializer. An image node is a Compose service with a fixed image whose config
files are read from fixed paths, so its content is delivered the way the retiring
``docker-compose.yml`` delivered it: a read-only bind mount of the resolved file
at its declared destination.

The bytes are resolved from the pristine pack (``scenario_root``, byte-bound by
digest) but written under ``realization_root`` (the writable engine checkout),
never back into the pack, so the pack's digest-validated inventory stays intact.
The resulting per-service mounts are emitted as a Compose override.
"""

from __future__ import annotations

import io
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath

from aptl.core.deployment.realization import (
    DeploymentContentRealization,
    DeploymentRealizationSpec,
)

CONTENT_MOUNT_ROOT_RELPATH = Path(".aptl") / "realization" / "content"
#: Where owner-declared content is staged inside an image node (#1273). A bind
#: mount keeps the host owner, so a file the node's SDL inventory declares with
#: an owner is mounted here instead and installed at its destination with the
#: declared owner and mode before the image's own entrypoint runs.
OWNED_CONTENT_ROOT = PurePosixPath("/run/aptl/owned-content")
OWNED_CONTENT_MANIFEST = OWNED_CONTENT_ROOT / "manifest"
#: The installer an implementation profile prefixes to its image entrypoint to
#: support owner-declared content. Only paths, modes and account names, all
#: validated when the manifest is written, enter it; content bytes never do.
OWNED_CONTENT_INSTALLER = (
    f'if [ -f "{OWNED_CONTENT_MANIFEST}" ]; then '
    "while read -r mode owner group name dest; do "
    'install -D -m "$mode" -o "$owner" -g "$group" '
    f'"{OWNED_CONTENT_ROOT}/$name" "$dest"; '
    f'done < "{OWNED_CONTENT_MANIFEST}"; fi'
)
#: The installer for an image whose entrypoint runs as its own non-root user
#: (#1422). Without root it cannot give a file another owner, so it installs
#: each file as the image user and refuses a declared owner or group that is
#: not the current one. Its staged copies are readable by that user.
OWNED_CONTENT_IMAGE_USER_INSTALLER = (
    f'if [ -f "{OWNED_CONTENT_MANIFEST}" ]; then '
    'image_user="$(id -un)"; image_group="$(id -gn)"; '
    "while read -r mode owner group name dest; do "
    'if [ "$owner" != "$image_user" ] || [ "$group" != "$image_group" ]; then '
    'echo "owned content $dest needs $owner:$group, not '
    '$image_user:$image_group" >&2; exit 1; fi; '
    'install -D -m "$mode" '
    f'"{OWNED_CONTENT_ROOT}/$name" "$dest"; '
    f'done < "{OWNED_CONTENT_MANIFEST}"; fi'
)
_OWNED_CONTENT_INSTALLERS = (
    OWNED_CONTENT_INSTALLER,
    OWNED_CONTENT_IMAGE_USER_INSTALLER,
)
#: Host modes for a copy staged for the image-user installer. The image user
#: reads the file across its bind mount; the owner-only directory keeps it from
#: other host users (the ``credentials.py`` pattern).
_IMAGE_USER_STAGING_DIR_MODE = 0o700
_IMAGE_USER_STAGED_FILE_MODE = 0o644
_ACCOUNT_NAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_MODE_RE = re.compile(r"^0?[0-7]{3}$")
_DESTINATION_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXECUTABLE_SCRIPT_MEDIA_TYPES = frozenset({"text/x-python", "text/x-shellscript"})


def image_node_content_override(
    realization: DeploymentRealizationSpec,
    scenario_root: Path,
    realization_root: Path,
) -> dict[str, object]:
    """Return a Compose override mounting each image node's declared content.

    Only content whose target is an image node (a Compose service) is handled;
    base-container-materialized targets are delivered by the generic materializer elsewhere.
    """

    # Bind sources must be absolute: Docker resolves a relative source against
    # the Compose project directory (the staged pack), where the generated file
    # does not exist, and would create the target as an empty directory (#875).
    realization_root = realization_root.resolve()
    imaged = {image.address for image in realization.images}
    node_by_address = {
        node.address: node for node in realization.nodes if node.service_name
    }
    services: dict[str, dict[str, object]] = {}
    manifests: dict[str, list[str]] = {}
    for item in realization.content:
        node = node_by_address.get(item.target_address)
        if item.target_address not in imaged or node is None:
            continue
        source = _place_content(item, scenario_root, realization_root)
        if source is None:
            continue
        volumes = services.setdefault(node.service_name, {}).setdefault("volumes", [])
        lines = manifests.setdefault(node.service_name, [])
        owned = _owned_content_mount(node, item, source, realization_root, lines)
        if owned is None:
            volumes.extend(_content_mounts(item, source))
        else:
            volumes.append(owned)
    for service_name, lines in manifests.items():
        if lines:
            services[service_name]["volumes"].append(
                _write_owned_manifest(realization_root, service_name, lines)
            )
    return {"services": services} if services else {"services": {}}


def _bind(source: Path, target: PurePosixPath) -> dict[str, object]:
    """Return one read-only bind mount."""

    return {
        "type": "bind",
        "source": str(source),
        "target": str(target),
        "read_only": True,
    }


def _owned_content_mount(
    node: object,
    item: DeploymentContentRealization,
    source: Path,
    realization_root: Path,
    manifest_lines: list[str],
) -> dict[str, object] | None:
    """Stage owner-declared content for the node's installer, or return ``None``.

    The returned mount places the file under :data:`OWNED_CONTENT_ROOT`, and
    *manifest_lines* gains its install line. Other content returns ``None``.
    """

    installer = _owned_content_installer(node)
    owned = _declared_ownership(node, item, source) if installer else None
    if owned is None:
        return None
    name = f"{len(manifest_lines):03d}"
    if installer == OWNED_CONTENT_IMAGE_USER_INSTALLER:
        directory = _owned_content_dir(realization_root, str(node.service_name))
        source = _stage_for_image_user(source, directory, name)
    manifest_lines.append(f"{owned} {name} /{item.dest_relpath.lstrip('/')}")
    return _bind(source, OWNED_CONTENT_ROOT / name)


def _write_owned_manifest(
    realization_root: Path, service_name: str, lines: list[str]
) -> dict[str, object]:
    """Write one service's install manifest and return its mount."""

    path = _owned_content_dir(realization_root, service_name) / "manifest"
    _remove_previous_output(path)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    path.chmod(0o644)
    return _bind(path, OWNED_CONTENT_MANIFEST)


def _owned_content_installer(node: object) -> str | None:
    """Return the owned-content installer the node's entrypoint runs, if any."""

    container = getattr(getattr(node, "runtime", None), "container", None)
    entrypoint = " ".join(getattr(container, "entrypoint", None) or ())
    return next(
        (
            installer
            for installer in _OWNED_CONTENT_INSTALLERS
            if installer in entrypoint
        ),
        None,
    )


def _owned_content_dir(realization_root: Path, service_name: str) -> Path:
    """Return the service's owner-only directory for its manifest and copies."""

    directory = _content_output_root(realization_root, f"{service_name}-owned-content")
    directory.chmod(_IMAGE_USER_STAGING_DIR_MODE)
    return directory


def _stage_for_image_user(source: Path, directory: Path, name: str) -> Path:
    """Copy one owner-declared file where the non-root image user can read it."""

    staged = directory / name
    _remove_previous_output(staged)
    shutil.copyfile(source, staged)
    staged.chmod(_IMAGE_USER_STAGED_FILE_MODE)
    return staged


def _declared_ownership(
    node: object, item: DeploymentContentRealization, source: Path
) -> str | None:
    """Return ``"mode owner group"`` for content the node must own, or ``None``.

    It applies only when the node's SDL inventory declares an owner for the
    file at this destination. The caller checks that the node's selected
    entrypoint runs an owned-content installer. Any other content keeps its
    bind mount.
    """

    runtime = getattr(node, "runtime", None)
    if not source.is_file():
        return None
    destination = "/" + item.dest_relpath.lstrip("/")
    entry = next(
        (
            entry
            for entry in getattr(runtime, "filesystem_inventory", None) or ()
            if str(getattr(entry, "path", "")) == destination
        ),
        None,
    )
    return _ownership_spec(entry, destination) if entry is not None else None


def _ownership_spec(entry: object, destination: str) -> str | None:
    """Validate the selected inventory entry's owner, group and mode."""

    owner = str(getattr(entry, "owner_user", "") or "")
    if not owner:
        return None
    group = str(getattr(entry, "owner_group", "") or owner)
    mode = str(getattr(entry, "mode", "") or "")
    valid = (
        _ACCOUNT_NAME_RE.fullmatch(owner)
        and _ACCOUNT_NAME_RE.fullmatch(group)
        and _MODE_RE.fullmatch(mode)
        and _DESTINATION_RE.fullmatch(destination)
    )
    if not valid:
        raise ValueError(f"owner-declared content at {destination} is invalid")
    return f"{mode} {owner} {group}"


def _content_mounts(
    item: DeploymentContentRealization,
    source: Path,
) -> list[dict[str, object]]:
    """Return mounts that place content without hiding image-owned siblings.

    A pack directory is a set of declared files to merge at its destination.
    Binding the extracted root over an image-owned directory hides every file
    the image already carries there. This is especially damaging for appliance
    extension directories whose entrypoint updates built-in files before it
    applies the mounted configuration. Mount each regular artifact member at
    its relative destination instead. Empty pack directories retain the prior
    whole-directory behavior because they have no members to merge.
    """

    target_root = PurePosixPath("/") / item.dest_relpath.lstrip("/")
    if item.source_kind == "pack-directory" and source.is_dir():
        entries = sorted(
            source.rglob("*"), key=lambda path: path.relative_to(source).as_posix()
        )
        if any(entry.is_symlink() for entry in entries):
            raise ValueError("pack directory content contains a symlink")
        files = [entry for entry in entries if entry.is_file()]
        if files:
            return [
                {
                    "type": "bind",
                    "source": str(path),
                    "target": str(target_root / path.relative_to(source).as_posix()),
                    "read_only": True,
                }
                for path in files
            ]
    return [
        {
            "type": "bind",
            "source": str(source),
            "target": str(target_root),
            "read_only": True,
        }
    ]


def _place_content(
    item: DeploymentContentRealization,
    scenario_root: Path,
    realization_root: Path,
) -> Path | None:
    """Resolve one content item's bytes and write them under realization_root.

    Returns the host path to bind, or ``None`` for a source kind that carries no
    bytes to mount.
    """

    slug = item.address.rsplit(".", 1)[-1]
    basename = PurePosixPath(item.dest_relpath).name or slug

    placed: Path | None = None
    if item.source_kind == "inline-text" and item.inline_text is not None:
        root = _content_output_root(realization_root, slug)
        placed = root / basename
        _remove_previous_output(placed)
        placed.write_text(item.inline_text, encoding="utf-8")
        placed.chmod(0o600 if item.sensitive else 0o644)
    elif item.source_kind in ("pack-file", "pack-directory") and item.artifact_id:
        root = _content_output_root(realization_root, slug)
        placed = _place_pack_content(item, scenario_root, root, basename)
    elif (
        item.source_kind in ("project-file", "project-directory")
        and item.source_relpath
    ):
        placed = _project_content_source(item, scenario_root)
    return placed


def _content_output_root(realization_root: Path, slug: str) -> Path:
    """Create one output root without following project-state symlinks."""

    realization_root.mkdir(parents=True, exist_ok=True)
    current = realization_root
    for part in (*CONTENT_MOUNT_ROOT_RELPATH.parts, slug):
        current = current / part
        if current.is_symlink():
            raise ValueError("content realization output path contains a symlink")
        current.mkdir(exist_ok=True)
        if not current.is_dir():
            raise ValueError("content realization output path is not a directory")
    return current


def _remove_previous_output(path: Path) -> None:
    """Remove generated output that a prior container may have made read-only."""

    if path.is_symlink():
        raise ValueError("content realization output path contains a symlink")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _project_content_source(
    item: DeploymentContentRealization,
    scenario_root: Path,
) -> Path | None:
    """Return a project source path when it exists with its declared kind.

    A declared ``project-file`` that resolves to a directory (or the reverse) is
    not the content the scenario declared, so nothing is bound for it.
    """

    source = (scenario_root / item.source_relpath).resolve()
    if item.source_kind == "project-file":
        return source if source.is_file() else None
    return source if source.is_dir() else None


def _place_pack_content(
    item: DeploymentContentRealization,
    scenario_root: Path,
    root: Path,
    basename: str,
) -> Path | None:
    """Resolve and verify env-pack content, writing it under realization_root."""

    from raes_env_packs import resolve_pack_artifact

    resolved = resolve_pack_artifact(str(scenario_root), item.artifact_id)
    digest = getattr(resolved.identity, "digest", None)
    if item.artifact_digest and _SHA256_RE.fullmatch(item.artifact_digest or ""):
        if digest != item.artifact_digest:
            raise ValueError(
                f"pack content digest mismatch for {item.artifact_id}: "
                f"{digest} != {item.artifact_digest}"
            )
    if item.source_kind == "pack-directory":
        return _place_pack_directory(root, resolved.data, sensitive=item.sensitive)
    return _place_pack_file(
        root,
        basename,
        resolved.data,
        executable=item.media_type in _EXECUTABLE_SCRIPT_MEDIA_TYPES,
        sensitive=item.sensitive,
    )


def _place_pack_directory(root: Path, data: bytes, *, sensitive: bool) -> Path:
    """Extract one verified pack tree and apply closed deterministic modes."""

    tree = root / "tree"
    _remove_previous_output(tree)
    tree.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        archive.extractall(tree, filter="data")
    for path in (tree, *sorted(tree.rglob("*"))):
        if path.is_symlink():
            raise ValueError("pack directory content contains a symlink")
        if path.is_dir():
            path.chmod(0o700 if sensitive else 0o755)
        elif path.is_file():
            executable = bool(path.stat().st_mode & 0o111)
            path.chmod(_pack_content_mode(sensitive, executable=executable))
    return tree


def _place_pack_file(
    root: Path,
    basename: str,
    data: bytes,
    *,
    executable: bool,
    sensitive: bool,
) -> Path:
    """Write one verified pack file with its declared access mode."""

    destination = root / basename
    _remove_previous_output(destination)
    destination.write_bytes(data)
    # The exact bytes retain their digest identity when a declared script is
    # executable. Set the mode explicitly: guest first boot uses umask 077,
    # while non-root image users must still read non-sensitive bind content.
    destination.chmod(_pack_content_mode(sensitive, executable=executable))
    return destination


def _pack_content_mode(sensitive: bool, *, executable: bool) -> int:
    """Return the exact regular-file mode for one realized pack artifact."""

    if sensitive:
        return 0o700 if executable else 0o600
    return 0o755 if executable else 0o644
