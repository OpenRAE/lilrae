---
name: gh-workflow-monitor
description: Monitor GitHub workflows, propose fixes for failures, and report status
disable-model-invocation: true
---

# Monitor a GitHub workflow

Use `gh` for GitHub operations.

## Step 1: Check current branch.

Read the current branch with `git branch --show-current`.

## Step 2: Find its workflow run.

Find the GitHub Actions run for the current branch and candidate commit.
Use `gh run list` and `gh run view` to confirm its identity.
Do not substitute a passing run from an earlier commit.

## Step 3: Monitor the workflow run for failures.

Follow the selected run to its terminal state with `gh run watch <id>`.

## Step 4: If the workflow run fails, propose a fix.

Read the failed steps and logs. Explain the cause and proposed correction.
Keep secrets and private log content out of the report.

## Step 5: If the workflow run succeeds, report the status.

If plan mode is active, exit it.
Report the observed result and run URL.
