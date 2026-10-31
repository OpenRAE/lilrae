"""Behavioral contracts for the required platform checks in issue #969."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.fixture_pack import FIXTURE_SDL

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "checks.yml"
BASELINE = ROOT / ".github" / "branch-protection-baseline.json"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _run_step(job: str, step_name: str) -> str:
    return next(
        step["run"] for step in _jobs()[job]["steps"] if step.get("name") == step_name
    )


def _stub(tmp_path: Path, name: str, body: str) -> None:
    path = tmp_path / "bin" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _shell(
    script: str, tmp_path: Path, **extra_env: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(extra_env)
    env["PATH"] = f"{tmp_path / 'bin'}:{env['PATH']}"
    return subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_capture_lifecycle_lane_requires_docker_and_propagates_test_failure(tmp_path):
    script = "set -e\n" + _run_step(
        "mcp-tests", "Extracted MCP shutdown through the real capture sidecar"
    )
    for name in ("node", "ssh", "ssh-keygen"):
        _stub(tmp_path, name, "exit 0")
    probe = tmp_path / "pytest-invocation"
    for daemon_status, test_status in ((19, 0), (0, 23), (0, 0)):
        probe.unlink(missing_ok=True)
        _stub(tmp_path, "docker", f"exit {daemon_status}")
        _stub(
            tmp_path,
            "python",
            f'printf "%s\\n" "$*" > "$LILRAE_TEST_CAPTURE_PROBE"\nexit {test_status}',
        )
        result = _shell(script, tmp_path, LILRAE_TEST_CAPTURE_PROBE=str(probe))
        assert result.returncode == (daemon_status or test_status)
        if daemon_status:
            assert not probe.exists()
        else:
            assert "tests/test_mcp_capture_lifecycle.py" in probe.read_text()
            assert "-m integration" in probe.read_text()


def test_dev_requires_existing_platform_job_contexts() -> None:
    jobs = _jobs()
    contexts = set(
        json.loads(BASELINE.read_text(encoding="utf-8"))["branches"]["dev"][
            "required_status_checks"
        ]["contexts"]
    )
    platform_jobs = {
        "pre-commit",
        "python-tests",
        "mcp-tests",
        "dependency-audit",
        "clean-install-lab-boot",
    }
    assert {jobs[job]["name"] for job in platform_jobs} <= contexts


def _protected_branches() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["branches"]


def _triggers(workflow: str) -> dict:
    data = yaml.safe_load((WORKFLOW.parent / workflow).read_text(encoding="utf-8"))
    # PyYAML follows YAML 1.1, which reads the `on:` key as the boolean True.
    return data[True]


@pytest.mark.parametrize(
    "workflow", ["checks.yml", "pr-title-lint.yml", "ground-control-phase-e.yml"]
)
def test_pull_request_workflows_run_for_every_protected_branch(workflow: str) -> None:
    branches = set(_triggers(workflow)["pull_request"]["branches"])
    assert set(_protected_branches()) <= branches, (
        f"{workflow} does not run for pull requests into every protected branch; "
        "a required check that never runs leaves the pull request blocked or unchecked"
    )


def test_checks_analyze_every_protected_branch_on_push() -> None:
    branches = set(_triggers("checks.yml")["push"]["branches"])
    assert set(_protected_branches()) <= branches


def test_go_cutover_requires_at_least_the_dev_checks() -> None:
    branches = _protected_branches()
    dev, cutover = branches["dev"], branches["go-cutover"]
    assert cutover["changes_land_via_pull_request"] is True
    assert cutover["admin_bypass_allowed"] == dev["admin_bypass_allowed"]
    assert cutover["required_status_checks"]["strict"] is True
    assert set(dev["required_status_checks"]["contexts"]) <= set(
        cutover["required_status_checks"]["contexts"]
    )


def test_combined_python_coverage_refuses_a_missing_group(tmp_path: Path) -> None:
    script = _run_step("python-tests", "Combine complete worker coverage")
    log = tmp_path / "combine.log"
    _stub(
        tmp_path,
        "coverage",
        'if [ "$1" = combine ]; then printf "%s\\n" "$@" > "$COMBINE_LOG"; fi\nexit 0',
    )
    groups = _jobs()["python-test-shards"]["strategy"]["matrix"]["shard"]
    files = [
        tmp_path / f"coverage-data/python-coverage-data-{group}/.coverage"
        for group in groups
    ]
    for path in files:
        path.parent.mkdir(parents=True)
        path.write_bytes(b"measurement")
    env = {"RUNNER_TEMP": str(tmp_path), "COMBINE_LOG": str(log)}
    assert _shell(script, tmp_path, **env).returncode == 0
    assert set(log.read_text(encoding="utf-8").splitlines()[1:]) == {
        str(path.relative_to(tmp_path)) for path in files
    }
    for path in files:
        path.unlink()
        assert _shell(script, tmp_path, **env).returncode != 0
        path.write_bytes(b"measurement")


def test_python_audit_covers_shipped_exports_and_fails_closed(tmp_path: Path) -> None:
    script = _run_step("dependency-audit", "pip-audit (Python dependencies) — blocking")
    for export in ("runtime.txt", "web.txt", "ci.txt"):
        assert f"requirements/{export}" in script
    assert "pip install -e ." not in script
    assert "--strict" in script
    _stub(tmp_path, "pip", "exit 0")
    _stub(tmp_path, "pip-audit", "exit 9")
    assert _shell(script, tmp_path).returncode != 0


def test_python_audit_rejects_scanner_install_failure(tmp_path: Path) -> None:
    script = _run_step("dependency-audit", "pip-audit (Python dependencies) — blocking")
    _stub(tmp_path, "pip", "exit 8")
    _stub(tmp_path, "pip-audit", "exit 0")
    assert _shell(script, tmp_path).returncode != 0


def test_node_audit_discovers_new_mcp_package_and_propagates_finding(
    tmp_path: Path,
) -> None:
    for package in (tmp_path / "web", tmp_path / "mcp" / "new-server"):
        package.mkdir(parents=True)
        (package / "package.json").write_text("{}\n", encoding="utf-8")
        (package / "package-lock.json").write_text("{}\n", encoding="utf-8")
    log = tmp_path / "npm.log"
    _stub(
        tmp_path,
        "npm",
        'printf "%s|%s\\n" "$PWD" "$*" >> "$AUDIT_LOG"\n'
        'case "$PWD:$1" in */mcp/new-server:audit) exit 9;; esac\n'
        "exit 0",
    )
    script = _run_step("dependency-audit", "npm audit (JS/TS workspaces)")
    result = _shell(script, tmp_path, AUDIT_LOG=str(log))
    calls = log.read_text(encoding="utf-8")
    assert "mcp/new-server|audit" in calls
    assert "--omit=dev" in calls
    assert result.returncode != 0


def test_node_audit_rejects_missing_adjacent_lock(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}\n", encoding="utf-8")
    _stub(tmp_path, "npm", "exit 0")
    script = _run_step("dependency-audit", "npm audit (JS/TS workspaces)")
    assert _shell(script, tmp_path).returncode != 0


def test_wheel_smoke_scopes_native_effect_and_always_proves_cleanup() -> None:
    steps = _jobs()["clean-install-lab-boot"]["steps"]
    native = next(
        step["run"]
        for step in steps
        if step.get("name") == "Start and verify the materialization envelope"
    )
    assert "com.docker.compose.project=" in native
    assert "aptl.node.address=provision.node.smoke-box" in native
    assert "-eq 1" in native

    stop = next(
        step
        for step in steps
        if step.get("name") == "Stop the lab and remove its volumes"
    )
    cleanup = next(
        step
        for step in steps
        if step.get("name")
        == "Assert no project containers, networks, or volumes remain"
    )
    assert "always()" in stop["if"]
    assert "always()" in cleanup["if"]
    assert '"$GITHUB_WORKSPACE/scripts/ci/assert_project_teardown.py"' in cleanup["run"]


class TestBootRealizationCoverage:
    """The boot job must verify what the shared fixture actually declares (#993).

    These read the SDL rather than grepping the workflow for assertion strings:
    a job that names a port the scenario no longer publishes, or that keeps its
    verifier step after the declaration behind it was dropped, is exactly the
    silently-vacuous gate issue #993 exists to prevent.
    """

    FIXTURE = FIXTURE_SDL
    NODE = "smoke-box"

    def _scenario(self) -> dict:
        return yaml.safe_load(self.FIXTURE.read_text(encoding="utf-8"))

    def _runtime(self) -> dict:
        return self._scenario()["nodes"][self.NODE]["runtime"]

    def _verifier_step(self) -> str:
        return _run_step(
            "clean-install-lab-boot",
            "Verify the realization regressions the scenario declares",
        )

    def test_the_fixture_declares_the_whole_causal_chain(self) -> None:
        """Content, service, listener and published port must all be present."""

        scenario = self._scenario()
        runtime = self._runtime()

        content = scenario["content"]["smoke-sshd-config"]
        assert content["target"] == self.NODE
        assert runtime["service_manager_units"]
        assert runtime["service_listeners"]
        assert runtime["network"]["published_ports"]
        assert scenario["workflows"]

    def test_the_declared_content_configures_the_declared_listener_port(self) -> None:
        """The chain is causal only while the content names the listener's port."""

        scenario = self._scenario()
        runtime = self._runtime()
        listener = runtime["service_listeners"][0]
        content_text = scenario["content"]["smoke-sshd-config"]["text"]

        assert f"Port {listener['port']}" in content_text
        assert listener["port"] != 22, "the package default proves nothing"

    def test_the_verifier_is_invoked_with_the_values_the_scenario_declares(
        self,
    ) -> None:
        """Every parameter the job passes must match the SDL, not a stale copy."""

        scenario = self._scenario()
        runtime = self._runtime()
        step = self._verifier_step()
        content = scenario["content"]["smoke-sshd-config"]
        listener = runtime["service_listeners"][0]
        published = runtime["network"]["published_ports"][0]
        unit = runtime["service_manager_units"][0]

        assert "scripts/ci/assert_boot_realization.py" in step
        assert f"--content-path {content['path']}" in step
        assert f"--unit-name {unit['unit_name']}" in step
        assert f"--container-port {listener['port']}" in step
        assert f"--protocol {listener['protocol']}" in step
        assert f"--host-ip {published['host_ip']}" in step
        assert f"--host-port {published['host_port']}" in step
        for name in scenario["workflows"]:
            assert f"--workflow-address orchestration.workflow.{name}" in step

    def test_the_host_publication_stays_loopback_only(self) -> None:
        """ADR-034: a scenario-declared host port never lands on every interface."""

        for published in self._runtime()["network"]["published_ports"]:
            assert published["host_ip"] == "127.0.0.1"

    def test_the_verifier_runs_from_the_installed_clean_venv(self) -> None:
        """A checkout interpreter would not prove the installed artifact."""

        step = self._verifier_step()

        assert '"$RUNNER_TEMP/clean-venv/bin/python"' in step
        assert "uv run" not in step

    def test_the_verifier_runs_before_teardown_and_cleanup_still_always_runs(
        self,
    ) -> None:
        """Verification must see a running lab; cleanup must run regardless."""

        steps = _jobs()["clean-install-lab-boot"]["steps"]
        names = [step.get("name") for step in steps]
        verify = names.index("Verify the realization regressions the scenario declares")
        stop = names.index("Stop the lab and remove its volumes")
        cleanup = names.index(
            "Assert no project containers, networks, or volumes remain"
        )

        assert verify < stop < cleanup
        assert "always()" in steps[stop]["if"]
        assert "always()" in steps[cleanup]["if"]
        assert steps[verify].get("if") == steps[
            names.index("Start and verify the materialization envelope")
        ].get("if")


def test_the_boot_gate_requires_the_service_to_answer_not_just_the_port() -> None:
    """Docker publishes the host port whether or not anything listens behind it.

    Without an expected greeting the connection probe passes on the publication
    alone, which `_binding_failures` already covers — so the job must name one.
    """

    step = _run_step(
        "clean-install-lab-boot",
        "Verify the realization regressions the scenario declares",
    )

    assert "--endpoint-banner-prefix SSH-" in step


def test_the_cleanup_proof_diffs_the_daemon_against_a_pre_start_baseline() -> None:
    """Debris with no project identity is caught only by a before/after diff.

    Anonymous volumes and ephemeral helpers carry neither the project label nor
    the ``<project>_`` volume prefix, so the project-scoped proof reported a
    clean teardown with both still present. The baseline must be recorded
    before the lab starts, and the proof must read that same file.
    """

    steps = _jobs()["clean-install-lab-boot"]["steps"]
    names = [step.get("name") for step in steps]
    record = names.index("Record the daemon baseline before the lab starts")
    start = names.index("Start and verify the materialization envelope")
    proof = names.index("Assert no project containers, networks, or volumes remain")

    assert record < start < proof
    baseline = '"$RUNNER_TEMP/daemon-baseline.json"'
    assert f"--record-baseline {baseline}" in steps[record]["run"]
    assert f"--baseline {baseline}" in steps[proof]["run"]
    assert "always()" in steps[proof]["if"]


_BLOCKING_SCANNER_JOBS = {
    "trivy-fs",
    "trivy-iac",
    "trivy-image-gate",
    "osv-scanner",
    "raes-scenario-gate",
}


def test_scanner_and_validation_gates_block_and_are_required() -> None:
    """No scanner or validation gate may report without failing (#1193).

    Each is a required ``dev`` context, none sets ``continue-on-error``, and
    every Trivy gate step fails on findings while the SARIF-recording step
    keeps unfixed findings tracked instead of gating on them.
    """

    jobs = _jobs()
    contexts = set(
        json.loads(BASELINE.read_text(encoding="utf-8"))["branches"]["dev"][
            "required_status_checks"
        ]["contexts"]
    )
    assert {jobs[job]["name"] for job in _BLOCKING_SCANNER_JOBS} <= contexts
    for job in [*_BLOCKING_SCANNER_JOBS, "trivy-image"]:
        assert "continue-on-error" not in jobs[job], job
        assert "advisory" not in jobs[job]["name"].lower(), job

    for job in ("trivy-fs", "trivy-iac", "trivy-image"):
        trivy = [
            step["with"]
            for step in jobs[job]["steps"]
            if "aquasecurity/trivy-action" in step.get("uses", "")
        ]
        gates = [w for w in trivy if w["exit-code"] == "1"]
        records = [w for w in trivy if w["exit-code"] == "0"]
        assert len(gates) == 1, job
        assert len(records) == 1, job
        assert records[0]["format"] == "sarif"
        assert "ignore-unfixed" not in records[0]
        assert gates[0]["severity"] == records[0]["severity"] == "CRITICAL,HIGH,MEDIUM"
        assert gates[0]["trivyignores"] == ".trivyignore.yaml"
        if job == "trivy-iac":
            # Misconfiguration waivers are permanent design decisions.
            assert records[0]["trivyignores"] == ".trivyignore.yaml"
        else:
            # Vulnerability waivers relax the gate only; the record and code
            # scanning keep tracking findings that have no upstream fix yet.
            assert "trivyignores" not in records[0]
        if job != "trivy-iac":
            assert gates[0]["ignore-unfixed"] == "true"

    image_gate = jobs["trivy-image-gate"]
    assert {"changes", "trivy-image"} <= set(image_gate["needs"])
    assert image_gate["if"] == "always()"


def test_trivy_waivers_are_scoped_and_justified() -> None:
    """Every waiver is narrow and states why the finding cannot be fixed.

    A misconfiguration waiver names exact Dockerfiles. A vulnerability waiver
    names exact package versions (``pkg:<type>/<name>@<version>``), so a
    release that ships a fix is no longer covered by it. None is rule-wide.
    """

    waivers = yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))
    assert set(waivers) <= {"misconfigurations", "vulnerabilities"}
    for waiver in waivers["misconfigurations"]:
        assert waiver["statement"].strip()
        assert waiver["paths"]
        for path in waiver["paths"]:
            assert (ROOT / path).is_file(), path
            assert Path(path).name.startswith("Dockerfile"), path
    for waiver in waivers.get("vulnerabilities", []):
        assert waiver["statement"].strip()
        assert waiver["id"].strip()
        assert "paths" not in waiver
        assert waiver["purls"]
        for purl in waiver["purls"]:
            assert re.fullmatch(r"pkg:[a-z]+/[^@\s]+@[^@\s]+", purl), purl


def test_msgpack_c_extension_exception_requires_pips_pure_python_copy() -> None:
    """The msgpack exception must not outlive its checked implementation."""
    from importlib.util import find_spec

    from pip._vendor import msgpack

    waivers = yaml.safe_load((ROOT / ".trivyignore.yaml").read_text(encoding="utf-8"))
    exception = next(
        item for item in waivers["vulnerabilities"] if item["id"] == "CVE-2026-114613"
    )
    assert exception["purls"] == [f"pkg:pypi/msgpack@{msgpack.__version__}"]
    assert find_spec("pip._vendor.msgpack._cmsgpack") is None
    assert msgpack.unpackb.__module__ == "pip._vendor.msgpack.fallback"
    assert msgpack.Unpacker.__module__ == "pip._vendor.msgpack.fallback"


_GO_GATE_JOBS = ("go-lint", "go-tests", "go-mutation", "go-regression", "go-vuln", "osv-scanner-go")


def test_go_gates_block_and_are_required_on_go_cutover() -> None:
    """Each ADR-065 Go gate is a required go-cutover context (#1553).

    A gate runs when routing fails or selects Go, checks the routing result
    first, and never reports success after a failure.
    """

    jobs = _jobs()
    cutover = set(_protected_branches()["go-cutover"]["required_status_checks"]["contexts"])
    for job in _GO_GATE_JOBS:
        assert jobs[job]["name"] in cutover, job
        assert "continue-on-error" not in jobs[job], job
        assert jobs[job]["if"] == (
            "always() && (needs.changes.result != 'success' || needs.changes.outputs.go == 'true')"
        ), job
        assert jobs[job]["steps"][0]["name"] == "Validate check selection", job
    # The project-wide analysis waits for current Go coverage.
    assert "go-tests" in jobs["sonarcloud"]["needs"]
    assert jobs["go-regression"]["permissions"] == {"contents": "read", "issues": "read"}


def test_go_architecture_runs_on_every_change_and_is_required_on_go_cutover() -> None:
    """The architecture check of ADR-065 runs whatever routing selects (#1583).

    The model covers web/caddy-build and the design notes, which routing does
    not send to the Go lane. Only a pull request from a protected branch of
    this repository skips the design comparison.
    """

    jobs = _jobs()
    job = jobs["go-architecture"]
    cutover = set(_protected_branches()["go-cutover"]["required_status_checks"]["contexts"])
    assert job["name"] in cutover
    assert "continue-on-error" not in job
    assert job["if"] == "always()"
    assert job["permissions"] == {"contents": "read"}
    assert job["steps"][0]["name"] == "Validate check selection"
    assert job["steps"][1]["with"]["fetch-depth"] == 0
    script = job["steps"][-1]["run"]
    assert 'bash tools/ci/go-gates.sh architecture "$BASE_SHA" "$issue" "$promotion"' in script
    assert '"$HEAD_REPO" == "$REPOSITORY" && "$HEAD_REF" =~ ^(main|dev|go-cutover)$' in script
