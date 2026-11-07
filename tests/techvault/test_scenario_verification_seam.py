"""TechVault verification knowledge stays in its adapter package (#1700)."""

from __future__ import annotations

from pathlib import Path

from aptl.validation.scenario_verification import (
    ENTRY_POINT_GROUP,
)


def test_the_techvault_adapter_is_its_own_package_in_the_one_distribution():
    """One release, and the adapter is reached only through its entry points.

    All three entry points TechVault owns are declared by this distribution and
    resolve into ``aptl_techvault``. That is the shape the seam needs: a single
    install gives an operator every extension surface the scenario owns, while
    no framework module is ever named as an extension target.
    """

    import tomllib

    root = Path(__file__).resolve().parents[2]
    core = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    entry_points = core["project"]["entry-points"]

    assert core["project"]["name"] == "lilrae"
    assert entry_points[ENTRY_POINT_GROUP] == {
        "techvault.aptl": "aptl_techvault.verification:verifier",
        "techvault-participant-study.aptl": "aptl_techvault.study:verifier",
    }
    assert entry_points["aptl.pack_backend_interactions"] == {
        "techvault.aptl": "aptl_techvault.serving:provider",
        "techvault-participant-study.aptl": "aptl_techvault.study:serving",
    }
    assert entry_points["aptl.participant_mcp_smoke_plans"] == {
        "guided-purple.techvault-attacker-target": (
            "aptl_techvault.participant_smoke:PARTICIPANT_SMOKE_OPERATIONS"
        ),
        "techvault-full.techvault": (
            "aptl_techvault.participant_smoke:FULL_TECHVAULT_SMOKE_OPERATIONS"
        ),
    }
    # A sibling of the framework in the wheel, never inside it.
    assert core["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/aptl",
        "src/aptl_techvault",
    ]
    assert (root / "src" / "aptl_techvault").is_dir()
    assert not any((root / "plugins").rglob("*.py"))


def test_core_holds_no_techvault_answer_key_behind_the_seam():
    """The point of extracting (#879): core must not know who the attacker is.

    The seam and the operations surface it hands a plugin are both
    scenario-neutral by construction. If a scenario constant -- the attacker
    node, the defensive stack's product names -- appeared in either, the plugin
    quadrant would have leaked back into core, and a second scenario would need
    core edits rather than a second installed plugin. The in-core semantic module
    that used to hold these answer keys is now deleted; the TechVault knowledge
    lives only in aptl-techvault-verifier.
    """

    import re
    from pathlib import Path

    seam_modules = (
        "scenario_verification.py",
        "scenario_verification_discovery.py",
        "_live_gate_operations.py",
    )
    answer_keys = re.compile(r"aptl-kali|wazuh|suricata|thehive|misp", re.I)
    root = Path(__file__).resolve().parents[2] / "src" / "aptl" / "validation"

    offenders = {
        name: sorted(set(answer_keys.findall((root / name).read_text())))
        for name in seam_modules
        if answer_keys.search((root / name).read_text())
    }

    assert not offenders, f"scenario knowledge leaked into the seam: {offenders}"

    # And the retired in-core scenario module is gone, not merely bypassed.
    assert not (root / "_live_gate_semantic.py").exists()


def test_core_source_contains_no_known_verification_answer_keys():
    """The wheel bundles all of ``src``, so ownership must cover the whole tree."""

    root = Path(__file__).resolve().parents[2] / "src" / "aptl"
    # Every marker below is a real string in `aptl_techvault` today. A marker
    # that exists nowhere would make this assertion vacuous, which is what
    # happened to the removed detection check's `aptl-live-gate-invalid`.
    markers = (
        "provision.node.wazuh-manager",
        "mcp.red.ssh-authentication-attack",
        "ATTACKER_NODE",
        "TECHVAULT_PACK_SET_DIGEST",
    )
    offenders = {
        str(path.relative_to(root)): [marker for marker in markers if marker in text]
        for path in root.rglob("*.py")
        if (text := path.read_text(encoding="utf-8"))
        and any(marker in text for marker in markers)
    }

    assert not offenders, f"verification answer keys remain in core: {offenders}"
