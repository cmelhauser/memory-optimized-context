#!/bin/bash
# End-to-end check of both installs, against stand-ins: a fake Messages API for the SDK path (as if
# a key were provided) and a fake `claude` for the subscription path. Everything runs in throwaway
# home directories under one temporary folder. Nothing calls Anthropic, nothing touches the real
# ~/memory or this checkout's .env, and the Docker phase uses its own Compose project and image tag,
# both removed on exit.
#
#   tools/e2e.sh              the native phases, then Docker when Docker Desktop is available
#   tools/e2e.sh --no-docker  the native phases only
#
# Needs git and Python 3.10+ (python3.12 if present). The Docker phase needs Docker Desktop, which
# reaches the fake API at host.docker.internal, and skips itself when a container named `memory`
# exists or port 8765 is taken, as on a machine running the real install. E2E_KEEP=1 keeps the
# temporary folder; E2E_VENV reuses a venv between runs.
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
E=$REPO/tools/e2e
tmp=${TMPDIR:-/tmp}
W=$(mktemp -d "${tmp%/}/memory-e2e.XXXXXX")   # macOS's TMPDIR ends in /; a // would not match Path.home()
PY=${PYTHON:-$(command -v python3.12 || command -v python3)}
PORT=${E2E_PORT:-18999}
VENV=${E2E_VENV:-$W/venv}
export GIT_AUTHOR_NAME=e2e GIT_AUTHOR_EMAIL=e2e@local GIT_COMMITTER_NAME=e2e GIT_COMMITTER_EMAIL=e2e@local
DC=(env HOME="$W/h4" DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}" docker compose -p memory-e2e -f "$W/compose/docker-compose.yml")
pass=0; fail=0

verdict() { if [ "$2" -eq 0 ]; then echo "PASS $1"; pass=$((pass + 1)); else echo "FAIL $1"; fail=$((fail + 1)); fi; }
check() { eval "$2"; verdict "$1" $?; }
wait_for() { for _ in $(seq 1 120); do grep -q "$2" "$1" 2>/dev/null && return 0; sleep 0.5; done; return 1; }
stop_json() {  # cwd transcript lesson -> a Stop hook's JSON, with a LESSONS block
  "$PY" -c 'import json, sys; print(json.dumps({"session_id": "e2e", "cwd": sys.argv[1], "transcript_path": sys.argv[2],
            "last_assistant_message": "Done.\n\nLESSONS:\n[all] " + sys.argv[3]}))' "$@"
}
new_home() { "$PY" "$E/fixture.py" "$1" && HOME=$1 "$REPO/tools/init_store.sh" >/dev/null; }
checkout() {  # dir [.env text]: hooks/ and bin/ copied, so the runner's choice never depends on this checkout's .env
  mkdir -p "$1/hooks" "$1/bin" && cp "$REPO"/hooks/*.sh "$1/hooks/" && cp "$REPO/bin/memory" "$1/bin/"
  if [ -n "${2:-}" ]; then printf '%s\n' "$2" > "$1/.env"; fi
}
store_checks() {  # phase home tag log
  local c=$2/memory/compiled/projects
  check "$1: us-hail-cat-model.md has the reflected lesson" "grep -q '$3 lesson for us-hail-cat-model' '$c/us-hail-cat-model.md'"
  check "$1: the README's tagged line was ingested with no LLM call, once" "grep -qx -- '- (1) tagged fact from the README' '$c/us-hail-cat-model.md'"
  check "$1: the worktree session is filed under doc-ingestion" "grep -q '$3 lesson for doc-ingestion' '$c/doc-ingestion.md'"
  check "$1: no collapsed slugs (model, ingestion, 15cf91)" "! ls '$c' | grep -qxE 'model.md|ingestion.md|15cf91.md|fervent-fermat-15cf91.md'"
  check "$1: each of the 160 turns of the long transcript reached the Reflector once" "'$PY' '$E/markers.py' '$4'"
  check "$1: the compile was committed to the store's git" "git -C '$2/memory' log --oneline | grep -q compile"
}
cleanup() {
  kill "$API" 2>/dev/null
  if [ -f "$W/compose/docker-compose.yml" ]; then "${DC[@]}" down -v --rmi all >/dev/null 2>&1; fi
  if [ -n "${E2E_KEEP:-}" ]; then echo "kept $W"; else rm -rf "$W"; fi
}

"$PY" "$E/fake_api.py" "$PORT" "$W/api.log" & API=$!
trap cleanup EXIT
for _ in $(seq 1 50); do "$PY" -c "import socket; socket.create_connection(('127.0.0.1', $PORT), 1)" 2>/dev/null && break; sleep 0.1; done
if [ ! -x "$VENV/bin/python3" ]; then
  read -r -a pins <<<"$(grep -oE '(anthropic|mcp)==[0-9.]+' "$REPO/Dockerfile" | tr '\n' ' ')"   # the image's pins
  if ! { "$PY" -m venv "$VENV" && "$VENV/bin/pip" install -q "${pins[@]}"; }; then echo "FAIL could not build the venv"; exit 1; fi
fi

echo "== 1. native, API key: the SDK, with the image's pins"
H=$W/h1; new_home "$H"
env -u MEMORY_RUNNER HOME="$H" ANTHROPIC_API_KEY=sk-ant-e2e-fake ANTHROPIC_BASE_URL="http://127.0.0.1:$PORT" MEMORY_LLM=auto \
  "$VENV/bin/python3" "$REPO/bin/memory" learn --all 2>&1 | tail -1
store_checks native-sdk "$H" sdk "$W/api.log"
check "native-sdk: every request carried the key" "! grep -v sk-ant-e2e-fake '$W/api.log' | grep -q ."
check "native-sdk: MCP over stdio lists the tools and recall reads the store" "HOME='$H' '$VENV/bin/python3' '$E/mcp_stdio.py' '$REPO/bin/memory'"

echo "== 2. native, no key: claude -p through the hooks, which choose native because .env has no key"
H=$W/h2; new_home "$H"; checkout "$W/native"
NATIVE=(env -u ANTHROPIC_API_KEY -u MEMORY_RUNNER HOME="$H" PATH="$E/bin:$PATH" E2E_CLI_LOG="$W/cli2.log")
wt=("$H"/.claude/projects/*worktrees*/w.jsonl)
stop_json "$H/GitHub/doc-ingestion/.claude/worktrees/fervent-fermat-15cf91" "${wt[0]}" "journaled through the native hook" \
  | "${NATIVE[@]}" bash "$W/native/hooks/journal.sh" main
wait_for "$H/memory/hook.log" "hook main:"
check "native-cli: the Stop hook ran bin/memory under Python 3.10+ (no traceback)" "grep -q 'hook main:' '$H/memory/hook.log' && ! grep -q Traceback '$H/memory/hook.log'"
check "native-cli: the LESSONS block was journaled and compiled" "grep -q 'journaled through the native hook' '$H/memory/compiled/PLAYBOOK.md'"
check "native-cli: the worktree's tail was reflected by claude -p, under doc-ingestion" "grep -q 'cli lesson for doc-ingestion' '$H/memory/compiled/projects/doc-ingestion.md'"
check "native-cli: claude -p was asked for JSON from claude-haiku-4-5-20251001" "grep -q '\"--output-format\", \"json\"' '$W/cli2.log' && grep -q claude-haiku-4-5-20251001 '$W/cli2.log'"
"${NATIVE[@]}" bash "$W/native/hooks/compile.sh" </dev/null
check "native-cli: the SessionStart hook ran ingest" "grep -q 'ingest:' '$H/memory/hook.log'"
"${NATIVE[@]}" "$PY" "$REPO/bin/memory" learn --all 2>&1 | tail -1
store_checks native-cli "$H" cli "$W/cli2.log"

echo "== 3. native, no key: a usage limit twice during the backfill, then a clean rerun"
H=$W/h3; new_home "$H"
LEARN=(env -u ANTHROPIC_API_KEY -u MEMORY_RUNNER HOME="$H" PATH="$E/bin:$PATH" E2E_CLI_LOG="$W/cli3.log" "$PY" "$REPO/bin/memory" learn --all)
out=$(E2E_FAIL_AFTER=2 "${LEARN[@]}" 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -q 'stopped early' <<<"$out"; verdict "resume: a limit inside a transcript stops learn with an error" $?
out=$(E2E_FAIL_ON="[documentation of" "${LEARN[@]}" 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -q 'stopped early' <<<"$out"; verdict "resume: the rerun carried on, then a limit at the docs stopped it" $?
out=$("${LEARN[@]}" 2>&1); rc=$?
verdict "resume: the third run finished" "$rc"
check "resume: the commits and the docs were each reflected once" "[ \"\$(grep -c 'git history of us-hail-cat-model' '$W/cli3.log')\" -eq 1 ] && [ \"\$(grep -c 'documentation of us-hail-cat-model' '$W/cli3.log')\" -eq 1 ]"
store_checks resume "$H" cli "$W/cli3.log"

skip=""
if [ "${1:-}" = --no-docker ]; then skip="--no-docker"
elif ! docker compose version >/dev/null 2>&1; then skip="docker compose is not available"
elif docker ps -a --format '{{.Names}}' | grep -qx memory; then skip="a container named memory exists (the real install?)"
elif "$PY" -c 'import socket; socket.create_connection(("127.0.0.1", 8765), 1)' 2>/dev/null; then skip="port 8765 is in use"
fi
if [ -n "$skip" ]; then
  echo "== 4. Docker: skipped, $skip"
else
  echo "== 4. Docker, API key: compose up --build, learn --all, the hooks via docker exec, MCP over HTTP"
  H=$W/h4; new_home "$H"
  env_text=$(printf 'ANTHROPIC_API_KEY=sk-ant-e2e-fake\nANTHROPIC_BASE_URL=http://host.docker.internal:%s\nMEMORY_LLM=sdk' "$PORT")
  mkdir -p "$W/compose/tools"
  cp "$REPO/Dockerfile" "$W/compose/" && cp -R "$REPO/bin" "$W/compose/" && cp "$REPO/tools/eval_recall.py" "$W/compose/tools/"
  sed 's/^\([[:space:]]*image:\).*/\1 memory-optimized-context:e2e/' "$REPO/docker-compose.yml" > "$W/compose/docker-compose.yml"
  printf '%s\n' "$env_text" > "$W/compose/.env"; checkout "$W/docker" "$env_text"
  "${DC[@]}" up -d --build 2>&1 | tail -2
  check "docker: MCP over HTTP answers on 127.0.0.1:8765" "'$PY' '$E/mcp_http.py' wait"
  check "docker: Path.home() in the container is the host HOME" "[ \"\$(docker exec memory python3 -c 'from pathlib import Path; print(Path.home())')\" = '$H' ]"
  check "docker: git's identity comes from /etc/gitconfig" "[ \"\$(docker exec memory git config --system user.name)\" = memory ]"
  : > "$W/api.log"
  docker exec memory python3 /app/memory learn --all 2>&1 | tail -1
  store_checks docker "$H" sdk "$W/api.log"
  wt=("$H"/.claude/projects/*worktrees*/w.jsonl)
  stop_json "$H/GitHub/doc-ingestion/.claude/worktrees/fervent-fermat-15cf91" "${wt[0]}" "journaled through the docker hook" \
    | env -u MEMORY_RUNNER HOME="$H" bash "$W/docker/hooks/journal.sh" main
  wait_for "$H/memory/hook.log" "hook main:"
  check "docker: a key in .env sent the Stop hook into the container; LESSONS compiled" "grep -q 'journaled through the docker hook' '$H/memory/compiled/PLAYBOOK.md'"
  env -u MEMORY_RUNNER HOME="$H" bash "$W/docker/hooks/compile.sh" </dev/null
  check "docker: the SessionStart hook ran ingest in the container" "grep -q 'ingest:' '$H/memory/hook.log'"
  check "docker: MCP over HTTP lists the tools and recall reads the volume's database" "'$PY' '$E/mcp_http.py'"
fi

echo "== $pass passed, $fail failed"
[ "$fail" -eq 0 ]
