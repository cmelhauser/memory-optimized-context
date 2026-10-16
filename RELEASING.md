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

### What 1.0.0 means

It ran against a real store from 15 September 2026, and in that month nothing required a `store/` branch: the store
schema, `lid()` and the journal line format are those of 0.1.0. 1.0.0 is the owner's declaration that they are stable.
From it, any change to them is a MAJOR release with a migration (see the synchronisation rule in `CLAUDE.md`). It does
not say the tuning is final: the scoring constants, the 150-line cap and the contradiction prompt are what the first
month chose, and changing them is a MINOR or PATCH release, since no existing store needs migrating.

---

## What a release requires

A tag asserts that the repository was in a releasable state at that commit. All of these, in
this order:

1. The pins are fresh. Dependabot does not watch the hashed lock files (see `.github/dependabot.yml`), so
   recompile both with `--upgrade`, with the command in each `.in` file's header, and merge the result in its own
   pull request when anything moved.
2. `tools/run_ci_locally.sh --image` and `tools/e2e.sh` clean.
3. CI green for that commit, including the `container` job: a fast-forward merge puts the
   pull request's tested commit on `main`, so the pull request's run is the run.
4. `CITATION.cff` `version:` equals the tag without the `v`.
5. `CHANGELOG.md` has a `## [x.y.z]` section for it, and `[Unreleased]` is empty.

The tagged commit must be on `main`; the release workflow refuses a tag that is not. Then tag. **Annotated, never lightweight**, because the message is where the state is recorded
and the release workflow rejects lightweight tags:

```bash
git tag -a v0.1.0 -m "v0.1.0: first cut. forty-six tests, coverage 89%, image python:3.12.6-slim-bookworm."
git push origin v0.1.0
```

Pushing a tag runs `.github/workflows/release.yml`, which re-runs lint and the full test matrix,
checks the tag against `CITATION.cff` and `CHANGELOG.md`, and then builds and pushes the
multi-architecture image to `ghcr.io/cmelhauser/memory-optimized-context`, with an SBOM and build provenance
attached to it as BuildKit attestations, and signs the provenance and each platform's SBOM with Sigstore (`gh attestation
verify`). It cannot make a bad
tag good, but it records publicly whether the claim held.

---

## GitHub Releases

A tag is a mark in the history. A GitHub Release is a publication. **Do not publish one without
the Human Author asking for it.** Tagging is the routine act; publishing is not.

---

## For agents

- Never commit to `main`. Branch, open a pull request, let CI run.
- A pull request's CI run is the whole verdict (lint, Python 3.10, 3.12 and 3.13, the image),
  but it does not start the image's default command or exercise the hooks end to end: run
  `tools/e2e.sh` before merging anything that touches the hooks, the Dockerfile, the Compose
  file or the Reflector, and before every release.
- Never create a tag to mark work finished.
- If you change `lid()`, the schema, or the journal regex, that is a MAJOR release and needs a
  migration in `bin/memory` before anything is tagged.
