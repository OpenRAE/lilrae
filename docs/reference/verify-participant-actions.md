# Verify participant action boundaries

Use this How-to guide for a change to participant admission, native dispatch, or accepted history.
Run behavior tests only in CI or an approved isolated VM.
The two source-structure checks can run on the workstation.
Use the existing project environment and the exact targeted test paths.

## Run the targeted checks

Run the enrolled layer check with `python tools/check_architecture.py` in the project environment.
Run the component check with `python tools/check_lilrae_participant_architecture.py` in the project environment.
Run the finite model with `bash tools/run-targeted-tests.sh tests/test_lilrae_participant_action_model.py`.

Run generated traces with `bash tools/run-targeted-tests.sh tests/test_lilrae_tool_model_fuzz.py -m fuzz`.
Run the runtime and carrier tests by their explicit paths in the table.

The [enforcement explanation](../architecture/participant-action-enforcement.md#research-and-qualification-surface) defines evidence limits and the relevant runtime cases.
