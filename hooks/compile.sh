#!/bin/bash
# Claude Code SessionStart hook: fold in anything new before this session reads compiled/. It runs
# in the foreground, so it waits at most 2 s for the lock: while a long `learn` holds it, the
# session reads compiled/ as it was, and the next compile catches up.
[ -n "$MEMORY_REFLECT" ] && exit 0
# shellcheck source=hooks/runner.sh
. "$(dirname "$0")/runner.sh"
$RUN ingest --wait 2 </dev/null >>"$HOME/memory/hook.log" 2>&1
exit 0
