# Branches, tags and releases

This is a tool with one user and a public repository. What a version number has to describe is
whether an existing `~/memory` store keeps working after an upgrade. The scheme below is built
around that.

---

## Branches

`main` is the only long-lived branch and takes no direct commits. Everything arrives through a
pull request from a short-lived topic branch, named for what it is for:

| Prefix | For |
|---|---|
| `store/` | the SQLite schema, the journal line format, or the lesson id |
| `fix/` | a defect in the tool, a hook, or a test |
| `docs/` | documentation |
| `ci/` | the workflows, tooling, lint, tests |
| `adapter/` | a new or changed input source (transcripts, exports, MCP) |

A `store/` branch is the serious one. Changing the schema or the id function changes what an
existing store means. Do not open one without a migration path written down first.

Delete the branch on merge. `git remote prune origin` afterwards.

---

## Versions

Semantic versioning, with the three levels mapped to what can actually change here.

**MAJOR** — the store schema, the journal line format, or `lid()` changes such that an existing
`~/memory` needs migration. A user who upgrades needs to know.

**MINOR** — a new capability or adapter. Existing stores keep working unchanged.

**PATCH** — corrections, tooling, lint, documentation. Nothing a user would notice except that a
bug is gone.

### Why this is pre-1.0

It has not yet run against a real store for a month. Until it has, the scoring constants, the
150-line cap and the contradiction prompt are guesses. 1.0.0 means a month of real use has not
required a `store/` branch.

---

## What a release requires

A tag asserts that the repository was in a releasable state at that commit. All of these, in
this order:

1. `tools/run_ci_locally.sh --image` clean.
2. CI green on `main` at that commit, including the `container` job.
3. `CITATION.cff` `version:` equals the tag without the `v`.
4. `CHANGELOG.md` has a `## [x.y.z]` section for it, and `[Unreleased]` is empty.

Then tag. **Annotated, never lightweight**, because the message is where the state is recorded
and the release workflow rejects lightweight tags:

```bash
git tag -a v0.1.0 -m "v0.1.0: first cut. forty-six tests, coverage 89%, image python:3.12.6-slim-bookworm."
git push origin v0.1.0
```

Pushing a tag runs `.github/workflows/release.yml`, which re-runs lint and the full test matrix,
checks the tag against `CITATION.cff` and `CHANGELOG.md`, and then builds and pushes the
multi-architecture image to `ghcr.io/cmelhauser/memory-optimized-context`. It cannot make a bad
tag good, but it records publicly whether the claim held.

---

## GitHub Releases

A tag is a mark in the history. A GitHub Release is a publication. **Do not publish one without
the Human Author asking for it.** Tagging is the routine act; publishing is not.

---

## For agents

- Never commit to `main`. Branch, open a pull request, let CI run.
- `container` does not run on pull requests, so **a green pull request is not a green
  release**; run `tools/run_ci_locally.sh --image` before merging anything that touches the
  Dockerfile or the Compose file.
- Never create a tag to mark work finished.
- If you change `lid()`, the schema, or the journal regex, that is a MAJOR release and needs a
  migration in `bin/memory` before anything is tagged.
