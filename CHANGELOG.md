# Changelog

Versioning is explained in `RELEASING.md`. In short: MAJOR means the store schema or the
journal line format changed in a way an existing `~/memory` cannot survive without migration,
MINOR means a new capability or adapter, PATCH means corrections and tooling. It stays below 1.0
until the system has run against a real store for at least a month.

## [Unreleased]

### Added

- `learn --transcripts` reads every transcript the machine holds, not only Claude Code's:
  Cursor's own store including each session's subagents, Claude Desktop's agent-mode sessions, and
  Codex rollouts, whose conversation is read out of the tool calls, reasoning and world state
  around it. `--transcripts-from DIR` takes any other folder. A session run inside a git
  repository is filed under it whatever wrote it; the rest are filed under their tool.
  `test_the_backfill_reads_cursor_desktop_and_codex_as_well`,
  `test_a_codex_rollout_reads_as_a_transcript`, `test_transcripts_from_reads_a_folder_you_name`.
- `decode_cwd`: a folder name that encoded a path by turning `/` into `-` is decoded against the
  filesystem, which is the only way to tell a repository's own hyphen from a path separator. It
  stops at the deepest path that exists, so a worktree since removed still names its repository.
  `test_a_folder_name_that_encoded_a_path_is_decoded_against_the_filesystem`.

- `learn --max-calls N`: a run stops after about N Reflector calls, each reflection counting one
  plus one per lesson it returns, and keeps its place like a usage-limit stop, so a first backfill
  can be spread over days. `test_learn_max_calls_stops_cleanly_and_the_next_run_carries_on`.
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
- Eighteen tests take the suite to full coverage: the lock giving up, `ingest --wait`, the MCP
  tools on both `mcp` versions and both transports and while busy, the SDK path without its
  package, the CLI's JSON, every embedding outcome, `journal_write` running out of names, junk
  lines in a transcript, each script run as `__main__`, every `check_docs.py` failure,
  `eval_recall.py` in the image's layout, `tools/init_store.sh`, and `tools/bootstrap.sh --dry-run`.
- `examples/claude_desktop_config.native.json`, beside the Docker one, now `.docker.json`.
- Cursor agent transcripts. Cursor runs the hooks in `~/.claude/settings.json`, and its
  transcripts mark a turn with `role` rather than `type`; the reader takes either, so a Cursor
  session's Stop hook learns from it. `test_cursor_transcript_lines_are_read_like_claude_codes`.
- actionlint in `tools/run_ci_locally.sh`, so the local lint is CI's; `numpy` and `actionlint-py`
  in `requirements-dev.txt`.

### Changed

- README gives Claude Desktop's config path on Windows as well as macOS.
- The hooks choose their runner in `hooks/runner.sh`: `MEMORY_RUNNER` if set, else the container
  when this checkout's `.env` holds an `ANTHROPIC_API_KEY`, else `bin/memory` natively with
  `claude -p`. Native was opt-in before; without a key it is now the default, because the image
  has no `claude` CLI and so no Reflector without one. The native runner prefers
  `.venv/bin/python3`, then Homebrew's Python (macOS's `/usr/bin/python3` is 3.9), and appends
  `~/.local/bin` to `PATH` so `claude` is found.
  `test_hook_runner_is_native_without_an_api_key_and_docker_with_one`.
- The Compose image is tagged `memory-optimized-context:compose` instead of `1.0.0`, which read
  as a release the project has not reached, and the unused `UID=502` is gone.
- The coverage gate is 100 per cent of lines and branches over `bin/memory`,
  `tools/check_docs.py` and `tools/eval_recall.py`, with nothing excluded. It had covered lines
  of `bin/memory` only, with the network clients excluded; those now run against stand-ins.
- The lint ruleset adds whitespace, the 160-column limit, ambiguous names, lambda assignment,
  pyupgrade, simplify, pylint errors and warnings, and ruff's own rules, all clean. The E70x
  one-liner rules stay off by design.
- The SessionStart hook runs `ingest --wait 2`, so a long `learn` holding the lock costs a new
  session at most 2 s instead of 20; `ingest --wait SECONDS` is new.
- The commit cursor is the full hash, which cannot become ambiguous as a repository grows.
- `tools/init_store.sh` keeps `exports/` out of the store's git history.
- CI runs on pull requests against any base branch, so a stacked pull request is checked.
- `tools/bootstrap.sh` points at the README's install rather than a Docker-first sequence, and
  the eval README's Docker path reads the questions from the mounted checkout.
- Test fixtures and this changelog use neutral names instead of the operator's private
  repositories.

### Removed

- Personal data from the tracked files: the Human Author's name and both email addresses (README,
  `AGENTS.md`, `ATTRIBUTION.md`, `CITATION.cff`, `LICENSE`, the Reflector prompt), and details of
  the operator's machine in the docs, tests and eval examples. `tools/check_docs.py` now rejects
  any email address and any `/home/<name>` path.
- `HANDOFF.md` from the repository. Session handoffs stay in an untracked, git-ignored copy.
- The Compose file's `platform: linux/arm64`; Compose builds for the host's architecture.

### Fixed

- A writer waiting for the lock asked how old it was, and the holder could release in the moment
  between that writer's failed `mkdir` and its `stat`. The `FileNotFoundError` reached the caller:
  for a Stop hook, a lost run. A lock that vanishes mid-check now simply means "try again".
  `test_a_waiter_survives_the_lock_vanishing_between_its_mkdir_and_its_stat`.
- Breaking a crashed holder's lock was not exclusive. Two writers that both judged it stale could
  both remove it and both create their own, after which each one's release removed whichever lock
  was there. Breaking now happens under `.lock.break`, and the staleness is checked again while
  holding it. `test_only_one_writer_breaks_a_crashed_holders_lock`.
- A lock now carries its holder's token, and a holder only touches and only removes a lock that is
  still its own, so one broken lock cannot cascade into no lock at all.
  `test_a_holder_leaves_a_lock_that_is_no_longer_its_own`.

- `fts_query` kept only ASCII word characters, so an accented or non-Latin word was cut to a stump
  that matched nothing: a lesson could not be found by its own words, by `search`, by MCP recall,
  or by the contradiction check that would have seen it as a duplicate. Tokens are now `\\w` under
  Unicode. `test_a_lesson_with_an_accent_can_be_found_by_its_own_words`.
- `--max-calls` charged one call per reflection plus one per lesson returned, for contradiction
  checks that mostly never happen: a lesson already in the store, or one with nothing to compare
  against, costs no check. A budget of 60 therefore bought a fraction of the work it was given.
  Every Reflector call is now counted where it is made, `reconcile` included, and a check that
  would exceed the budget is left for the next run.
  `test_the_budget_counts_the_calls_it_actually_makes`.
- `db()` ended its transaction but never closed the connection. The CLI got away with it because
  the process ends; the MCP server runs for as long as the editor does and opens one per tool
  call. `test_a_database_handle_is_closed_when_its_block_ends`.

- A `learn` run was a single transaction: every lesson and every cursor it had earned was
  discarded if anything interrupted it — a crash, a reboot, the machine sleeping, a Ctrl-C. An
  overnight backfill once held the store for ten hours and saved none of it. Each source is now
  reconciled and committed as it is finished, so an interruption costs the transcript, repository,
  note folder or conversation in hand and nothing else.
  `test_an_interrupted_learn_keeps_the_sources_it_finished`,
  `test_a_checkpoint_reconciles_before_it_commits`.

- A failed `claude -p` call was logged by the first 300 bytes of its output, which are counters;
  the CLI reports the reason in `result`, at the end. An expired login therefore logged nothing
  that named it, and the twice-daily backfill read "paused" for two days while it learned nothing.
  The reason is now extracted, logged, and carried into the message `learn` exits with.
  `test_a_failed_cli_call_is_reported_by_its_reason_not_its_first_bytes`.
- `learn` and `ingest` exited 1 whether they had read half their work or none of it, so a run
  that could not reach the Reflector at all was indistinguishable from a normal `--max-calls`
  stop. A run that read nothing now exits 2.
  `test_a_run_that_read_nothing_exits_differently_from_one_that_ran_out_of_budget`.
- `remember` reported success for lessons it did not store: a project slug with a space or a
  leading dash was dropped by `LESSON_RE` on the way back in, and only a lesson's first line was
  kept. It now stores the whole lesson on one line, or refuses with the reason.
  `test_remember_saves_the_whole_lesson_or_says_why_it_cannot`.
- `vote` and the MCP `feedback` tool answered "ok" for any id at all, so a typo read as recorded.
  Both now report that no lesson has that id.
  `test_a_vote_for_a_lesson_that_is_not_there_is_not_ok`.

- A lesson's project slug was whatever the Reflector answered, and `compile_` makes a slug a
  filename, so a slug of `../../../escaped` wrote outside `~/memory` and replaced whatever file
  it landed on. The slug is chosen from text that merely passed through a session, so the target
  was too. `as_project` now keeps a slug to `LESSON_RE`'s own shape where the answer is read,
  and `compile_` skips any slug a store written before this fix may already hold.
  `test_a_project_slug_is_a_name_never_a_path`.
- A transcript line whose `message`, `content` or text block was null raised `AttributeError`,
  and an export message of the same shape raised `TypeError`. A `learn` run is one transaction,
  so either one discarded every lesson and every cursor the run had earned. Both now read as
  "not a turn" and "no text", which is what their docstrings always promised.
  `test_a_transcript_line_of_an_unknown_shape_is_not_a_turn`,
  `test_an_export_message_of_an_unknown_shape_is_empty_text`.
- `parse_json` sliced from the first `[` to the last `]`, so an answer that opened with a
  sentence containing a bracket parsed as nothing: the lessons were dropped and the cursor moved
  on past them. It now takes the first array or object that parses.
  `test_an_answer_that_opens_with_prose_still_yields_its_lessons`.
- A contradiction check that answered with a JSON array instead of an object ended the run with
  `AttributeError`, rolling it back. An answer that is not a verdict is now no verdict.
  `test_reconcile_ignores_an_answer_that_is_not_a_verdict`.

- Every Reflector call through `claude -p` saved a Claude Code session, so a backfill found
  thousands of transcripts of its own prompts and would have reflected their windows again, and
  each run made more. The call now passes `--no-session-persistence`, and `learn --transcripts`
  skips a transcript whose first user turn is the Reflector's instructions.
  `test_backfill_skips_transcripts_the_reflector_left_behind`.
- A Stop hook that got the lock after earlier stops had given up reflected only the last 30k
  characters of everything since, then moved the cursor to the end, so the middle of a busy
  session was never learned. It now reads from its cursor, oldest first, at most two windows
  per stop, and moves the cursor only past them.
- A ticked Markdown checkbox (`- [x] done`) in a doc or note was read as a lesson tagged for
  project `x`, so release checklists filed their items under `x`. A task-list item is now
  prose. `test_a_ticked_checkbox_is_not_a_project_tag`.
- `learn --repo` on a folder that does not exist exited 0 having read nothing, so a typo passed
  for success. It now fails with `no such folder` before taking the lock.
  `test_learn_repo_refuses_a_folder_that_does_not_exist`.
- A `learn` longer than ten minutes lost its lock. Any writer that found the lock older than
  600 s broke it as a crashed holder's, so a Stop hook could write while the `learn` was still
  running, and SQLite refused it with `database is locked`. The holder now touches the lock
  every 60 s, so only a crashed holder's lock goes stale. `test_a_live_holder_keeps_its_lock_fresh`.
- `learn --repo` re-reflected the whole history on every run because `git cat-file -e`
  succeeds silently and the helper treated empty stdout as failure. Caught by
  `test_learn_repo_reads_commits_and_docs_incrementally`.
- `learn --transcripts` named each project after the last `-` segment of its encoded folder:
  repositories whose hyphenated names shared a last segment all got the same slug, and no slug
  matched the one the Stop hook uses. The slug now comes from the `cwd`
  recorded in the transcript, through `project_of()`, which the hook shares; a Claude Code
  worktree counts as its repository. `test_learn_transcripts_backfills_claude_code_dirs`,
  `test_hook_files_a_worktree_session_under_its_repository`.
- `learn --transcripts` reflected only the last 30k characters of each transcript, about 6 per
  cent of one real history. A backfill now reflects every ~30k window.
  `test_backfill_reads_every_window_and_a_hook_two_oldest_first`.
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
- A writer that could not get the lock raised a bare `SystemExit`, which inside an MCP tool could
  stop the server during a long `learn`. It is now `LockBusy`: the CLI still exits with its
  message, and `remember` and `feedback` answer "busy", a remembered lesson staying journaled.
  `test_mcp_tools_answer_busy_while_a_learn_holds_the_lock`.
- An embedding call that failed raised through `learn` and rolled back the whole run. It now logs
  and leaves the vectors for `embed_missing` to fill in later.
  `test_embed_batches_both_providers_and_never_fails_a_run`.
- `memory hook --input` left its file open.

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
- Test suite: forty-six tests, coverage gate at eighty per cent on `bin/memory`, including a six-process
  concurrent-hook test.
- `tools/check_docs.py`: test counts, version, relative links and host paths re-derived from
  the tree; runs in the CI `lint` job.
- `tools/eval_recall.py` and `eval/`: recall@k harness against a frozen question set.
- `docs/`: architecture as built, concurrency audit mapping each race to its test, research
  notes with what each finding changed, six decision records, and the diagram history from the
  original paper sketch to the as-built drawing.
- `examples/`: claude.ai Project instructions, global and per-project `CLAUDE.md` lines, Claude
  Desktop MCP config.
