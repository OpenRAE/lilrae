"""Value types and compact builders for backend implementation profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from raes_contracts.canonical import canonical_json_digest


@dataclass(frozen=True)
class SemanticRuntimeSelector:
    """One typed runtime record that identifies an implementation family.

    ``authorization_required`` narrows a family by whether the authored record
    binds an authorization. ``None`` ignores the axis; ``True`` matches only a
    record naming an ``authorization_ref``, and ``False`` only one that does
    not. It exists because the same product needs different mechanics depending
    on whether the scenario declared that the service authenticates, and that
    is a portable semantic fact rather than a product-keyed special case.
    """

    collection: str
    field_name: str
    value: str
    version: str = ""
    authorization_required: bool | None = None


@dataclass(frozen=True)
class BackendImplementationProfile:
    """One immutable image and the minimum mechanics needed to run it."""

    profile_id: str
    selector: SemanticRuntimeSelector | None
    source_name: str
    source_version: str
    image_ref: str
    image_mode: str = "pull"
    dockerfile_relpath: str = ""
    context_relpath: str = ""
    runtime_selections: dict[str, object] = field(default_factory=dict)
    source_aliases: tuple[tuple[str, str], ...] = ()
    provenance_refs: tuple[str, ...] = ()
    supported_os: tuple[tuple[str, str], ...] = (("linux", ""),)
    source_runtime_selector: SemanticRuntimeSelector | None = None

    @property
    def source_catalog_revision(self) -> str:
        """Fingerprint only the non-secret policy that selects a source image."""

        selector = self.source_runtime_selector or self.selector
        return canonical_json_digest({
            "id": self.profile_id,
            "source": [self.source_name, self.source_version],
            "aliases": [list(alias) for alias in self.source_aliases],
            "image_ref": self.image_ref,
            "mode": self.image_mode,
            "supported_os": [list(os) for os in self.supported_os],
            "runtime_selector": asdict(selector) if selector is not None else None,
            "provenance_refs": list(self.provenance_refs),
        })


@dataclass(frozen=True)
class BackendBaseSelection:
    """A local substrate plus any semantic provider it must bootstrap."""

    image_ref: str
    use_image_command: bool = False
    run_capabilities: tuple[str, ...] = ()
    provider_kind: str = ""
    provider_parameters: tuple[tuple[str, str], ...] = ()


def environment(*variables: dict[str, str]) -> list[dict[str, str]]:
    """Build an authored-order runtime environment profile value."""

    return list(variables)


def variable(
    name: str,
    value: str = "",
    *,
    classification: str = "plain",
    provenance: str = "compose",
) -> dict[str, str]:
    """Build one classified runtime environment variable."""

    return {
        "name": name,
        "value": value,
        "value_classification": classification,
        "provenance": provenance,
    }


def published_port(
    container_port: int, host_port: int, protocol: str = "tcp"
) -> dict[str, object]:
    """Build one loopback-only published port selection."""

    return {
        "container_port": container_port,
        "protocol": protocol,
        "host_port": host_port,
        "host_ip": "127.0.0.1",
    }


__all__ = (
    "BackendBaseSelection",
    "BackendImplementationProfile",
    "SemanticRuntimeSelector",
    "environment",
    "published_port",
    "variable",
)
