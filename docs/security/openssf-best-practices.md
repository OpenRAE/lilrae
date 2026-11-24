# OpenSSF Best Practices Assessment

This historical Reference records the OpenSSF assessment dated 2026-09-22.
Its findings apply to that review window, not current advisory or badge status.
The tables preserve the recorded assessment and its evidence links.
Follow [Update the assessment](update-assessment.md) for a new review and badge publication.

Assessment date: 2026-09-22.
Sources included the [passing criteria](https://www.bestpractices.dev/criteria/0), repository, release history, CI, Scorecard, and private-advisory metadata at that date. There were no
published or draft GitHub security advisories at assessment time.

## User And Contributor Evidence

The table records the user and contributor evidence selected for the assessment.

| Criterion | Status | Evidence |
| --- | --- | --- |
| `description_good` | Met | [Documentation home](../index.md) explains what APTL does and its safety boundary. |
| `interact` | Met | [Installation](../getting-started/installation.md), [support](https://github.com/OpenRAE/lilrae/blob/main/SUPPORT.md), and [contribution](https://github.com/OpenRAE/lilrae/blob/main/CONTRIBUTING.md) paths are linked from the project front door. |
| `contribution` | Met | [CONTRIBUTING.md](https://github.com/OpenRAE/lilrae/blob/main/CONTRIBUTING.md) describes the fork, branch, test, and pull-request process. |
| `contribution_requirements` | Met | [Making changes](https://github.com/OpenRAE/lilrae/blob/main/CONTRIBUTING.md#making-changes) states the acceptance requirements. |
| `documentation_basics` | Met | [Lab guide](../getting-started/index.md) covers prerequisites, installation, safe use, troubleshooting, and teardown. |
| `documentation_interface` | Met | The [CLI](../reference/cli.md), [MCP](../reference/mcp.md), and [web](../reference/web.md) references describe the supported interfaces. |
| `report_process` | Met | [SUPPORT.md](https://github.com/OpenRAE/lilrae/blob/main/SUPPORT.md) explains how to submit useful bug reports and feedback. |
| `vulnerability_report_process` | Met | [SECURITY.md](https://github.com/OpenRAE/lilrae/security/policy) directs reporters to private vulnerability reporting. |

The repository-root `.bestpractices.json` proposes these answers to the badge
application. That file deliberately does not propose facts that only the
maintainer can attest.

## Passing-Criteria Review

| Area | Criteria | Assessment |
| --- | --- | --- |
| Basics | `description_good`, `interact`, `contribution`, `contribution_requirements`, `floss_license`, `floss_license_osi`, `license_location`, `documentation_basics`, `documentation_interface`, `sites_https`, `discussion`, `english`, `maintained` | Met. The task-oriented manual, contribution and support policies, MIT license, HTTPS project sites, public issue discussions, and active release history provide direct evidence. |
| Change control | `repo_public`, `repo_track`, `repo_interim`, `repo_distributed`, `version_unique`, `version_semver`, `version_tags`, `release_notes`, `release_notes_vulns` | Met. Public Git history and pull requests retain interim work; release-please creates unique three-part versions, tags, GitHub releases, and human-readable notes. No public APTL vulnerability with a CVE has been fixed to date. |
| Reporting | `report_process`, `report_tracker`, `report_responses`, `enhancement_responses`, `report_archive`, `vulnerability_report_process`, `vulnerability_report_private`, `vulnerability_report_response` | Met, with `vulnerability_report_response` not applicable during the review window. GitHub issues are the public tracker and archive. A sample of the latest 300 issues had responses on 174, which exceeds the required majority. GitHub private reporting is enabled and had no advisories to time during the previous six months. |
| Build and tests | `build`, `build_common_tools`, `build_floss_tools`, `test`, `test_invocation`, `test_most`, `test_continuous_integration`, `test_policy`, `tests_are_added`, `tests_documented_added` | Met. Standard FLOSS Python and Node build tools, pytest, Hypothesis, and Vitest are documented and run in CI. The contribution policy requires tests and recent major changes include them. `test_most` is a considered suggested criterion; coverage is measured, but this assessment does not claim a repository-wide branch percentage. |
| Warnings | `warnings`, `warnings_fixed`, `warnings_strict` | Met. Pre-commit, Ruff, Vale, strict MkDocs, TypeScript checks, and SonarCloud run as blocking checks; targeted suppressions require an explicit source-level rationale. |
| Security knowledge | `know_secure_design`, `know_common_errors` | Met based on the maintained security ADRs, threat-boundary documentation, vulnerability policy, redaction and path-safety controls, and their regression suites. Both answers require the maintainer’s personal confirmation during submission. |
| Cryptography | `crypto_published`, `crypto_call`, `crypto_floss`, `crypto_keylength`, `crypto_working`, `crypto_weaknesses`, `crypto_pfs`, `crypto_password_storage`, `crypto_random`, `delivery_mitm`, `delivery_unsigned` | Met where applicable. APTL uses published algorithms through FLOSS libraries and platform TLS/SSH implementations. Python’s `secrets` module supplies tokens. Certificate and host-key verification remain enabled. APTL implements no private cryptography. Password-hash and forward-secrecy criteria are not applicable to APTL's loopback operator process; scenario-service credentials are isolated lab fixtures, not a project authentication service. HTTPS, hash-locked dependencies, signed release attestations, and SSH host-key checks protect delivery. |
| Vulnerability handling | `vulnerabilities_fixed_60_days`, `vulnerabilities_critical_fixed`, `no_leaked_credentials` | Met based on no known public vulnerabilities in APTL itself and no private advisories at assessment time. Secret detection and redaction gates are active. The Scorecard dependency result is separate. It does not prove an APTL vulnerability. A clean claim requires clean advisory-scanner results. |
| Analysis | `static_analysis`, `static_analysis_common_vulnerabilities`, `static_analysis_fixed`, `static_analysis_often`, `dynamic_analysis`, `dynamic_analysis_unsafe`, `dynamic_analysis_enable_assertions`, `dynamic_analysis_fixed` | Met where applicable. SonarCloud and pip-audit are blocking checks. Trivy and OSV-Scanner report dependency and artifact findings. Property-based fuzz tests and release qualification provide dynamic analysis with assertions. Memory-unsafe-language analysis is not applicable. No confirmed exploitable static- or dynamic-analysis finding is awaiting remediation. |

## Honest Limitations

The assessment does not claim Silver or Gold.
OpenSSF Scorecard and Best Practices are separate programs.
The assessment-time Scorecard had separate findings for approvals, fuzzing integration, dependency vulnerabilities, branch protection, and scan frequency. Those findings remain
visible and are not waived by a passing self-assessment.

For current review and publication steps, follow [Update the assessment](update-assessment.md).
