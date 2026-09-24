# Agent instructions

Entry point for any agent working on this repository: Cursor, Codex, Claude, or a human. Read
this file first. `CLAUDE.md` is the long form of the same rules and is authoritative where the
two overlap.

## What this project is

A single-file personal memory system for Claude. `bin/memory` (about 740 lines, standard
library only) owns a SQLite store, an append-only journal, a locked compiler, a Reflector that
calls Claude to extract lessons from transcripts, a contradiction check, a pruner, hybrid
search, and an MCP server. Two shell hooks, sharing `hooks/runner.sh`, connect it to Claude
Code. It runs natively by default, reflecting through `claude -p`; a Dockerfile and Compose file
run it in a container when an API key is configured. One hundred and eight tests cover it
at 100 per cent of lines and branches, including a six-process concurrency test, and
`tools/e2e.sh` runs both installs end to end against a fake Reflector.

The Human Author is the repository owner; the AI Collaborator is theonlymuffinbot, using
Anthropic Claude. See `ATTRIBUTION.md` and `LICENSE`.

## Ground rules

1. **One writer per file.** `compiled/` and `memory.db` are written only by `bin/memory` under
   `Lock()`. Journal files are written once, by exclusive create, and never edited. Do not add a
   code path that violates either.
2. **ADD-only.** Lessons are never deleted. Supersession, merging and archiving are state
   changes. If you need to remove something, it is a state, not a `DELETE`.
3. **Do not weaken a test to make it pass.** `test_parallel_hook_processes_do_not_lose_updates`
   and `test_journal_write_never_appends` exist because the bugs they catch were real.
4. **No new runtime dependencies.** The standard library is the runtime. `anthropic` and `mcp`
   are optional imports and must stay behind `try:`.
5. **Do not commit a store.** No `memory.db`, no journal, no transcript, no export. The
   `.gitignore` enforces the obvious cases; you enforce the rest.
6. **Keep the file single.** Do not split `bin/memory` into a package. Its whole value is that
   it installs by copying one file.
7. **Keep the prose true.** `tools/check_docs.py` runs in CI. If you add a test, the counts in
   `README.md`, `AGENTS.md`, `CHANGELOG.md` and `RELEASING.md` must move with it.
8. **`main` takes no direct commits.** Branch, open a pull request, let CI run. See
   `RELEASING.md`.
9. **Keep coverage whole.** `.coveragerc` holds `bin/memory`, `tools/check_docs.py` and
   `tools/eval_recall.py` to 100 per cent of lines and branches with nothing excluded. New code
   arrives with the test that runs it; never add an exclusion to get past the gate.
10. **Name nothing private, and no one.** The repository is public. Tests, fixtures, prose and
    pull requests use neutral names, never the operator's own repositories, folders or
    conversations, and carry no personal data: no names, email addresses, home paths or details
    of the operator's machine. `tools/check_docs.py` rejects email addresses and home paths.
    Session handoffs go in an untracked `HANDOFF.md`, which `.gitignore` keeps out.

## Where things are

| Path | What |
|---|---|
| `bin/memory` | the tool |
| `hooks/` | Claude Code hook scripts, the runner they share, and the `settings.json` snippet |
| `tests/test_memory.py` | the suite |
| `tools/run_ci_locally.sh` | what CI runs, runnable locally |
| `tools/e2e.sh`, `tools/e2e/` | both installs end to end against a fake API and a fake `claude`; local only |
| `tools/check_docs.py` | prose counts, version, links and paths re-derived from the tree |
| `tools/eval_recall.py`, `eval/` | recall@k against a frozen question set |
| `tools/init_store.sh`, `tools/bootstrap.sh` | create the store; publish the repository |
| `examples/` | snippets for claude.ai, `CLAUDE.md`, Claude Desktop (native and Docker) |
| `docs/` | architecture, concurrency audit, research notes, decision records, diagrams |
| `Dockerfile`, `docker-compose.yml` | the container |
| `README.md` | install and operation |

## Verifying a change

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
tools/run_ci_locally.sh
tools/e2e.sh            # after a change to the hooks, the Dockerfile, the Compose file or the Reflector
```
