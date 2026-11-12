"""Lifecycle exclusion errors shared by resource owners and policy services."""


class LifecycleBusyError(RuntimeError):
    """Raised when another lifecycle owner already holds the project lock."""
