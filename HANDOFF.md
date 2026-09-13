# Project handoff

**Written for a cold start.** You may be Claude, ChatGPT, Cursor, or a person. Assume you have
no memory of this project and no access to any prior session. Everything you need is in this
repository. Read this file, then `AGENTS.md`, then `CLAUDE.md`.

Last updated 13 September 2026, after the learn adapters and the performance pass.

## State

`v0.1.0` is the first cut. It is tested (46 tests, 89 per cent coverage, concurrency covered by
a real six-process test) but it has not yet run against a real `~/memory` store on the Human
Author's Mac mini. The Docker image has not been built on arm64 hardware; the sandbox that
produced this repository had no Docker daemon. `docker compose up -d --build` is the first thing
to run.

## What was verified without a Docker daemon

The sandbox that produced this had no Docker. Instead: the base image tag was confirmed on
Docker Hub with an arm64 manifest; the exact `pip install` line from the Dockerfile was run in
a clean Python 3.12 venv; the image's entrypoint, CMD, healthcheck and the CI smoke command were
run against that venv; `learn --all` was exercised end to end over fake repositories, notes,
transcripts and an export with a traceable fake LLM. `docker compose up -d --build` on the Mac
mini is still the first real build.

## What is settled

- The architecture: append-only journals, one locked compiler, file-first with SQLite as a
  derived index. See `README.md`.
- The concurrency model. See `CLAUDE.md`, "Invariants the tests enforce".
- The choice not to fine-tune, not to run a vector server, and not to self-host OAuth for
  claude.ai. The claude.ai path is Google Drive sync of `compiled/` and `journal/claude-ai/`.

## What is not settled

- The scoring constants (`half_life_days=90`, `min_score=0.15`, `max_lines=150`). Guesses.
  Revisit after a month of real journals.
- The Reflector prompt. It has been exercised only against a fake LLM.
- Whether embeddings earn their cost. They are off by default and the README says when to turn
  them on.

## Do not

- Do not run the hooks on the Mac mini until Bitcoin Core's initial block download and
  Fulcrum's indexing are finished; both compete for the same 8 GB.
- Do not point `autoMemoryDirectory` at `~/memory`. Claude Code's own AutoDream consolidation
  writes there and would race the compiler. Native directories stay native.
