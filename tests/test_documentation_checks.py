"""Exercise the pinned upstream prose checker, not copies of its rules."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).parents[1]


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


def test_no_paths_cannot_start_a_corpus_walk() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "tools/ste-lint.sh")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="Linux installer contract")
def test_installer_rejects_bad_download_before_execution(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copy(ROOT / "tools/install-ste.sh", tools)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text('#!/bin/sh\nwhile [ "$1" != "-o" ]; do shift; done\nprintf bad > "$2"\n')
    curl.chmod(0o755)
    result = subprocess.run(
        ["bash", str(tools / "install-ste.sh")],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "checksum" in result.stderr.lower()
    assert not list(tmp_path.glob(".tools/**/ste"))
