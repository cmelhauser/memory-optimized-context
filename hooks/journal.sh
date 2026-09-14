#!/bin/bash
# Claude Code Stop / SubagentStop hook. Returns immediately; work runs in background.
# runner.sh picks the CLI: MEMORY_RUNNER, else the container when .env holds an API key, else native.
[ -n "$MEMORY_REFLECT" ] && exit 0
role=${1:-main}
# shellcheck source=hooks/runner.sh
. "$(dirname "$0")/runner.sh"
tmp=$(mktemp /tmp/memory-hook.XXXXXX); cat > "$tmp"
nohup bash -c "$RUN hook --role '$role' < '$tmp'; rm -f '$tmp'" >>"$HOME/memory/hook.log" 2>&1 &
exit 0
