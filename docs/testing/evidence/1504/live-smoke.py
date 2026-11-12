"""One bounded, free-route OpenCode smoke; credentials arrive only on stdin."""
import json
import sys


def run():
    from pathlib import Path
    from threading import Event
    import hashlib
    from aptl.core.config import ProcessEnvironmentCredentialSource
    from aptl.core.opencode import OpenRouterRoute
    from aptl.backends.lilrae_participant_configuration import opencode_manifest, OpenCodeConfigurationValidator
    from aptl.workbench.lilrae_opencode import OpenCodeOptions
    from aptl.workbench.opencode_bootstrap import managed_opencode_executor
    from aptl.workbench.process import AgentExecutionError
    from raes_contracts.participant_configuration import ConfigurationOverrideModel, realize_participant_configuration
    from raes_contracts.satisfiability import canonical_contract_digest

    source_environment = json.loads(sys.stdin.buffer.readline(65537))
    model = 'openrouter/liquid/lfm-2.5-2.6b:free'
    endpoint = 'https://openrouter.ai/api/v1'
    serving_provider = 'liquid/fp8'
    prompt = 'Reply with exactly OK. No tools or explanation.'
    manifest = opencode_manifest(version='1.0.0')
    values = {
        'model': model, 'gateway_endpoint': endpoint, 'serving_provider': serving_provider,
        'prompt_ref': 'content.smoke-prompt@v1', 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
        'timeout_seconds': 10, 'max_output_tokens': 16,
    }
    config = realize_participant_configuration(
        participant_address='participant.behavior.red', manifest=manifest,
        manifest_ref='participant-implementation-manifests.opencode.v1',
        manifest_digest=canonical_contract_digest(manifest),
        overrides=[ConfigurationOverrideModel(target_id=k,value={'kind':'literal','value':v}) for k,v in values.items()],
        validator=OpenCodeConfigurationValidator(frozenset({model})),
    )
    record = None
    completed = False
    failure_type = None
    with managed_opencode_executor(
        options=OpenCodeOptions(executable=Path.home()/'opencode-1504/opencode', work_root=Path.home()/'opencode-smoke-work',
            route=OpenRouterRoute(endpoint=endpoint,serving_provider=serving_provider), max_output_tokens=16),
        configuration=config, manifest=manifest, prompt=prompt, prompt_ref=values['prompt_ref'],
        supported_models=frozenset({model}), run_id='issue-1504-free-smoke',
        credential_source=ProcessEnvironmentCredentialSource(kind='process-environment',variable='OPEN_ROUTER_KEY'),
        source_environment=source_environment,
    ) as (active, credential_evidence):
        try:
            active('free-smoke-action', Event())
            completed = True
        except AgentExecutionError as error:
            failure_type = type(error).__name__
        record = active.last_evidence
    source_environment.clear()
    return {
        'scope': 'single bounded free-model connectivity and trigger smoke; not experiment qualification',
        'model': model, 'endpoint': endpoint, 'serving_provider_requested': serving_provider,
        'build_version': manifest.constraints['opencode_version'],
        'build_sha256': manifest.constraints['opencode_executable_sha256'],
        'output_token_cap': 16, 'timeout_seconds': 10,
        'completed': completed, 'failure_type': failure_type,
        'status': record.status if record else 'not-launched',
        'stdout_bytes': record.stdout_bytes if record else 0,
        'input_tokens': record.input_tokens if record else None,
        'output_tokens': record.output_tokens if record else None,
        'cost_reported': record.cost if record else None,
        'cleanup_residual': record.cleanup_residual if record else None,
        'credential_local_cleanup': credential_evidence.local_cleanup,
        'served_model': None, 'served_provider': None,
    }


try:
    print(json.dumps(run(), sort_keys=True))
except BaseException as failure:
    print(json.dumps({'status':'failed-before-completion','failure_type':type(failure).__name__}))
    sys.exit(1)
