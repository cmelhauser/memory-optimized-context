# Changelog

Versioning is explained in `RELEASING.md`. In short: MAJOR means the store schema or the
journal line format changed in a way an existing `~/memory` cannot survive without migration,
MINOR means a new capability or adapter, PATCH means corrections and tooling. 1.0.0 declares the schema, `lid()` and
the journal line format stable.

## [Unreleased]

### Changed

- Pylint is a second gate beside ruff: `.pylintrc` requires 10.00 over `bin/memory`, `tools/` and `tests/`, in CI's lint job and in `tools/run_ci_locally.sh`, and pins `pylint` in `requirements-dev.txt`. What the configuration switches off is each given a reason in the file. Every function in the tool and the scripts now has a docstring, and a docstring that had been left under a statement in `ingest_transcript` is where it belongs.
- Every text file the tool reads or writes is opened as UTF-8 by name, instead of by the machine's locale, so what is written is the same on every host.
- The release workflow signs each platform's SBOM with `actions/attest`, which replaces the deprecated `actions/attest-sbom`; `RELEASING.md` says what to do when signing hits a Rekor timeout (re-run the failed job). `test_workflows_pin_actions_by_commit_and_only_the_publish_job_writes_packages` covers the workflow.
- Documentation brought in line with the code: the README's `MEMORY_ROOT`, `MEMORY_UID`, `MEMORY_GID`, `memory hook` flags and `MEMORY_MAX_LINES` rows (Claude Code's 200 lines is guidance for an instruction file, not an import cap); decision 002 (the database is the system of record, not a derived index), 005 and 006; the architecture notes on the commit, on the image and on `CLAUDE_CODE_DISABLE_AUTO_MEMORY`; the as-built diagram's inputs; the tag example in `RELEASING.md`; and the rule on personal data, which now names the copyright holder in `LICENSE` as the one exception.
- The copyright holder in `LICENSE` now reads "Christopher Melhauser (GitHub: cmelhauser)", the same name in every repository (it said "cmelhauser"). The MIT terms are unchanged.

## [1.1.0] - 2026-10-16

The container runs as an unprivileged user, so a Docker install made with an earlier release needs one command to give
its `memory-db` volume to it (under Changed). The store's schema, `lid()` and the journal line format are unchanged, and
the native install needs nothing.

### Added

- `SECURITY.md` (what is in scope, and GitHub's private vulnerability reporting as the way to report), a bug-report form
  that asks for invented text rather than a memory store, and a pull request checklist that repeats the privacy rules.
- `CODE_OF_CONDUCT.md`, the Contributor Covenant 2.1, with GitHub's private reporting form as the way to report.

### Changed

- The container no longer runs as root. The image creates an unprivileged user (uid 10001) and runs as it, and Compose
  takes `user:` from `MEMORY_UID` and `MEMORY_GID` (default 10001), so a Linux host can name its own uid. `/data` is made
  before the volume is declared, so a new `memory-db` volume belongs to that user. **Upgrading:** a `memory-db` volume
  made by an earlier release is owned by root and the container can no longer write it; give it to the new user once with
  `docker compose run --rm --user root --entrypoint chown memory -R 10001:10001 /data`. The native install is unchanged.
  `test_the_container_runs_as_an_unprivileged_user_and_compose_can_name_the_uid`.

- The nightly catch-up tests no longer show real macOS notifications. The runs that alert on purpose found the real
  `osascript`, so each run of the suite posted "The catch-up did not run as it should" to the desktop; `run_nightly`
  now puts a stand-in `osascript` under the test's `$HOME`.
- `LICENSE` is the standard MIT text alone, so GitHub recognises it. The note that versions up to 0.2.4 are under the
  Unlicense lives in `ATTRIBUTION.md`, where it already was.
  `test_the_license_is_the_plain_mit_text_and_the_repository_says_how_to_report_a_vulnerability`.

- Four timing bounds in the tests (the lock's break, its heartbeat, `ingest --wait` and the `LESSON_RE` line) are
  generous enough that a machine under heavy load no longer fails them; one did, at a load average of 46. Each still
  fails on the bug it guards against.

## [1.0.0] - 2026-10-16

The system ran against a real store for the month from 15 September 2026 without its schema, `lid()` or journal line
format changing from 0.1.0's, so an existing `~/memory` needs no migration, and 1.0.0 declares them stable: a change to
any of them is a MAJOR release with a migration from now on. Nothing else differs from 0.2.6 but the release workflow.

### Changed

- The release workflow signs the image's attestations. The build provenance is signed by `actions/attest-build-provenance`
  and each platform's SBOM, read back from the registry, by `actions/attest-sbom`: Sigstore certificates issued to the
  publish job's identity, recorded in GitHub's attestation store and attached to the image. Only that job holds
  `id-token: write` and `attestations: write`. BuildKit's own unsigned attestations stay. Check one with
  `gh attestation verify oci://ghcr.io/cmelhauser/memory-optimized-context:<tag> --repo cmelhauser/memory-optimized-context`.
  The steps run only on a tag, so the first tag after this change tests them.
  `test_workflows_pin_actions_by_commit_and_only_the_publish_job_writes_packages`.

## [0.2.6] - 2026-10-16

### Added

- The published image carries an SBOM and build provenance (`mode=max`) as BuildKit attestations. They are unsigned: signing
  them would need a keyless identity the workflow does not have yet. The release workflow cannot be run without a tag,
  so the first tag after this change is its test.

### Changed

- Dependabot no longer watches the Python lock files. Its pip updater regenerates them without `--universal`, which
  drops the environment markers: its pull request failed the Python 3.10 job, GitHub emailed a failed run, and it
  would have reopened every week. The locks are refreshed by hand as the first step of a release (`RELEASING.md`).
  Actions and the image's base stay watched.
  `test_dependabot_watches_the_actions_and_the_image_by_patch_and_leaves_the_universal_locks_to_a_person`.

- `mcp` is 2.3.0 and the image's `numpy` 2.5.4. Dependabot's pull request for them regenerated the lock files without
  `--universal`, which dropped the environment markers (`numpy` 2.5.4 for every Python, `colorama`, `exceptiongroup`
  and `tomli` gone), so it failed on 3.10; it is closed, and the locks are compiled by hand as their headers say.

- Everything that is installed is now pinned exactly, with hashes, and installed checking them. The image's base is named
  by digest (`python:3.12.15-slim-bookworm@sha256:...`, the index, so arm64 and amd64 both resolve) and its Python
  packages by `requirements-runtime.txt`, which pip installs with `--require-hashes`; CI, the release workflow and
  `tools/e2e.sh` do the same with `requirements-dev.txt`, which was a list of floors and is now `requirements-dev.in`
  resolved by `uv pip compile` to one lock that holds for every Python from 3.10. The suite thereby runs against the
  `mcp` the image ships. The release workflow no longer upgrades pip unpinned. Dependabot watches the lock files again
  and the base image by patch. `test_every_python_package_and_the_base_image_are_pinned_with_hashes_and_installed_checking_them`.

- Dependabot no longer watches `requirements-dev.txt`, whose floors CI does not honour, so its first five pull requests
  changed nothing but that file, and it moves the image's base by patch only: its first docker pull request was a
  jump to Python 3.14, which CI does not cover. Both are closed with a reason. Its pull request for the six pinned
  actions was merged: CI had run on it.

### Fixed

- `memory status` created an empty `memory.db` on a machine with no store, which it is documented not to touch: it now
  reports an empty store and leaves none behind.
  `test_status_on_a_machine_with_no_store_reports_an_empty_one_and_does_not_create_it`.

- A review of the documents against the code corrected what they said of it: a contradiction check also looks at the
  `all` project, and the lesson from the older source loses; in a repository's own docs a `[project] fact` line counts
  only for that repository; a commit cursor is the tip of every branch; a lock is broken after 10 minutes untouched,
  its holder touching it every 60 s; the SDK path logs `$0.000`; a compile is a commit only when something changed and
  the store is a git repository. The environment table lists `MEMORY_STATE_DIR`, `MEMORY_PYTHON`, `CALLS` and
  `RETRY_WAIT`, the layout lists what was missing, and `RELEASING.md` no longer says the first month is still to run.

## [0.2.5] - 2026-10-15

### Added

- `.github/dependabot.yml`: a weekly pull request for the commit-pinned actions, the dev tools and the image's base,
  so the pins do not age unseen.

### Changed

- The workflows are harder to abuse, from a supply-chain review. Every action is pinned to a commit rather than a
  tag. Only the release workflow's publish job holds `packages: write`; `verify`, which installs and runs third-party
  tools, no longer does. A release now requires the tagged commit to be on `main`, and `:latest` moves only for a tag
  with no `-` in it, so a pre-release such as `v0.3.0-rc1` no longer takes it. A `.dockerignore` keeps `.env` and the
  local store out of the build context, `.gitignore` covers `.env.*`, and Compose runs the container with
  `no-new-privileges` and every capability dropped.
  `test_workflows_pin_actions_by_commit_and_only_the_publish_job_writes_packages`.

- The project is licensed under the MIT License, from the next release on, in place of The Unlicense. Versions up to
  and including 0.2.4 were released under The Unlicense and stay so. `LICENSE`, `CITATION.cff`, `README.md` and
  `ATTRIBUTION.md` say so. The courtesy credit the Unlicense text asked for is dropped from `LICENSE`; the
  acknowledgment of the AI collaboration stays in `ATTRIBUTION.md`.

### Fixed

- Reviews of the compile path and of the hooks found these, each reproduced. `clean_lesson` ran only when a lesson was
  stored, so a row stored before it existed (the live store holds one over 500 characters) reached `compiled/` as
  written: lessons are now cleaned where the file is written, and every `@path`, which Claude Code imports anywhere in
  a line and not only at its start, is broken with a zero-width space. `LESSON_RE` took 14 s on a 40,000-space line
  while holding the lock (a lazy `.+?` before `\s*$`) and is linear. A journal file was created empty and then
  written, so an ingest in between could read it empty, mark it read and lose the lesson: it is written under a
  `.part` name and hard-linked whole. A failed `git add` or `git commit` in the store was dropped, and a store with no
  git identity staged for months without one commit: it is logged, git gets 60 s under the lock, and the commit
  adds only the store's own folders, so a store with no `.gitignore` no longer commits `memory.db`. `memory remember`
  on a busy store said to try again, which wrote a second file and a second vote: the lesson is saved and it says so.
  A Stop hook before `~/memory` existed left its temp file, holding the transcript path and the last message, in
  `/tmp`. A checkout path with a space or a quote broke both hooks: the command is an array now. An empty or quoted
  `ANTHROPIC_API_KEY` in `.env`, or one ending in a carriage return, sent the hooks to a container that was not
  there. `tools/e2e.sh` could write into the operator's own store if `MEMORY_ROOT` was exported. A new store is
  created with mode 700; an existing one is left alone (`chmod 700 ~/memory` to match).

## [0.2.4] - 2026-10-14

### Added

- Each `hook`, `ingest` and `learn` log line ends with the Reflector calls it made and the dollars `claude -p` reported
  for them, and `memory status` totals the hooks' for the last seven days. Nothing recorded what the Reflector cost
  before, so there was nothing to reduce it against.
- `memory status`: what the store holds and owes, the last nightly run (and its alert, if any), whether the lock is held,
  and how the Stop and SessionStart hooks have done over the last seven days, from the dated `hook.log`. Read-only,
  so it answers during a long `learn`.

### Changed

- A `[proj] fact` line in a repository's docs goes into the store with no Reflector, so a cloned repository's
  `[all] ...` line became a rule in the playbook every session imports. In a repository's docs a line is now a lesson
  only for that repository's own slug; any other is prose for the Reflector to weigh. `--notes` is unchanged.

### Fixed

- Editing a document that holds `[proj] fact` lines re-voted for every one of them; a line a document has already
  given a vote to is counted once. The commit cursor was one hash, so reading a repository on one branch, another,
  and the first again read the first's commits twice and double-voted them; it is now the tips read, one per branch.
  A one-hash cursor from before is read as one tip. A document edited after upgrading may vote once more for its
  lines, since nothing recorded which it had already counted.
  `test_switching_branches_and_back_reads_no_commit_twice`, `test_editing_a_document_does_not_vote_again_for_the_lines_it_already_gave`.

- A review of the adapters and the MCP server found these, each reproduced. A symlink in a cloned repository or a
  notes folder (`README.md -> ~/.ssh/...`, or a `docs` that leads out) made `learn --all`, which reads every clone,
  send what it pointed to to the Reflector: an adapter now reads only files that are its root's own, at most
  2 MB, notes included. A commit message in latin-1 made every `learn --repo` of that repository raise at
  git's strict decoding: it is decoded with replacement. The HTTP MCP server, run with `--host 0.0.0.0` as the
  image runs it, did not check the `Host` header, so a web page that rebound its own name to the published
  loopback port could write or archive lessons: only loopback names are accepted now, `--allowed-host` adds
  more. A folder or repository name that is not a slug (`Obsidian Vault`, `.dotfiles`) was stored as the project
  and never compiled: it is made a slug (`obsidian-vault`). `learn` with a `--notes`, `--repos`, `--exports`,
  `--transcripts-from` or `--export` that does not exist exited 0 having read nothing, or with a traceback: it
  names the path and stops. A transcript's cursor depended on how its path was spelled, so a relative and an
  absolute path both read it, each lesson getting two votes. A negative `-k` returned all but the last results,
  a very long query took minutes, `"cwd": 5` in a transcript raised, and a directory named `x.jsonl` raised.
  `test_a_symlink_cannot_make_an_adapter_read_outside_its_root`,
  `test_the_http_server_refuses_a_host_it_was_not_told_to_expect`.

## [0.2.3] - 2026-10-14

### Fixed

- A fresh review of the 0.2.2 fixes found four small gaps. A new lesson from an old source that lost one
  contradiction went on to retire another candidate in the same verdict, though it was no longer active to
  replace it: it stops at its first loss. A repository folder name longer than the new 64-character slug limit
  was never compiled: the slug is cut to 64. `remember` could say a 900-character lesson was saved as written
  when `upsert` stored 500 characters of it: it now reports the line as it will be stored. `install_nightly.sh
  --calls 00` passed as a budget of zero, which every night would alert on.
  `test_a_lesson_that_loses_a_contradiction_supersedes_nothing_else`.
- Gemini activity is cut into pieces like a transcript, and they shared one cursor too: a failure part-way
  through a long record re-sent the pieces already answered and double-voted them. Its cursor, a time, now reads
  `<time>|<k>` inside such a record. A lesson that was archived, met again from an old source and pruned again
  added a second line to the month's archive file each time; it adds one.
  `test_a_failure_inside_a_long_gemini_record_resumes_at_the_next_piece`.

## [0.2.2] - 2026-10-14

### Fixed

- A review of the nightly scripts found that every failure other than exit 2 was logged as an ordinary night
  with no alert: a missing or crashed interpreter (127, a traceback) or a store whose lock was held through
  every try could go unnoticed for as long as it lasted. Those now write `needs-attention` and notify, and a
  night that stopped part-way clears an old alert, since the Reflector answered. The installer writes a
  well-formed agent file for a checkout path with `&` or `<` in it, checks it with `plutil -lint` before
  installing, waits for the old job to go before bootstrapping and retries once, quotes the cron line's
  path for the shell and for `%`, rejects `--hour` or `--calls` without a value or beyond 999999 with the
  usage line, and `--uninstall` works off macOS.
- A review of the source-time change found three gaps. `stamp` kept the offset of the time it was given, and
  `upsert` compares those times as text, which orders them only if they share one offset: a lesson met again from a
  source stamped `+14:00` could take the wrong `last_seen` or `first_seen`. They are always UTC now. Folding a
  duplicate into a survivor set the survivor's `last_seen` to today, so a backfill that deduplicated made lessons
  look new again; it keeps the newest of the two, and the oldest `first_seen`. A contradiction always superseded the
  other lesson, on the assumption that the one read last is the newer, which a backfill breaks: it reads old
  transcripts after new ones, so an old "never use tabs" could retire a current "always use tabs". The newer source
  now wins. `test_the_newer_source_wins_a_contradiction_whichever_was_read_last`.
- A review of the Reflector's path from answer to store found five gaps. A lesson was stored as the model wrote
  it, so a newline in it (from a transcript that told the model what to write) became a heading or an `@` line
  of its own in `compiled/PLAYBOOK.md`, which every session imports, and a lesson could be any length: a lesson
  is now one printable line of at most 500 characters. A slug of any length was accepted, and one past the
  operating system's file-name limit made every later run fail in `compile_`: a slug is now at most 64
  characters. A lone surrogate, which a JSON escape in a transcript or an answer decodes to, made the call or the
  database write raise and stalled that source for good: text is scrubbed before it is sent or stored, and a
  transcript line with an invalid byte is skipped. An answer cut short returned its first inner object as if it
  were the answer, losing every lesson: it now keeps the complete lessons at its head, and a cut-short contradiction
  verdict counts as no verdict. A lesson an answer repeated got a vote for each repeat: it gets one.
  `test_a_lesson_is_one_printable_line_that_cannot_forge_lines_in_compiled`.
- A turn longer than a window is cut into pieces that used to share one cursor, the start of the turn. A
  Reflector failure part-way through it left the cursor there, so the next run sent the pieces already answered
  again and each of their lessons got a second vote. The cursor now moves piece by piece (`N+K`), a failure
  resumes at the next piece, and a Stop hook may stop inside a long turn, which made `hook_windows` unnecessary.
  A cursor that names more pieces than the turn now has, because the window size changed, reads the turn whole.
  `test_a_failure_inside_a_long_turn_resumes_at_the_next_piece`. Gemini activity, cut the same way, is unchanged.
- An independent review of the hook's two-lock flow found three gaps, each now closed. A hook that died, or
  whose second lock wait timed out, between storing its lessons and settling their contradiction checks
  lost those checks for good, since a later `learn` meets the lessons as already stored: a check is now owed
  from the moment it is planned. A merge folded in the votes the lesson had when planned, losing one a second
  hook added meanwhile; it now takes them as they are. A writer that died while breaking a stale lock left
  `.lock.break` behind, and every later writer failed within milliseconds, without sleeping; a `.lock.break`
  a minute old is now removed, and a waiting writer sleeps between tries.
  `test_a_check_planned_but_not_yet_settled_is_owed`, `test_a_merge_takes_the_votes_the_lesson_has_by_then`,
  `test_a_break_lock_a_dead_writer_left_does_not_stop_every_writer_for_good`.

### Added

- `examples/global-CLAUDE.md` tells Claude to call the `memory` server's `feedback` tool on a recalled lesson
  it acted on. The tool existed, but nothing asked for it, so no lesson had ever been marked helpful and
  the score's `helpful` term was always zero.

## [0.2.1] - 2026-10-13

### Added

- `tools/install_nightly.sh` and `tools/nightly_catchup.sh`: a nightly `learn --transcripts` that reads the
  tails a Stop hook missed, with a retry while a hook holds the lock and an alert file and notification when
  the Reflector answers nothing. macOS gets a launchd agent; elsewhere the installer prints a cron line.

### Changed

- CI runs less for the same assurance. A pull request now runs everything (lint, 3.10, 3.12 and 3.13,
  the image), so there is no manual dispatch and no second run when the tested commit reaches `main`;
  that was about 13 job-runs a change and is 5. Python 3.11 is dropped from the matrix and the release
  check, the coverage gate is measured on 3.12 only, the lint job installs only the linters and calls
  actionlint from pip rather than through a third-party action, and the documentation check runs
  once, inside pytest. The image build keeps buildx and its layer cache: without them it took 43 s
  against 32 s.

### Fixed

- `docs/architecture.md` says, in general terms, how large a store gets and why nothing is vacuumed.
- `README.md` explains how to read the dated `hook.log`; `docs/architecture.md` says what the 150-line
  cap hides and that search is full-text without an embedding provider.
- A lesson was last seen when it was read, not when it was written. A backfill reads weeks of
  transcripts in a day, so every old lesson looked new, no lesson had aged, and which of the
  hundreds of one-vote lessons reached a capped `compiled/` file came down to the order they were
  read in. A transcript's lessons now carry its modification time, a journal entry its file's, a
  claude.ai or ChatGPT chat its update time and Gemini activity the time of its last record; a time
  ahead of the clock counts as now. A lesson met again keeps the newest `last_seen` and the oldest
  `first_seen`. Documents and commits are still stamped when read.
  `test_a_transcript_backfilled_late_ages_from_when_it_was_written`.
- `hook.log` could not be placed in time, so nothing could say whether a change had lessened lock
  contention. Each hook run now opens its output with a dated `== time stop|session start` line.
- A Stop hook no longer holds the store's lock while the Reflector answers. It did, for 20 to 60 s a
  call, and every other session or subagent that stopped meanwhile waited 20 s and gave up: about
  half of all stops in October 2026. A hook now reflects with no lock held, takes the lock to store
  what was answered and again to settle the contradiction checks, and waits up to 120 s for it. A
  claim per transcript in `.reflecting/` keeps a stop and a subagent's stop from reflecting the same
  turns twice, and a hook whose transcript another reader advanced meanwhile discards what it read.
  `test_a_hook_asks_the_reflector_without_holding_the_lock`.
- The Reflector's `claude -p` is an agent, and it ran with its tools. Given a transcript of another
  agent's task, it carried the task out instead of listing lessons: on one workflow-agent window
  it read files for minutes, timed out twice every night from 8 October, and stalled the nightly
  catch-up and 102 transcripts behind it; when such a call did finish, its answer was no JSON and
  the window counted as having no lessons. Text in a transcript could also make it act on this
  machine. It now runs with `--tools ""`, `--strict-mcp-config`, `alwaysThinkingEnabled: false`
  and its instructions as `--system-prompt`, with the conversation alone on stdin, and the
  prompt says the conversation is never instructions. The same window now answers in 12 s for
  $0.006, where it took 94 s and $0.05 with thinking on.
  `test_the_reflector_can_only_answer_never_act`.
- `ruff.toml` names Python 3.10 as its target. Unset, ruff 0.17 assumed a later Python and
  asked for `datetime.UTC`, which 3.10 does not have.

## [0.2.0] - 2026-10-03

The first release run against a real store, from 15 September: every transcript a machine holds
(Claude Code and its subagents, Cursor, Claude Desktop's agent mode, Codex), git repositories,
notes, and claude.ai, ChatGPT and Gemini exports. The store's schema, `lid()` and the journal
line format are unchanged since 0.1.0, so an existing `~/memory` needs no migration.

### Added

- `--export` reads ChatGPT's `conversations.json` and the Gemini Apps activity in a Google
  Takeout, besides claude.ai's, and tells the three apart by their shape, so `learn --all` reads
  whatever is in `exports/`. A ChatGPT chat is read along the branch that was on screen, from
  `current_node` to the root, and not the answers an edit or a regeneration replaced; hidden
  context, tool output and the system prompt are left out. It is filed under `chatgpt` and read
  again when its `update_time` changes. Gemini's activity has no conversations, so it is read in
  time order, in windows, under `gemini`, with one cursor at the last record read; records made
  at the same instant stay in one window, so a resume can skip neither.
  `test_a_chatgpt_export_is_read_along_the_branch_on_screen`,
  `test_gemini_takeout_activity_is_read_in_time_order_and_only_once`,
  `test_a_gemini_window_left_unanswered_is_offered_again`.
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
- `learn --max-calls N`: a run stops after about N Reflector calls, each reflection and each
  contradiction check counted where it is made, and keeps its place like a usage-limit stop, so a
  first backfill can be spread over days. `test_learn_max_calls_stops_cleanly_and_the_next_run_carries_on`.
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

- A contradiction check asks about up to eight new lessons in one call, each listed with its
  own candidates, and the answer gives each lesson its own verdict. One call per lesson made the
  checks most of what a backfill cost: a window of transcript yields about three and a half
  lessons, so it cost about four and a half calls where it now costs about one and a half. A
  verdict applies only against lessons still active, so two new lessons that duplicate each
  other merge once, and a group left unanswered is owed as a whole.
  `test_a_windows_lessons_are_checked_in_one_call`,
  `test_each_lesson_in_a_group_gets_its_own_verdict`,
  `test_a_group_left_unanswered_is_owed_and_the_groups_before_it_are_settled`.
- README gives Claude Desktop's config path on Windows as well as macOS.
- `memory --help` describes every subcommand and every flag; only `learn` had descriptions, and
  most of the other commands' flags had none.
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

- The image's default command, `mcp --transport http`, exited at once and left the container
  restarting: a comment after the `CMD` array made Docker run it through `/bin/sh`, so the
  entrypoint was handed `/bin/sh` as its subcommand. CI's container job overrides the command, so
  only `tools/e2e.sh` saw it. `test_mcp_tools_answer_on_both_mcp_versions_and_transports` now
  reads `CMD` as JSON.
- Every new lesson with a neighbour cost two contradiction checks: each source's lessons were
  reconciled as it was committed, and `learn` then reconciled the whole run's lessons again at
  the end. Once a `--max-calls` budget was spent, that second pass recorded every lesson of the
  run as owed, so the next batch paid for them a third time. A run now handles each lesson once.
  `test_a_new_lesson_is_checked_for_contradictions_once_per_run`.
- A contradiction check that got no answer, or that `--max-calls` left for later, was skipped for
  good: the new lesson stayed active and was never compared with anything. A usage limit that
  hit mid-run left several hundred such lessons. The check is now owed, as a `recheck:<id>` row
  in `sources`, and the next `learn` pays it before reading anything new, stopping at the first
  one still unanswered; a lesson retired meanwhile is owed nothing. No schema change.
  `test_a_contradiction_check_that_got_no_answer_is_owed_and_paid_by_the_next_learn`,
  `test_a_check_the_budget_left_for_later_is_owed_too`,
  `test_paying_owed_checks_stops_at_the_first_unanswered_and_forgets_retired_lessons`.
- `memory mcp --transport http` listened on every interface, with no authentication, when run
  outside the container. It now listens on `127.0.0.1` unless `--host` says otherwise; the image
  passes `--host 0.0.0.0`, which Compose publishes on the host's loopback only.
- The transcript backfill read each Claude Code session but not what it ran: `<session>/subagents/`
  and a workflow's agents beneath it were never read. They are now, under the session's project.
  `test_a_sessions_subagents_and_workflow_agents_are_read_under_its_project`.
- A run whose every Reflector call went unanswered could exit 1, "part-way, run me again",
  instead of 2, so an expired login went unreported. Lessons the hooks journaled during the
  outage are ingested at the start of the next run, and each one with a neighbour costs a
  contradiction check; the exit code counted those calls as made rather than as answered. It
  now counts answers. `test_a_run_whose_every_call_went_unanswered_exits_2_even_after_a_contradiction_check`.
- The MCP `remember` tool, when a `learn` held the lock, said the lesson would reach `compiled/`
  when that `learn` ended; `learn` reads the journal only as it starts. It now says the lesson
  arrives at the next session start, hook, ingest or learn.
- Stale comments, docstrings and workflow notes: `--transcripts` and `--all` in the module
  docstring, what `archive/` and the journal hold, the exit codes, the lint ruleset, what
  `check_docs.py` checks, what the container does not mount, and the prose counts of lines.
- A JSON file in `exports/` that is no conversation export stopped `learn --all` on every run:
  the manifest that comes with a claude.ai export raised `AttributeError`, and a claude.ai
  project was read as a conversation and left a cursor behind. Such a file, or a truncated one,
  is now logged and skipped. `test_a_json_file_that_is_no_export_is_skipped_not_misread`.
- An exported claude.ai chat was filed under a project named after its title, so an export of
  several hundred chats would have made several hundred projects, each with a compiled file of its
  own. A chat now defaults to `claude-ai`, the tool that held it, as a Codex session outside a
  repository defaults to `codex`. The title travels with the text, and the Reflector is given
  every known project, so a chat about one of them is still filed under it.
  `test_an_exported_chat_is_filed_under_claude_ai_not_under_its_title`.
- A single `claude -p` call that timed out ended the whole run. A backfill of 323 transcripts,
  two days in, stopped on one slow window with twelve left to read. A timed-out call is now tried
  once more before the run gives up; a refusal, a usage limit or an authentication error is not
  retried, since trying again would only spend the same answer twice.
  `test_a_timed_out_call_is_tried_once_more`, `test_a_call_that_keeps_timing_out_gives_up_and_says_so`.

- A document longer than `DOC_MAX_CHARS` was cut to its first 20,000 characters, and its cursor
  was then set as though all of it had been read, so the rest was never offered to the Reflector
  again. A long document is now read in pieces, broken at a line end, and marked read only once
  its last piece has been. `test_a_long_document_is_read_in_full_and_marked_read_only_when_it_is`,
  `test_a_document_whose_last_piece_went_unanswered_is_offered_again`.
- An exported conversation longer than 30,000 characters kept only its tail, through the cut in
  `reflect`, and was then marked fully read. It is windowed like a transcript.
  `test_a_long_exported_conversation_keeps_more_than_its_tail`.

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
