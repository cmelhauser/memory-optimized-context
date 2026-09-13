# Architecture

The system as built. For how it got here, read `docs/research.md` and the decision records in
`docs/decisions/`. For the drawings, `docs/diagrams/04-as-built.svg` is this document in one
picture; `00` to `03` are the earlier drafts, kept because each one was wrong in an instructive
way.

## The rule everything follows

**No file has two writers.** Every other design choice is downstream of that.

| File or directory | Writer | Everyone else |
|---|---|---|
| `journal/DATE/*.md` | the process that created it, once, by exclusive create | read |
| `journal/claude-ai/*.md` | claude.ai, through Google Drive, one new file per note | read |
| `memory.db` | `bin/memory` inside `Lock()` | read |
| `compiled/*.md` | `bin/memory` inside `Lock()`, by atomic rename | read |
| `archive/*.md` | `bin/memory` inside `Lock()` | read |
| `~/.claude/projects/*/memory/` | Claude Code itself | untouched by this system |

## Data flow

0. **Learn.** `memory learn --all` walks Claude Code transcripts, git repositories (commit
   messages and docs), note folders and claude.ai exports. Each source has a cursor in the
   `sources` table, so the walk is incremental: a commit hash, a content hash, a byte offset,
   an `updated_at`. `[project] fact` lines anywhere are ingested without an LLM call; prose and
   whole transcripts are windowed into ~30k-character batches for the Reflector, headers
   counted, so nothing is cut. A transcript's project is the `cwd` recorded in it, the same slug
   the Stop hook derives; a Claude Code worktree counts as its repository.
1. **Capture.** A Claude Code `Stop` or `SubagentStop` hook writes the hook JSON to a temp file,
   forks `memory hook`, and returns. `memory hook` journals any `LESSONS:` block from the last
   assistant message, then hands the transcript tail to the Reflector.
2. **Reflect.** Claude Haiku reads the transcript since the last byte offset and returns a JSON
   array of `{project, text}` lessons. The offset is stored so the next stop reflects only what
   is new. The same Reflector runs over claude.ai `conversations.json` exports, keyed by
   conversation `updated_at`. When no answer comes (an API or CLI error, a usage limit), no
   cursor moves past the text that went unanswered: `learn` stops, keeps and compiles what it
   did, and the next run resumes there.
3. **Ingest.** Each lesson is upserted by `sha1(project | normalised text)[:10]`. An exact
   duplicate is a vote. Nothing is ever overwritten.
4. **Reconcile.** A new lesson is compared with its six nearest neighbours in the same project.
   `same` folds the new lesson's votes into the older one and retires the new one as `merged`.
   `contradicts` marks the older lesson `superseded` by the new one. Both stay in the database.
5. **Prune.** `score = (votes + helpful - 2*harmful) * 0.5^(age_days/90)`. Below 0.15, or
   `harmful >= 2`, moves a lesson to `archived` and appends it to `archive/YYYY-MM.md`.
6. **Compile.** Active lessons, sorted by score, capped at 150 lines per file, written to
   `compiled/PLAYBOOK.md` (project `all`) and `compiled/projects/<slug>.md` via `.tmp` then
   `os.replace`. Then one git commit.
7. **Deliver.** Claude Code reads the project file through an `@` import in `CLAUDE.md`.
   claude.ai reads `compiled/` through the Google Drive connector. Claude Desktop and Claude
   Code can also call `recall` on the MCP server mid-session.

## Memory tiers

Four, collapsed into one table with a `state` column:

| Tier in the plan | In the store |
|---|---|
| Episodic (raw) | the journal files and transcripts; not in the database at all |
| Semantic (distilled facts) | `lessons` rows, `state='active'` |
| Procedural (rules that keep recurring) | the same rows, surfaced by vote count |
| Working (this session) | not stored; Claude Code's own context |

The original plan had four tables. One table with a state column and a project column does the
same job with no joins.

## Retrieval

FTS5 BM25 over `text`, top 30, fused by reciprocal rank with an optional cosine pass over
stored embeddings, top 30. Default search returns `active` only; `--all` adds `superseded` and
`archived` but never `merged`, because a merged lesson's votes now live in its survivor.

Embeddings are off by default. The corpus is dense with exact tokens (`dbcache`, `rpcauth`,
`bitcoin-net`) that BM25 handles and embeddings blur; see `docs/research.md`.

## Concurrency

- **Journal:** one file per event, `open(path, "x")`, nanosecond stamp plus PID. Two events in
  one process in one tick still get two files; the test suite proves it.
- **Lock:** `mkdir .lock` on the bind-mounted store, so host and container processes serialise
  against the same directory. Waits up to 20 s. Breaks a lock older than 10 minutes.
- **Outputs:** `.tmp` sibling then `os.replace`. A reader never sees a torn file.
- **SQLite:** WAL, 30 s busy timeout, and on a named Docker volume rather than a macOS bind mount.
- **Recursion:** the Reflector's own `claude -p` runs with `MEMORY_REFLECT=1`; both hooks exit
  immediately when it is set.
- **Accepted residual:** two main Claude Code sessions in the same repository share one native
  auto-memory directory. That is Claude Code's race, not this system's; both sessions' journals
  survive independently.

## Runtime placement

`hooks/runner.sh` decides on every run. When this checkout's `.env` holds an `ANTHROPIC_API_KEY`
the hooks `docker exec` into the container; otherwise they run `bin/memory` on the host, which
reflects through `claude -p` on the subscription. `MEMORY_RUNNER` overrides both. Natively,
everything is on the host and `memory.db` sits in `~/memory`. In the container:

| Piece | Where | Why |
|---|---|---|
| `bin/memory`, Reflector, MCP server | container | pinned image, restart policy, 256 MB cap |
| `memory.db` | named volume | SQLite locking on macOS bind mounts is unreliable |
| journals, compiled, archive, `.git` | bind mount `~/memory` | Drive sync and `@` imports need host files |
| `~/.claude/projects` | bind mount, read-only | transcripts |
| `~/GitHub` | bind mount, read-only | `learn --all`: commit messages and docs |
| hooks | host | Claude Code runs there |

Identical paths inside and outside the container, so hook JSON needs no translation, and `HOME`
is the host's, so `Path.home()` finds the mounts. The two installs keep separate databases:
choose one and keep it, or carry `memory.db` across when switching.
