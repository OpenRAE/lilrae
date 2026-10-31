"""Recorded descendants keep deadlines and lifecycle evidence across readback."""

from types import SimpleNamespace

from tests.test_lilrae_docker_recording import _store


class Native:
    def __init__(self):
        self.containers = {}
        self.stopped = []
        self.unreadable = set()

    def inspect(self, native_id):
        if native_id in self.unreadable:
            raise OSError("native observation failed")
        return self.containers.get(native_id)

    def stop(self, native_id):
        self.stopped.append(native_id)


def _tracker(tmp_path):
    from aptl.core.deployment.lilrae_recorded_inventory import RecordedInventory

    clock = SimpleNamespace(wall=1000.0, monotonic=500.0)
    store = _store(tmp_path, clock=lambda: clock.wall)
    native = Native()
    tracker = RecordedInventory(
        store,
        native,
        wall_clock=lambda: clock.wall,
        monotonic_clock=lambda: clock.monotonic,
    )
    return store, native, tracker, clock


def _created(store, native):
    record = store.commit(
        store.begin("provision.node.holder", timeout_seconds=60), "a" * 64
    )
    native.containers[record.native_id] = {
        "Id": record.native_id,
        "Image": "sha256:" + "b" * 64,
        "Platform": "linux",
        "State": {"Running": True, "Status": "running"},
        "Config": {"Env": ["PASSWORD=credential-canary"], "Cmd": ["credential-canary"]},
    }
    return record


def test_deadline_is_not_restarted_by_another_inventory_scan(tmp_path):
    store, native, tracker, clock = _tracker(tmp_path)
    record = _created(store, native)
    tracker.capture(record)
    clock.wall += 59
    clock.monotonic += 59
    assert tracker.supervise() == ()
    assert native.stopped == []
    clock.wall += 1
    clock.monotonic += 1
    assert tracker.supervise() == ()
    assert native.stopped == [record.native_id]


def test_inspect_failure_during_supervision_never_mutates_the_candidate(tmp_path):
    store, native, tracker, clock = _tracker(tmp_path)
    record = _created(store, native)
    tracker.capture(record)
    native.unreadable.add(record.native_id)
    clock.wall += 61
    clock.monotonic += 61
    assert tracker.supervise() == ("child-inspect-unavailable",)
    assert native.stopped == []
    observed = tracker.observe()
    assert not observed.complete
    assert observed.children[0].creation == record


def test_autoremoved_child_retains_safe_identity_and_a_tombstone(tmp_path):
    store, native, tracker, _clock = _tracker(tmp_path)
    record = _created(store, native)
    tracker.capture(record)
    del native.containers[record.native_id]
    observed = tracker.observe()
    assert observed.complete
    (child,) = observed.children
    assert child.state == "autoremoved"
    assert child.platform == "linux"
    assert child.image_id == "sha256:" + "b" * 64
    assert all(
        b"credential-canary" not in path.read_bytes()
        for path in tmp_path.rglob("*.json")
    )


def test_recovery_uses_persisted_deadline_instead_of_a_new_timeout(tmp_path):
    from aptl.core.deployment.lilrae_recorded_inventory import RecordedInventory

    store, native, tracker, clock = _tracker(tmp_path)
    record = _created(store, native)
    tracker.capture(record)
    clock.wall += 61
    clock.monotonic += 61
    recovered = RecordedInventory(
        store,
        native,
        wall_clock=lambda: clock.wall,
        monotonic_clock=lambda: clock.monotonic,
    )
    recovered.supervise()
    assert native.stopped == [record.native_id]


def test_native_identity_mismatch_does_not_authorize_action(tmp_path):
    store, native, tracker, clock = _tracker(tmp_path)
    record = _created(store, native)
    native.containers[record.native_id]["Id"] = "f" * 64
    clock.wall += 61
    clock.monotonic += 61
    assert tracker.supervise() == ("child-inspect-unavailable",)
    assert native.stopped == []


def test_delegated_deadline_respects_parent_after_wall_clock_moves_back(tmp_path):
    store, native, tracker, clock = _tracker(tmp_path)
    parent = _created(store, native)
    tracker.capture(parent)
    clock.wall = 990.0
    clock.monotonic = 550.0
    child = store.commit(
        store.begin(
            "provision.node.holder",
            timeout_seconds=60,
            parent_native_id=parent.native_id,
        ),
        "c" * 64,
    )
    native.containers[child.native_id] = {
        **native.containers[parent.native_id],
        "Id": child.native_id,
    }
    tracker.capture(child)
    clock.wall += 10
    clock.monotonic += 10
    assert tracker.supervise() == ()
    assert set(native.stopped) == {parent.native_id, child.native_id}


def test_native_handoff_retains_initial_and_later_readbacks(tmp_path):
    import json
    from aptl.core.deployment.lilrae_native_evidence import native_evidence_artifacts

    store, native, tracker, clock = _tracker(tmp_path)
    child = _created(store, native)
    tracker.capture(child)
    native.containers[child.native_id]["State"] = {"Running": False, "Status": "exited"}
    clock.wall += 5
    tracker.capture(child)
    artifacts = native_evidence_artifacts(
        store.ownership, store.attempt_id, store.daemon_id
    )
    states = {
        json.loads(data)["observation"]["state"]
        for role, data in artifacts
        if role == "native-readback/v1"
    }
    assert states == {"active", "terminated"}
    assert all(b"credential-canary" not in data for _, data in artifacts)
