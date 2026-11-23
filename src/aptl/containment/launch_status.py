"""The launcher's status protocol on its private status descriptor.

The launcher writes ``ok <layer> <detail>`` for each layer, then ``exec`` just
before it executes the target. On a failure it writes ``fail <layer> <detail>``
and exits. The descriptor closes on exec, so the target cannot write to it.
"""

from dataclasses import dataclass

LAYERS = ("descriptors", "no_new_privs", "limits", "landlock", "seccomp")
_STATUS_BYTES = 65536
_DETAIL_CHARS = 200


@dataclass(frozen=True)
class LaunchStatus:
    """The layers that the launcher applied and whether it reached exec."""

    applied: dict[str, str]
    executed: bool
    failure: tuple[str, str] | None


def parse_launch_status(data: bytes) -> LaunchStatus:
    """Read the status lines; unknown lines add no evidence."""
    applied: dict[str, str] = {}
    executed, failure = False, None
    for line in data[:_STATUS_BYTES].decode("utf-8", errors="replace").splitlines():
        kind, _, rest = line.partition(" ")
        layer, _, detail = rest.partition(" ")
        if kind == "ok" and layer in LAYERS:
            applied[layer] = detail[:_DETAIL_CHARS]
        elif kind == "exec" and not rest:
            executed = True
        elif kind == "fail" and failure is None:
            failure = (layer[:32], detail[:_DETAIL_CHARS])
    if failure is not None:
        executed = False
    return LaunchStatus(applied, executed and set(applied) == set(LAYERS), failure)
