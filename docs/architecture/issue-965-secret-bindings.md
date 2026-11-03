# Operational environment bindings

Both container routes use the existing `EnvironmentGrant` contract: pack,
consumer, target variable and named source. Operator grants remain in
`aptl.json`. Startup plans declare their own grants, restricted to keys the
same plan supplies in the project environment file. Exact pack identity
checks apply before those adapter grants are considered. A fixture or alias
name alone grants no consumer access.

The deployment preflight snapshots only sources needed by declared consumers.
It checks generated `value_from` references against the selected artifact,
output and consumer on both routes before mutation. Backend-generated
dependencies retain their explicit artifact consumers. A new preflight clears
the previous run's bindings; delivery uses that run's captured values.

Authored values retain precedence over external grants. Operational values
travel through existing private, no-follow env-file writers. Logs and argv
carry source names or file paths. Readback withholds commitments for external
and generated values; authored fixture commitments remain unchanged (ADR-029).

The existing architecture layer map in `pyproject.toml` remains sufficient:
the startup contract uses the core credential-source model and deployment
applies it through the existing adapter boundary. Focused canary tests check
pack and consumer selection, pre-mutation refusal, source changes across runs,
and disclosure. Mutation checks remove those guards to verify the tests fail.
