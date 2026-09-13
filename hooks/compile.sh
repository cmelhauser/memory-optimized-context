#!/bin/bash
# Claude Code SessionStart hook: fold in anything new before this session reads compiled/.
[ -n "$MEMORY_REFLECT" ] && exit 0
# shellcheck source=hooks/runner.sh
. "$(dirname "$0")/runner.sh"
$RUN ingest </dev/null >>"$HOME/memory/hook.log" 2>&1
exit 0
