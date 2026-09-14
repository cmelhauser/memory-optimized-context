# memory-optimized-context

*A single-file, parallel-safe long-term memory for Claude.*

Human Author: the repository owner
AI Collaborator: theonlymuffinbot, using Anthropic Claude

See [ATTRIBUTION.md](ATTRIBUTION.md) for the authorship and rights statement, and
[LICENSE](LICENSE) for the public-domain dedication and courtesy-credit request.

One Python file, two hook scripts. No server, no vector database, no scheduler. It captures
durable lessons from every Claude Code session and subagent, from claude.ai exports, and from
Claude Desktop, compiles them into short markdown files every Claude surface reads at session
start, and never lets two processes write the same file.

## Current status

`v0.1.0`. 52 tests, coverage 93 per cent on `bin/memory`, six-process concurrency test green.
The image is built and smoke-tested on arm64, and both installs have run end to
end against a fake Reflector. Not yet run against a real store; see `HANDOFF.md`.

## What it does

| Capability | How |
|---|---|
| Capture without the `LESSONS:` instruction | Stop hook passes the Claude Code transcript path; a Reflector (Claude Haiku via `claude -p` or SDK) extracts durable lessons from the session tail. Incremental by byte offset. |
| Capture from Desktop, web, mobile, Cowork | `memory ingest --export conversations.json` (claude.ai → Settings → Privacy → Export data). Same Reflector. Idempotent per conversation `updated_at`. Claude Desktop also gets live `remember`/`recall` via the MCP server. |
| Semantic recall | `MEMORY_EMBED=voyage` (or `openai`). Hybrid FTS5 + cosine, fused with RRF. Off by default; keyword search alone works. numpy in the image makes ranking 5,000 lessons a ~20 ms matmul; the stdlib fallback is ~300 ms. |
| Learn from history | `memory learn --all`: Claude Code transcripts, git commit messages and docs of every repo, notes, claude.ai exports. Incremental by cursor. |
| Contradiction handling | Every new lesson is compared with its nearest neighbours in the same project. `same` → votes merge. `contradicts` → older lesson marked `superseded_by` newer. ADD-only: nothing is deleted, `search --all` still finds it. |
| Automatic pruning | score = (votes + helpful − 2·harmful) × 0.5^(age/90d). Below threshold or harmful ≥ 2 → archived to `archive/YYYY-MM.md`, removed from compiled output, still searchable. |
| Parallel-safe | One journal file per event (never appended). Single `mkdir` lock around every DB/compiled write. Atomic rename on output. SQLite WAL. |

## Install

Two directories, kept apart on purpose: this repository is the code; `~/memory` is the store,
its own private git repository, so nothing you push here can publish your lessons.

Which install the hooks use follows from one fact, checked on every run by `hooks/runner.sh`:
does this checkout's `.env` hold an `ANTHROPIC_API_KEY`?

| Key in `.env` | Install | Reflector (Claude Haiku) |
|---|---|---|
| none (the default) | native: `bin/memory` from this checkout | `claude -p` on your subscription; the SDK instead if `ANTHROPIC_API_KEY` is exported and `anthropic` is installed |
| present | Docker: the `memory` container | the Anthropic SDK in the image |

`MEMORY_RUNNER` overrides the choice. The two installs keep separate databases
(`~/memory/memory.db` natively, the `memory-db` volume in Docker), so pick one and keep it, or
carry `memory.db` across when you switch.

### Native (default without an API key)

```bash
git clone https://github.com/cmelhauser/memory-optimized-context ~/GitHub/memory-optimized-context
cd ~/GitHub/memory-optimized-context
tools/init_store.sh                          # creates ~/memory with its own .git
python3 -m venv .venv && .venv/bin/pip install anthropic==1.5.0 mcp==2.2.0   # MCP server + SDK, the image's pins
.venv/bin/python3 bin/memory compile
```

Python 3.10 or newer; macOS's `/usr/bin/python3` is 3.9, so build the venv with Homebrew's. The
venv is optional. Without it the hooks run Homebrew's `python3`, and reflection still works,
because `claude -p` needs nothing installed; the hooks find `claude` on `PATH` or in
`~/.local/bin`. `MEMORY_LLM=none` for keyword-only.

### Docker (with an API key)

```bash
tools/init_store.sh
cp .env.example .env && $EDITOR .env         # ANTHROPIC_API_KEY; from now on the hooks use the container
docker compose up -d --build
docker exec memory python3 /app/memory compile   # creates compiled/, DB on the memory-db volume
```

What runs where:

| Piece | Where | Why |
|---|---|---|
| `memory` CLI, MCP server (HTTP :8765), Reflector, embeddings | container | pinned image, `restart: unless-stopped`, 256 MB cap |
| `memory.db` | named volume `memory-db` | SQLite locking is unreliable on macOS bind mounts |
| `journal/`, `compiled/`, `archive/`, `.git` | bind mount `~/memory` | Drive sync and `@` imports need them on the host |
| `~/.claude/projects` | bind mount, read-only | transcripts for the Reflector |
| `~/GitHub` | bind mount, read-only | `learn --all`: commit messages and docs |
| Hooks | host (Claude Code runs there) | short shells that `docker exec` into the container and return |

Paths are mounted at identical locations inside the container and the container's `HOME` is
your host `HOME`, so `transcript_path` from hook JSON needs no translation and `learn --all`
finds `~/.claude/projects` and `~/GitHub`. The container runs as root per your Docker ground
rules (no `--user`); Docker Desktop maps written files to your host user.

Compose refuses to start without `.env`. That is deliberate: the image has no `claude` CLI, so
a container without a key has no Reflector.

### Claude Code — `~/.claude/settings.json`

The hooks run from this checkout; the same lines are in `hooks/settings.snippet.json`.

```json
{ "hooks": {
  "SessionStart": [{ "hooks": [{ "type": "command", "command": "~/GitHub/memory-optimized-context/hooks/compile.sh" }] }],
  "Stop":         [{ "hooks": [{ "type": "command", "command": "~/GitHub/memory-optimized-context/hooks/journal.sh main" }] }],
  "SubagentStop": [{ "hooks": [{ "type": "command", "command": "~/GitHub/memory-optimized-context/hooks/journal.sh sub" }] }]
}}
```

Register the MCP server so Claude can search and save mid-session:

```bash
claude mcp add --scope user memory -- ~/GitHub/memory-optimized-context/.venv/bin/python3 ~/GitHub/memory-optimized-context/bin/memory mcp   # native
claude mcp add --scope user --transport http memory http://127.0.0.1:8765/mcp     # Docker
```

Each project's `CLAUDE.md`, one line:

```
@~/memory/compiled/projects/<slug>.md
```

`<slug>` is the repo folder name, lowercased; a session in a Claude Code worktree
(`<repo>/.claude/worktrees/<name>`) counts as the repository. Optional in `~/.claude/CLAUDE.md`
(improves signal, no longer required):

```
If a durable cross-session fact was learned, end your final message with a LESSONS: block:
one line per fact, `[project-slug] fact` or `[all] fact`.
```

### VS Code and JetBrains extensions

Nothing extra. The extensions run the same Claude Code and share `~/.claude/settings.json`
(hooks, MCP servers), `CLAUDE.md`, and the transcript store under `~/.claude/projects`. Register
the MCP server with `claude mcp add --scope user`, not through VS Code's own `mcp.json`; the
extension does not read that file.

### Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`

Claude Desktop only accepts stdio commands. Native (needs the venv above):

```json
{ "mcpServers": { "memory": { "command": "/Users/<you>/GitHub/memory-optimized-context/.venv/bin/python3", "args": ["/Users/<you>/GitHub/memory-optimized-context/bin/memory", "mcp"] } } }
```

Docker, exec into the container:

```json
{ "mcpServers": { "memory": { "command": "/usr/local/bin/docker", "args": ["exec", "-i", "memory", "python3", "/app/memory", "mcp"] } } }
```

### claude.ai web / mobile / Cowork

Google Drive for desktop: sync exactly `~/memory/compiled` and `~/memory/journal/claude-ai`. Project instructions:

```
At the start of each conversation, read memory/compiled/PLAYBOOK.md and
memory/compiled/projects/<project>.md from Google Drive. To save a durable lesson,
create a NEW file in memory/journal/claude-ai/ containing lines `[project] fact`.
Never edit anything under memory/compiled/.
```

Full-history capture from these surfaces: export data monthly, drop `conversations.json` in
`~/memory/exports/`, then `memory ingest --export ~/memory/exports/conversations.json`
(prefixed as under [Commands](#commands)).

## Learning from everything you already have

`memory learn` reads the sources below once, then only what changed. Cursors live in the
database, so it is safe to run daily; a second run over an unchanged source makes no LLM call.

| Source | Flag | What is read | Cursor |
|---|---|---|---|
| Claude Code transcripts, all projects | `--transcripts` | every `~/.claude/projects/*/*.jsonl`, whole, in ~30k windows; project from the `cwd` recorded in the transcript, a worktree counting as its repository | byte offset per file |
| A git repository | `--repo PATH` | commit messages (`--no-merges`, oldest first), `README*`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/**/*.md`, `*.md` | last commit hash; content hash per doc |
| A folder of notes | `--notes DIR [--project slug]` | every `.md` and `.txt`, recursively | content hash per file |
| claude.ai export (web, Desktop, mobile, Cowork) | `--export FILE` | `conversations.json`, both message shapes | `updated_at` per conversation |
| All of the above | `--all [--repos ~/GitHub] [--notes DIR] [--exports ~/memory/exports]` | transcripts, every git repo under `--repos`, notes, every `*.json` under `--exports` | as above |

Lines already in the form `[project] fact` (bulleted or not) in any doc or note are ingested
directly with no LLM call. Everything else goes through the Reflector in windows of about 30k
characters, one Haiku call per window. A repository with a thousand commits costs roughly ten
calls the first time and none afterwards. `--since 2025-01-01` bounds the first pass. No notes
folder is read unless you name one with `--notes`.

```bash
python3 bin/memory learn --all                           # native
docker exec memory python3 /app/memory learn --all       # Docker
```

## Commands

Prefix with `python3 ~/GitHub/memory-optimized-context/bin/memory` (native; `.venv/bin/python3`
if you made the venv) or `docker exec memory python3 /app/memory` (Docker).

```
memory search "query" [--project slug] [-k 8] [--all]
memory remember "fact" --project slug
memory vote <id> --helpful | --harmful
memory ingest [--transcript PATH --project slug] [--export conversations.json]
memory learn --all | --repo PATH | --notes DIR | --transcripts | --export FILE
memory compile
```

## Environment

| Var | Default | Notes |
|---|---|---|
| `MEMORY_ROOT` | `~/memory` | set in the image to the mounted host path |
| `MEMORY_DB` | `$MEMORY_ROOT/memory.db` | `/data/memory.db` in Docker |
| `MEMORY_RUNNER` | chosen by `hooks/runner.sh` | hooks only: the container if `.env` has `ANTHROPIC_API_KEY`, else `bin/memory` natively; set it to override |
| `MEMORY_LLM` | `auto` | `sdk` / `cli` / `none` |
| `MEMORY_MODEL` | `claude-haiku-4-5-20251001` | reflector + contradiction check |
| `MEMORY_EMBED` | `none` | `voyage` (`VOYAGE_API_KEY`) or `openai` (`OPENAI_API_KEY`) |
| `MEMORY_HALF_LIFE` | `90` | days |
| `MEMORY_MAX_LINES` | `150` | per compiled file; keep under Claude Code's 200-line import cap |
| `MEMORY_MIN_SCORE` | `0.15` | archive below this |

## Guarantees

- No file has two writers. Journals are write-once. `compiled/` and `memory.db` are written only under `.lock`.
- Readers never see a torn file (`os.replace`).
- A hook never blocks Claude: it forks and returns.
- Reflection can't recurse: `MEMORY_REFLECT=1` is set on the inner `claude -p`, and both hooks exit on it.
- The lock is a `mkdir` on the bind-mounted `~/memory/.lock`, so host processes and container processes serialize against each other.
- Every compile is a git commit. `git log -p compiled/` is the audit trail.
- Nothing is ever deleted: superseded, merged, and archived lessons stay in `memory.db` and `archive/`.

## Repository layout

```
bin/memory                 the tool, one file
hooks/                     Claude Code hook scripts, the runner they share, the settings.json snippet
examples/                  prompt and config snippets for claude.ai, CLAUDE.md, Claude Desktop
eval/                      recall@k harness and an example question set
tests/test_memory.py       52 tests, six-process concurrency test included
tools/                     init_store.sh, bootstrap.sh, run_ci_locally.sh, check_docs.py, eval_recall.py
docs/architecture.md       the system as built
docs/concurrency.md        every race considered and the test that closes it
docs/research.md           what was checked before deciding, and what each finding changed
docs/decisions/            one record per closed alternative
docs/diagrams/             the original sketch and four drafts, ending at 04-as-built.svg
Dockerfile, docker-compose.yml, .env.example
```

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
tools/run_ci_locally.sh            # lint, shellcheck, tests with the coverage gate
tools/run_ci_locally.sh --image    # plus the container build
```

`AGENTS.md` has the ground rules, `RELEASING.md` the branch and tag scheme, `CONTRIBUTING.md`
what will and will not be merged. `tools/check_docs.py` fails CI if a count in this file stops
matching the tree.

## Costs

One Haiku call per session stop (transcript tail ≤ 30k chars) plus one per new lesson for the contradiction check. Typical day: a few cents on the API, or a negligible slice of a subscription via `claude -p`. Embeddings, if enabled: one call per new lesson.

The first `learn --all` is the expensive run: one call per ~30k window of every transcript, commit
log and doc set, which for months of history is hundreds of calls. On a subscription that can
reach usage limits, so it can be taken a source at a time (`--repo`, `--transcripts`).
