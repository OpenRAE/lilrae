"""Isolated OpenCode invocations for installed autonomous participant bindings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts import ParticipantConfigurationResultModel
    from aptl.core.participant_tools.contracts import ToolSession

from aptl.utils.pathsafe import create_exclusive_nofollow
from aptl.core.opencode import (
    OpenCodeBuild,
    OpenCodeInvocationEvidence,
    OpenRouterRoute,
    SUPPORTED_OPENCODE_BUILD,
)
from aptl.core.evidence.participant_capture import ParticipantCaptureArchive
from aptl.workbench.opencode_capture import OpenCodeCaptureLease
from aptl.workbench.provider_capture import redact_capture_value
from aptl.workbench.opencode_events import (
    OpenCodeResponse,
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
    REASON_TIMEOUT,
    ProcessRequest,
    CancellableProcessRunner,
)
from aptl.core.participant_requests.request import ParticipantRequest
from aptl.core.participant_requests.binding import ParticipantRequestBinding
from aptl.workbench.participant_request import validate_opencode_request


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
    max_output_tokens: int = 128
    runner: CancellableProcessRunner | None = None
    tools: OpenCodeToolProfile | None = None
    build: OpenCodeBuild = SUPPORTED_OPENCODE_BUILD
    route: OpenRouterRoute | None = None
    evidence_sink: Callable[[OpenCodeInvocationEvidence], None] | None = None
    request: ParticipantRequest | None = None
    request_binding: ParticipantRequestBinding | None = None
    capture: ParticipantCaptureArchive | None = field(default=None, repr=False)


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
        self._evidence_sink = options.evidence_sink
        self._max_output_tokens = options.max_output_tokens
        self._executable = _admitted_executable(options.executable)
        self._work_root = _prepare_work_dir(options.work_root)
        self._model = model
        self._prompt = prompt.encode("utf-8")
        self._prompt_sha256 = hashlib.sha256(self._prompt).hexdigest()
        self._environment = dict(options.environment)
        self._closed = False
        self._last_evidence: OpenCodeInvocationEvidence | None = None
        self._timeout_seconds = timeout_seconds
        self._configuration_result = (
            configuration_result.model_copy(deep=True)
            if configuration_result is not None
            else None
        )
        self._capture = options.capture
        if self._capture is not None and (
            not isinstance(self._capture, ParticipantCaptureArchive)
            or self._configuration_result is None
            or self._capture.grant.configuration_digest
            != self._configuration_result.configuration_digest
            or self._capture.grant.participant_address
            != self._configuration_result.participant_address
        ):
            raise ValueError(
                "participant capture differs from its admitted configuration"
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
        return self._timeout_seconds

    @property
    def last_evidence(self) -> OpenCodeInvocationEvidence | None:
        """Retain the last safe observation even without an external evidence sink."""
        return self._last_evidence

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
        if self._capture is None:
            return
        safe = redact_capture_value(
            dict(event),
            tuple(self._environment.values()) + tuple(self._mcp_credentials.values()),
        )
        self._capture.record_tool_event(safe)

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

    def _run(
        self, action_id: str, cancellation: Event, tools: ToolSession | None = None
    ) -> str:
        """Retain partial evidence for launch, provider, and teardown failures."""
        result = None
        partial = None
        transport_cleanup = None
        process_error = None
        partial_stdout = b""

        def retain_partial(output: bytes) -> None:
            """Reduce private failure bytes to a safe metadata snapshot."""
            nonlocal partial, partial_stdout
            partial = replace(parse_opencode_response(output), text="")
            if self._capture is not None:
                partial_stdout = output

        def close_transport(*exc: object) -> bool | None:
            """Retain transport closure status while preserving the original failure."""
            nonlocal transport_cleanup, process_error
            if isinstance(exc[1], BoundedProcessError):
                process_error = exc[1]
            try:
                outcome = transport.__exit__(*exc)
            except Exception:
                raise AgentExecutionError(
                    "participant tool transport cleanup failed"
                ) from None
            transport_cleanup = "succeeded"
            return outcome

        try:
            self._check_launch(cancellation)
            with ExitStack() as stack:
                servers = {}
                if tools is not None:
                    transport_cleanup = "uncertain"
                    transport = tools.transport()
                    carrier = transport.__enter__()
                    stack.push(close_transport)
                    servers = deepcopy(self._tool_servers)
                    for name, server in servers.items():
                        server["environment"].update(carrier.environment(name))
                        # OpenCode merges parent environment into MCP children.
                        server["environment"].update(
                            dict.fromkeys(PROVIDER_CREDENTIAL_NAMES, "")
                        )
                directory = stack.enter_context(
                    TemporaryDirectory(
                        prefix="lilrae-participant-", dir=self._work_root
                    )
                )
                work = Path(directory)
                config = render_opencode_config(
                    self.model,
                    self._route,
                    self._tool_permissions,
                    servers,
                    request_profile=self._request.profile
                    if self._request is not None
                    else None,
                )
                environment = opencode_environment(
                    work, self._environment, self._max_output_tokens
                )
                capture_lease = None
                if self._capture is not None:
                    capture_lease = OpenCodeCaptureLease(
                        work,
                        self._capture,
                        action_id,
                        self._route.endpoint,
                        self._environment,
                        self._route.serving_provider,
                        self.prompt_sha256,
                        len(self._prompt),
                    )
                    capture_lease.configure(config, environment)
                    stack.push(
                        lambda _type, exc, _tb: capture_lease.retain(
                            result.stdout if result else partial_stdout,
                            failure_reason=(exc.reason if isinstance(exc, BoundedProcessError)
                                and exc.reason in {REASON_TIMEOUT, REASON_CANCELLED}
                                else "harness-failed" if exc is not None else None),
                        )
                    )
                create_exclusive_nofollow(
                    work, "opencode.json", json.dumps(config).encode()
                )
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
                        result = self._runner.run_observed(
                            request, failure_stdout_observer=retain_partial
                        )
                    else:
                        result = request.run_with(self._runner)
                except BoundedProcessError as exc:
                    process_error = exc
                    raise
                text = _supervised_result_text(result)
        except BoundedProcessError as exc:
            self._record(action_id, "failed", result, exc, partial, transport_cleanup)
            raise
        except AgentExecutionError:
            self._record(
                action_id, "failed", result, process_error, partial, transport_cleanup
            )
            raise
        except Exception:
            self._record(
                action_id, "failed", result, process_error, partial, transport_cleanup
            )
            raise AgentExecutionError(
                "participant private context or launch failed"
            ) from None
        self._record(
            action_id, "succeeded", result, tool_transport_cleanup=transport_cleanup
        )
        return text

    def _record(
        self,
        action_id: str,
        status: str,
        result: ProcessResult | None,
        error: BoundedProcessError | None = None,
        partial: OpenCodeResponse | None = None,
        tool_transport_cleanup: str | None = None,
    ) -> None:
        """Retain safe partial metadata after process and transport cleanup."""
        response = partial or parse_opencode_response(result.stdout if result else b"")
        cleanup = None
        stdout_sha256 = None
        stdout_bytes = stderr_bytes = 0
        if result is not None:
            cleanup = result.cleanup
            stdout_sha256 = hashlib.sha256(result.stdout).hexdigest()
            stdout_bytes, stderr_bytes = len(result.stdout), len(result.stderr)
        elif error is not None:
            cleanup = error.cleanup
            stdout_sha256 = error.stdout_sha256
            stdout_bytes, stderr_bytes = error.stdout_bytes, error.stderr_bytes
        self._last_evidence = OpenCodeInvocationEvidence(
            action_id=action_id,
            build=self._build,
            requested_model=self.model,
            endpoint=self._route.endpoint,
            requested_serving_provider=self._route.serving_provider,
            prompt_sha256=self.prompt_sha256,
            status=status,
            stdout_sha256=stdout_sha256,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            partial_text_sha256=response.partial_text_sha256,
            session_id=response.session_id,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=response.cost,
            finish_reason=response.finish_reason,
            cleanup_residual=cleanup.residual if cleanup else None,
            tool_transport_cleanup=tool_transport_cleanup,
        )
        if self._evidence_sink is not None:
            try:
                self._evidence_sink(self._last_evidence)
            except Exception:
                self._last_evidence = replace(self._last_evidence, status="failed")
                raise AgentExecutionError(
                    "participant evidence could not be retained"
                ) from None
