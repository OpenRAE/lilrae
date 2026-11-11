"""Version demand follows emitted Compose merge features, not service names."""

from collections.abc import Callable
from itertools import chain
from pathlib import Path
from subprocess import CompletedProcess

import yaml
from yaml.tokens import TagToken

from aptl.core.deployment._compose_stateful_constants import MIN_OVERRIDE_COMPOSE_VERSION
from aptl.core.deployment._compose_stateful_graph import compose_version
from aptl.core.lab_types import LabResult

BASE_COMPOSE_VERSION = (2, 0, 0)


def compose_feature_minimum(paths: tuple[Path, ...], *, documents: tuple[str, ...] = ()) -> tuple[int, int, int]:
    """Return the qualified floor for removal/replacement tags actually emitted."""
    for document in chain((path.read_text(encoding="utf-8") for path in paths), documents):
        for token in yaml.scan(document):
            if isinstance(token, TagToken) and token.value in {("!", "override"), ("!", "reset")}:
                return MIN_OVERRIDE_COMPOSE_VERSION
    return BASE_COMPOSE_VERSION


def compose_capability_refusal(
    run: Callable[..., CompletedProcess[str]],
    paths: tuple[Path, ...],
    *,
    documents: tuple[str, ...] = (),
) -> LabResult | None:
    """Refuse unsupported merge features before a Compose up mutation."""
    try:
        minimum = compose_feature_minimum(paths, documents=documents)
    except (OSError, ValueError, yaml.YAMLError):
        return LabResult(success=False, error="Compose feature requirements could not be read.")
    refusal: LabResult | None = None
    if minimum != BASE_COMPOSE_VERSION:
        result = run(["docker", "compose", "version", "--short"], timeout=30)
        version = compose_version(result.stdout) if result.returncode == 0 else None
        if version is None or version < minimum:
            floor = ".".join(map(str, minimum))
            refusal = LabResult(
                success=False,
                error=f"Docker Compose {floor} or later is required for the selected merge features.",
            )
    return refusal
