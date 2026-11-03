"""Bounded decision-only adapter for an installed Codex CLI."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from aptl.workbench.agent_usage import AgentUsage, AgentUsageRecorder

from aptl.core.config import validate_installed_participant_model_id
from aptl.utils.pathsafe import (
    PathContainmentError,
    create_exclusive_nofollow,
    read_contained_nofollow,
)
from aptl.utils.placeholders import contains_placeholder
from aptl.workbench.agent import (
    _admitted_executable,
    _prepare_work_dir,
)
from aptl.workbench.decision_schema import admit_decision_response_schema
from aptl.workbench.process import (
    AgentExecutionError,
    BoundedProcessRunner,
    ProcessRunner,
)
from aptl.workbench.agent_responses import parse_codex_result, classify_codex_failure
from aptl.workbench.runtime import AgentLaunch, DecisionAgentLaunch
from aptl.workbench.participant_request import validate_request, request_arguments

_MODEL_CREDENTIAL = "CODEX_API_KEY"
_BASE_ENVIRONMENT = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "NO_COLOR": "1",
}
_SCHEMA_SEAL_ERROR = "agent output schema could not be sealed"


@dataclass
class _CodexHandle:
    """Represent CodexHandle state."""

    launch: DecisionAgentLaunch
    environment: dict[str, str]
    ready: bool = False
    closed: bool = False
    usage: AgentUsage = AgentUsage()


class CodexManagedAgentAdapter:
    """Invoke Codex in an empty, read-only, ephemeral decision compartment."""

    def __init__(
        self,
        *,
        codex_executable: Path,
        work_dir: Path,
        runner: ProcessRunner | None = None,
        timeout_seconds: float = 120.0,
        max_output_bytes: int = 1_000_000,
        max_prompt_chars: int = 64_000,
    ) -> None:
        """Initialize an admitted Codex executable in an ephemeral home."""

        if timeout_seconds <= 0 or max_output_bytes <= 0 or max_prompt_chars <= 0:
            raise AgentExecutionError("agent limits are invalid")
        self._executable = _admitted_executable(codex_executable)
        self._work_dir = _prepare_work_dir(work_dir)
        self._private_home = _prepare_work_dir(self._work_dir / "home")
        self._xdg_config_home = _prepare_work_dir(self._private_home / ".config")
        self._codex_home = _prepare_work_dir(self._work_dir / "codex-home")
        self._runner = runner or BoundedProcessRunner()
        self._usage = AgentUsageRecorder("codex")
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._max_prompt_chars = max_prompt_chars

    def launch(
        self,
        launch: AgentLaunch,
        credentials: Mapping[str, str],
    ) -> object:
        """Create a decision-only handle backed by a minimal binding."""

        if not isinstance(launch, DecisionAgentLaunch):
            raise AgentExecutionError("Codex adapter supports decision-only launches")
        if launch.provider != "codex":
            raise AgentExecutionError("agent launch provider does not match adapter")
        validate_request(
            launch.request, provider="codex", model=launch.model,
            executable=self._executable, binding=launch.request_binding,
        )
        try:
            validate_installed_participant_model_id(launch.provider, launch.model)
        except ValueError as exc:
            raise AgentExecutionError("agent model selection is invalid") from exc
        credential = credentials.get(_MODEL_CREDENTIAL)
        if not credential or contains_placeholder(credential):
            raise AgentExecutionError("agent credential binding is incomplete")
        environment = {
            **_BASE_ENVIRONMENT,
            "HOME": str(self._private_home),
            "XDG_CONFIG_HOME": str(self._xdg_config_home),
            "CODEX_HOME": str(self._codex_home),
            _MODEL_CREDENTIAL: credential,
        }
        return _CodexHandle(launch=launch, environment=environment)

    @staticmethod
    def list_tools(
        handle: object,
    ) -> Mapping[str, Collection[str]]:
        """Expose the intentionally empty action-tool inventory."""

        active = _require_handle(handle)
        if active.closed:
            raise AgentExecutionError("agent profile is closed")
        active.ready = True
        return {}

    def credential_isolation_controls(self, handle: object) -> tuple[str, ...]:
        """Return only the credential controls this adapter actually enforces."""

        active = _require_handle(handle)
        if active.closed:
            raise AgentExecutionError("credential isolation controls are unavailable")
        expected = {
            **_BASE_ENVIRONMENT,
            "HOME": str(self._private_home),
            "XDG_CONFIG_HOME": str(self._xdg_config_home),
            "CODEX_HOME": str(self._codex_home),
        }
        if any(active.environment.get(name) != value for name, value in expected.items()):
            raise AgentExecutionError("credential isolation controls are incomplete")
        if set(active.environment) != {*expected, _MODEL_CREDENTIAL}:
            raise AgentExecutionError("credential isolation controls are incomplete")
        return (
            "minimal-child-environment",
            "private-home",
            "private-codex-home",
            "codex-user-config-disabled",
            "codex-ephemeral-mode",
        )

    def respond(
        self,
        handle: object,
        message: str,
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> str:
        """Obtain one bounded structured decision from the installed provider."""

        active = _require_handle(handle)
        if active.closed or not active.ready:
            raise AgentExecutionError("agent profile is not ready")
        validate_request(
            active.launch.request, provider="codex", model=active.launch.model,
            executable=self._executable, binding=active.launch.request_binding,
        )
        if active.launch.request is not None:
            message = active.launch.request.prompt + message
        schema_json = admit_decision_response_schema(
            active.launch,
            response_schema,
        )
        if schema_json is None:
            raise AgentExecutionError("agent response schema is required")
        schema_path = self._sealed_output_schema(schema_json)
        if not message or len(message) > self._max_prompt_chars:
            raise AgentExecutionError(
                "participant message exceeds the configured limit"
            )
        active.usage = AgentUsage()
        result = self._runner.run(
            self._argv(self._executable, active, schema_path),
            env=dict(active.environment),
            cwd=self._work_dir,
            stdin=message.encode(),
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
        )
        active.usage = self._usage.record(active.launch, result)
        if result.returncode != 0:
            raise AgentExecutionError(classify_codex_failure(result.stdout))
        return parse_codex_result(result.stdout)

    @staticmethod
    def usage(handle: object) -> AgentUsage:
        """Return only the latest invocation's reported token counters."""
        return _require_handle(handle).usage

    def _sealed_output_schema(self, schema_json: str) -> Path:
        """Create or verify one private schema file keyed by its exact bytes."""

        schema_bytes = (schema_json + "\n").encode()
        schema_name = (
            "participant-selection-"
            f"{hashlib.sha256(schema_bytes).hexdigest()}.schema.json"
        )
        try:
            create_exclusive_nofollow(
                self._work_dir,
                schema_name,
                schema_bytes,
            )
        except FileExistsError:
            try:
                existing = read_contained_nofollow(self._work_dir, schema_name)
            except PathContainmentError as exc:
                raise AgentExecutionError(_SCHEMA_SEAL_ERROR) from exc
            if not hmac.compare_digest(existing, schema_bytes):
                raise AgentExecutionError(_SCHEMA_SEAL_ERROR)
        except PathContainmentError as exc:
            raise AgentExecutionError(_SCHEMA_SEAL_ERROR) from exc
        return self._work_dir / schema_name

    @staticmethod
    def close(handle: object) -> None:
        """Destroy the handle's credential-bearing environment."""

        active = _require_handle(handle)
        active.environment.clear()
        active.ready = False
        active.closed = True

    @staticmethod
    def _argv(
        executable: Path,
        handle: _CodexHandle,
        response_schema_path: Path,
    ) -> tuple[str, ...]:
        """Build the tool-disabled Codex invocation."""

        return (
            str(executable),
            "exec",
            "--model",
            handle.launch.model,
            "--disable",
            "shell_tool",
            "--disable",
            "unified_exec",
            "--disable",
            "code_mode_host",
            "--disable",
            "browser_use",
            "--disable",
            "computer_use",
            "--disable",
            "apps",
            "--disable",
            "multi_agent",
            "--disable",
            "image_generation",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "--output-schema",
            str(response_schema_path),
            "--json",
            *request_arguments(handle.launch.request),
            "-",
        )


def _require_handle(handle: object) -> _CodexHandle:
    """Handle handle for the bounded participant workflow."""
    if not isinstance(handle, _CodexHandle):
        raise AgentExecutionError("unknown agent handle")
    return handle



__all__ = ("CodexManagedAgentAdapter",)
