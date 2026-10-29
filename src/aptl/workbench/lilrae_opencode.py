"""Isolated OpenCode invocations for installed autonomous participant bindings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from raes_contracts.contracts import ParticipantConfigurationResultModel

from aptl.utils.pathsafe import create_exclusive_nofollow
from aptl.workbench.agent import (
    InventoryProbe,
    _admitted_executable,
    _prepare_work_dir,
    _load_server_config,
    _read_private_config,
    _server_environment,
    probe_mcp_server,
)
from aptl.workbench.profiles import (
    ProfileId,
    profile_for,
    verify_profile_tool_inventory,
)
from aptl.workbench.process import (
    AgentExecutionError,
    BoundedProcessRunner,
    ProcessResult,
    BoundedProcessError,
    REASON_CANCELLED,
)

_PROVIDER_ENVIRONMENT = frozenset(
    {
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
        "AZURE_OPENAI_API_KEY",
    }
)
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*/[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}\Z")


class CancellableProcessRunner(Protocol):
    """The process runner's explicit per-invocation cancellation extension."""

    def run(
        self,
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        cwd: Path,
        stdin: bytes,
        timeout_seconds: float,
        max_output_bytes: int,
        cancel_event: Event | None = None,
    ) -> ProcessResult: ...


@dataclass(frozen=True)
class OpenCodeToolProfile:
    """An admitted MCP profile and the private inputs needed to verify it."""

    profile: ProfileId
    config: Path
    credentials: Mapping[str, str] = field(default_factory=dict, repr=False)
    inventory_probe: InventoryProbe = probe_mcp_server


@dataclass(frozen=True)
class OpenCodeOptions:
    """Operator-owned launch settings, separate from participant configuration."""

    executable: Path
    work_root: Path
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    max_output_bytes: int = 1_000_000
    runner: CancellableProcessRunner | None = None
    tools: OpenCodeToolProfile | None = None


def _validate_provider_environment(environment: Mapping[str, str]) -> None:
    """Permit only explicit provider credentials without ambient configuration."""
    if set(environment) - _PROVIDER_ENVIRONMENT:
        raise ValueError("participant provider environment is not admitted")
    if any(
        not isinstance(value, str) or not value or "\0" in value
        for value in environment.values()
    ):
        raise ValueError("participant provider environment is invalid")


def _validate_invocation_inputs(
    model: str, prompt: str, timeout_seconds: float, max_output_bytes: int
) -> None:
    """Bound participant inputs before any process or tool probe starts."""
    if (
        not _MODEL.fullmatch(model)
        or not prompt.strip()
        or len(prompt.encode()) > 128_000
    ):
        raise ValueError("participant model or prompt is invalid")
    if (
        not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 3600
        or not 0 < max_output_bytes <= 1_000_000
    ):
        raise ValueError("participant execution limits are invalid")


class LilraeOpenCodeExecutor:
    """Run one bounded prompt with no ambient workspace, history, or tools.

    Provider credentials are explicit management inputs. They are never read
    from the host environment. Each call receives a fresh private context.
    """

    def __init__(
        self,
        *,
        options: OpenCodeOptions,
        model: str,
        prompt: str,
        timeout_seconds: float,
        configuration_result: ParticipantConfigurationResultModel | None = None,
    ) -> None:
        """Validate participant configuration and verify tools before dispatch."""
        _validate_provider_environment(options.environment)
        _validate_invocation_inputs(
            model, prompt, timeout_seconds, options.max_output_bytes
        )
        self._executable = _admitted_executable(options.executable)
        self._work_root = _prepare_work_dir(options.work_root)
        self._model = model
        self._prompt = prompt.encode("utf-8")
        self._prompt_sha256 = hashlib.sha256(self._prompt).hexdigest()
        self._environment = dict(options.environment)
        self._timeout_seconds = timeout_seconds
        self._configuration_result = (
            configuration_result.model_copy(deep=True)
            if configuration_result is not None
            else None
        )
        self._validate_delivery()
        self._max_output_bytes = options.max_output_bytes
        self._runner = options.runner or BoundedProcessRunner()
        self._install_profile(options.tools)
        # Tool inventory is installation/admission work, outside native action
        # dispatch. It must not delay cancellation of an already admitted action.
        self._tool_servers, self._tool_permissions = self._tools()

    def _validate_delivery(self) -> None:
        """Verify delivered model, prompt, and deadline against the sealed result."""
        if self._configuration_result is None:
            return
        values = {
            item.target_id: item.value.value
            for item in self._configuration_result.configuration.values
            if item.value.kind == "literal"
        }
        if (
            values.get("model") != self.model
            or values.get("prompt_sha256") != self.prompt_sha256
            or values.get("timeout_seconds") != self.timeout_seconds
        ):
            raise ValueError("participant delivery differs from its configuration")

    def _install_profile(self, tools: OpenCodeToolProfile | None) -> None:
        """Require the private server configuration to match the selected profile."""
        self._profile = tools.profile if tools is not None else None
        self._profile_config = tools.config if tools is not None else None
        self._mcp_credentials = dict(tools.credentials) if tools is not None else {}
        self._inventory_probe = (
            tools.inventory_probe if tools is not None else probe_mcp_server
        )
        self._servers = {}
        self._profile_digest = ""
        if tools is not None:
            self._servers, self._profile_digest = _load_server_config(tools.config)
            if set(self._servers) != set(profile_for(tools.profile).server_ids):
                raise ValueError(
                    "participant MCP servers do not match the selected profile"
                )

    @property
    def model(self) -> str:
        return self._model

    @property
    def prompt_sha256(self) -> str:
        return self._prompt_sha256

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    @property
    def configuration_result(self) -> ParticipantConfigurationResultModel | None:
        return (
            self._configuration_result.model_copy(deep=True)
            if self._configuration_result is not None
            else None
        )

    def _tools(self) -> tuple[dict[str, object], dict[str, str]]:
        """Translate only a private, unchanged and verified profile."""
        if self._profile_config is None:
            return {}, {"*": "deny"}
        self._verify_profile_config()
        inventory = {}
        servers = {}
        for name, server in self._servers.items():
            environment = _server_environment(server, self._mcp_credentials)
            inventory[name] = self._inventory_probe(
                name, str(server["command"]), list(server["args"]), environment
            )
            servers[name] = {
                "type": "local",
                "command": [server["command"], *server["args"]],
                "environment": environment,
                "enabled": True,
            }
        verify_profile_tool_inventory(self._profile, inventory)
        permissions = {"*": "deny"}
        permissions.update(
            {
                f"{name}_{tool}": "allow"
                for name, tools in inventory.items()
                for tool in tools
            }
        )
        return servers, permissions

    def _verify_profile_config(self) -> None:
        if self._profile_config is not None and (
            hashlib.sha256(_read_private_config(self._profile_config)).hexdigest()
            != self._profile_digest
        ):
            raise AgentExecutionError("participant MCP configuration changed")

    def __call__(self, action_id: str, cancellation: Event) -> str:
        """Deliver the exact prompt on stdin and retain only terminal text."""
        # Never use an external action identity as a path.
        del action_id
        if cancellation.is_set():
            raise AgentExecutionError(REASON_CANCELLED)
        self._verify_profile_config()
        with TemporaryDirectory(
            prefix="lilrae-participant-", dir=self._work_root
        ) as directory:
            work = Path(directory)
            config = {
                "model": self.model,
                "autoupdate": False,
                "share": "disabled",
                "permission": self._tool_permissions,
                "mcp": self._tool_servers,
                "plugin": [],
                "instructions": [],
                "snapshot": False,
            }
            create_exclusive_nofollow(
                work, "opencode.json", json.dumps(config).encode()
            )
            environment = {
                "PATH": os.defpath,
                "HOME": str(work),
                "NO_COLOR": "1",
                "XDG_CONFIG_HOME": str(work / "config"),
                "XDG_DATA_HOME": str(work / "data"),
                "XDG_STATE_HOME": str(work / "state"),
                "XDG_CACHE_HOME": str(work / "cache"),
                "OPENCODE_CONFIG": str(work / "opencode.json"),
                "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
                "OPENCODE_DISABLE_CLAUDE_CODE": "true",
                "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
                "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
                "OPENCODE_DISABLE_AUTOUPDATE": "true",
                "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
                "OPENCODE_DISABLE_MODELS_FETCH": "true",
                "OPENCODE_PURE": "true",
                **self._environment,
            }
            result = self._runner.run(
                (
                    str(self._executable),
                    "run",
                    "--format",
                    "json",
                    "--model",
                    self.model,
                ),
                env=environment,
                cwd=work,
                stdin=self._prompt,
                timeout_seconds=self.timeout_seconds,
                max_output_bytes=self._max_output_bytes,
                cancel_event=cancellation,
            )
            return _supervised_result_text(result)


def _supervised_result_text(result: ProcessResult) -> str:
    """Keep cleanup proof when a terminated harness cannot supply usable output."""
    try:
        if result.returncode != 0:
            raise AgentExecutionError("participant harness exited unsuccessfully")
        return _terminal_text(result.stdout)
    except AgentExecutionError as exc:
        if result.cleanup is None:
            raise
        raise BoundedProcessError(
            str(exc),
            cleanup=result.cleanup,
            stdout_bytes=len(result.stdout),
            stderr_bytes=len(result.stderr),
        ) from None


def _terminal_text(output: bytes) -> str:
    """Parse bounded JSON events without exposing malformed provider output."""
    try:
        texts = []
        for line in output.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict) or event.get("type") == "error":
                raise ValueError("invalid provider event")
            if event.get("type") == "text":
                text = event["part"]["text"]
                if not isinstance(text, str):
                    raise ValueError("invalid provider text")
                texts.append(text)
        if not texts:
            raise ValueError("missing terminal text")
        return "\n".join(texts)
    except (ValueError, KeyError, TypeError):
        raise AgentExecutionError("participant harness output is invalid") from None
