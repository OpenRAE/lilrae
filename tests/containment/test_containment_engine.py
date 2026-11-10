"""Engine pin loading and the verified engine snapshot that workers import."""

import stat
import subprocess
from pathlib import Path

import pytest

from aptl.containment.engine import (
    EngineInstallation,
    EnginePin,
    load_engine_pin,
    source_digest,
)
from aptl.core.containment import ReasonCode

REPO = Path(__file__).resolve().parents[2]
SUBMODULE = REPO / "third_party" / "raptor"


def _engine_tree(root: Path) -> Path:
    (root / "core" / "sandbox" / "__pycache__").mkdir(parents=True)
    (root / "core" / "__init__.py").write_text("")
    (root / "core" / "sandbox" / "__init__.py").write_text("ENGINE = 1\n")
    (root / "core" / "sandbox" / "__pycache__" / "x.cpython-314.pyc").write_bytes(b"cache")
    (root / "LICENSE").write_text("MIT License\n")
    (root / "json.py").write_text("raise SystemExit('shadow')\n")
    return root


def _pin(root: Path, **overrides: str) -> EnginePin:
    fields = {
        "schema_version": "lilrae.containment.engine-pin/v1",
        "repository": "https://github.com/OpenRAE/raptor",
        "upstream": "https://github.com/gadievron/raptor",
        "commit": "a" * 40,
        "source_tree": "core",
        "source_digest": source_digest(root),
        "license_file": "LICENSE",
    }
    fields.update(overrides)
    return EnginePin.model_validate(fields)


@pytest.fixture
def state_root(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    return root


def _writable(tree: Path) -> None:
    for path in [tree, *tree.rglob("*")]:
        path.chmod(path.stat().st_mode | stat.S_IWUSR)


def test_source_digest_ignores_bytecode_caches(tmp_path: Path) -> None:
    root = _engine_tree(tmp_path / "engine")
    before = source_digest(root)
    (root / "core" / "stray.pyc").write_bytes(b"cache")

    assert source_digest(root) == before
    (root / "core" / "sandbox" / "__init__.py").write_text("ENGINE = 2\n")
    assert source_digest(root) != before


def test_source_digest_refuses_a_symbolic_link(tmp_path: Path) -> None:
    root = _engine_tree(tmp_path / "engine")
    (root / "core" / "link.py").symlink_to(root / "LICENSE")

    with pytest.raises(ValueError, match="symbolic link"):
        source_digest(root)


def test_snapshot_holds_only_verified_source_read_only(tmp_path: Path, state_root: Path) -> None:
    root = _engine_tree(tmp_path / "engine")

    verification = EngineInstallation(root, _pin(root)).prepare(state_root)

    snapshot = verification.snapshot
    assert verification.reason is None and snapshot is not None
    assert snapshot.parent.parent == state_root
    assert sorted(path.name for path in snapshot.iterdir()) == ["LICENSE", "core"]
    assert not list(snapshot.rglob("__pycache__"))
    assert not list(snapshot.rglob("*.pyc"))
    assert (snapshot / "core" / "sandbox" / "__init__.py").read_text() == "ENGINE = 1\n"
    for path in [snapshot, *snapshot.rglob("*")]:
        mode = stat.S_IMODE(path.lstat().st_mode)
        assert mode & 0o277 == 0, (path, oct(mode))


def test_source_changes_after_verification_never_reach_the_snapshot(
    tmp_path: Path, state_root: Path
) -> None:
    root = _engine_tree(tmp_path / "engine")
    pin = _pin(root)
    first = EngineInstallation(root, pin).prepare(state_root)
    (root / "core" / "sandbox" / "__init__.py").write_text("ENGINE = 'attacker'\n")

    second = EngineInstallation(root, pin).prepare(state_root)

    assert second.reason is None and second.snapshot == first.snapshot
    assert second.snapshot is not None
    assert (second.snapshot / "core" / "sandbox" / "__init__.py").read_text() == "ENGINE = 1\n"


@pytest.mark.parametrize(
    "plant",
    [
        Path("core/sandbox/__pycache__/__init__.cpython-314.pyc"),
        Path("core/sandbox/extra.py"),
        Path("sitecustomize.py"),
    ],
)
def test_a_modified_snapshot_is_refused(tmp_path: Path, state_root: Path, plant: Path) -> None:
    root = _engine_tree(tmp_path / "engine")
    pin = _pin(root)
    snapshot = EngineInstallation(root, pin).prepare(state_root).snapshot
    assert snapshot is not None
    _writable(snapshot)
    (snapshot / plant).parent.mkdir(parents=True, exist_ok=True)
    (snapshot / plant).write_bytes(b"planted")

    verification = EngineInstallation(root, pin).prepare(state_root)

    assert verification.reason is ReasonCode.ENGINE_UNVERIFIED
    assert verification.snapshot is None


def test_a_different_source_tree_is_refused_without_a_snapshot(
    tmp_path: Path, state_root: Path
) -> None:
    root = _engine_tree(tmp_path / "engine")
    pin = _pin(root, source_digest="sha256:" + "0" * 64)

    verification = EngineInstallation(root, pin).prepare(state_root)

    assert verification.reason is ReasonCode.ENGINE_UNVERIFIED
    assert verification.detail is not None and source_digest(root) in verification.detail
    assert list((state_root / "engine").iterdir()) == []


@pytest.mark.parametrize("missing", ["core", "LICENSE"])
def test_a_missing_engine_part_is_unavailable(
    tmp_path: Path, state_root: Path, missing: str
) -> None:
    root = _engine_tree(tmp_path / "engine")
    pin = _pin(root)
    target = root / missing
    if target.is_dir():
        for path in sorted(target.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        target.rmdir()
    else:
        target.unlink()

    assert EngineInstallation(root, pin).prepare(state_root).reason is ReasonCode.ENGINE_UNAVAILABLE


def test_packaged_pin_names_the_fork_commit() -> None:
    pin = load_engine_pin()

    assert pin.repository == "https://github.com/OpenRAE/raptor"
    assert pin.commit == "28c996ca997c0aeaf94080c88733788a3b26c9e5"


@pytest.mark.integration
@pytest.mark.containment
def test_packaged_pin_matches_the_submodule(state_root: Path) -> None:
    assert (SUBMODULE / "core" / "sandbox" / "__init__.py").is_file(), (
        "initialize the third_party/raptor submodule"
    )
    stage = subprocess.run(
        ["git", "ls-files", "--stage", "third_party/raptor"],
        cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.split()
    pin = load_engine_pin()

    assert stage[0] == "160000"
    assert stage[1] == pin.commit
    assert EngineInstallation(SUBMODULE, pin).prepare(state_root).reason is None
