"""A trial keeps its product dump and host audit records before the seal."""

import json
from types import SimpleNamespace

from aptl.backends import trial_end_capture
from aptl.backends.trial_end_capture import retain_host_audit, retain_soc_dump
from aptl.core.runstore import LocalRunStore

RUN = "run-1"


def _store(tmp_path):
    store = LocalRunStore(tmp_path / "runs")
    store.create_run(RUN)
    return store


def _read(store, relative):
    return (store.get_run_path(RUN) / relative).read_bytes()


def test_product_dump_is_kept_with_granted_credentials_removed(tmp_path):
    store = _store(tmp_path)
    seen = {}

    class Adapter:
        @staticmethod
        def trial_end_capture(context):
            seen["operations"] = context.operations
            return {
                "wazuh-indexer.ndjson": b'{"user":"admin","password":"Indexer-Secret-1"}\n'
            }

    retain_soc_dump(
        store,
        RUN,
        adapter=Adapter(),
        backend=SimpleNamespace(),
        node_names=("wazuh-manager",),
        environment={
            "INDEXER_PASSWORD": "Indexer-Secret-1",
            "INDEXER_USERNAME": "admin",
        },
    )

    dump = _read(store, "trial/soc/wazuh-indexer.ndjson")
    assert b"Indexer-Secret-1" not in dump
    assert b'"user":"admin"' in dump
    assert json.loads(_read(store, "trial/soc/status.json")) == {
        "files": ["wazuh-indexer.ndjson"],
        "status": "captured",
    }
    assert seen["operations"] is not None


def test_product_dump_records_an_absent_adapter_and_a_refused_file_name(tmp_path):
    store = _store(tmp_path)
    retain_soc_dump(
        store, RUN, adapter=None, backend=None, node_names=(), environment={}
    )
    assert json.loads(_read(store, "trial/soc/status.json"))["status"] == "unavailable"

    class Adapter:
        @staticmethod
        def trial_end_capture(_context):
            return {"../escape": b"x"}

    retain_soc_dump(
        store,
        RUN,
        adapter=Adapter(),
        backend=SimpleNamespace(),
        node_names=(),
        environment={},
    )
    assert json.loads(_read(store, "trial/soc/status.json")) == {
        "reason": "ValueError",
        "status": "failed",
    }


def test_host_audit_keeps_only_records_of_the_trial_window_in_order(tmp_path):
    store = _store(tmp_path)
    logs = tmp_path / "audit"
    logs.mkdir()
    (logs / "audit.log.1").write_bytes(
        b"type=SYSCALL msg=audit(1794290000.100:1): before\n"
        b"type=EXECVE msg=audit(1794290100.200:2): first\n"
    )
    (logs / "audit.log").write_bytes(
        b"type=EXECVE msg=audit(1794290200.300:3): second\n"
        b"type=SYSCALL msg=audit(1794299999.400:4): after\n"
    )

    retain_host_audit(
        store,
        RUN,
        started_at="2026-11-10T05:54:00Z",
        ended_at="2026-11-10T05:57:00Z",
        log_dir=logs,
    )

    kept = b"type=EXECVE msg=audit(1794290100.200:2): first\ntype=EXECVE msg=audit(1794290200.300:3): second\n"
    assert _read(store, "trial/audit/audit.log") == kept
    assert json.loads(_read(store, "trial/audit/status.json")) == {
        "bytes": len(kept),
        "records": 2,
        "status": "captured",
        "truncated": False,
    }

    retain_host_audit(
        store,
        RUN,
        started_at="2026-11-10T05:54:00Z",
        ended_at="2026-11-10T05:57:00Z",
        log_dir=tmp_path / "missing",
    )
    assert (
        json.loads(_read(store, "trial/audit/status.json"))["status"] == "unavailable"
    )


def test_host_audit_truncation_keeps_a_contiguous_oldest_first_prefix(
    tmp_path, monkeypatch
):
    store = _store(tmp_path)
    logs = tmp_path / "audit"
    logs.mkdir()
    first = b"type=EXECVE msg=audit(1794290100.200:1): a\n"
    later = b"type=EXECVE msg=audit(1794290200.300:3): b\n"
    (logs / "audit.log.1").write_bytes(
        first + b"type=EXECVE msg=audit(1794290110.200:2): a much longer record\n"
    )
    (logs / "audit.log").write_bytes(later)
    # The later record fits after the first one, but keeping it would leave a gap.
    monkeypatch.setattr(trial_end_capture, "MAX_AUDIT_BYTES", len(first) + len(later))

    retain_host_audit(
        store,
        RUN,
        started_at="2026-11-10T05:54:00Z",
        ended_at="2026-11-10T05:57:00Z",
        log_dir=logs,
    )

    assert _read(store, "trial/audit/audit.log") == first
    assert json.loads(_read(store, "trial/audit/status.json")) == {
        "bytes": len(first),
        "records": 1,
        "status": "captured",
        "truncated": True,
    }
