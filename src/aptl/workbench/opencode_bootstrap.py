"""Entry assembly for an explicitly sourced managed OpenCode participant."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import cast

from raes_contracts.contracts import (
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
)

from aptl.backends.lilrae_participant_configuration import configured_opencode_executor
from aptl.core.config import ProcessEnvironmentCredentialSource
from aptl.workbench.credentials import EphemeralCredentialBroker
from aptl.workbench.lilrae_opencode import LilraeOpenCodeExecutor, OpenCodeOptions
from aptl.workbench.participant_source_binding import (
    CredentialBindingEvidence,
    ProcessEnvironmentCredentialResolver,
    observe_local_cleanup,
)


@dataclass(frozen=True)
class OpenCodeParticipantRequest:
    """Admitted configuration, exact prompt, and the installed model domain."""

    configuration: ParticipantConfigurationResultModel
    manifest: ParticipantImplementationManifestModel
    prompt: str = field(repr=False)
    prompt_ref: str
    supported_models: frozenset[str]


@contextmanager
def managed_opencode_executor(
    *,
    options: OpenCodeOptions,
    request: OpenCodeParticipantRequest,
    run_id: str,
    credential_source: ProcessEnvironmentCredentialSource,
    source_environment: Mapping[str, str],
) -> Iterator[tuple[LilraeOpenCodeExecutor, CredentialBindingEvidence]]:
    """Use inside the trial owner; drain its RAES runtime before context exit."""
    if options.environment:
        raise ValueError("managed OpenCode requires its configured credential source")
    credentials, evidence = ProcessEnvironmentCredentialResolver(
        source_environment
    ).acquire(
        "opencode",
        run_id,
        source=credential_source,
        delivery_alias="OPENROUTER_API_KEY",
    )
    broker = EphemeralCredentialBroker(credentials)
    active = None
    try:
        lease = broker.prepare_named("opencode", run_id, ("OPENROUTER_API_KEY",))
        # replace preserves the input's concrete dataclass type.
        prepared_options = cast(OpenCodeOptions, replace(options, environment=lease))
        active = configured_opencode_executor(
            options=prepared_options,
            configuration=request.configuration,
            manifest=request.manifest,
            prompt=request.prompt,
            prompt_ref=request.prompt_ref,
            supported_models=request.supported_models,
        )
        # These controls are configuration/process controls, not an OS sandbox.
        evidence.isolation_controls_applied = (
            "minimal-child-environment",
            "private-home",
            "private-xdg-directories",
            "explicit-provider-route",
            "default-deny-tools",
        )
        yield active, evidence
    finally:
        if active is not None:
            active.close()
        broker.destroy_named("opencode", run_id)
        credentials.clear()
        observe_local_cleanup(evidence, succeeded=True)
