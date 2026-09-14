# Project instructions

Read `AGENTS.md` first; this file is the long form. Work directly in this repository. Preserve
unrelated user work. Never commit a home directory path: the Compose file uses `${HOME}` and the
hooks use `$HOME` for that reason. Never commit the name of anything private to the operator
either, or any personal data (a name, an email address, details of the operator's machine); the
repository is public. Session handoffs go in `HANDOFF.md`, which is git-ignored.

## Authority

1. `bin/memory` for behaviour;
2. `tests/test_memory.py` for what that behaviour is required to be;
3. `README.md` for how it is installed and operated;
4. everything else for context.

If the README and the code disagree, the code is wrong or the README is stale; find out which
before editing either.

## Invariants the tests enforce

- A journal file is created with `open(path, "x")` and is never opened for writing again.
- Every write to `compiled/` or the database happens inside `with Lock():`.
- `compiled/*.md` are written to a `.tmp` sibling and `os.replace`d.
- `cmd_hook` returns without side effects when `MEMORY_REFLECT` is set.
- Six concurrent `hook` processes journaling the same lesson produce a vote count of exactly
  six and leave no `.lock` behind.
- A superseded or archived lesson is absent from `compiled/` and from default search, and
  present in `search --all`.
- No cursor moves past text the Reflector did not answer. A resumed `learn` sends each
  transcript turn, commit and doc to the Reflector once, and counts a doc's tagged lines once.
- A transcript's project is the `cwd` recorded in it, through `project_of()`, the same slug for
  the Stop hook and the backfill; a Claude Code worktree counts as its repository.
- A writer that cannot get the lock raises `LockBusy`; the MCP tools answer "busy" and the
  server keeps running.
- A lock holder touches `.lock` every 60 s, and only a lock untouched for 600 s is broken as a
  crashed holder's, so a `learn` of any length keeps its lock.
- Coverage is 100 per cent of lines and branches over `bin/memory`, `tools/check_docs.py` and
  `tools/eval_recall.py`, with nothing excluded in `.coveragerc`.

## Things that look like bugs and are not

- `search --all` does not return `merged` lessons. A merged lesson is a duplicate whose votes
  were folded into the survivor; showing both would double-count.
- `compile_` deletes `compiled/projects/<slug>.md` when the slug has no active lessons. That is
  the pruner working, not data loss; the lessons are in `archive/` and the database.
- The hooks discard the exit status of the background job. A hook that fails must never fail
  Claude Code's turn; failures go to `~/memory/hook.log`.
- `learn` exits non-zero after a Reflector failure and leaves some cursors short of the end.
  That is the resume point; running it again carries on from there.
- A doc's cursor can read `tagged:<hash>`: its `[project] fact` lines are in, and its prose is
  still owed to the Reflector.
- Compose refuses to start without `.env`. Without a key the install is native
  (`hooks/runner.sh`), and a container without one would have no Reflector.
- The hooks choose Docker from a key in this checkout's `.env`, not from an exported
  `ANTHROPIC_API_KEY`; an exported key serves the native install's SDK path instead.
- During a long `learn` the SessionStart hook gives up on the lock after 2 s, so `compiled/` can
  be one compile behind when a session starts.
- A Reflector answer with no JSON array in it counts as "no lessons", not as a failure, so one
  odd answer cannot stall a backfill.

## Synchronisation rule

A change to `lid()`, the schema in `SCHEMA`, or `LESSON_RE` changes what an existing store
means. Such a change requires, in the same pull request: a migration in `bin/memory`, a test
that runs it against a store built by the previous version, a `## [x.0.0]` entry in
`CHANGELOG.md`, and a `store/` branch name.

## Release identity

The tag, `CITATION.cff` `version:`, and the `CHANGELOG.md` section must agree. The release
workflow checks all three and refuses lightweight tags. See `RELEASING.md`.
