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
- A lesson's `first_seen` and `last_seen` are when its source was written (`seen_at`): a transcript's or
  journal file's modification time, an export's update time, always written in UTC. A source dated ahead of the
  clock counts as now. A merge keeps the survivor's newest `last_seen`, and of two lessons that contradict, the
  one from the newer source wins, whichever was read last.
- A Stop hook asks the Reflector with no lock held (`reflect_ahead`, `ask_checks`); it takes the
  lock only to store the answers, and a `.reflecting/` claim keeps two hooks off one transcript.
  A check is owed (`recheck:` row) from `plan_checks` until `settle_checks`, so a hook that dies or
  times out between its two locks loses none.
- `compiled/*.md` are written to a `.tmp` sibling and `os.replace`d.
- `cmd_hook` returns without side effects when `MEMORY_REFLECT` is set.
- Six concurrent `hook` processes journaling the same lesson produce a vote count of exactly
  six and leave no `.lock` behind.
- A superseded or archived lesson is absent from `compiled/` and from default search, and
  present in `search --all`.
- No cursor moves past text the Reflector did not answer. A resumed `learn` sends each
  transcript turn, commit and doc to the Reflector once, and counts a doc's tagged lines once, however the doc is
  edited or the repository's branches are switched (the commit cursor is the tips read, one per branch).
  A run asks each new lesson's contradiction check at most once.
- A Claude Code transcript's project is the `cwd` recorded in it, through `project_of()`, the
  same slug for the Stop hook and the backfill; a Claude Code worktree counts as its repository.
  A Cursor, agent-mode or Codex session is filed under the repository it ran in, through
  `repo_of()`, and otherwise under its tool.
- The Reflector's `claude -p` gets `--tools ""`, `--strict-mcp-config`, no extended thinking, and its
  instructions through `--system-prompt`; only the conversation goes to stdin.
- A lesson is stored as one printable line of at most 500 characters (`clean_lesson`, applied in `upsert`),
  under a slug of at most 64 characters, with nothing that cannot be encoded: it is model-written text that
  every session imports from `compiled/`, so a newline in it must not forge a heading or an `@` line.
- An adapter reads only files that are its root's own: not a symlink, not under one that leads out, at most
  2 MB (`inside()`), so a cloned repository cannot send `~/.ssh` to the Reflector. The HTTP MCP server accepts
  only a loopback `Host` and `Origin` (plus `--allowed-host`), whatever `--host` it listens on.
- A `[proj] fact` line in a repository's own docs is a lesson only for that repository's slug; one for `all` or
  another project is prose for the Reflector. In `--notes` it may name any project: they are the operator's own.
- A writer that cannot get the lock raises `LockBusy`; the MCP tools answer "busy" and the
  server keeps running.
- A lock holder touches `.lock` every 60 s, and only a lock untouched for 600 s is broken as a
  crashed holder's, so a `learn` of any length keeps its lock. Breaking one happens under
  `.lock.break`, so two writers cannot both break it (a `.lock.break` a minute old was left by a
  writer that died, and is removed); a holder touches and removes only a lock whose `owner` token
  is still its own.
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
  odd answer cannot stall a backfill. An answer cut short keeps the complete lessons at its head.
- An exported chat is filed under its tool (`claude-ai`, `chatgpt`, `gemini`), not under a
  project named after its title, unless the Reflector recognises one of the known projects in it.
- A JSON file in `exports/` that is none of the three exports, such as the manifest that comes
  with a claude.ai export, is logged and skipped by `learn --all`.
- A `recheck:<id>` row in `sources` is a contradiction check owed to an active lesson: it got no
  answer, or the budget ran out. The next `learn` pays it first; the hooks and `ingest` never do,
  because the SessionStart hook runs in the foreground.
- `hook.log` has a dated `== time stop|session start` line before each hook run's output; lines under it
  belong to that run, though concurrent runs can interleave. It has no other timestamps.
- A Stop hook reads at most two windows of new transcript. A session that outran its stops while
  the lock was busy is caught up by its next stops or by `learn --transcripts`; its cursor never
  moves past what was read.
- A transcript's cursor can read `N+K`: the turn that starts at byte N was longer than a window, and its
  first K pieces are reflected. Nothing else reads it as a plain offset; use `split_cursor()`. Gemini's
  cursor, a time, reads `<time>|<k>` for the same reason (a time has a `+` of its own).

## Synchronisation rule

A change to `lid()`, the schema in `SCHEMA`, or `LESSON_RE` changes what an existing store
means. Such a change requires, in the same pull request: a migration in `bin/memory`, a test
that runs it against a store built by the previous version, a `## [x.0.0]` entry in
`CHANGELOG.md`, and a `store/` branch name.

## Release identity

The tag, `CITATION.cff` `version:`, and the `CHANGELOG.md` section must agree. The release
workflow checks all three and refuses lightweight tags. See `RELEASING.md`.
