"""Isolated OpenCode invocations for installed autonomous participant bindings."""

from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts import ParticipantConfigurationResultModel
    from aptl.core.participant_tools.contracts import ToolSession

from raes_contracts.contracts import ParticipantImplementationManifestModel
from aptl.core.opencode import OpenCodeInvocationEvidence
from aptl.workbench.opencode_capture import (
    admitted_capture,
    prepare_capture,
    retain_native_observations,
    retain_tool_event,
)
from aptl.core.trial_readiness import ParticipantReadiness
from aptl.utils.pathsafe import create_exclusive_nofollow
from aptl.workbench.agent import (
    _admitted_executable,
    _load_server_config,
    _prepare_work_dir,
    _read_private_config,
    _server_environment,
    probe_mcp_server,
)
from aptl.workbench.opencode_configuration import (
    opencode_arguments,
    opencode_environment,
    render_opencode_config,
    validate_invocation_inputs,
    validate_provider_environment,
)
from aptl.workbench.opencode_events import (
    _supervised_result_text,
)
from aptl.workbench.participant_request import validate_opencode_request
from aptl.workbench.process import (
    REASON_CANCELLED,
    AgentExecutionError,
    BoundedProcessError,
    BoundedProcessRunner,
    ProcessRequest,
    run_request,
)
from aptl.workbench.profiles import profile_for, verify_profile_tool_inventory
from aptl.workbench.opencode_evidence import (
    OpenCodeRunState,
    invocation_recorder,
    invocation_servers,
)
from aptl.workbench.opencode_observation import (
    install_request_observer,
)
from aptl.workbench.provider_readiness import (
    openrouter_access_ready,
    probe_opencode_version,
)
from aptl.workbench.opencode_history import export_native_session
from aptl.workbench.opencode_options import OpenCodeOptions, OpenCodeToolProfile
from aptl.workbench.provider_capture import redact_capture_value
from aptl.utils.logging import get_logger

__all__ = ["LilraeOpenCodeExecutor", "OpenCodeOptions", "OpenCodeToolProfile"]

logger = get_logger("workbench.opencode")


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
        validate_provider_environment(options.environment, options.route)
        validate_invocation_inputs(
            model,
            prompt,
            timeout_seconds,
            options.max_output_bytes,
            options.max_output_tokens,
        )
        if options.route is None or not options.route.admits(model):
            raise ValueError("an explicit provider route that admits the model is required")
        self._build = options.build
        self._route = options.route
        self._tool_governance = options.tool_governance
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
        self._capture = admitted_capture(options.capture, self._configuration_result)
        self._transcript_sink = options.transcript_sink
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
        self._evidence = invocation_recorder(
            options, self.model, self.prompt_sha256, self._configuration_result
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
        if self._configuration_result is None or self._request is not None:
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

    def check_readiness(self, expected_version: str) -> bool:
        """Verify the selected build and approved access without sending a task."""
        if expected_version != self._build.version:
            return False
        self._check_launch(Event())
        self._validate_delivery()
        return probe_opencode_version(
            self._runner,
            self._executable,
            self._work_root,
            expected_version,
            self.timeout_seconds,
        ) and openrouter_access_ready(
            self.model, self._route, self._environment, self._max_output_tokens
        )

    def readiness_owner(
        self, manifest: ParticipantImplementationManifestModel
    ) -> ParticipantReadiness:
        """Expose actual complete settings and this harness's bounded probe."""

        def configuration() -> ParticipantConfigurationResultModel:
            """Return the complete configuration after verifying its delivery."""
            current = self.configuration_result
            if current is None:
                raise ValueError("participant-configuration-unavailable")
            self._validate_delivery()
            return current

        return ParticipantReadiness(
            manifest.model_copy(deep=True),
            configuration,
            lambda: self.check_readiness(self._build.version),
        )

    def _install_profile(self, tools: OpenCodeToolProfile | None) -> None:
        """Require the private server configuration to match the selected profile."""
        self._profile = None
        self._profile_config = tools.config if tools is not None else None
        self._mcp_credentials = dict(tools.credentials) if tools is not None else {}
        self._inventory_probe = (
            tools.inventory_probe if tools is not None else probe_mcp_server
        )
        self._servers = {}
        self._profile_digest = ""
        if tools is not None:
            self._profile = profile_for(tools.profile, server_ids=tools.server_ids)
            self._servers, self._profile_digest = _load_server_config(tools.config)
            if set(self._servers) != set(self._profile.server_ids):
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

    @property
    def tool_evidence_sink(self) -> Callable[[Mapping[str, object]], None] | None:
        return self.observe_tool_event if self._capture is not None else None

    def observe_tool_event(self, event: Mapping[str, object]) -> None:
        """Retain tool observations with both provider and MCP credentials removed."""
        retain_tool_event(
            self._capture,
            event,
            tuple(self._environment.values()) + tuple(self._mcp_credentials.values()),
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
        """Run without a tool session only with no tools or an explicit allowlist."""
        if self._tool_servers and self._tool_governance != "allowlist":
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

    def _run_in_context(
        self,
        work: Path,
        servers: dict[str, object],
        cancellation: Event,
        state: OpenCodeRunState,
        action_id: str,
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
        capture_lease = prepare_capture(
            work,
            self._capture,
            action_id,
            route=self._route,
            credentials=self._environment,
            prompt=self._prompt,
            request_observer=self._request_observation_required,
        )
        expected_controls = None
        if self._request_observation_required:
            environment, expected_controls = install_request_observer(
                work,
                config,
                environment,
                self._prompt,
                capture=capture_lease.observer_options if capture_lease else None,
            )
        elif capture_lease is not None:
            capture_lease.configure(config, environment)
        create_exclusive_nofollow(work, "opencode.json", json.dumps(config).encode())
        try:
            request = ProcessRequest(
                opencode_arguments(self._executable, self.model),
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
                state.result = run_request(request, self._runner)
        except BoundedProcessError as exc:
            state.error = exc
            raise
        finally:
            retain_native_observations(
                work,
                state,
                self._prompt,
                self.model,
                expected_controls,
                self._request_observation_required,
                capture_lease,
            )
            self._retain_transcript(work)

    def _retain_transcript(self, work: Path) -> None:
        """Pass the redacted native session to the transcript sink, if any."""
        if self._transcript_sink is None:
            return
        session = export_native_session(work)
        if session is None:
            logger.warning("participant native session was not exported")
            return
        secrets = tuple(self._environment.values()) + tuple(
            self._mcp_credentials.values()
        )
        try:
            self._transcript_sink(redact_capture_value(session, secrets))
        except Exception as exc:
            # Never mask the invocation outcome.
            logger.warning(
                "participant native session was not retained: %s", type(exc).__name__
            )

    def _run(
        self, action_id: str, cancellation: Event, tools: ToolSession | None = None
    ) -> str:
        """Retain partial evidence for launch, provider and teardown failures."""
        state = OpenCodeRunState()
        try:
            self._check_launch(cancellation)
            with ExitStack() as stack:
                servers = invocation_servers(
                    stack,
                    tools,
                    self._tool_servers,
                    state,
                    allowlisted=self._tool_governance == "allowlist",
                )
                directory = stack.enter_context(
                    TemporaryDirectory(
                        prefix="lilrae-participant-", dir=self._work_root
                    )
                )
                self._run_in_context(
                    Path(directory), servers, cancellation, state, action_id
                )
                text = _supervised_result_text(state.result)
                state.require_observations(self._native_history_required)
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
