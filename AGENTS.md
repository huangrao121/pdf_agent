# AGENTS.md

## Setup
uv sync

## Unit Tests
uv run pytest {Path to the specific unit test} -v

## Integration Tests
uv run pytest {Path to the specific integration test} -v

## Lint
uv run ruff check . --fix && uv run ruff format .

## Rules
- Do NOT edit migrations
- Do NOT change terraform files
- Never commit secrets
- Prefer minimal diffs