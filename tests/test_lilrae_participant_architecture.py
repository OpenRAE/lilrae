"""Architectural ownership checks against source, with deliberate violations."""

from pathlib import Path

from tools.check_lilrae_participant_architecture import (
    COMPONENTS,
    check_component,
    check_repository,
)


ROOT = Path(__file__).resolve().parents[1]


def test_participant_components_obey_the_executable_owner_model():
    assert check_repository(ROOT) == []


def test_model_rejects_a_second_runtime_owner_in_tool_dispatch():
    path = "src/aptl/backends/participant_tools/session.py"
    original = (ROOT / path).read_text()
    mutant = (
        original + "\nfrom raes_runtime.manager import RuntimeManager as HiddenOwner\n"
    )
    assert check_component(path, mutant)
    assert check_component(path, original + "\nimport subprocess\n")
    assert check_component(path, original + "\n__import__('raes_runtime.manager')\n")


def test_model_rejects_native_transport_or_history_ownership_in_the_pure_model():
    path = "src/aptl/core/participant_tools/model.py"
    assert path in COMPONENTS
    assert check_component(path, (ROOT / path).read_text() + "\nimport socket\n")
    assert check_component(
        path,
        (ROOT / path).read_text()
        + "\nfrom raes_contracts.runtime_state import RuntimeSnapshot\n",
    )
