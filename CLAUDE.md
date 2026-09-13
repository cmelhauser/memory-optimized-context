# Project instructions

Read `AGENTS.md` first; this file is the long form. Work directly in this repository. Preserve
unrelated user work. Never commit a home directory path: the Compose file uses `${HOME}` and the
hooks use `$HOME` for that reason.

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

## Things that look like bugs and are not

- `search --all` does not return `merged` lessons. A merged lesson is a duplicate whose votes
  were folded into the survivor; showing both would double-count.
- `compile_` deletes `compiled/projects/<slug>.md` when the slug has no active lessons. That is
  the pruner working, not data loss; the lessons are in `archive/` and the database.
- The hooks discard the exit status of the background job. A hook that fails must never fail
  Claude Code's turn; failures go to `~/memory/hook.log`.

## Synchronisation rule

A change to `lid()`, the schema in `SCHEMA`, or `LESSON_RE` changes what an existing store
means. Such a change requires, in the same pull request: a migration in `bin/memory`, a test
that runs it against a store built by the previous version, a `## [x.0.0]` entry in
`CHANGELOG.md`, and a `store/` branch name.

## Release identity

The tag, `CITATION.cff` `version:`, and the `CHANGELOG.md` section must agree. The release
workflow checks all three and refuses lightweight tags. See `RELEASING.md`.
