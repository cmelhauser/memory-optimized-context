# Concurrency audit

Every writer the system has, every race that was considered, and what closes it. The test that
proves each closure is named.

| Race | Closed by | Test |
|---|---|---|
| Two hooks fire in the same tick | one journal file per event, exclusive create, ns stamp + PID | `test_journal_write_never_appends`, `test_parallel_hook_processes_do_not_lose_updates` |
| Two compiles at once | `mkdir .lock` is atomic; the loser waits, then proceeds | `test_lock_serialises_writers` |
| A compile crashes holding the lock | locks older than 600 s are broken | `test_stale_lock_is_broken` |
| Reader sees a half-written `PLAYBOOK.md` | `.tmp` then `os.replace` | `test_compile_is_atomic_and_removes_empty_projects` |
| Same lesson from N parallel subagents | identical ids collapse; count is the vote | `test_parallel_hook_processes_do_not_lose_updates` |
| Reflector's `claude -p` re-triggers the Stop hook | `MEMORY_REFLECT=1` on the child; hooks exit on it | `test_cmd_hook_is_inert_inside_reflection`, `test_llm_cli_success_and_recursion_guard` |
| Same transcript reflected twice | byte-offset cursor in `sources` | `test_ingest_transcript_stores_cursor` |
| Same export ingested twice | `updated_at` cursor per conversation | `test_export_ingest_is_idempotent_per_updated_at` |
| Drive conflict copies | `compiled/` written only locally; `journal/claude-ai/` written only by claude.ai | by construction; no file has two writers |
| Host and container both compile | the lock directory is on the bind mount both see | by construction |
| SQLite corruption on macOS bind mount | database on a named volume | Compose file |
| Hook blocks Claude Code | hook forks and exits 0 unconditionally | `test_hook_scripts_pass_through_to_runner` |
| A hook fires mid-`cat` of another compile | its file is picked up by the next compile, which runs at the next `SessionStart` before Claude reads anything | accepted bounded lag |
| Two main sessions in one repository share native auto memory | Claude Code's own race; journals survive independently | accepted; out of scope |
