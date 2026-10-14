Append to `~/.claude/CLAUDE.md`. Optional once the Reflector is enabled; it raises precision. The second
paragraph applies only where the `memory` MCP server is registered.

---

If a durable cross-session fact was learned, end your final message with a `LESSONS:` block as
the very last thing: one line per fact, `[project-slug] fact` or `[all] fact`. If nothing durable
was learned, omit the block. Subagents that may run in parallel must not have a `memory:` field.

When the `memory` server's `recall` returns a lesson and you act on it, call `feedback` with its id:
`helpful` true if it held, false if it was wrong or out of date. Skip it when you did not use the lesson.
