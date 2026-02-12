---
name: "issue2pr"
description: "End-to-end: take a GitHub issue, create a branch, implement, run unit+integration tests, and if green then stage/commit/push and open a draft PR for review. If tests fail, iterate and retry up to a limit."
---

## Prerequisites (must enforce)
- Require GitHub CLI `gh`. Run `gh --version`. If missing, ask the user to install and stop.
- Require authenticated `gh` session. Run `gh auth status`. If not authenticated, ask user to run `gh auth login`, then stop.
- Repo must be a clean git repo. Run `git rev-parse --is-inside-work-tree` and `git status -sb`.

## Inputs (ask only if missing)
- issue: Github issue URL or "#123"
- description: kebab-case short summary (used in branch/commit/PR title)
- base_branch: branch to branch off from (default: main or master)
- unit_test_cmd: repo-specific (from AGENTS.md if present)
- integration_Test_cmd: repo-specific (from AGENTS.md if present)

## Naming conventions
- Branch: `codex/{issue number}-{description}`
- Commit: `{issue number}: {description}`
- PR title: `{issue number}: {description}`

## Workflow

### 0. Load guidance
- If `AGENTS.md` exists at repo root, read it first and follow its commands for install/tests/lint.
- Also read relevant docs if present: README, CONTRIBUTING, Makefile/package scripts.

### 1. Sync and branch
- Switch base branch and sync:
  - `git switch {base_branch}`
  - `git pull --rebase`
- create new branch:
  - `git switch -c codex/{issue number}-{description}`

### 2. Understand issue and plan
- Read the issue title and escription
- If the issue has implementation plan, then follow it, else create one:
  - Break down the issue into smaller tasks/steps
  - For each task, outline the approach and any dependencies

### 3. Implement + test loop
- Attempt up to 2 iterations:
  1) Implement the planned changes.
  2) Run unit tests:
     - `{unit_test_cmd}`
  3) Run integration tests:
     - `{integration_test_cmd}`
  4) If any test fails:
     - capture the failing output (summary + key error lines)
     - identify root cause
     - fix and retry (next iteration)

- If still failing after 3 iterations:
  - stop and report:
    - what’s failing
    - suspected cause
    - what files changed
    - suggested next steps

### 4. If passed, Stage, commit, push, PR
- Confirm status, then stage everything:
  - `git status -sb`
  - `git add -A`
- Commit:
  - Summarize changes in commit message
  - `git commit -m "{description}"`
- Push with tracking:
  - `git push -u origin $(git branch --show-current)`

### 5. Open a draft PR via gh
- Create draft PR:
  - `GH_PROMPT_DISABLED=1 GIT_TERMINAL_PROMPT=0 gh pr create --draft --fill --head $(git branch --show-current)`
- Ensure PR title is: `[codex] {description}`
- PR body must be detailed prose with:
  - What issue this fixes (link/number)
  - User impact (before/after)
  - Root cause
  - Fix details (key files/approach)
  - Tests run (unit + integration commands + result)

## Safety / Guardrails
- Do not touch secrets. Never print token values.
- Prefer minimal changes.
- If uncertain about behavior, add TODO notes in PR body and keep PR as draft.