"""The serialization vector schemes of the TechVault adapter (#1555, #1700).

Each function calls one owner of the adapter, or a generic owner that only
the TechVault pack uses, with a vector input. ``tests/test_serialization_vectors.py``
loads ``OWNER_SCHEMES`` from this module.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from aptl.appliance.policy import write_full_techvault_boundary_policy
from aptl.backends.raes_participant_fixture_core import (
    _mapping_digest as fixture_mapping_digest,
)
from aptl.backends.raes_participant_fixture_core import participant_episode_state_dir
from aptl_techvault.database_access import _scram_verifier
from aptl_techvault.evidence import techvault as techvault_evidence
from aptl_techvault.evidence import (
    techvault_misp_readiness,
    techvault_readiness_probes,
    techvault_wazuh_agent_readiness,
)
from aptl_techvault.evidence.techvault_readiness import SuricataRuleReadinessSource
from aptl_techvault.evidence.techvault_transcript import (
    TranscriptFrame,
    TranscriptSession,
    _transcript_chain,
    _transcript_result,
)

from tests.serialization_owner_schemes import _written


def _workflow_digest(case_input: dict) -> dict[str, str]:
    return {"text": fixture_mapping_digest(case_input)}


def _bytes_or_none(data: bytes | None) -> dict[str, object]:
    return {"value": None if data is None else data.hex()}


def _source_result(result: object) -> dict[str, object]:
    return {
        "value": {
            "status": result.status.value,
            "chunks_hex": [chunk.hex() for chunk in result.chunks],
            "source_pipeline": result.source_pipeline,
        }
    }


def _episode_state_dir(case_input: dict) -> dict[str, str]:
    return {"text": participant_episode_state_dir(case_input["participant_address"], case_input["episode_id"])}


def _scram(case_input: dict) -> dict[str, str]:
    return {"text": _scram_verifier(case_input["password"], salt=bytes.fromhex(case_input["salt_hex"]))}


def _transcript(case_input: dict) -> dict[str, str]:
    frames = [
        TranscriptFrame(frame["sequence"], frame["timestamp"], frame["direction"], bytes.fromhex(frame["data_hex"]))
        for frame in case_input["frames"]
    ]
    return {"text": _transcript_chain(frames)}


def _techvault_boundary_policy(_case_input: dict) -> dict[str, object]:
    data = _written(write_full_techvault_boundary_policy, "policy.json")
    return {"value": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}}


def _techvault_bounded_json(case_input: dict) -> dict[str, object]:
    native = techvault_evidence._bounded_json(case_input["value"])
    readiness = techvault_readiness_probes.bounded_json(case_input["value"], case_input["limit"])
    return {
        "value": {
            "native_hex": None if native is None else native.hex(),
            "readiness_hex": None if readiness is None else readiness.hex(),
        }
    }


def _misp_readiness(case_input: dict) -> dict[str, object]:
    admitted = techvault_misp_readiness.AdmittedMispState(**case_input["admitted"])
    return _bytes_or_none(techvault_misp_readiness._readiness_document(case_input["payload"], admitted))


def _wazuh_agent_readiness(case_input: dict) -> dict[str, object]:
    return _bytes_or_none(
        techvault_wazuh_agent_readiness._readiness_document(case_input["payload"], tuple(case_input["expected_nodes"]))
    )


def _sqli_correlation(case_input: dict) -> dict[str, object]:
    source = techvault_evidence.SuricataWazuhSqliSource(
        lambda: case_input["trigger"],
        lambda _start, _end: case_input["suricata_events"],
        lambda _start, _end: case_input["wazuh_events"],
    )
    return _source_result(source.fetch(case_input["start"], case_input["end"]))


def _suricata_readiness(case_input: dict) -> dict[str, object]:
    source = SuricataRuleReadinessSource(lambda _start, _end: case_input["payload"])
    return _source_result(source.fetch(case_input["start"], case_input["end"]))


def _transcript_document(case_input: dict) -> dict[str, object]:
    sessions = tuple(
        TranscriptSession(
            session_id=item["session_id"],
            started_at=item["started_at"],
            finished_at=item["finished_at"],
            close_reason=item["close_reason"],
            frames=tuple(
                TranscriptFrame(frame["sequence"], frame["timestamp"], frame["direction"], bytes.fromhex(frame["data_hex"]))
                for frame in item["frames"]
            ),
            final_chain_digest=item["final_chain_digest"],
        )
        for item in case_input["sessions"]
    )
    return _source_result(_transcript_result(sessions, case_input["start"], case_input["end"]))


OWNER_SCHEMES: dict[str, Callable[[dict], dict[str, object]]] = {
    "participant-episode-state-dir": _episode_state_dir,
    "participant-workflow-digest": _workflow_digest,
    "postgres-scram-verifier": _scram,
    "techvault-transcript-chain": _transcript,
    "techvault-boundary-policy": _techvault_boundary_policy,
    "techvault-bounded-json": _techvault_bounded_json,
    "techvault-misp-readiness": _misp_readiness,
    "techvault-wazuh-agent-readiness": _wazuh_agent_readiness,
    "techvault-sqli-correlation": _sqli_correlation,
    "techvault-suricata-readiness": _suricata_readiness,
    "techvault-transcript-document": _transcript_document,
}
