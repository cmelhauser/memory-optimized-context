#!/bin/bash
# Claude Code Stop / SubagentStop hook. Returns immediately; work runs in background.
# MEMORY_RUNNER: how to invoke the CLI. Default = the Docker container. Native: export MEMORY_RUNNER="python3 $HOME/GitHub/memory-optimized-context/bin/memory"
[ -n "$MEMORY_REFLECT" ] && exit 0
role=${1:-main}
RUN=${MEMORY_RUNNER:-"/usr/local/bin/docker exec -i memory python3 /app/memory"}
tmp=$(mktemp /tmp/memory-hook.XXXXXX); cat > "$tmp"
nohup bash -c "$RUN hook --role '$role' < '$tmp'; rm -f '$tmp'" >>"$HOME/memory/hook.log" 2>&1 &
exit 0
