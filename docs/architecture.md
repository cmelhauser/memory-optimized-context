# Architecture

The system as built. For how it got here, read `docs/research.md` and the decision records in
`docs/decisions/`. For the drawings, `docs/diagrams/04-as-built.svg` is this document in one
picture, showing the main paths (the README lists every adapter); `00` to `03` are the earlier drafts, kept because each one was wrong in an instructive
way.

## The rule everything follows

**No file has two writers.** Every other design choice is downstream of that.

| File or directory | Writer | Everyone else |
|---|---|---|
| `journal/DATE/*.md` | the process that created it, once, hard-linked whole from a `.part` file | read |
| `journal/claude-ai/*.md` | claude.ai, through Google Drive, one new file per note | read |
| `memory.db` | `bin/memory` inside `Lock()` | read |
| `compiled/*.md` | `bin/memory` inside `Lock()`, by atomic rename | read |
| `archive/*.md` | `bin/memory` inside `Lock()` | read |
| `~/.claude/projects/*/memory/` | Claude Code itself | untouched by this system |

## Data flow

0. **Learn.** `memory learn --all` walks every transcript the machine holds (Claude Code,
   Cursor, Claude Desktop's agent mode, Codex), git repositories (commit messages and docs), note
   folders, and claude.ai, ChatGPT and Gemini exports. Each source has a cursor in the `sources`
   table, so the walk is incremental: a commit hash, a content hash, a byte offset, an export's
   update time (a commit cursor lists the tips read so far, one per branch that was checked out). `[project] fact` lines anywhere are ingested without an
   LLM call (in a repository's own docs only those for its own slug); prose,
   transcripts and chats are windowed into ~30k-character batches for the Reflector, headers
   counted, so nothing is cut. A Claude Code transcript's project is the `cwd` recorded in it,
   the same slug the Stop hook derives, a worktree counting as its repository; the other tools'
   sessions are filed under their repository, or else under the tool. An exported chat defaults
   to its tool (`claude-ai`, `chatgpt`, `gemini`) unless the Reflector files it under a known
   project.
1. **Capture.** A Claude Code `Stop` or `SubagentStop` hook writes the hook JSON to a temp file,
   forks `memory hook`, and returns. `memory hook` journals any `LESSONS:` block from the last
   assistant message, then hands the transcript's new turns to the Reflector: at most two ~30k
   windows, oldest first, so a session that outran its stops is caught up, not skipped. The
   Reflector is asked with no lock held; the hook takes the lock only to store what it was
   told and, later, to settle the contradiction checks.
2. **Reflect.** Claude Haiku reads the transcript since the last byte offset and returns a JSON
   array of `{project, text}` lessons. The offset is stored so the next stop reflects only what
   is new. The same Reflector runs over claude.ai and ChatGPT `conversations.json` exports, keyed
   by each conversation's update time, and over Gemini's Takeout activity, keyed by the time of
   the last record read. When no answer comes (an API or CLI error, a usage limit), no
   cursor moves past the text that went unanswered: `learn` stops, keeps and compiles what it
   did, and the next run resumes there.
3. **Ingest.** Each lesson is upserted by `sha1(project | normalised text)[:10]`. An exact
   duplicate is a vote. Nothing is ever overwritten.
4. **Reconcile.** A new lesson is compared with its nearest neighbours in the same project and
   in `all`, up to six; one with none costs no call. Up to eight new lessons share a call, each with its own
   candidates, and the answer gives each its own verdict. A check that gets no answer, or that a `--max-calls`
   budget leaves for later, is owed: a `recheck:<id>` row in `sources`, paid first by the next
   `learn`.
   `same` folds the new lesson's votes into the older one and retires the new one as `merged`.
   `contradicts` marks the lesson from the older source `superseded` by the one from the newer. Both stay in the database.
5. **Prune.** `score = (votes + helpful - 2*harmful) * 0.5^(age_days/90)`. Below 0.15, or
   `harmful >= 2`, moves a lesson to `archived` and appends it to `archive/YYYY-MM.md`.
   Age runs from `last_seen`, the time the lesson's source was written (a transcript's, journal
   file's or chat's; a document's or commit's is the time it was read), so a backfill does not make
   old lessons look new. A lesson met again keeps its newest `last_seen` and oldest `first_seen`.
6. **Compile.** Active lessons, sorted by score, capped at 150 lines per file, written to
   `compiled/PLAYBOOK.md` (project `all`) and `compiled/projects/<slug>.md` via `.tmp` then
   `os.replace`. Then, when the store is a git repository and something changed, one git commit. A project with more active lessons than the cap shows only
   its top 150 here; the rest are in the database and reached by `search` and the MCP `recall`.
   Search is full-text (BM25) unless an embedding provider is set.
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

## What a model's answer may put in the store

The Reflector's lessons are written by a model from text that reached it, and `compiled/` is imported into
every session, so a lesson is data that can steer later sessions. Three things limit it. The Reflector runs
with no tools and is told the conversation is never instructions. A lesson is stored as one printable line
of at most 500 characters under a slug of at most 64, so it cannot forge a heading or an import line, and
a slug cannot be a path. And contradiction checks, votes and `harmful` marks can retire a lesson that proves
wrong. None of this makes a lesson's content trustworthy: a persuasive false lesson is still a lesson.

## Size

Lessons are one sentence each, so the store stays small. A store of several thousand active lessons
is a database of the order of ten megabytes, and the merged and superseded lessons kept beside
them are a minor part of that, mostly duplicates of a sentence already stored once. That is why
nothing is deleted and there is no vacuum command. What grows is the number of lessons per
project, and `compiled/` caps that at `MEMORY_MAX_LINES` per file, ranked by score; the rest are
reached through `search` and the MCP `recall`.

## Retrieval

FTS5 BM25 over `text`, top 30, fused by reciprocal rank with an optional cosine pass over
stored embeddings, top 30. Default search returns `active` only; `--all` adds `superseded` and
`archived` but never `merged`, because a merged lesson's votes now live in its survivor.

Embeddings are off by default. The corpus is dense with exact tokens (`maxconn`, `safe.directory`,
`GID=20`) that BM25 handles and embeddings blur; see `docs/research.md`.

## Concurrency

- **Journal:** one file per event, written under a `.part` name and hard-linked to its own (`os.link` fails if the name
  exists), so it appears whole; nanosecond stamp plus PID. Two events in
  one process in one tick still get two files; the test suite proves it.
- **Lock:** `mkdir .lock` on the bind-mounted store, so host and container processes serialise
  against the same directory. Waits up to 20 s (2 s for the SessionStart hook's
  `ingest --wait 2`), then gives up with `LockBusy`; `feedback` answers "busy" and `remember` says the
  lesson is journaled for the next ingest, instead of stopping. Breaks a lock untouched for 10 minutes (a holder touches it every 60 s). A Stop hook waits up to 120 s, and holds the
  lock only to store its lessons and to settle contradiction checks, never across a Reflector
  call; `.reflecting/` holds one claim per transcript a hook is reflecting.
- **Outputs:** `.tmp` sibling then `os.replace`. A reader never sees a torn file.
- **SQLite:** WAL, 30 s busy timeout, and on a named Docker volume rather than a macOS bind mount.
- **Recursion:** the Reflector's own `claude -p` runs with `MEMORY_REFLECT=1`; both hooks exit
  immediately when it is set, and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` keeps that call from writing
  an auto-memory of its own.
- **The Reflector only answers:** its `claude -p` runs with no tools, no MCP servers and no
  extended thinking, its instructions as the system prompt and the conversation alone on stdin.
  A transcript of another agent's task is read, not carried out.
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
