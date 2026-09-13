# Changelog

Versioning is explained in `RELEASING.md`. In short: MAJOR means the store schema or the
journal line format changed in a way an existing `~/memory` cannot survive without migration,
MINOR means a new capability or adapter, PATCH means corrections and tooling. It stays below 1.0
until the system has run against a real store for at least a month.

## [Unreleased]

### Added

- `memory learn`: incremental adapters for git repositories (commit messages since the last
  seen hash, docs by content hash), note folders, a backfill of every Claude Code transcript
  under `~/.claude/projects`, and claude.ai exports in both message shapes; `--all` runs every
  source. `[project] fact` lines in any doc or note are ingested with no LLM call.
- `vector_rank`: numpy matmul when numpy is present, `math.sumprod` otherwise. numpy pinned in
  the image. 5,000 x 1024 ranking: ~20 ms with numpy, ~300 ms without.
- Compose mounts `~/GitHub` read-only; the image ships `eval_recall.py`.

### Fixed

- `learn --repo` re-reflected the whole history on every run because `git cat-file -e`
  succeeds silently and the helper treated empty stdout as failure. Caught by
  `test_learn_repo_reads_commits_and_docs_incrementally`.

## [0.1.0] - 2026-09-13

### Added

- `bin/memory`: single-file CLI. SQLite store with FTS5, ADD-only lessons keyed by
  `sha1(project | normalised text)`, votes as duplicate count.
- Append-only journals, one file per event, exclusive-create so two events in one process and
  one tick cannot collide.
- One `mkdir` lock around every write path, with stale-lock recovery after ten minutes.
- Compiler writing `compiled/PLAYBOOK.md` and `compiled/projects/*.md` by atomic rename, with a
  git commit per compile when the root is a repository.
- Reflector: Claude (SDK or `claude -p`) extracts lessons from Claude Code transcripts,
  incrementally by byte offset, and from claude.ai `conversations.json` exports, idempotent per
  conversation `updated_at`.
- Contradiction check: new lessons are compared with their nearest neighbours; `same` merges
  votes, `contradicts` marks the older lesson superseded. Nothing is deleted.
- Pruning by decayed score, `(votes + helpful - 2*harmful) * 0.5^(age/90d)`, and by
  `harmful >= 2`; archived lessons go to `archive/YYYY-MM.md` and stay searchable with `--all`.
- Optional embeddings (Voyage or OpenAI) fused with FTS5 by reciprocal rank fusion.
- MCP server with `recall`, `remember`, `feedback`; stdio and streamable HTTP; compatible with
  `mcp` 1.x and 2.x.
- Claude Code hooks (`SessionStart`, `Stop`, `SubagentStop`) that fork and return immediately,
  with a recursion guard for the Reflector's own `claude -p` call.
- Dockerfile and Compose file: pinned `python:3.12.6-slim-bookworm`, SQLite on a named volume,
  bind mounts at identical host and container paths, MCP on host loopback only.
- Test suite: 46 tests, coverage gate at 80 per cent on `bin/memory`, including a six-process
  concurrent-hook test.
- `tools/check_docs.py`: test counts, version, relative links and host paths re-derived from
  the tree; runs in the CI `lint` job.
- `tools/eval_recall.py` and `eval/`: recall@k harness against a frozen question set.
- `docs/`: architecture as built, concurrency audit mapping each race to its test, research
  notes with what each finding changed, six decision records, and the diagram history from the
  original paper sketch to the as-built drawing.
- `examples/`: claude.ai Project instructions, global and per-project `CLAUDE.md` lines, Claude
  Desktop MCP config.
