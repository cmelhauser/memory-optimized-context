# Sourced by compile.sh and journal.sh. Sets RUN, an array holding the command that invokes bin/memory, so a checkout
# whose path has a space or a quote in it still runs (`"${RUN[@]}"`):
#
#   1. MEMORY_RUNNER, when set.
#   2. The container, when this checkout's .env holds an ANTHROPIC_API_KEY. Compose will not start
#      without that file and the image has no `claude` CLI, so a key is what a Docker install is.
#   3. Otherwise bin/memory from this checkout, natively. It reflects through `claude -p` on the
#      subscription, or through the SDK when ANTHROPIC_API_KEY is exported and `anthropic` is
#      installed.
#
# Hooks can start with a short PATH, so the usual install locations are appended, never
# prepended: whatever the caller put first still wins. macOS's /usr/bin/python3 is 3.9, below the
# 3.10 floor, so a newer interpreter is looked for by path before falling back to PATH.
# shellcheck shell=bash disable=SC2034  # RUN is read by the hook that sources this file
PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin"
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# The key as the file spells it: no carriage return (a file edited on Windows), no space, no quotes. A key written
# as "" is no key, and must not send the hooks to a container that is not there.
key=$(sed -n 's/^ANTHROPIC_API_KEY=//p' "$repo/.env" 2>/dev/null | tail -n 1 | tr -d '\r' \
      | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e "s/^[\"']//" -e "s/[\"']\$//")
if [ -n "${MEMORY_RUNNER:-}" ]; then
  if [ -x "$MEMORY_RUNNER" ]; then RUN=("$MEMORY_RUNNER"); else read -r -a RUN <<<"$MEMORY_RUNNER"; fi   # a program, or a command and its arguments
else
  case $key in
    '' | *...*)   # absent, or the .env.example placeholder
      py=python3
      for c in "$repo/.venv/bin/python3" /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        if [ -x "$c" ]; then py=$c; break; fi
      done
      RUN=("$py" "$repo/bin/memory") ;;
    *)
      RUN=(docker exec -i memory python3 /app/memory) ;;
  esac
fi
