"""Native Docker kernel-policy preflight, application and owned cleanup."""

from __future__ import annotations
from typing import TYPE_CHECKING
from aptl.core.deployment.realization import DeploymentRealizationSpec

if TYPE_CHECKING:
    from aptl.core.deployment.docker_compose import DockerComposeBackend

from aptl.core.deployment.boundary import BoundaryNetwork, NativeRangeBoundarySpec
from aptl.core.deployment.errors import BackendTimeoutError
from aptl.core.lab_types import LabResult


def uses_native_policy(backend: DockerComposeBackend) -> bool:
    """Keep native policy distinct from signed VM guest policy."""
    from aptl.core.execution_boundary import revalidate_execution_boundary

    return (
        getattr(backend, "_appliance_boundary", None) is None
        and revalidate_execution_boundary(backend).host_containment == "native-docker"
    )


def _kernel_check(backend: DockerComposeBackend) -> LabResult | None:
    """Dry-run native syntax on the selected host without installing rules."""
    from aptl.core.deployment._compose_boundary import _ensure_helper, _run_helper

    policy = NativeRangeBoundarySpec(
        backend._project_name,
        (BoundaryNetwork(name="preflight", bridge="lilrae-check"),),
    )
    try:
        failure = _ensure_helper(backend, backend._boundary_helper_image)
        if failure is not None:
            return failure
        result = _run_helper(
            backend,
            "check",
            policy.canonical_json(),
            backend._boundary_helper_image,
            backend._offline_staged,
        )
        supported = result.returncode == 0
    except OSError, RuntimeError, BackendTimeoutError:
        supported = False
    return (
        None
        if supported
        else LabResult(
            success=False,
            error=(
                "Native Docker range policy requires host nftables bridge/inet hooks, "
                "fib matching and NET_ADMIN; kernel policy check failed before deployment."
            ),
        )
    )


class ComposeNativeBoundaryMixin:
    """Enforce native range policy before participant workload creation."""

    def _native_range_preflight(
        self, realization: DeploymentRealizationSpec | None = None
    ) -> LabResult | None:
        """Check host capability after semantic admission, before deployment."""
        if not uses_native_policy(self):
            return None
        if realization is not None and not getattr(self, "_dedicated_vm", False) and (
            realization.docker_authority_admissions
            or any("SYS_ADMIN" in n.backend_run_capabilities for n in realization.nodes)
        ):
            return LabResult(
                success=False,
                error=(
                    "Native Docker range policy cannot contain a host-root-equivalent "
                    "Docker socket authority; use an isolated runtime."
                ),
            )
        return _kernel_check(self)

    def _realize_native_range_boundary(self) -> LabResult | None:
        """Protect every owned range and apparatus bridge before startup."""
        from aptl.core.deployment._native_range_publications import (
            refresh_native_policy,
        )

        if not uses_native_policy(self):
            return None
        return refresh_native_policy(self, required=True)


def cleanup_native_policy(backend: DockerComposeBackend) -> list[str]:
    """Remove only the owner's tables after owned network removal succeeded."""
    from aptl.core.deployment._compose_boundary import _run_helper
    from aptl.core.execution_boundary import revalidate_execution_boundary

    if revalidate_execution_boundary(backend).host_containment != "native-docker":
        return []
    policy = NativeRangeBoundarySpec(
        backend._project_name,
        (BoundaryNetwork(name="cleanup", bridge="lilrae-cleanup"),),
    )
    result = _run_helper(
        backend,
        "cleanup",
        policy.canonical_json(),
        backend._boundary_helper_image,
        backend._offline_staged,
    )
    failures = []
    if result.returncode != 0:
        failures.append("Native range policy cleanup failed")
    else:
        backend._boundary_receipts.pop("native-range", None)
        backend._boundary_specs.pop("native-range", None)
    return failures
