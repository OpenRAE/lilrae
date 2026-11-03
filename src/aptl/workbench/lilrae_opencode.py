"""Isolated OpenCode invocations for installed autonomous participant bindings."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts import ParticipantConfigurationResultModel
    from aptl.core.participant_tools.contracts import ToolSession

from aptl.utils.pathsafe import create_exclusive_nofollow
from aptl.core.opencode import (
    OpenCodeInvocationEvidence,
)
from aptl.workbench.opencode_events import (
    parse_opencode_response,
    _supervised_result_text,
)
from aptl.workbench.opencode_configuration import (
    render_opencode_config,
    opencode_environment,
    PROVIDER_CREDENTIAL_NAMES,
    validate_provider_environment,
    validate_invocation_inputs,
)
from aptl.workbench.agent import (
    _admitted_executable,
    _prepare_work_dir,
    _load_server_config,
    _read_private_config,
    _server_environment,
    probe_mcp_server,
)
from aptl.workbench.profiles import (
    profile_for,
    verify_profile_tool_inventory,
)
from aptl.workbench.process import (
    AgentExecutionError,
    BoundedProcessRunner,
    BoundedProcessError,
    REASON_CANCELLED,
    ProcessRequest,
)
from aptl.workbench.participant_request import validate_opencode_request
from aptl.workbench.opencode_history import read_native_history
from aptl.workbench.opencode_evidence import OpenCodeEvidenceRecorder, OpenCodeRunState
from aptl.workbench.opencode_observation import (
    OBSERVER_CREDENTIAL,
    install_request_observer,
    read_request_observations,
)


# Existing public launch types remain available from this module.
from aptl.workbench.opencode_options import OpenCodeOptions, OpenCodeToolProfile

__all__ = ["LilraeOpenCodeExecutor", "OpenCodeOptions", "OpenCodeToolProfile"]


class LilraeOpenCodeExecutor:
    """Run a bounded prompt with explicit credentials and a fresh private context."""

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
        validate_provider_environment(options.environment)
        validate_invocation_inputs(
            model,
            prompt,
            timeout_seconds,
            options.max_output_bytes,
            options.max_output_tokens,
        )
        if options.route is None or not model.startswith("openrouter/"):
            raise ValueError("explicit OpenRouter route and model are required")
        self._build = options.build
        self._route = options.route
        self._native_history_required = options.native_history_required
        self._request_observation_required = options.request_observation_required
        self._max_output_tokens = options.max_output_tokens
        self._executable = _admitted_executable(options.executable)
        self._work_root = _prepare_work_dir(options.work_root)
        self._model = model
        self._prompt = prompt.encode("utf-8")
        self._prompt_sha256 = hashlib.sha256(self._prompt).hexdigest()
        self._environment = dict(options.environment)
        self._closed = False
        self._timeout_seconds = timeout_seconds
        self._set_limits(options)
        self._configuration_result = (
            configuration_result.model_copy(deep=True)
            if configuration_result is not None
            else None
        )
        self._request = options.request
        self._request_binding = options.request_binding
        validate_opencode_request(
            self._request,
            model=model,
            prompt=prompt,
            build=options.build,
            route=self._route,
            output_limit=self._max_output_tokens,
            binding=self._request_binding,
        )
        if (
            self._request is not None
            and self._request.configuration_result != self._configuration_result
        ):
            raise ValueError(
                "participant request differs from its sealed configuration"
            )
        self._validate_delivery()
        self._max_output_bytes = options.max_output_bytes
        self._runner = options.runner or BoundedProcessRunner()
        self._install_profile(options.tools)
        # Tool inventory is installation/admission work, outside native action
        # dispatch. It must not delay cancellation of an already admitted action.
        self._tool_servers, self._tool_permissions = self._tools()
        self._evidence = OpenCodeEvidenceRecorder(
            OpenCodeInvocationEvidence(
                action_id="",
                build=self._build,
                requested_model=self.model,
                endpoint=self._route.endpoint,
                requested_serving_provider=self._route.serving_provider,
                prompt_sha256=self.prompt_sha256,
                status="not-started",
                participant_address=self._configuration_result.participant_address
                if self._configuration_result is not None
                else None,
                configuration_digest=self._configuration_result.configuration_digest
                if self._configuration_result is not None
                else None,
                trial_scope=options.trial_scope,
            ),
            options.evidence_sink,
        )

    def _set_limits(self, options: OpenCodeOptions) -> None:
        """Retain the original monotonic deadline and exact native turn pin."""
        if options.max_steps is not None and (
            type(options.max_steps) is not int or not 1 <= options.max_steps <= 10_000
        ):
            raise ValueError("participant native turn bound is invalid")
        self._max_steps = options.max_steps
        self._deadline = options.deadline
        self._clock = options.clock
        self._monotonic_deadline = None
        if self._deadline is not None:
            remaining = (self._deadline - self._clock()).total_seconds()
            if remaining <= 0:
                raise ValueError("participant attempt deadline is exhausted")
            self._monotonic_deadline = monotonic() + remaining
        if options.request is not None:
            turns = options.request.profile.assistant_turn_limit
            if turns is not None and turns.value != self._max_steps:
                raise ValueError(
                    "participant native assistant turn limit differs from its pin"
                )

    @property
    def tool_inventory(self) -> frozenset[tuple[str, str]]:
        """Exact installed inventory, independent of an invocation's authority."""
        return self._tool_inventory

    def _validate_delivery(self) -> None:
        """Verify delivered model, prompt, and deadline against the sealed result."""
        if self._configuration_result is None:
            return
        if self._request is not None:
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
            or values.get("gateway_endpoint") != self._route.endpoint
            or values.get("serving_provider") != self._route.serving_provider
            or values.get("max_output_tokens") != self._max_output_tokens
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
        if self._deadline is not None:
            return max(
                0,
                min(
                    self._timeout_seconds,
                    (self._deadline - self._clock()).total_seconds(),
                    self._monotonic_deadline - monotonic(),
                ),
            )
        return self._timeout_seconds

    @property
    def last_evidence(self) -> OpenCodeInvocationEvidence | None:
        """Retain the last safe observation even without an external evidence sink."""
        return self._evidence.last

    def close(self) -> None:
        """Drop owned credential copies after the trial owner drains native work."""
        self._closed = True
        self._environment.clear()
        self._mcp_credentials.clear()
        self._tool_servers.clear()

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
            self._tool_inventory = frozenset()
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
        self._tool_inventory = frozenset(
            (server, tool) for server, tools in inventory.items() for tool in tools
        )
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
        """Preserve ordinary no-tool invocations; refuse ungoverned tool launch."""
        if self._tool_servers:
            raise AgentExecutionError("Participant tool session is required.")
        return self._run(action_id, cancellation)

    def invoke_with_tools(
        self, action_id: str, cancellation: Event, tools: ToolSession
    ) -> str:
        """Deliver fresh server authority from the enclosing RAES invocation."""
        self._verify_profile_config()
        installed = frozenset(
            (item.server_id, item.tool_name) for item in tools.bindings
        )
        if (
            action_id != tools.invocation_action_instance_id
            or tools.cancellation is not cancellation
            or installed != self.tool_inventory
        ):
            raise AgentExecutionError(
                "Participant tool session does not match the installed profile."
            )
        return self._run(action_id, cancellation, tools)

    def _check_launch(self, cancellation: Event) -> None:
        """Refuse changed build/configuration before native work starts."""
        if self._closed:
            raise AgentExecutionError("participant OpenCode executor is closed")
        if self.timeout_seconds <= 0:
            raise AgentExecutionError("participant attempt deadline is exhausted")
        if cancellation.is_set():
            raise AgentExecutionError(REASON_CANCELLED)
        if self._request is not None:
            self._request_binding.validate(self._request)
        self._verify_profile_config()
        try:
            executable = _admitted_executable(self._executable)
            with executable.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError:
            raise AgentExecutionError(
                "participant OpenCode build is unavailable"
            ) from None
        if digest != self._build.executable_sha256:
            raise AgentExecutionError(
                "participant OpenCode build does not match its pin"
            )
        if any(Path("/etc/opencode").glob("opencode.json*")):
            raise AgentExecutionError(
                "ambient managed OpenCode configuration is not admitted"
            )

    def _invocation_servers(
        self, stack: ExitStack, tools: ToolSession | None, state: OpenCodeRunState
    ) -> dict[str, object]:
        """Open one scoped tool transport and retain its cleanup outcome."""
        if tools is None:
            return {}
        state.tool_transport_cleanup = "uncertain"
        transport = tools.transport()
        carrier = transport.__enter__()

        def close_transport(*exc: object) -> bool | None:
            """Preserve native process failure if tool transport closure also fails."""
            if isinstance(exc[1], BoundedProcessError):
                state.error = exc[1]
            try:
                outcome = transport.__exit__(*exc)
            except Exception:
                raise AgentExecutionError(
                    "participant tool transport cleanup failed"
                ) from None
            state.tool_transport_cleanup = "succeeded"
            return outcome

        stack.push(close_transport)
        servers = deepcopy(self._tool_servers)
        for name, server in servers.items():
            server["environment"].update(carrier.environment(name))
            # Native MCP children must not inherit either provider credential alias.
            server["environment"].update(
                dict.fromkeys(PROVIDER_CREDENTIAL_NAMES | {OBSERVER_CREDENTIAL}, "")
            )
        return servers

    def _run_in_context(
        self,
        work: Path,
        servers: dict[str, object],
        cancellation: Event,
        state: OpenCodeRunState,
    ) -> None:
        """Launch once and reduce native observations before private teardown."""
        config = render_opencode_config(
            self.model,
            self._route,
            self._tool_permissions,
            servers,
            request_profile=self._request.profile
            if self._request is not None
            else None,
            max_steps=self._max_steps,
        )
        environment = opencode_environment(
            work, self._environment, self._max_output_tokens
        )
        expected_controls = None
        if self._request_observation_required:
            environment, expected_controls = install_request_observer(
                work, config, environment, self._prompt
            )
        create_exclusive_nofollow(work, "opencode.json", json.dumps(config).encode())
        try:
            request = ProcessRequest(
                (
                    str(self._executable),
                    "run",
                    "--format",
                    "json",
                    "--model",
                    self.model,
                    "--title",
                    "lilrae-participant",
                ),
                env=environment,
                cwd=work,
                stdin=self._prompt,
                timeout_seconds=self.timeout_seconds,
                max_output_bytes=self._max_output_bytes,
                cancel_event=cancellation,
            )
            if isinstance(self._runner, BoundedProcessRunner):
                state.result = self._runner.run_observed(
                    request, failure_stdout_observer=state.retain_partial
                )
            else:
                state.result = request.run_with(self._runner)
        except BoundedProcessError as exc:
            state.error = exc
            raise
        finally:
            native_response = state.partial or parse_opencode_response(
                state.result.stdout if state.result else b""
            )
            state.native_history = read_native_history(
                work,
                expected_prompt=self._prompt,
                expected_model=self.model,
                session_id=native_response.session_id,
            )
            if self._request_observation_required:
                state.request_observation = read_request_observations(
                    work,
                    expected_controls=expected_controls,
                    expected_prompt_sha256=self.prompt_sha256,
                )

    def _require_observations(self, state: OpenCodeRunState) -> None:
        """Refuse missing required evidence without confusing it with selected intent."""
        observation, history = state.request_observation, state.native_history
        if observation is not None and observation.status != "observed":
            raise AgentExecutionError(
                "participant provider request evidence is unavailable"
            )
        if history.status == "invalid" or (
            self._native_history_required and history.status != "observed"
        ):
            raise AgentExecutionError("participant native delivery evidence is invalid")

    def _run(
        self, action_id: str, cancellation: Event, tools: ToolSession | None = None
    ) -> str:
        """Retain partial evidence for launch, provider and teardown failures."""
        state = OpenCodeRunState()
        try:
            self._check_launch(cancellation)
            with ExitStack() as stack:
                servers = self._invocation_servers(stack, tools, state)
                directory = stack.enter_context(
                    TemporaryDirectory(
                        prefix="lilrae-participant-", dir=self._work_root
                    )
                )
                self._run_in_context(Path(directory), servers, cancellation, state)
                text = _supervised_result_text(state.result)
                self._require_observations(state)
        except Exception as exc:
            if isinstance(exc, BoundedProcessError):
                state.error = exc
            self._evidence.record(action_id, "failed", state)
            if isinstance(exc, (BoundedProcessError, AgentExecutionError)):
                raise
            raise AgentExecutionError(
                "participant private context or launch failed"
            ) from None
        self._evidence.record(action_id, "succeeded", state)
        return text
