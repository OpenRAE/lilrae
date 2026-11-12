"""Rebuild and qualify the immutable #1646 source snapshot, independent of HEAD."""

import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from tests.test_lilrae_scoped_tools import qualify_scoped_wheel


def main():
    repo = Path(__file__).resolve().parents[1]
    record = json.loads(
        (repo / "docs/testing/scoped-tools-1646-candidate.json").read_text()
    )
    with tempfile.TemporaryDirectory(prefix="lilrae-scoped-candidate-") as directory:
        root = Path(directory)
        archive = root / "source.tar"
        subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                "--output",
                str(archive),
                record["source_snapshot_tree"],
            ],
            cwd=repo,
            check=True,
            timeout=120,
        )
        source = root / "source"
        source.mkdir()
        with tarfile.open(archive) as stream:
            stream.extractall(source, filter="data")
        report = qualify_scoped_wheel(root, source_root=source)
        assert report["wheel"] == record["wheel"]
        assert report["sha256"] == record["wheel_sha256"]
        for coordinate in (
            "capability_sha256",
            "lilrae",
            "python",
            "raes-env-packs",
            "policy",
            "tool_semantics",
            "backend_manifest_digest",
            "implementation_manifest_digest",
            "scenario_digest",
        ):
            assert report["compatibility"][coordinate] == record[coordinate], coordinate
        assert report["compatibility"]["raes"] in record["raes"]
        print(
            "Verified immutable source snapshot, artifact bytes, installed behavior and compatibility tuple."
        )


if __name__ == "__main__":
    main()
