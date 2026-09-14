# Project handoff

**Written for a cold start.** You may be Claude, ChatGPT, Cursor, or a person. Assume you have
no memory of this project and no access to any prior session. Everything you need is in this
repository. Read this file, then `AGENTS.md`, then `CLAUDE.md`.

Last updated 13 September 2026, after the first review on the Mac mini.

## State

`v0.1.0` plus the unreleased fixes in `CHANGELOG.md`. It is tested (52 tests, 93 per cent
coverage, concurrency covered by a real six-process test), and both installs have run end to
end on the Human Author's Mac mini against a fake Reflector. It has not yet run against a real
`~/memory` store. Nothing is installed on the Mac mini: no `~/memory`, no hooks in
`~/.claude/settings.json`, no MCP registration, no container.

## Handoff log

Newest first.

### 13 September 2026 — first review on the Mac mini

- The image was built on arm64 for the first time (Docker Desktop, 4 GB VM). The MCP server
  answers over HTTP; the Compose mounts resolve at identical paths.
- Three defects that would have made the first `learn --all` wrong were found against the real
  `~/.claude/projects` and fixed: project slugs decoded from folder names (three repositories
  collapsed to `model`), transcript backfill limited to the last 30k characters (6 per cent of
  11.7M characters of history), and `Path.home()` being `/root` in the container. A fourth, the
  window budget in `reflect_batches`, was found while fixing the second. See `CHANGELOG.md`.
- There is no `ANTHROPIC_API_KEY` on this machine, so the hooks now default to the native
  install with `claude -p`, and use the container only when `.env` holds a key
  (`hooks/runner.sh`; decision 006 amended).
- Verified end to end with fakes, in throwaway home directories: native with a key (SDK),
  native without one (`claude -p`, through the real hooks), and Docker (Compose, `learn --all`,
  hooks via `docker exec`, MCP over HTTP and stdio). No real API call and no real `claude -p`
  call was made.
- CI on `main` had been red since the first push, because its compose check needs `.env`.
  Fixed.
- Scope agreed with the Human Author: `~/Documents/Claude` (job-search and résumé material,
  synced to iCloud) is not ingested.
- The Bitcoin Core and Fulcrum rule under "Do not" still stands, although neither was running
  during this session. Nothing was run against the real store.

### 13 September 2026 — v0.1.0

Built in a sandbox with no Docker daemon. The base image tag was confirmed on Docker Hub with an
arm64 manifest, the Dockerfile's `pip install` line was run in a clean Python 3.12 venv, and
`learn --all` was exercised over fake repositories, notes, transcripts and an export with a
traceable fake LLM.

## What is settled

- The architecture: append-only journals, one locked compiler, file-first with SQLite as a
  derived index. See `README.md`.
- The concurrency model. See `CLAUDE.md`, "Invariants the tests enforce".
- The choice not to fine-tune, not to run a vector server, and not to self-host OAuth for
  claude.ai. The claude.ai path is Google Drive sync of `compiled/` and `journal/claude-ai/`.
- Which install runs: native with `claude -p` unless `.env` holds an API key.

## What is not settled

- The scoring constants (`half_life_days=90`, `min_score=0.15`, `max_lines=150`). Guesses.
  Revisit after a month of real journals.
- The Reflector prompt. It has been exercised only against a fake LLM.
- Whether embeddings earn their cost. They are off by default and the README says when to turn
  them on.
- A Reflector call that fails still advances its source's cursor. When `claude -p` exits
  non-zero (a usage limit, say), `llm()` returns nothing, `reflect()` returns no lessons, and
  the window is recorded as read, never to be retried. An SDK error does the opposite: it
  propagates and rolls back the whole run. The first `learn --all` here is about 510 windows,
  so until this is fixed, run it a source at a time.

## Before the first real run

1. Wait for Bitcoin Core's initial block download and Fulcrum's indexing to finish.
2. Install natively as the README says: `tools/init_store.sh`, the hooks from
   `hooks/settings.snippet.json`, and optionally the `.venv` for the MCP server.
3. Backfill one source at a time, reading `compiled/projects/` after each: one repository with
   `learn --repo`, then `learn --transcripts`, then the rest.

## Do not

- Do not run the hooks on the Mac mini until Bitcoin Core's initial block download and
  Fulcrum's indexing are finished; both compete for the same 8 GB.
- Do not point `autoMemoryDirectory` at `~/memory`. Claude Code's own AutoDream consolidation
  writes there and would race the compiler. Native directories stay native.
- Do not pass `~/Documents/Claude` to `learn --notes`.
- Do not put a key in `.env` unless you mean to move to Docker: the hooks follow it at once,
  and the container's database starts empty.
