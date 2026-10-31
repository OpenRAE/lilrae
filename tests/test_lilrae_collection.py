"""Ordinary helper imports must have no live-lab effects."""

import runpy
import subprocess
from pathlib import Path

from aptl.core import env


def test_helper_collection_neither_reads_dotenv_nor_provisions_keys(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("collection attempted live lab I/O")

    monkeypatch.setattr(env, "load_dotenv", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    namespace = runpy.run_path(str(Path(__file__).with_name("helpers.py")))
    assert namespace["SHUFFLE_API_KEY"] == ""
    assert namespace["MISP_API_KEY"] == ""
