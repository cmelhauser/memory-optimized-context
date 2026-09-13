# 005. No self-hosted OAuth for claude.ai

**Context.** claude.ai custom connectors require HTTPS plus OAuth. Self-hosting that is where
the time would have gone, and the open bug reports in September 2026 said it often fails.

**Decision.** claude.ai reads `compiled/` and writes `journal/claude-ai/` through the Google
Drive connector already attached to the account.

**Consequences.** Nothing hosted, nothing exposed, no OAuth. Web-side writes arrive at the next
compile rather than instantly. Full web history is captured by monthly export.

**Would reopen it.** Anthropic shipping a stable header-auth path for custom connectors, at
which point `memory mcp --transport http` behind a tunnel is a one-line change.
