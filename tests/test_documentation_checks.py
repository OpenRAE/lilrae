"""Exercise the pinned upstream prose checker, not copies of its rules."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).parents[1]


def _consumer(tmp_path: Path) -> Path:
    """Create a consumer without a tool cache or personal skill installation."""
    root = tmp_path / "consumer with spaces"
    tools = root / "tools"
    tools.mkdir(parents=True)
    for name in ("install-doc-tools.sh", "install-ste.sh", "ste-lint.sh"):
        shutil.copy(ROOT / "tools" / name, tools)
    return root


def test_clean_setup_checks_a_caller_relative_page(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    caller = tmp_path / "author directory"
    caller.mkdir()
    page = caller / "changed page.md"
    original = "Read the instructions. Then start the lab.\n"
    page.write_text(original)
    result = subprocess.run(
        ["bash", str(root / "tools/ste-lint.sh"), "--format", "json", page.name],
        cwd=caller, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["findings"] == []
    assert page.read_text() == original
    packages = list((root / ".tools/doc-tools").glob("*/THIRD_PARTY_NOTICES.md"))
    assert len(packages) == 1
    package = packages[0].parent
    for notice in ("LICENSE", "skills/documentation/LICENSE"):
        assert (package / notice).is_file()


def test_bad_package_checksum_stops_before_extraction(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text(
        '#!/bin/sh\nwhile [ "$1" != "-o" ]; do shift; done\nprintf bad > "$2"\n'
    )
    curl.chmod(0o755)
    extracted = tmp_path / "extracted"
    tar = fake_bin / "tar"
    tar.write_text(f'#!/bin/sh\ntouch "{extracted}"\nexit 1\n')
    tar.chmod(0o755)
    result = subprocess.run(
        ["bash", str(root / "tools/install-ste.sh")],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert not extracted.exists()
    assert not list(root.glob(".tools/**/ste"))
    assert "checksum" in result.stderr.lower()


def test_parallel_package_setup_activates_complete_files(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    command = ["bash", str(root / "tools/install-doc-tools.sh")]
    processes = [
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    packages = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=300)
        assert process.returncode == 0, stderr
        package = Path(stdout.strip())
        assert (package / "tools/ste-lint.sh").is_file()
        assert (package / ".ste.yml").is_file()
        assert (package / "THIRD_PARTY_NOTICES.md").is_file()
        packages.append(package)
    assert packages[0] == packages[1]


def test_no_input_refuses_before_package_download(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    result = subprocess.run(
        ["bash", str(root / "tools/ste-lint.sh")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert not (root / ".tools").exists()


def _lint(text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / "tools/ste-lint.sh"), "--format", "json", "-"],
        input=text, text=True, capture_output=True, check=False,
    )


def test_selected_rules_fail_and_corrected_sample_passes() -> None:
    negative = (
        "You can't start the lab until you have read all of the instructions "
        "and verified every prerequisite on the host that will run the lab for this exercise.\n\n"
        "The lab has a network. It has a server. It has a client. "
        "It has a router. It has a log. It has a clock. It has a disk.\n"
    )
    failed = _lint(negative)
    assert failed.returncode == 1, failed.stderr
    report = json.loads(failed.stdout)
    assert {finding["rule_id"] for finding in report["findings"]} == {
        "STE-4.2", "STE-5.1", "STE-6.6",
    }
    assert all(finding["line"] > 0 for finding in report["findings"])

    corrected = _lint(
        "Read the instructions. Verify the prerequisites on the lab host. "
        "Then start the lab.\n\n"
        "The lab has a network, a server, a client, and a router.\n\n"
        "It also has a log, a clock, and a disk.\n"
    )
    assert corrected.returncode == 0, corrected.stderr
    assert json.loads(corrected.stdout)["findings"] == []


def test_markdown_literals_are_preserved(tmp_path: Path) -> None:
    original = (
        "Run `lilrae lab start --help`.\n\n"
        "```shell\n# You can't rewrite literal commands.\n"
        "lilrae lab start --help\n```\n"
    )
    sample = tmp_path / "literal.md"
    sample.write_text(original)
    result = subprocess.run(
        ["bash", str(ROOT / "tools/ste-lint.sh"), str(sample)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert sample.read_text() == original


def test_ci_corpus_command_keeps_findings_advisory(tmp_path: Path) -> None:
    """Run the configured CI report command against one failing page."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/checks.yml").read_text())
    step = next(
        step for step in workflow["jobs"]["docs"]["steps"]
        if step.get("name") == "STE corpus report (legacy findings are advisory)"
    )
    command = shlex.split(step["run"])
    command = command[command.index("bash"):]
    command[1] = str(ROOT / command[1])
    page = tmp_path / "legacy.md"
    page.write_text("You can't start the lab.\n")
    result = subprocess.run(
        [*command, str(page)], cwd=tmp_path,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "STE-4.2" in result.stdout


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="Linux installer contract")
def test_installer_rejects_bad_download_before_execution(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    setup = subprocess.run(
        ["bash", str(root / "tools/install-doc-tools.sh")],
        capture_output=True, text=True, check=False,
    )
    assert setup.returncode == 0, setup.stderr
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text('#!/bin/sh\nwhile [ "$1" != "-o" ]; do shift; done\nprintf bad > "$2"\n')
    curl.chmod(0o755)
    result = subprocess.run(
        ["bash", str(root / "tools/install-ste.sh")],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "checksum" in result.stderr.lower()
    assert not list(root.glob(".tools/**/ste"))
