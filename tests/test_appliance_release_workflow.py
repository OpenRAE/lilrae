"""Structural gates for the release workflow's container publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/release-please.yml"
RETRY_WORKFLOW = ROOT / ".github/workflows/publish-seat-image.yml"
PUBLISHER = ROOT / "scripts/appliance/publish-seat-image.sh"


def _jobs() -> dict[str, dict]:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def test_package_release_only_publishes_python_artifacts() -> None:
    jobs = _jobs()
    assert set(jobs) == {"release-please", "publish", "backmerge"}
    assert set(jobs["backmerge"]["needs"]) == {"release-please", "publish"}


def test_backmerge_binds_values_and_fails_closed() -> None:
    """The back-merge reaches shell values only through env and reports failures.

    The step once interpolated the tag into its script and ended with
    ``|| echo``, so an auth or network failure read as "dev already up to date".
    """
    (step,) = _jobs()["backmerge"]["steps"]
    run = step["run"]
    assert "${{" not in run
    assert step["env"]["TAG"] == "${{ needs.release-please.outputs.tag_name }}"
    assert "|| echo" not in run
    assert "|| true" not in run
    assert "compare/dev...main" in run
    assert '--title "chore: back-merge ${TAG} into dev"' in run
    # A squashed back-merge leaves main's release commit out of dev's history,
    # so the next promotion replays the version bump and can conflict (#1375).
    assert 'Admin-merge it with \\"Create a merge commit\\"' in run
    assert "Do not squash" in run


_GH_STUB = """#!/bin/sh
echo "$*" >> "$GH_CALLS"
case "$1 $2" in
  "pr list") [ -n "$GH_LIST_FAIL" ] && exit 1; echo "${GH_OPEN:-0}" ;;
  "api repos/OpenRAE/lilrae/compare/dev...main") echo "${GH_AHEAD:-0}" ;;
  "pr create") exit 0 ;;
  *) exit 2 ;;
esac
"""


def _run_backmerge(tmp_path: Path, **stub_env: str) -> tuple[int, list[str]]:
    """Run the back-merge step's script against a stub ``gh``."""

    (step,) = _jobs()["backmerge"]["steps"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(_GH_STUB)
    stub.chmod(0o755)
    calls = tmp_path / "calls"
    calls.touch()
    environment = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_REPO": "OpenRAE/lilrae",
        "TAG": "v8.0.0",
        "GH_CALLS": str(calls),
        **stub_env,
    }
    completed = subprocess.run(
        ["bash", "-c", step["run"]], env=environment, capture_output=True, text=True
    )
    return completed.returncode, calls.read_text().splitlines()


@pytest.mark.parametrize(
    ("stub_env", "expected_status", "creates_pr"),
    [
        pytest.param({"GH_LIST_FAIL": "1"}, "fail", False, id="list-fails"),
        pytest.param({"GH_OPEN": "1"}, "ok", False, id="already-open"),
        pytest.param({"GH_AHEAD": "0"}, "ok", False, id="dev-current"),
        pytest.param({"GH_AHEAD": "2"}, "ok", True, id="creates-pr"),
    ],
)
def test_backmerge_script_outcomes(
    tmp_path: Path, stub_env: dict[str, str], expected_status: str, creates_pr: bool
) -> None:
    status, calls = _run_backmerge(tmp_path, **stub_env)
    assert (status == 0) is (expected_status == "ok")
    created = [call for call in calls if call.startswith("pr create")]
    assert bool(created) is creates_pr
    if creates_pr:
        assert "--title chore: back-merge v8.0.0 into dev" in created[0]


def test_release_attestation_bundle_is_named_for_the_distribution() -> None:
    publish = _jobs()["publish"]
    upload = next(s for s in publish["steps"] if "gh release upload" in s.get("run", ""))
    assert 'cp "$BUNDLE" "dist/lilrae-${TAG}.intoto.jsonl"' in upload["run"]


def test_every_project_owned_image_is_still_published() -> None:
    # The seat image is what a participant boots, but the lab's own container
    # images are still published; deleting the golden pipeline must not have
    # taken them with it.
    publisher = (ROOT / "scripts/appliance/publish-images.sh").read_text()
    published = set(re.findall(r"^build_image ([a-z0-9-]+) ", publisher, re.MULTILINE))
    assert len(published) == 13
    assert "docker build --provenance=false" in publisher


@pytest.mark.parametrize("fresh_candidate", [False, True])
def test_private_candidate_does_not_move_latest(
    tmp_path: Path, fresh_candidate: bool
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "seat-disk.qcow2").write_bytes(b"disk")
    (out / "seat-image-config.json").write_bytes(b"{}")
    subprocess.run([sys.executable, str(ROOT / "scripts/appliance/seat-build-record.py"),
                    "write", str(out), "--commit", "a" * 40, "--dirty", "0"], check=True)
    manifest = {
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.aptl.seat.config.v1+json",
                   "digest": "sha256:" + hashlib.sha256(b"{}").hexdigest(), "size": 2},
        "layers": [{"mediaType": "application/vnd.aptl.seat.disk.v1+qcow2",
                    "digest": "sha256:" + hashlib.sha256(b"disk").hexdigest(), "size": 4}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_bytes = json.dumps(manifest).encode()
    manifest_path.write_bytes(manifest_bytes)
    manifest_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    binary = tmp_path / "bin"
    binary.mkdir()
    stubs = {
        "oras": """#!/bin/sh
case "$1" in
  login) cat >/dev/null ;;
  resolve)
    if test "$APTL_TEST_FRESH_CANDIDATE" = 1 && ! test -f "$APTL_TEST_PUSH_LOG"; then
      exit 1
    fi
    case "$2" in *:v5.6.0) exit 1 ;; esac
    printf '%s\\n' "$APTL_TEST_MANIFEST_DIGEST" ;;
  push) printf '%s\\n' "$@" > "$APTL_TEST_PUSH_LOG" ;;
  manifest) cp "$APTL_TEST_MANIFEST" "$5" ;;
  tag) printf 'tag\\n' >> "$APTL_TEST_ORAS_LOG" ;;
esac
""",
        "curl": """#!/bin/sh
printf 'request\\n' >> "$APTL_TEST_CURL_LOG"
case "${*}" in
  *'/token?'*) printf '{"token":"anonymous"}\\n' ;;
  *) printf '401' ;;
esac
""",
        "jq": "#!/bin/sh\ncat >/dev/null\nprintf 'anonymous\\n'\n",
        "sha256sum": "#!/bin/sh\nif test \"$#\" -eq 0; then cat >/dev/null; fi\nprintf '%064d  -\\n' 0\n",
        "cosign": "#!/bin/sh\nprintf 'unexpected signature attempt' > \"$APTL_TEST_COSIGN_LOG\"\nexit 1\n",
        "sleep": "#!/bin/sh\nexit 0\n",
    }
    for name, body in stubs.items():
        path = binary / name
        path.write_text(body)
        path.chmod(0o755)
    log = tmp_path / "oras.log"
    result = subprocess.run(
        ["bash", str(PUBLISHER), str(out)],
        env={
            "PATH": f"{binary}:{os.environ['PATH']}",
            "APTL_SEAT_SIGNING_KEY": str(tmp_path / "fixture.key"),
            "REPOSITORY_OWNER": "Brad-Edwards",
            "GHCR_TOKEN": "test-token",
            "GITHUB_ACTOR": "test-actor",
            "APTL_TEST_ORAS_LOG": str(log),
            "APTL_TEST_FRESH_CANDIDATE": "1" if fresh_candidate else "0",
            "APTL_TEST_PUSH_LOG": str(tmp_path / "push.log"),
            "APTL_TEST_MANIFEST": str(manifest_path),
            "APTL_TEST_MANIFEST_DIGEST": manifest_digest,
            "APTL_TEST_COSIGN_LOG": str(tmp_path / "cosign.log"),
            "APTL_TEST_CURL_LOG": str(tmp_path / "curl.log"),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert manifest_digest in result.stderr
    assert "not anonymously pullable" in result.stderr
    assert not log.exists()
    assert not (tmp_path / "cosign.log").exists()
    assert len((tmp_path / "curl.log").read_text().splitlines()) <= 4
    if fresh_candidate:
        pushed = (tmp_path / "push.log").read_text().splitlines()
        assert "org.opencontainers.image.source=https://github.com/OpenRAE/lilrae" in pushed
        assert any(arg.startswith("ghcr.io/brad-edwards/aptl-seat:key-") for arg in pushed)
