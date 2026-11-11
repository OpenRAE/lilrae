"""The CI lifecycle command must run with original-family code unavailable."""
from pathlib import Path
import subprocess
import sys
import re


def test_public_start_help_does_not_load_original_family_modules():
    fixture = Path(__file__).parent / 'fixtures/lilrae_core_only_cli.py'
    result = subprocess.run([sys.executable, str(fixture), 'lab', 'start', '--help'], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', result.stdout)
    assert '--scenario-path' in plain
