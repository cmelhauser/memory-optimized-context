# Project handoff

**Written for a cold start.** You may be Claude, ChatGPT, Cursor, or a person. Assume you have
no memory of this project and no access to any prior session. Everything you need is in this
repository. Read this file, then `AGENTS.md`, then `CLAUDE.md`.

Last updated 14 September 2026, when #1 and #2 were merged.

## State

`v0.1.0` plus the unreleased work in `CHANGELOG.md`, on `main`:

- #1: the backfill fixes and the native default.
- #2: the Reflector-failure fix, `tools/e2e.sh`, and the review pass (full coverage, the wider
  lint, the lock under a long `learn`).

Both were squash-merged on 14 September 2026. The suite has 76 tests at 100 per cent of lines
and branches, and `tools/e2e.sh` passes its 41 checks on the Mac mini. Nothing has run against a
real `~/memory` store, and nothing is installed on the Mac mini: no `~/memory`, no hooks in
`~/.claude/settings.json`, no MCP registration, no container.

## Next steps, in order

1. Wait for Bitcoin Core's initial block download and Fulcrum's indexing to finish.
2. Install natively, as the README says: `tools/init_store.sh`; the three hooks from
   `hooks/settings.snippet.json` in `~/.claude/settings.json`; optionally the `.venv`, then
   `claude mcp add` and `examples/claude_desktop_config.native.json` for the MCP server. The
   Docker install is not needed; on the Mac mini it would first need Docker Desktop's builder
   working again (see the log).
3. Add `@~/memory/compiled/projects/<slug>.md` to each project's `CLAUDE.md`.
4. Backfill. Start with one repository (`learn --repo`) and read `compiled/projects/`, to judge
   the Reflector prompt before it runs over everything. Then `learn --all`: a usage limit stops
   it, and running it again resumes. Pass no `--notes` folder the Human Author has not named.
5. After a month of real journals, settle what is listed under "What is not settled". Cut 0.2.0
   as `RELEASING.md` describes when the Human Author wants a release.

## Handoff log

Newest first.

### 14 September 2026 — #1 and #2 merged

- Both pull requests were squash-merged into `main`, #1 as `2a07963`, each with a message
  written for `main`.
- Before #2 was merged, its final tree passed the whole CI set under `workflow_dispatch`,
  Python 3.10 to 3.13 and the `container` job included.
- Docker Desktop's builder on the Mac mini now times out loading the base image's metadata
  (`DeadlineExceeded`), although the host reaches Docker Hub. The image built there on
  13 September and builds on GitHub. Restarting Docker Desktop is the likely fix; other
  containers run there, so the restart is the Human Author's call. The native install does not
  need it.
- Nothing was run against the real store. The Bitcoin Core and Fulcrum rule still stands.

### 13 September 2026 — review pass to full coverage

- Coverage is 100 per cent of lines and branches over `bin/memory`, `tools/check_docs.py` and
  `tools/eval_recall.py`, with nothing excluded; the gate in `.coveragerc` enforces it. The
  network clients that used to be excluded now run against stand-ins.
- The lint ruleset is wider (`ruff.toml`) and clean, and actionlint runs locally as in CI.
- A long `learn` holds the lock for its whole run. The SessionStart hook now gives up after 2 s
  instead of 20, and the MCP tools answer "busy" instead of stopping the server.
- An embedding failure no longer rolls back a run; commit cursors are full hashes; the store's
  git history no longer takes claude.ai exports.
- CI runs on pull requests against any base branch, so a stacked pull request gets its checks.
- Stale prose fixed: the scope note in `.coveragerc`, the size note in `ruff.toml`, the next
  steps in `tools/bootstrap.sh`, the eval README's Docker path, and the Claude Desktop example,
  which was Docker-only.
- Names of the operator's private repositories had reached test fixtures and the changelog;
  they are now neutral. `AGENTS.md` rule 10 forbids it from here on.

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
- Scope agreed with the Human Author: `~/Documents/Claude`, a personal folder, is not
  ingested.
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
- Coverage stays at 100 per cent of lines and branches, with nothing excluded.

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

## Do not

- Do not run the hooks on the Mac mini until Bitcoin Core's initial block download and
  Fulcrum's indexing are finished; both compete for the same 8 GB.
- Do not point `autoMemoryDirectory` at `~/memory`. Claude Code's own AutoDream consolidation
  writes there and would race the compiler. Native directories stay native.
- Do not pass `~/Documents/Claude` to `learn --notes`.
- Do not put a key in `.env` unless you mean to move to Docker: the hooks follow it at once,
  and the container's database starts empty.
