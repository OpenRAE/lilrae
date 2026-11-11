"""Deprecation notice for the legacy ``aptl`` command names.

The ADR-062 successor clause for issue #1402 makes ``lilrae`` and
``lilrae-misp-suricata-sync`` the primary commands. ``aptl`` and
``aptl-misp-suricata-sync`` stay as aliases until the removal release (#1403).
An alias writes one fixed line to stderr per invocation and then runs the same
implementation, so stdout and the exit status do not change.

This module imports nothing heavy: the sync daemon uses it too.
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
