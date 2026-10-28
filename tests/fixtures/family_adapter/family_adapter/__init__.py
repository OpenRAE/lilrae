"""Independent adapter fixture: documented public imports and literal APIs."""

from importlib.resources import files

from aptl.backends.scenario_family import decode_family_target
from aptl.backends.pack_interaction import (
    ComponentGroupMembership,
    PackBackendInteractionResult,
)
from aptl.backends.scenario_capture import ScenarioCaptureContribution
from aptl.backends.scenario_startup import ScenarioStartupPlan
from aptl.backends.scenario_planning_compatibility import PlanningCompatibilityDecision
from aptl.core.evidence.adapters.sources import SourceResult
from aptl.core.evidence.outcomes import CollectorStatus
from aptl.core.experiment.capture_registry import (
    CaptureLimits,
    CaptureVisibility,
    CollectorRegistration,
)
from raes_backend_protocols.capabilities import ObservationCaptureOffer
from aptl.validation.scenario_verification import (
    VerificationCheck,
    VerificationReport,
    VerificationStatus,
)

TARGET = decode_family_target(
    files(__package__).joinpath("qualification.json").read_text()
)
SEEN = []


class Provider:
    family_api_version = "1"
    extension_api_version = "1"
    qualified_family_targets = (TARGET,)
    supported_pack_id = TARGET.pack.pack_id
    provider_id = "example-family-provider"


class Serving(Provider):
    def resolve(self, context):
        assert not hasattr(context, "trial")
        return PackBackendInteractionResult(
            tuple(
                ComponentGroupMembership(address, ("lab",))
                for address in context.component_addresses
            )
        )


class Parameters(Provider):
    def resolve(self, bundle):
        return None


class Startup(Provider):
    def resolve(self, bundle):
        SEEN.append(bundle.trial.identity())
        return ScenarioStartupPlan("scripts/seed.sh", ("lab",), ("lab",))

    def realize_runtime(self, operations, nodes, *, trial):
        SEEN.append(trial.identity())
        return []


class NativeSource:
    def fetch(self, start, end):
        return SourceResult(CollectorStatus.OK, [{"public_fact": "observed"}])


class CaptureRuntime:
    def native_sources(self, context):
        assert not hasattr(context, "run_store")
        return {"example.events": NativeSource()}


class Capture(Provider):
    def resolve(self, context):
        SEEN.append(context.trial.identity())
        offer = ObservationCaptureOffer(
            offer_id="example.events",
            offer_version="1.0.0",
            output_contract="experiment-evidence-record-v1",
            field_selectors=frozenset({""}),
            artifact_roles=frozenset({"service_materialization_readback"}),
            media_types=frozenset({"application/json"}),
            capture_kind="observation",
            source_classes=frozenset({"native"}),
            source_refs=frozenset({"nodes.shared.primary"}),
            scopes=frozenset({"Selected payload readiness."}),
            channel_kinds=frozenset({"participant-observation"}),
            channel_refs=frozenset(),
            window_kinds=frozenset({"system_under_test"}),
            integrity_modes=frozenset({"checksum"}),
            sensitivity="plain",
            availability="available",
            fidelity="complete",
            disclosure="redacted",
            retention_policy_refs=frozenset({"run_lifetime"}),
            export_policy="not-required",
            redaction_policy="redact_secrets",
            scope_refs=frozenset({"nodes.shared.primary"}),
        )
        registration = CollectorRegistration(
            registration_id="example.events",
            implementation_version="1.0.0",
            contract_version="experiment-capture-spec/v1",
            channel_kind="participant-observation",
            capture_kind="observation",
            capture_scope="scenario",
            window_kinds=frozenset({"system_under_test"}),
            media_types=frozenset({"application/json"}),
            required_artifact_roles=frozenset({"service_materialization_readback"}),
            supported_sensitivities=frozenset({"plain"}),
            supports_redaction=True,
            integrity_modes=frozenset({"checksum"}),
            sealing_modes=frozenset({"digest"}),
            supports_chain_of_custody=False,
            supports_retention=True,
            supports_loss_disclosure=True,
            visibility_class=CaptureVisibility.EVALUATOR_ONLY,
            limits=CaptureLimits(4096, 10, 60),
            redaction_policies=frozenset({"redact_secrets"}),
            retention_policies=frozenset({"run_lifetime"}),
            capture_offer=offer,
        )
        return ScenarioCaptureContribution(
            (registration,),
            native_registration_ids=frozenset({registration.registration_id}),
            runtime_adapter=CaptureRuntime(),
        )

    def resume_capture(self, context):
        return ScenarioCaptureContribution((), runtime_adapter=CaptureRuntime())


class Planning(Provider):
    def resolve(self, context):
        SEEN.append(context.trial.identity())
        return PlanningCompatibilityDecision()


class Verifier(Provider):
    extension_api_version = "2"
    plugin_id = "example-family-verifier"

    def run(self, context):
        SEEN.append(context.trial.identity())
        assert context.trial.scenario.content["payload"].path in {"/opt/a", "/opt/b"}
        return VerificationReport(
            VerificationStatus.PASSED,
            context.scenario,
            context.backend,
            run_id=context.run_id,
            attempt_id=context.attempt_id,
            checks=(VerificationCheck("selected-payload", VerificationStatus.PASSED),),
        )


serving, parameters, startup = Serving(), Parameters(), Startup()
capture, planning, verifier = Capture(), Planning(), Verifier()
