"""Check the declared participant adapter dependency boundary against Python ASTs.

This is a source dependency check, not an information-flow proof. Runtime
conformance tests independently check native effects and accepted histories.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys


COMPONENTS = {
    "src/aptl/backends/participant_tools/delivery.py": frozenset(
        {
            "__future__",
            "aptl.backends.participant_tools.session",
            "aptl.backends.participant_tools.transport",
            "aptl.core.agent_errors",
            "aptl.core.mcp_results",
            "aptl.core.participant_tools.contracts",
            "collections.abc",
            "concurrent.futures",
            "dataclasses",
            "raes_contracts.canonical",
            "raes_contracts.contracts",
            "raes_contracts.participant_binding",
            "raes_contracts.participant_native_execution",
            "raes_contracts.runtime_state",
            "raes_contracts.satisfiability",
            "raes_processor.models",
            "raes_runtime.control_plane",
            "raes_runtime.control_plane_security",
            "raes_runtime.participant_crossing_mediation",
            "threading",
            "typing",
            "uuid",
        }
    ),
    "src/aptl/core/participant_tools/model.py": frozenset(
        {
            "dataclasses",
            "enum",
            "typing",
        }
    ),
    "src/aptl/backends/participant_tools/session.py": frozenset(
        {
            "__future__",
            "collections.abc",
            "copy",
            "dataclasses",
            "hashlib",
            "json",
            "re",
            "threading",
            "rfc8785",
            "raes_backend_protocols.capabilities",
            "raes_backend_protocols.participant_invocation_tools",
            "raes_contracts.contracts",
            "raes_contracts.canonical",
            "raes_contracts.participant_tool_actions",
            "aptl.core.participant_tools.model",
            "aptl.core.mcp_results",
            "aptl.core.agent_errors",
            "aptl.core.participant_tools.contracts",
            "aptl.backends.participant_tools.transport",
        }
    ),
    "src/aptl/backends/participant_tools/transport.py": frozenset(
        {
            "__future__",
            "hmac",
            "json",
            "os",
            "pathlib",
            "secrets",
            "socket",
            "socketserver",
            "tempfile",
            "threading",
            "aptl.core.participant_tools.contracts",
            "typing",
            "pydantic",
        }
    ),
}


def check_component(path: str, source: str) -> list[str]:
    """Refuse imports outside the component's reviewed dependency set."""
    allowed = COMPONENTS[path]
    findings = []
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module if not node.level else "relative-import"]
            if any(alias.name == "*" for alias in node.names):
                findings.append(
                    f"{path}:{node.lineno}: wildcard import obscures ownership"
                )
        elif isinstance(node, ast.Name) and node.id in {"__import__", "eval", "exec"}:
            findings.append(f"{path}:{node.lineno}: dynamic code obscures ownership")
        for module in modules:
            if module not in allowed:
                findings.append(f"{path}:{node.lineno}: undeclared dependency {module}")
    return findings


def check_repository(root: Path) -> list[str]:
    findings = []
    for path in COMPONENTS:
        source = root / path
        if not source.is_file():
            findings.append(f"{path}: missing component")
        else:
            findings.extend(check_component(path, source.read_text()))
    return findings


if __name__ == "__main__":
    issues = check_repository(Path(__file__).resolve().parents[1])
    for issue in issues:
        print(issue, file=sys.stderr)
    if not issues:
        print(
            f"Participant architecture: {len(COMPONENTS)} component boundaries passed."
        )
    raise SystemExit(bool(issues))
