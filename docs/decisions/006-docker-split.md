# 006. Container for the tool, host for the hooks

**Context.** Claude Code runs on the host. The Mac mini has 8 GB shared with Bitcoin Core.

**Decision.** `bin/memory`, the Reflector and the MCP server run in one pinned container capped
at 256 MB. Hooks stay on the host and `docker exec` in. The database is on a named volume; the
markdown store is a bind mount at the same path inside and out.

**Consequences.** Restart policy, memory cap and pinned dependencies for free. Hooks are trivial.
The subscription-based `claude -p` Reflector is unavailable inside the container; the SDK is used
there.

**Would reopen it.** Running natively is fully supported via `MEMORY_RUNNER`; nothing is lost
by choosing it.
