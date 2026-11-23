# Historical Runtime Architecture Note

This page is retained only for older ADR links. The APTL-local SDL compiler,
planner, and runtime target registry described by the old version of this page
were removed after the ADR-035 RAES SDL cutover.

The supported runtime handoff is now:

1. Resolve the configured acquired-pack identity or explicit project-contained development SDL path.
2. Validate the selected file with `raes.parse_sdl_file`.
3. Pass any explicit per-run runtime bindings to
   `raes_runtime.manager.RuntimeManager.plan(parameters=...)`. RAES owns
   substitution, type and constraint validation, unresolved-reference checks,
   and post-substitution semantic validation.
4. Consume the planner's `ExecutionPlan` and its concrete `RuntimeModel`
   throughout realization, participant actions, selected-profile reporting,
   evidence, and apply. The start path does not recompile the authored scenario.

5. Start the lab through `aptl.backends.raes.start_raes_scenario()`.

LilRAE applies the admitted `ExecutionPlan` one time. A failed apply ends the
start without an automatic retry.

Runtime bindings are an in-process admission input, not APTL configuration or
secrets. APTL does not source them from the environment, forward them to
Compose or process arguments, or persist them in run records. Instantiation
failures stop before backend side effects and return bounded, value-free
remediation. The backend does not render the upstream exception.

APTL still keeps `aptl.core.runtime.workflow_engine` as an implementation
helper for the RAES orchestrator's workflow result/history records. It is not a
scenario parser, compiler, planner, or schema authority.
