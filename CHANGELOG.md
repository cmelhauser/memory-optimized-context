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
- `test_llm_uses_the_sdk_when_an_api_key_is_present`: the SDK Reflector path, the one both
  installs take when a key is configured, and its fall-through to `claude -p` when `anthropic`
  is not installed.
- `tools/e2e.sh`: both installs end to end on the operator's machine, against a fake Messages
  API (the SDK path, as if a key were provided) and a fake `claude` (the subscription path), in
  throwaway home directories: native with a key, native through the real hooks, a usage limit
  twice during a backfill and the resumed run, and Docker through Compose with the hooks and MCP
  over HTTP. Local only; the Docker phase needs Docker Desktop and skips itself beside a real
  install.

### Changed

- The hooks choose their runner in `hooks/runner.sh`: `MEMORY_RUNNER` if set, else the container
  when this checkout's `.env` holds an `ANTHROPIC_API_KEY`, else `bin/memory` natively with
  `claude -p`. Native was opt-in before; without a key it is now the default, because the image
  has no `claude` CLI and so no Reflector without one. The native runner prefers
  `.venv/bin/python3`, then Homebrew's Python (macOS's `/usr/bin/python3` is 3.9), and appends
  `~/.local/bin` to `PATH` so `claude` is found.
  `test_hook_runner_is_native_without_an_api_key_and_docker_with_one`.
- The Compose image is tagged `memory-optimized-context:compose` instead of `1.0.0`, which read
  as a release the project has not reached, and the unused `UID=502` is gone.

### Fixed

- `learn --repo` re-reflected the whole history on every run because `git cat-file -e`
  succeeds silently and the helper treated empty stdout as failure. Caught by
  `test_learn_repo_reads_commits_and_docs_incrementally`.
- `learn --transcripts` named each project after the last `-` segment of its encoded folder:
  `us-hail-cat-model`, `us-hurricane-cat-model` and `global-unified-cat-model` all became
  `model`, and no slug matched the one the Stop hook uses. The slug now comes from the `cwd`
  recorded in the transcript, through `project_of()`, which the hook shares; a Claude Code
  worktree counts as its repository. `test_learn_transcripts_backfills_claude_code_dirs`,
  `test_hook_files_a_worktree_session_under_its_repository`.
- `learn --transcripts` reflected only the last 30k characters of each transcript, about 6 per
  cent of the history on the Mac mini. A backfill now reflects every ~30k window; the Stop hook
  keeps its one-call tail. `test_backfill_reflects_every_window_but_the_hook_only_the_tail`.
- `reflect_batches` budgeted the text but not the `### name` headers or the label, so the
  Reflector's 30k tail cut dropped the head of any window made of many short commits.
  `test_reflect_batches_never_cut_the_head_of_a_window`.
- In the container `Path.home()` was `/root`, so `learn --all` found no transcripts and no
  repositories under the mounts. Compose sets `HOME=${HOME}`, and git's identity and
  `safe.directory` moved to `/etc/gitconfig` so compile commits survive the change.
  `test_container_home_is_the_host_home`.
- CI's compose check failed on every run because `.env` is never committed. It now validates
  against `.env.example`, and `tools/run_ci_locally.sh` checks a copy instead of skipping.
- A Reflector call that failed was taken for "no lessons" and the source's cursor still moved
  on, so on a subscription a usage limit silently skipped the rest of a backfill. `reflect()` now
  raises `ReflectorFailed` when no answer comes, and cursors move only past what was reflected: a
  transcript window by window, commits up to the last one reflected, a doc once its prose is
  reflected, its tagged lines counted once. `learn` and `ingest` keep and compile what was done
  and exit non-zero with a message; the next run resumes there. The Stop hook still journals and
  compiles, and leaves the transcript for the next stop.
  `test_backfill_stops_at_a_failed_window_and_the_next_run_resumes_there`,
  `test_learn_stops_on_a_failed_reflector_keeps_its_progress_and_resumes`,
  `test_hook_still_journals_and_compiles_when_the_reflector_fails`.
- An SDK error (API, rate limit, network) or a `claude -p` timeout raised through the whole run
  and rolled it back, and `claude -p` can report an error in its output rather than its exit
  status. `llm()` now returns no answer for all of them, asks `claude -p` for
  `--output-format json` so it can read the CLI's own `is_error`, and in `auto` mode falls back
  from a failed SDK call to the CLI. `test_llm_answers_none_on_sdk_errors_cli_errors_and_timeouts`.
- `learn_repo` split the log on blank lines, so a commit whose body had paragraphs became several
  chunks, one of them named after a body word as if it were a hash. Commits are now delimited by
  `\x1e` and chunked whole. `test_commit_cursor_after_a_failure_is_the_last_reflected_commit`.
- The transcript reader moved its offset past a half-written last line, which was then never
  read. `test_a_half_written_last_line_is_left_for_the_next_read`.

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
- Test suite: forty-six tests, coverage gate at 80 per cent on `bin/memory`, including a six-process
  concurrent-hook test.
- `tools/check_docs.py`: test counts, version, relative links and host paths re-derived from
  the tree; runs in the CI `lint` job.
- `tools/eval_recall.py` and `eval/`: recall@k harness against a frozen question set.
- `docs/`: architecture as built, concurrency audit mapping each race to its test, research
  notes with what each finding changed, six decision records, and the diagram history from the
  original paper sketch to the as-built drawing.
- `examples/`: claude.ai Project instructions, global and per-project `CLAUDE.md` lines, Claude
  Desktop MCP config.
