"""Regression contract for issue #1179: pending lab cleanup survives upgrades."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aptl.core.lab_types import LabResult

BASELINE = Path(".aptl/realization/wazuh-agent-identity/baseline.json")
LEGACY_DIR = Path(".aptl/lifecycle/startup-reset-v1")
LEGACY_DONE_DIR = Path(".aptl/lifecycle/startup-reset-completed-v1")
ACTION_DIR = Path(".aptl/lifecycle/cleanup-actions-v1")
ACTION_DONE_DIR = Path(".aptl/lifecycle/cleanup-actions-completed-v1")
OTHER_DIGEST = "sha256:" + "b" * 64


def _canonical(payload: dict[str, str]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )


def _write_record(root: Path, directory: Path, encoded: bytes) -> Path:
    path = root / directory / f"{hashlib.sha256(encoded).hexdigest()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return path


def _legacy(
    root: Path,
    *,
    pack_id: str = "otherpack",
    digest: str = OTHER_DIGEST,
    distribution: str = "otherpack-adapter",
    version: str = "1.0.0",
    pack_version: str = "1.0.0",
    admission: str = "a" * 64,
) -> Path:
    return _write_record(
        root,
        LEGACY_DIR,
        _canonical(
            {
                "schema_version": "aptl-startup-reset-authority/v1",
                "admission_id": admission,
                "distribution": distribution,
                "distribution_version": version,
                "entry_point": pack_id,
                "pack_id": pack_id,
                "pack_set_digest": digest,
                "pack_version": pack_version,
            }
        ),
    )


def _baseline(root: Path) -> Path:
    path = root / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"db":"001"}\n', encoding="utf-8")
    return path


def _no_installed_providers(monkeypatch) -> None:
    from aptl.backends import scenario_startup

    monkeypatch.setattr(scenario_startup, "_entry_points", lambda: [])


def _provider(**extra: object) -> SimpleNamespace:
    return SimpleNamespace(
        extension_api_version="1",
        supported_pack_id="otherpack",
        supported_pack_versions=("1.0.0",),
        supported_pack_set_digests=(OTHER_DIGEST,),
        resolve=lambda _bundle: None,
        **extra,
    )


def _install(monkeypatch, *providers: tuple[str, object]) -> None:
    from aptl.backends import scenario_startup

    entries = [
        SimpleNamespace(
            name="otherpack",
            dist=SimpleNamespace(name="otherpack-adapter", version=version),
            load=lambda provider=provider: provider,
        )
        for version, provider in providers
    ]
    monkeypatch.setattr(scenario_startup, "_entry_points", lambda: entries)


def test_pack_reset_without_compatible_installed_handler_stays_pending(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    calls: list[object] = []
    # The upgraded adapter supports the admitted release but never declared
    # that it can finish cleanup recorded by another distribution version.
    _install(monkeypatch, ("2.0.0", _provider(reset=calls.append)))
    receipt = _legacy(
        tmp_path,
        pack_id="otherpack",
        digest=OTHER_DIGEST,
        distribution="otherpack-adapter",
        version="1.0.0",
    )

    report = run_pending_cleanup(tmp_path, object())

    assert calls == []
    assert len(report.pending) == 1
    failure = report.pending[0]
    assert failure.action == "pack.reset"
    assert failure.subject == "otherpack 1.0.0"
    assert failure.reason == "provider-reset-authority-unavailable"
    assert failure.record == f"startup-reset-v1/{receipt.name[:12]}"
    assert not (tmp_path / LEGACY_DONE_DIR).exists()


def test_declared_pack_handler_finishes_cleanup_after_upgrade(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    calls: list[object] = []
    handler = _provider(reset=calls.append, supported_reset_action_versions=("1",))
    _install(monkeypatch, ("2.0.0", handler))
    _legacy(
        tmp_path,
        pack_id="otherpack",
        digest=OTHER_DIGEST,
        distribution="otherpack-adapter",
        version="1.0.0",
    )
    backend = object()

    report = run_pending_cleanup(tmp_path, backend)

    assert (report.completed, report.pending) == (1, ())
    assert [context.backend for context in calls] == [backend]


def test_pack_handler_for_another_digest_is_never_dispatched(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    calls: list[object] = []
    handler = _provider(reset=calls.append, supported_reset_action_versions=("1",))
    _install(monkeypatch, ("2.0.0", handler))
    _legacy(
        tmp_path,
        pack_id="otherpack",
        digest="sha256:" + "c" * 64,
        distribution="otherpack-adapter",
        version="1.0.0",
    )

    report = run_pending_cleanup(tmp_path, object())

    assert calls == []
    assert [item.reason for item in report.pending] == [
        "provider-reset-authority-unavailable"
    ]


def test_ambiguous_pack_handlers_stay_pending(tmp_path: Path, monkeypatch) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    calls: list[object] = []
    declared = {"reset": calls.append, "supported_reset_action_versions": ("1",)}
    _install(
        monkeypatch, ("2.0.0", _provider(**declared)), ("3.0.0", _provider(**declared))
    )
    _legacy(
        tmp_path,
        pack_id="otherpack",
        digest=OTHER_DIGEST,
        distribution="otherpack-adapter",
        version="1.0.0",
    )

    report = run_pending_cleanup(tmp_path, object())

    assert calls == []
    assert [item.reason for item in report.pending] == [
        "provider-reset-authority-ambiguous"
    ]


def test_failing_pack_handler_stays_pending_then_completes_on_retry(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup

    attempts: list[object] = []

    def reset(context: object) -> None:
        attempts.append(context)
        if len(attempts) == 1:
            raise RuntimeError("transient")

    _install(monkeypatch, ("1.0.0", _provider(reset=reset)))
    _legacy(
        tmp_path,
        pack_id="otherpack",
        digest=OTHER_DIGEST,
        distribution="otherpack-adapter",
        version="1.0.0",
    )

    first = run_pending_cleanup(tmp_path, object())
    second = run_pending_cleanup(tmp_path, object())

    assert [item.reason for item in first.pending] == ["provider-hook-failed"]
    assert (second.completed, second.pending) == (1, ())
    assert len(attempts) == 2


def test_admitted_cleanup_actions_round_trip(tmp_path: Path, monkeypatch) -> None:
    from aptl.core.lifecycle_cleanup import run_pending_cleanup
    from aptl.core.startup_reset_state import (
        ACTION_CLEAR_WAZUH_ENROLLMENT_BASELINE,
        ACTION_PACK_RESET,
        CleanupAction,
        persist_cleanup_action,
    )

    calls: list[object] = []
    _install(monkeypatch, ("1.0.0", _provider(reset=calls.append)))
    provenance = {
        "admission_id": "f" * 64,
        "pack_id": "otherpack",
        "pack_version": "1.0.0",
        "pack_set_digest": OTHER_DIGEST,
        "distribution": "otherpack-adapter",
        "distribution_version": "1.0.0",
        "entry_point": "otherpack",
    }
    for action in (ACTION_CLEAR_WAZUH_ENROLLMENT_BASELINE, ACTION_PACK_RESET):
        persist_cleanup_action(tmp_path, CleanupAction(action, "1", **provenance))
        persist_cleanup_action(tmp_path, CleanupAction(action, "1", **provenance))
    baseline = _baseline(tmp_path)

    report = run_pending_cleanup(tmp_path, object())

    assert (report.completed, report.pending) == (2, ())
    assert not baseline.exists()
    assert len(calls) == 1
    assert len(list((tmp_path / ACTION_DONE_DIR).iterdir())) == 2
    anonymous = CleanupAction(ACTION_PACK_RESET, "1", **{**provenance, "pack_id": ""})
    with pytest.raises(ValueError):
        persist_cleanup_action(tmp_path, anonymous)


class _Backend:
    def __init__(self, result: LabResult) -> None:
        self.result = result
        self.calls: list[tuple[list[str], bool]] = []

    def stop(self, profiles: list[str], remove_volumes: bool = False) -> LabResult:
        self.calls.append((profiles, remove_volumes))
        return self.result


class _Project(_Backend):
    """A project the backend can observe and tear down, as Compose does."""

    def __init__(
        self, containers: int = 3, networks: int = 2, *, observed: bool = True
    ) -> None:
        super().__init__(LabResult(success=True))
        self.containers = containers
        self.networks = networks
        self.observed = observed

    def observe_project_runtime(self):
        from aptl.core.deployment.backend_host_inventory import ProjectRuntimePresence

        if not self.observed:
            return ProjectRuntimePresence(error="container observation failed")
        return ProjectRuntimePresence(
            container_count=self.containers, network_count=self.networks
        )

    def stop(self, profiles: list[str], remove_volumes: bool = False) -> LabResult:
        result = super().stop(profiles, remove_volumes)
        self.containers = self.networks = 0
        return result


def _started(root: Path) -> str:
    """Record the workspace scope a start leaves, and return its project name.

    A reset counts only that workspace-scoped project, the one its teardown
    removes (#1054), so a project without a recorded scope counts as empty.
    """
    from aptl.core.deployment._compose_resource_ownership import WorkspaceOwnership

    return WorkspaceOwnership.ensure(root, "aptl").project_name


def _kept_host_files(root: Path) -> dict[Path, bytes]:
    """Write the host files a reset must keep, and return their bytes.

    Each goes where `lilrae lab init` or `lilrae lab start` writes it: the public
    half of the lab SSH key under ``keys/``, the Wazuh and SOC certificates
    under ``config/``, and the run record in the run store that ``aptl.json``
    configures, ``./runs`` by default.
    """
    from aptl.cli._common import resolve_run_store

    config = b'{"lab": {"name": "reset"}}\n'
    (root / "aptl.json").write_bytes(config)
    run_record = resolve_run_store(root).get_run_path("run-1") / "manifest.json"
    files = {
        root / "aptl.json": config,
        root / ".env": b"APTL_LAB_LABEL=keep-me\n",
        root / "keys" / "aptl_lab_key.pub": b"ssh-ed25519 lab-key-fixture\n",
        root / "config" / "wazuh_indexer_ssl_certs" / "root-ca.pem": b"wazuh-ca\n",
        root / "config" / "soc_certs" / "lab-ca.pem": b"soc-ca\n",
        run_record: b'{"run": "1"}\n',
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return files


def test_repeated_teardown_on_the_real_backend_is_safe(
    tmp_path: Path, monkeypatch
) -> None:
    """Repeated `stop`, `stop -v` and `reset` run the real teardown (#1218).

    Docker holds nothing for the project, which is what a first teardown
    leaves. Each call builds its backend as the CLI does, runs the Compose
    teardown and its absence check, and succeeds, and every call removes the
    same workspace-scoped project: the one the first call recorded.
    """
    from aptl.core.deployment._compose_resource_ownership import WorkspaceOwnership
    from aptl.core.lab import reset_lab, stop_lab

    _no_installed_providers(monkeypatch)
    commands: list[list[str]] = []

    def run(cmd: list[str], *_args: object, **_kwargs: object):
        commands.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def no_process(*_args: object, **_kwargs: object):
        raise AssertionError("teardown started a process outside subprocess.run")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", no_process)

    stops = [
        stop_lab(remove_volumes=volumes, project_dir=tmp_path)
        for volumes in (False, False, True, True)
    ]
    resets = [reset_lab(tmp_path) for _ in range(2)]

    assert [result.success for result in stops] == [True] * 4
    assert [
        (outcome.result.success, outcome.containers_found, outcome.networks_found)
        for outcome in resets
    ] == [(True, 0, 0)] * 2
    scope = WorkspaceOwnership.load(tmp_path, "aptl")
    assert scope is not None
    downs = [cmd for cmd in commands if cmd[:2] == ["docker", "compose"]]
    assert [cmd[cmd.index("-p") + 1] for cmd in downs] == [scope.project_name] * 6
    assert ["down" in cmd for cmd in downs] == [True] * 6


def test_reset_reports_cleanup_it_could_not_finish(tmp_path: Path, monkeypatch) -> None:
    from aptl.core.lab import reset_lab

    _install(monkeypatch, ("2.0.0", _provider(reset=lambda _context: None)))
    _started(tmp_path)
    record = _legacy(
        tmp_path,
        pack_id="otherpack",
        digest=OTHER_DIGEST,
        distribution="otherpack-adapter",
        version="1.0.0",
    )

    outcome = reset_lab(tmp_path, backend=_Project())

    assert outcome.result.success is False
    assert outcome.result.error == (
        "[lifecycle-host-cleanup-pending] Docker teardown completed and the "
        "project volumes were removed, but 1 host-side cleanup action remains "
        "pending: pack.reset for otherpack 1.0.0 "
        f"({LEGACY_DIR.name}/{record.name[:12]}): "
        "provider-reset-authority-unavailable. The pending records were kept. "
        "Resolve the cause, then retry with `lilrae lab reset --yes`."
    )
    assert (outcome.containers_found, outcome.networks_found) == (3, 2)


def test_reset_of_an_unobservable_project_still_resets(
    tmp_path: Path, monkeypatch
) -> None:
    from aptl.core.lab import reset_lab

    _no_installed_providers(monkeypatch)
    _started(tmp_path)
    project = _Project(observed=False)

    outcome = reset_lab(tmp_path, backend=project)

    assert outcome.result.success is True
    assert (outcome.containers_found, outcome.networks_found) == (None, None)
    assert [remove_volumes for _profiles, remove_volumes in project.calls] == [True]


def test_reset_refuses_while_another_lifecycle_owner_holds_the_lock(
    tmp_path: Path,
) -> None:
    import threading

    from aptl.core.lab import reset_lab
    from aptl.core.lifecycle_guard import lifecycle_mutation_lock

    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with lifecycle_mutation_lock(tmp_path):
            held.set()
            release.wait(timeout=10)

    owner = threading.Thread(target=hold)
    owner.start()
    assert held.wait(timeout=10)
    project = _Project()
    try:
        outcome = reset_lab(tmp_path, backend=project)
    finally:
        release.set()
        owner.join(timeout=10)

    assert outcome.result.success is False
    assert outcome.result.error.startswith("[lifecycle-owner-busy]")
    assert "`lilrae lab reset`" in outcome.result.error
    assert project.calls == []


class _Daemon:
    """The projects one Docker daemon holds, answered by exact label value.

    It answers the project observation queries as the daemon filters them.
    ``stop`` stands in for the Compose teardown, which needs ownership
    receipts this fake does not hold. Like the real one, it first binds the
    workspace scope, recording a new one when none is recorded, and then
    removes only that project.
    """

    def __init__(
        self, backend: object, projects: dict[str, tuple[list[str], list[str]]]
    ) -> None:
        self.backend = backend
        self.projects = projects
        self.stops: list[bool] = []

    def run(self, cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess:
        del timeout
        label = cmd[cmd.index("--filter") + 1].removeprefix("label=")
        containers, networks = self.projects.get(label.partition("=")[2], ([], []))
        if cmd[:3] == ["docker", "ps", "-aq"]:
            return subprocess.CompletedProcess(cmd, 0, "\n".join(containers), "")
        if cmd[:3] == ["docker", "network", "ls"]:
            return subprocess.CompletedProcess(cmd, 0, "\n".join(networks), "")
        raise AssertionError(f"unexpected Docker command: {cmd}")

    def stop(self, profiles: list[str], *, remove_volumes: bool = False) -> LabResult:
        del profiles
        self.stops.append(remove_volumes)
        scope = self.backend._ensure_resource_ownership().project_name
        self.projects.pop(scope, None)
        return LabResult(success=True)


def _unscoped_project() -> dict[str, tuple[list[str], list[str]]]:
    """An unscoped `aptl` project from before workspace scoping (#1054)."""

    return {"aptl": (["legacy-c"], ["legacy-n"])}


def _compose_daemon(
    root: Path, monkeypatch, projects: dict[str, tuple[list[str], list[str]]]
) -> tuple[object, _Daemon]:
    """Build the real Compose backend that `reset_lab` builds, on a fake daemon."""
    from aptl.core.deployment.docker_compose import DockerComposeBackend

    backend = DockerComposeBackend(root)
    daemon = _Daemon(backend, projects)
    monkeypatch.setattr(backend, "_run", daemon.run)
    monkeypatch.setattr(backend, "stop", daemon.stop)
    return backend, daemon


def test_reset_counts_the_project_that_start_labelled(
    tmp_path: Path, monkeypatch
) -> None:
    """A newly built Compose backend counts the workspace-scoped project.

    `lilrae lab start` binds the workspace-scoped name (`aptl-w<id>`) and labels
    every container and network with it. A backend built as `reset_lab` builds
    one holds the logical name `aptl` until the workspace scope loads, so the
    count must not run before that (#1218). An unscoped project from before
    #1054 on the same daemon is neither counted nor removed.
    """
    from aptl.core.lab import reset_lab

    _no_installed_providers(monkeypatch)
    scoped = _started(tmp_path)
    backend, daemon = _compose_daemon(
        tmp_path,
        monkeypatch,
        {scoped: (["c1", "c2", "c3"], ["n1", "n2"]), **_unscoped_project()},
    )

    outcome = reset_lab(tmp_path, backend=backend)

    assert outcome.result.success is True
    assert (outcome.containers_found, outcome.networks_found) == (3, 2)
    assert daemon.stops == [True]
    assert daemon.projects == _unscoped_project()


def test_reset_before_any_start_counts_nothing(tmp_path: Path, monkeypatch) -> None:
    """Without a recorded workspace scope, a reset counts zero (#1218).

    Its teardown records a new, empty scope and removes only that project, so
    an unscoped `aptl` project from before #1054 on the same daemon is neither
    counted nor removed.
    """
    from aptl.core.lab import reset_lab

    _no_installed_providers(monkeypatch)
    backend, daemon = _compose_daemon(tmp_path, monkeypatch, _unscoped_project())

    outcome = reset_lab(tmp_path, backend=backend)

    assert outcome.result.success is True
    assert (outcome.containers_found, outcome.networks_found) == (0, 0)
    assert daemon.stops == [True]
    assert daemon.projects == _unscoped_project()


def _malformed_state(state: Path) -> None:
    state.write_text("{}\n", encoding="utf-8")


def _linked_state(state: Path) -> None:
    target = state.with_name("elsewhere.json")
    target.write_text('{"schema": 1, "workspace_id": "' + "a" * 32 + '"}\n')
    state.symlink_to(target)


@pytest.mark.parametrize(
    "write_state",
    [_malformed_state, _linked_state],
    ids=["malformed", "symlink"],
)
def test_reset_refuses_unreadable_workspace_state_before_teardown(
    tmp_path: Path, monkeypatch, write_state
) -> None:
    """Unreadable workspace state stops a reset before anything changes (#1218).

    That state names the project the teardown removes, so the refusal names
    the file to repair, not a Docker failure, and no Docker command runs.
    """
    from aptl.core.deployment.docker_compose import DockerComposeBackend
    from aptl.core.lab import reset_lab

    _no_installed_providers(monkeypatch)
    state = tmp_path / ".aptl" / "lifecycle" / "workspace-ownership-v1.json"
    state.parent.mkdir(parents=True)
    write_state(state)
    before = state.read_bytes()
    commands: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    backend = DockerComposeBackend(tmp_path)
    monkeypatch.setattr(backend, "_run", run)

    outcome = reset_lab(tmp_path, backend=backend)

    assert outcome.result.success is False
    assert outcome.result.error == (
        "[lifecycle-state-invalid] Lab reset blocked: unreadable workspace "
        "ownership state; refusing to guess which project to remove. Repair or "
        "restore .aptl/lifecycle/workspace-ownership-v1.json and retry."
    )
    assert (outcome.containers_found, outcome.networks_found) == (None, None)
    assert commands == []
    assert state.read_bytes() == before


@pytest.mark.parametrize(
    ("state_file", "content", "error"),
    [
        (
            "aptl.json",
            "{not json\n",
            "[lifecycle-invalid-configuration] Lab reset blocked: invalid "
            "configuration; refusing to guess the deployment project identity. "
            "Repair aptl.json and retry.",
        ),
        (
            ".aptl/lifecycle/operator-groups-v1/not-a-receipt.json",
            "{}\n",
            "[lifecycle-state-invalid] Lab reset blocked: invalid operator-group "
            "recovery state.",
        ),
    ],
    ids=["invalid-configuration", "invalid-operator-groups"],
)
def test_reset_blocked_before_teardown_names_reset(
    tmp_path: Path, state_file: str, content: str, error: str
) -> None:
    """A reset refused before teardown names `Lab reset`, not `Lab stop`."""
    from aptl.core.lab import reset_lab

    path = tmp_path / state_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    outcome = reset_lab(tmp_path)

    assert outcome.result.success is False
    assert outcome.result.error == error
    assert (outcome.containers_found, outcome.networks_found) == (None, None)


def test_start_persists_aptl_owned_and_declared_pack_cleanup(tmp_path: Path) -> None:
    from aptl.backends.scenario_startup import (
        ScenarioStartupPlan,
        ScenarioStartupSelection,
        StartupHook,
        StartupProviderProvenance,
    )
    from aptl.core.config import AptlConfig
    from aptl.core.lab import StartSelection, _LabStartContext, _persist_start_recovery
    from aptl.core.scenario_bundle import (
        PackIdentity,
        ScenarioBundle,
        ScenarioSourceKind,
    )
    from aptl.core.startup_reset_state import load_pending_cleanup

    identity = PackIdentity("otherpack", "1.0.0", OTHER_DIGEST)
    plan = ScenarioStartupPlan(
        "scripts/seed.sh",
        ("blue-team",),
        ("blue-team",),
        startup_hooks=frozenset({StartupHook.RESET}),
    )
    selection = ScenarioStartupSelection(
        identity,
        object(),
        plan,
        StartupProviderProvenance("otherpack-adapter", "1.0.0", "otherpack"),
    )
    bundle = ScenarioBundle(
        "otherpack",
        tmp_path,
        tmp_path / "otherpack.sdl.yaml",
        ScenarioSourceKind.ENV_PACK,
        identity,
    )
    ctx = _LabStartContext(tmp_path, skip_seed=False)
    ctx.selected_profiles = ["blue-team"]
    ctx.start_selection = StartSelection(AptlConfig(), bundle, plan, selection)

    assert _persist_start_recovery(ctx) is None

    pending, malformed = load_pending_cleanup(tmp_path)
    assert malformed == ()
    assert sorted(item.action.action for item in pending) == [
        "aptl.wazuh-enrollment-baseline.clear",
        "pack.reset",
    ]
    assert {item.action.pack_set_digest for item in pending} == {OTHER_DIGEST}
    assert not (tmp_path / LEGACY_DIR).exists()


def test_start_without_pack_still_records_aptl_owned_cleanup(tmp_path: Path) -> None:
    from aptl.core.lab import _LabStartContext, _persist_start_recovery
    from aptl.core.startup_reset_state import load_pending_cleanup

    ctx = _LabStartContext(tmp_path, skip_seed=False)
    ctx.selected_profiles = ["wazuh"]

    assert _persist_start_recovery(ctx) is None

    pending, _ = load_pending_cleanup(tmp_path)
    assert [(item.action.action, item.action.pack_id) for item in pending] == [
        ("aptl.wazuh-enrollment-baseline.clear", "")
    ]


def test_start_fails_closed_when_cleanup_cannot_be_recorded(tmp_path: Path) -> None:
    from aptl.core.lab import _LabStartContext, _persist_start_recovery

    ctx = _LabStartContext(tmp_path, skip_seed=False)
    ctx.selected_profiles = ["wazuh"]
    (tmp_path / ".aptl" / "lifecycle").mkdir(parents=True)
    (tmp_path / ACTION_DIR).symlink_to(tmp_path)

    result = _persist_start_recovery(ctx)

    assert result is not None
    assert result.success is False
    assert "pending lab cleanup records" in result.error
