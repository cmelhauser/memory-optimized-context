# Project handoff

**Written for a cold start.** You may be Claude, ChatGPT, Cursor, or a person. Assume you have
no memory of this project and no access to any prior session. Everything you need is in this
repository. Read this file, then `AGENTS.md`, then `CLAUDE.md`.

Last updated 13 September 2026, after the Reflector-failure fix and the end-to-end harness.

## State

`v0.1.0` plus the unreleased work in `CHANGELOG.md`, in two pull requests. #1 holds the backfill
fixes and the native default, with CI green on every job. The second is stacked on #1 and holds
the Reflector-failure fix and `tools/e2e.sh`. Neither is merged: merging is the Human Author's
step. The suite has 58 tests at 93 per cent coverage, and `tools/e2e.sh` passes its 41 checks
on the Mac mini. Nothing has run against a real `~/memory` store, and nothing is installed on the
Mac mini: no `~/memory`, no hooks in `~/.claude/settings.json`, no MCP registration, no
container.

## Handoff log

Newest first.

### 13 September 2026 — Reflector failures and the end-to-end harness

- A Reflector call that gets no answer no longer moves any cursor. That covers a usage limit, an
  API error, a CLI timeout, and the CLI reporting `is_error`. `learn` stops at the first such
  call, keeps and compiles what it did, and exits non-zero. The next run resumes without sending
  anything twice. The Stop hook journals and compiles regardless.
- `claude -p` is now asked for `--output-format json`. That was decided after reading the
  installed CLI's result object: it carries `is_error`, and a `subtype` of `success` or
  `error_during_execution`.
- `tools/e2e.sh` is now in the repository. It is the harness that verified the first review,
  plus a scenario that hits a usage limit twice during a backfill. It needs no key and makes no
  real call. Run it after any change to the hooks, the Dockerfile, the Compose file or the
  Reflector.
- Compose's image tag is now `compose` (it was `1.0.0`), and the unused `UID=502` is gone.
- This session's permission settings refused the merge of #1, so both pull requests wait for the
  Human Author.

### 13 September 2026 — first review on the Mac mini

- The image was built on arm64 for the first time (Docker Desktop, 4 GB VM). The MCP server
  answers over HTTP, and the Compose mounts resolve at identical paths.
- Three defects that would have made the first `learn --all` wrong were found against the real
  `~/.claude/projects` and fixed:
  - project slugs were decoded from folder names, which collapsed three repositories into
    `model`;
  - transcript backfill read only the last 30k characters, 6 per cent of the 11.7M characters of
    history;
  - `Path.home()` was `/root` in the container.

  A fourth, the window budget in `reflect_batches`, was found while fixing the second. See
  `CHANGELOG.md`.
- There is no `ANTHROPIC_API_KEY` on this machine. The hooks therefore default to the native
  install with `claude -p`, and use the container only when `.env` holds a key
  (`hooks/runner.sh`; decision 006 amended).
- CI on `main` had been red since the first push, because its compose check needs `.env`. Fixed.
- Scope agreed with the Human Author: `~/Documents/Claude` (job-search and résumé material,
  synced to iCloud) is not ingested.
- The Bitcoin Core and Fulcrum rule under "Do not" still stands, although neither was running.
  Nothing was run against the real store.

### 13 September 2026 — v0.1.0

Built in a sandbox with no Docker daemon. The base image tag was confirmed on Docker Hub with an
arm64 manifest, and the Dockerfile's `pip install` line was run in a clean Python 3.12 venv.
`learn --all` was exercised over fake repositories, notes, transcripts and an export, with a
traceable fake LLM.

## What is settled

- The architecture: append-only journals, one locked compiler, file-first with SQLite as a
  derived index. See `README.md`.
- The concurrency model. See `CLAUDE.md`, "Invariants the tests enforce".
- The choice not to fine-tune, not to run a vector server, and not to self-host OAuth for
  claude.ai. The claude.ai path is Google Drive sync of `compiled/` and `journal/claude-ai/`.
- Which install runs: native with `claude -p` unless `.env` holds an API key.
- A failed Reflector call costs nothing already done, and nothing is sent twice after it.

## What is not settled

- The scoring constants (`half_life_days=90`, `min_score=0.15`, `max_lines=150`). Guesses.
  Revisit after a month of real journals.
- The Reflector prompt. It has been exercised only against a fake LLM.
- Whether embeddings earn their cost. They are off by default and the README says when to turn
  them on.
- claude.ai exports are still reflected one conversation at a time, from its last 30k
  characters, so a long conversation loses its beginning. Transcripts, commits and docs are
  windowed; exports are not yet.
- An answer with no JSON array in it counts as "no lessons", not as a failure, so one odd answer
  cannot stall a backfill. If the Reflector prompt drifts, that is where lessons would go
  missing unnoticed.

## Before the first real run

1. Merge #1, then the pull request stacked on it.
2. Wait for Bitcoin Core's initial block download and Fulcrum's indexing to finish.
3. Install natively as the README says: `tools/init_store.sh`, the hooks from
   `hooks/settings.snippet.json`, and optionally the `.venv` for the MCP server.
4. Add `@~/memory/compiled/projects/<slug>.md` to each project's `CLAUDE.md`.
5. Backfill. Start with one repository (`learn --repo`) and read `compiled/projects/`, to judge
   the Reflector prompt before it runs over everything. After that, `learn --all` can run
   whole: a usage limit stops it, and running it again resumes.

## Do not

- Do not run the hooks on the Mac mini until Bitcoin Core's initial block download and
  Fulcrum's indexing are finished; both compete for the same 8 GB.
- Do not point `autoMemoryDirectory` at `~/memory`. Claude Code's own AutoDream consolidation
  writes there and would race the compiler. Native directories stay native.
- Do not pass `~/Documents/Claude` to `learn --notes`.
- Do not put a key in `.env` unless you mean to move to Docker: the hooks follow it at once,
  and the container's database starts empty.
