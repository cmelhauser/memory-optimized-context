# Contributing

This is a personal tool with a public repository. Contributions are welcome; the bar is that they
keep the guarantees in `README.md` under "Guarantees" intact.

## Before you open a pull request

1. Read `AGENTS.md`. It is short and it is the same set of rules for people and for agents.
2. Run `tools/run_ci_locally.sh`. It runs exactly what CI runs.
3. Add a test. The coverage gate is 80 per cent on `bin/memory` and the suite already covers the
   concurrency guarantees; a change that weakens one of those without a failing test is the kind
   of change this repository exists to prevent.
4. Add a line under `[Unreleased]` in `CHANGELOG.md`.

## What will not be merged

- Anything that gives a second writer to `compiled/` or `memory.db`.
- Anything that appends to an existing journal file.
- A dependency the tool needs at runtime beyond the Python standard library. `anthropic` and
  `mcp` are optional and stay optional.
- A weakened check to make a test pass.
- A committed memory store, transcript, or export. Those are the operator's own conversations.

## Branch naming and versions

See `RELEASING.md`.

## Style

`ruff.toml` and `shellcheck` are the whole style guide. The single-file layout of `bin/memory` is
deliberate; do not split it into a package.
