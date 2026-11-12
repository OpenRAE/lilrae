# Retained issue #1504 evidence

These artifacts support the [qualification record](../../opencode-1504-qualification.md).
They contain no credentials, raw model output, or tenant data.

- `live-smoke-result.json` is the retained JSON output of the VM smoke runner.
- `live-smoke.py` is the original runner, preserved without changes. It accepted the approved credential through stdin and used the installed package. It is not run by tests or CI.
- `candidate.json` identifies the tested wheel and pinned executable by SHA-256. It includes source-file commitments from that wheel and an offline reconstruction of its route configuration and token cap. The reconstruction is not a network capture.
- `free-route-recheck.json` contains a later unauthenticated read of the public endpoint catalog. It verifies zero prompt and completion prices for the selected route. The original pre-invocation catalog response was not retained; this artifact does not attest historical pricing.
- `instance-audit.json` projects only timestamps, method names, resource names, operation boundaries, and status codes from GCP administrative audit records. It identifies creation and deletion of `test-1504` in `prod-mgau4w`.
- `cleanup-recheck.json` retains the later empty resource-list responses for the issue-owned resource names.

The smoke result came from the SSH-run process on that VM.
Its original payload did not include a hostname or a signed host attestation.
The candidate wheel was tested before the later failure-evidence fixes in this PR.

Those fixes use offline installed-wheel tests; the live smoke was not repeated.
Later refactors group the managed entry inputs and separate event validation helpers.
Credential acquisition and route enforcement retain the same owners and controls.

The result reports no text completion and does not retain the exact supervised failure reason.
The process can retry internally, so the HTTP request count is unknown.
No artifact asserts a full experimental run or release qualification.
