# Contributing

This is a personal tool with a public repository. Contributions are welcome; the bar is that they
keep the guarantees in `README.md` under "Guarantees" intact.

## Before you open a pull request

1. Read `AGENTS.md`. It is short and it is the same set of rules for people and for agents.
2. Run `tools/run_ci_locally.sh`. It runs what CI runs: ruff, actionlint, shellcheck, the Compose
   check, `tools/check_docs.py` and the tests. If you touched the hooks, the Dockerfile, the
   Compose file or the Reflector, run `tools/e2e.sh` as well.
3. Add a test. The coverage gate is 100 per cent, lines and branches, over `bin/memory`,
   `tools/check_docs.py` and `tools/eval_recall.py`, with nothing excluded, so new code arrives
   with the test that runs it. The suite already covers the concurrency guarantees; a change
   that weakens one of those without a failing test is the kind of change this repository exists
   to prevent.
4. Add a line under `[Unreleased]` in `CHANGELOG.md`.

## What will not be merged

- Anything that gives a second writer to `compiled/` or `memory.db`.
- Anything that appends to an existing journal file.
- A dependency the tool needs at runtime beyond the Python standard library. `anthropic` and
  `mcp` are optional and stay optional.
- A weakened check to make a test pass, including an exclusion added to `.coveragerc`.
- A committed memory store, transcript, or export. Those are the operator's own conversations.
- The name of anything private to the operator: a repository, a folder, a conversation. Tests
  and fixtures use neutral names.

## Branch naming and versions

See `RELEASING.md`.

## Style

`ruff.toml` and `shellcheck` are the whole style guide, and actionlint checks the workflows. The
single-file layout of `bin/memory` is deliberate; do not split it into a package.
