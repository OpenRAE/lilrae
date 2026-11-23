---
name: stage
description: Stage files, run pre-commit, fix failures, loop until clean
disable-model-invocation: true
---

# Stage Changes

Use this workflow to prepare the intended files for a commit.

## Step 1: Identify Changed Files

1. Run `git status` to inspect changed and untracked paths.
2. Exclude `.env` files, credentials, secrets, and large binaries.

## Step 2: Stage Files

Use `git add` with the intended paths.

## Step 3: Pre-commit Loop

Run at most five iterations:

1. Run `pre-commit run` on staged files.
2. If it passes, proceed to Step 4.
3. If it fails, read the output and fix each failure.
4. Stage the corrections and repeat the check.

Do not use `--all-files` locally. CI owns whole-tree checks.
If the fifth attempt fails, report the failures and stop.

## Step 4: Report

Show staged paths with `git diff --cached --name-only`.
Confirm the observed pre-commit result.
Only after success, report that the files are staged and ready for commit.
