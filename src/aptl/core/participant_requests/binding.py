"""Trusted participant coordinates, separate from reconstructed request data."""

from dataclasses import dataclass, field

from aptl.core.participant_requests.owner import ParticipantRequestOwner
from aptl.core.participant_requests.request import ParticipantRequest


@dataclass(frozen=True)
class ParticipantRequestBinding:
    """Trusted assembly retains the owner and expected participant at dispatch."""

    owner: ParticipantRequestOwner = field(repr=False)
    participant_address: str

    def validate(self, request: ParticipantRequest) -> None:
        """Recheck the trusted manifest, participant and native SDL asset scope."""
        request.validate()
        if request.manifest != self.owner.manifest:
            raise ValueError("participant request differs from its trusted manifest")
        contents = {
            slot: content.encode("utf-8")
            for slot, content in zip(
                request.profile.context_order, request.context_contents, strict=True
            )
        }
        verified = self.owner.verify_content(
            request.configuration_result,
            participant_address=self.participant_address,
            contents=contents,
        )
        if verified != request.context_contents:
            raise ValueError(
                "participant request content differs from its trusted binding"
            )
