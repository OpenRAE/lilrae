"""Exception types raised by deployment backends.

Lives in its own module so callers (including ones inside the
``aptl.core`` package whose top-level imports would otherwise create a
cycle through ``aptl.core.deployment.__init__`` ->
``aptl.core.deployment.backend`` -> ``aptl.core.lab`` -> ``aptl.core.snapshot``)
can import these symbols without pulling in the rest of the deployment
package.
"""


class BackendTimeoutError(Exception):
    """A backend operation exceeded its configured timeout.

    Backends raise this when an underlying ``docker``/``docker compose``
    invocation times out, so callers can catch a backend-defined
    exception rather than depending on ``subprocess.TimeoutExpired`` as
    an implementation detail. Pre-existing ``OSError`` semantics for
    other failure modes are unchanged.
    """


class BackendObservationError(RuntimeError):
    """Checked backend inventory could not be observed or parsed.

    The message is safe for an operator-facing boundary: callers construct it
    from bounded, redacted backend diagnostics rather than raw command output.
    Raising distinguishes observation failure from a valid empty inventory.
    """


class BackendSeedError(Exception):
    """A named-volume seed or legacy-path retire operation failed.

    Raised by :meth:`DeploymentBackend.seed_named_volumes` when a seed
    container exits non-zero (ADR-043). Carries only the artifact name
    (volume suffix / legacy path), never raw Docker stderr, so the lab
    step can surface it through the existing redacted ``LabResult``
    envelope.
    """


class CaptureReconciliationError(ValueError):
    """The broker's accepted sessions differ from the MCP session census.

    Raised by ``export_capture_apparatus`` instead of a bare ``None`` so the
    finalizer can report the mismatch. It carries only set sizes, never
    session identities or transcript content.
    """

    def __init__(
        self, *, census: int, accepted: int, census_only: int, broker_only: int
    ) -> None:
        super().__init__("broker custody does not match the session census")
        self.census = census
        self.accepted = accepted
        self.census_only = census_only
        self.broker_only = broker_only
