# Concurrency audit

Every writer the system has, every race that was considered, and what closes it. The test that
proves each closure is named.

| Race | Closed by | Test |
|---|---|---|
| Two hooks fire in the same tick | one journal file per event, exclusive create, ns stamp + PID | `test_journal_write_never_appends`, `test_parallel_hook_processes_do_not_lose_updates` |
| Two compiles at once | `mkdir .lock` is atomic; the loser waits, then proceeds | `test_lock_serialises_writers` |
| A compile crashes holding the lock | a lock nobody has touched for 600 s is broken; a live holder touches it every 60 s | `test_stale_lock_is_broken` |
| A `learn` runs past 600 s | its lock's heartbeat keeps it fresh, so no writer takes it for a crashed holder's | `test_a_live_holder_keeps_its_lock_fresh` |
| A `learn` holds the lock for hours | writers wait 20 s, then give up with `LockBusy`; the SessionStart hook's `ingest --wait 2` gives up after 2 s and the session reads `compiled/` as it was; a Stop hook's `LESSONS:` journal file is already written; the MCP tools answer "busy" | `test_lock_gives_up_with_lock_busy_and_tolerates_a_vanished_lock`, `test_ingest_wait_bounds_how_long_session_start_can_block`, `test_mcp_tools_answer_busy_while_a_learn_holds_the_lock` |
| Reader sees a half-written `PLAYBOOK.md` | `.tmp` then `os.replace` | `test_compile_is_atomic_and_removes_empty_projects` |
| Claude Code is still writing a transcript's last line | a line with no newline is left for the next read | `test_a_half_written_last_line_is_left_for_the_next_read` |
| Same lesson from N parallel subagents | identical ids collapse; count is the vote | `test_parallel_hook_processes_do_not_lose_updates` |
| Reflector's `claude -p` re-triggers the Stop hook | `MEMORY_REFLECT=1` on the child; hooks exit on it | `test_cmd_hook_is_inert_inside_reflection`, `test_llm_cli_success_and_recursion_guard` |
| Same transcript reflected twice | byte-offset cursor in `sources`, moved window by window | `test_ingest_transcript_stores_cursor`, `test_backfill_stops_at_a_failed_window_and_the_next_run_resumes_there` |
| A session outruns its stops while the lock is busy | the next stop reads from the cursor, oldest first, at most two windows, and moves the cursor only past them | `test_backfill_reads_every_window_and_a_hook_two_oldest_first` |
| A Reflector call fails part-way through a source | no cursor moves past unanswered text; the run stops, keeps and compiles what it did | `test_learn_stops_on_a_failed_reflector_keeps_its_progress_and_resumes`, `test_commit_cursor_after_a_failure_is_the_last_reflected_commit` |
| Same export ingested twice | `updated_at` cursor per conversation | `test_export_ingest_is_idempotent_per_updated_at` |
| Drive conflict copies | `compiled/` written only locally; `journal/claude-ai/` written only by claude.ai | by construction; no file has two writers |
| Host and container both compile | the lock directory is on the bind mount both see | by construction |
| SQLite corruption on macOS bind mount | database on a named volume | Compose file |
| Hook blocks Claude Code | the Stop hooks fork and exit 0 unconditionally; the SessionStart hook waits at most 2 s for the lock | `test_hook_scripts_pass_through_to_runner`, `test_ingest_wait_bounds_how_long_session_start_can_block` |
| A hook fires mid-`cat` of another compile | its file is picked up by the next compile, which runs at the next `SessionStart` before Claude reads anything | accepted bounded lag |
| Two main sessions in one repository share native auto memory | Claude Code's own race; journals survive independently | accepted; out of scope |
