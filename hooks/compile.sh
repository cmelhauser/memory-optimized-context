#!/bin/bash
# Claude Code SessionStart hook: fold in anything new before this session reads compiled/.
[ -n "$MEMORY_REFLECT" ] && exit 0
RUN=${MEMORY_RUNNER:-"/usr/local/bin/docker exec memory python3 /app/memory"}
$RUN ingest >>"$HOME/memory/hook.log" 2>&1
exit 0
