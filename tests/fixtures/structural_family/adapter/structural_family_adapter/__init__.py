"""Independent structural family adapter: public imports and literal APIs only."""

from importlib.resources import files

from aptl.backends.pack_interaction import (
    ComponentGroupMembership,
    PackBackendInteractionResult,
)
from aptl.backends.scenario_capture import ScenarioCaptureContribution
from aptl.backends.scenario_family import decode_family_target
from aptl.backends.scenario_planning_compatibility import PlanningCompatibilityDecision
from aptl.backends.scenario_startup import ScenarioStartupPlan
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
    provider_id = "structural-family-provider"


class Serving(Provider):
    def resolve(self, context):
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
        return ScenarioStartupPlan("scripts/seed.sh", ("lab",), ("lab",))


class Capture(Provider):
    def resolve(self, context):
        return ScenarioCaptureContribution(())


class Planning(Provider):
    def resolve(self, context):
        return PlanningCompatibilityDecision()


class Verifier(Provider):
    extension_api_version = "2"
    plugin_id = "structural-family-verifier"

    def run(self, context):
        trial = context.trial
        SEEN.append(
            {
                "plan_entry_id": trial.identity()["plan_entry_id"],
                "sensor_present": "sensor-9" in trial.scenario.nodes,
                "configuration_digests": [
                    item.configuration_digest
                    for item in trial.participant_configuration_results
                ],
            }
        )
        return VerificationReport(
            VerificationStatus.PASSED,
            context.scenario,
            context.backend,
            run_id=context.run_id,
            attempt_id=context.attempt_id,
            checks=(VerificationCheck("selected-entry", VerificationStatus.PASSED),),
        )


serving, parameters, startup = Serving(), Parameters(), Startup()
capture, planning, verifier = Capture(), Planning(), Verifier()
