"""Create private, retry-stable random artifact outputs for an admitted run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from raes.random_value import RandomValueRecipe
from raes_contracts.random_value_generation import render_random_value
from raes_contracts.vocabulary import GeneratedArtifactRegenerationScope

from aptl.core.deployment.realization import DeploymentGeneratedArtifactRealization
from aptl.utils.pathsafe import (
    REASON_NOT_FOUND,
    PathContainmentError,
    create_exclusive_nofollow,
    read_contained_nofollow,
)


def random_value_directory(address: str, scope_binding: str) -> Path:
    """Keep independent artifact/run outputs in separate private directories."""

    if not scope_binding.startswith("run:") or not 4 < len(scope_binding) <= 132:
        raise ValueError("random value requires an admitted run binding")
    identity = hashlib.sha256(address.encode()).hexdigest()
    scope = hashlib.sha256(scope_binding.encode()).hexdigest()
    return Path(".aptl/realization/random-values") / identity / scope


def _recipe(artifact: DeploymentGeneratedArtifactRealization) -> RandomValueRecipe:
    if (
        artifact.regeneration_scope is not GeneratedArtifactRegenerationScope.PER_RUN
        or artifact.random_value is None
        or len(artifact.outputs) != 1
    ):
        raise ValueError("unsupported random value recipe or regeneration scope")
    return artifact.random_value


def _matches(value: bytes, recipe: RandomValueRecipe) -> bool:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return False
    prefix = recipe.format.prefix if recipe.format else ""
    suffix = recipe.format.suffix if recipe.format else ""
    length = recipe.random_segment_length()
    segment = text[len(prefix) : len(prefix) + length]
    return (
        text == prefix + segment + suffix
        and len(segment) == length
        and all(character in recipe.charset() for character in segment)
    )


def read_random_value(
    root: Path, artifact: DeploymentGeneratedArtifactRealization
) -> bytes:
    """Read a complete output only when its persisted recipe still agrees."""

    recipe = _recipe(artifact)
    directory = random_value_directory(artifact.address, artifact.scope_binding)
    stored = read_contained_nofollow(root, directory / "recipe.json")
    if stored != _recipe_bytes(recipe):
        raise ValueError("random value recipe changed within the admitted run")
    value = read_contained_nofollow(
        root, directory / "outputs" / artifact.outputs[0].path
    )
    if not _matches(value, recipe):
        raise ValueError("random value output does not match its recipe")
    return value


def realize_random_value(
    root: Path, artifact: DeploymentGeneratedArtifactRealization
) -> None:
    """Publish one draw once; concurrent retries use the same winning output."""

    recipe = _recipe(artifact)
    directory = random_value_directory(artifact.address, artifact.scope_binding)
    declaration = _recipe_bytes(recipe)
    try:
        create_exclusive_nofollow(root, directory / "recipe.json", declaration)
    except FileExistsError:
        if read_contained_nofollow(root, directory / "recipe.json") != declaration:
            raise ValueError(
                "random value recipe changed within the admitted run"
            ) from None
    output = directory / "outputs" / artifact.outputs[0].path
    try:
        read_contained_nofollow(root, output)
    except PathContainmentError as exc:
        if exc.reason != REASON_NOT_FOUND:
            raise
        try:
            create_exclusive_nofollow(
                root,
                output,
                render_random_value(recipe.model_dump(mode="json")).encode(),
            )
        except FileExistsError:
            pass
    read_random_value(root, artifact)


def _recipe_bytes(recipe: RandomValueRecipe) -> bytes:
    return json.dumps(
        recipe.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
