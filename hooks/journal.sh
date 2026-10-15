#!/bin/bash
# Claude Code Stop / SubagentStop hook. Returns immediately; work runs in background.
# Each run opens hook.log with a dated `== time what` line, so a line under it can be placed in time.
# runner.sh picks the CLI: MEMORY_RUNNER, else the container when .env holds an API key, else native.
[ -n "$MEMORY_REFLECT" ] && exit 0
role=${1:-main}
# shellcheck source=hooks/runner.sh
. "$(dirname "$0")/runner.sh"
mkdir -p "$HOME/memory"      # without it the log cannot be opened, the job below never starts, and its temp file stays
tmp=$(mktemp /tmp/memory-hook.XXXXXX); cat > "$tmp"
echo "== $(date -u +%FT%TZ) stop $role" >>"$HOME/memory/hook.log"
# shellcheck disable=SC2016  # the single quotes are the point: this text is read by the inner shell, with its own $1
# The command travels as arguments, not as text for a shell to read again: a path with a space or a quote is one word.
nohup bash -c 'tmp=$1; role=$2; shift 2; "$@" hook --role "$role" < "$tmp"; rm -f "$tmp"' _ "$tmp" "$role" "${RUN[@]}" \
  >>"$HOME/memory/hook.log" 2>&1 &
exit 0
