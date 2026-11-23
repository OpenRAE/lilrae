# Compose participant requests

Use trusted experiment entry assembly with reviewed models, roles, and versioned prompt assets.
The [manifest reference](participant-request-manifests.md) defines targets, scope, controls, and evidence limits.
This procedure does not authorize a provider connection.

## Publish the trusted owner

1. Validate the reviewed catalog through `RequestCatalog.model_validate_json()`.
2. Resolve admitted control-context descriptors through the existing artifact owner.
3. Create exact asset pins with `control_context_asset_reference()`.
4. Map each slot to its admitted SDL declaration references and pins.
5. Construct `ParticipantRequestOwner` with the catalog, domains, and admitted scenario:

```python
from aptl.core.participant_requests import ParticipantRequestOwner, RequestCatalog
from raes_contracts.contracts import ParticipantImplementationManifestModel

catalog = RequestCatalog.model_validate_json(reviewed_catalog_bytes)
owner = ParticipantRequestOwner(
    catalog=catalog,
    context_domains=consumer_context_domains,
    scenario=admitted_scenario,
)
manifest = owner.manifest
manifest_schema = ParticipantImplementationManifestModel.model_json_schema()
registry = manifest.configuration_registry
validators = {
    (registry.owner.validator_id, registry.owner.validator_version): owner,
}
```

6. Pass the owner/version map to the public trial compiler as `participant_configuration_validators`.
7. For a fixed selection, call `realize_participant_configuration()` with `validator=owner`.
8. For the older controller, give a `ParticipantManifestBinding` with its trusted validator.

Do not discover executable validators from authored artifact names.

## Verify content and dispatch

1. Get the participant's sealed configuration result.
2. Resolve approved content bytes through the existing contained artifact resolver.
3. Call `owner.verify_content()` with the result, expected participant address, and bytes keyed by slot.
4. Keep required separators in the pinned authored content.
5. Create the immutable native request with `prepare_request()`.
6. Pass it through `DecisionAgentLaunch.request` or `OpenCodeOptions.request`.
7. Pass `ParticipantRequestBinding(owner, expected_participant_address)` independently through trusted assembly.
8. Give the admitted invocation timeout and required evidence sink before participant preparation.
9. Before you acquire credential leases, configure the existing cancellation-and-drain callback.
10. Keep typed invocation evidence through the existing evidence owner.

Do not substitute a peer participant's configuration, even when its prompt bytes match.
Before you make a capture claim, examine unavailable observation fields.
Use [managed OpenCode configuration](opencode-operations.md) for that installed implementation.
