# Update the OpenSSF assessment

Use this guide when project practices or OpenSSF criteria change.
The [2026-09-22 assessment](openssf-best-practices.md) is a historical record.
Do not treat its advisory counts or findings as current evidence.

## Review evidence

1. Read the current [passing criteria](https://www.bestpractices.dev/criteria/0).
2. Check each proposed answer in `.bestpractices.json` against current repository evidence.
3. Check the contribution, support, private vulnerability-reporting, release, and verification procedures.
4. Record the source revision, review date, evidence links, and limits for each answer.
5. Keep historical counts and observations with their original review window.
6. Ask the maintainer to confirm response-history and security-knowledge attestations personally.

OpenSSF Scorecard and Best Practices are separate programs.
A passing self-assessment does not waive scanner findings or establish Silver or Gold status.
Do not describe dependency findings as resolved until their scanners report that result.

## Publish an approved assessment

Use a maintainer-owned web session and obtain approval before changing the external badge record.

1. Sign in to the [badge application](https://www.bestpractices.dev/).
2. Register `https://github.com/OpenRAE/lilrae` or open its existing record.
3. Review the verified proposals and required personal attestations.
4. Save the approved assessment.
5. Add the numeric badge URL returned by OpenSSF to `README.md` only after the application reports passing.
6. Do not guess a badge ID or present an in-progress badge as earned.

Keep evidence free of private advisory details, credentials, and unreviewed logs.
