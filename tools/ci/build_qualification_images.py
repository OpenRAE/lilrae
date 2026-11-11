"""Prepare integration prerequisites from the existing CI image matrix."""

from pathlib import Path
import subprocess

import yaml


def main():
    from aptl.backends._raes_backend_implementation_catalog import BACKEND_IMPLEMENTATION_PROFILES

    dashboard = next(
        item.image_ref for item in BACKEND_IMPLEMENTATION_PROFILES
        if item.profile_id == "wazuh-dashboard-4.12"
    )
    subprocess.run(["docker", "pull", dashboard], check=True)
    subprocess.run(["docker", "image", "inspect", dashboard], check=True)
    workflow = yaml.safe_load(Path(".github/workflows/checks.yml").read_text())
    rows = workflow["jobs"]["trivy-image"]["strategy"]["matrix"]["include"]
    for row in rows:
        args = ["docker", "build", "-f", row["dockerfile"], "-t", f"aptl/{row['name']}:latest"]
        if row.get("parent_dockerfile"):
            parent = f"aptl/{row['name']}-qualification-parent:latest"
            subprocess.run([
                "docker", "build", "-f", row["parent_dockerfile"],
                "-t", parent, row["parent_context"],
            ], check=True)
            args.extend(["--build-arg", f"APTL_PARENT_IMAGE={parent}"])
        subprocess.run([*args, row["context"]], check=True)


if __name__ == "__main__":
    main()
