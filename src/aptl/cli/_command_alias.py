"""Deprecation notices for the registered legacy command aliases.

``lilrae`` and ``lilrae-misp-suricata-sync`` are the primary package scripts.
The package also registers ``aptl`` and ``aptl-misp-suricata-sync`` for compatibility.
Their removal is tracked by issue #1403.
Each alias writes one fixed stderr line before running the shared implementation.
The notice preserves stdout and the implementation's exit status.

The module avoids heavy imports because the sync daemon also imports it.
"""

from __future__ import annotations

import os
import sys

SUPPRESS_ENV = "LILRAE_SUPPRESS_APTL_DEPRECATION"
REMOVAL_RELEASE = "10.0.0"


def warn_deprecated_command(legacy: str, replacement: str) -> None:
    """Write the alias notice to stderr unless the user suppressed it.

    Only the exact value ``1`` suppresses the notice. The notice names the
    replacement and the removal release; it never echoes argv or environment
    values.
    """
    if os.environ.get(SUPPRESS_ENV) == "1":
        return
    sys.stderr.write(
        f"warning: the '{legacy}' command is deprecated and will be removed in "
        f"LilRAE {REMOVAL_RELEASE}. Use '{replacement}' instead. "
        f"Set {SUPPRESS_ENV}=1 to hide this notice.\n"
    )
    sys.stderr.flush()
