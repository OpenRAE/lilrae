# Trace a participant action

This Tutorial follows one action through the paper research fixture.
You will distinguish participant-visible information from evaluator-only evidence.
No lab startup or provider connection is required.
Use a source checkout with `scenarios/paper-agent-loop.sdl.yaml`.

## Find the action

Open the fixture and find `action_contracts.probe-customer-portal-login`.
Find `behavior_specifications.paper-agent-behavior` and its runtime-binding extension.
Observe how the binding names the action and observation boundary.
The backend uses these references rather than a TechVault participant preset.

## Follow the observation

Find `observation_boundaries.paper-agent-view`.
Compare its disclosed references with the negative database and Wazuh reachability evidence.
The participant can receive its terminal observation.
The negative reachability markers remain evaluator-only evidence.
Their existence does not authorize disclosure to the participant.

## Distinguish intent from proof

Find `wazuh-evidence` and `boundary-check-evidence` under the evidence requirements.
These declarations state what capture should collect.
They do not prove that capture ran or that a detector succeeded.
A run needs observed evidence and evaluation for those claims.

See the [realization reference](../raes/paper-scenario-realization.md) for exact backend mappings and limits.
Use [scenario validation](../raes/scenario-validation.md) when you change the fixture.
