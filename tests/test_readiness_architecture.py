"""The completed readiness boundaries obey the repository's actual layer map."""

from pathlib import Path

from tests.test_check_architecture import check as check


def test_readiness_composition_and_qualification_import_closures(check):
    root = Path(__file__).resolve().parents[1]
    settings = check.load_settings(root)
    graph = check.build_graph(root, settings.roots)
    slots = check.assign_slots(graph, settings)
    boundaries = (
        "aptl.backends.installed_readiness",
        "aptl.core.placement_readiness",
    )
    assert set(boundaries) <= set(settings.enrolled)
    assert slots[boundaries[0]].layer == "entry"
    assert slots[boundaries[1]].layer == "application"
    assert (
        list(check.layer_findings(graph, slots, boundaries, settings.extension_api))
        == []
    )
