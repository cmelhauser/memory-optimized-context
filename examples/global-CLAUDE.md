Append to `~/.claude/CLAUDE.md`. Optional once the Reflector is enabled; it raises precision.

---

If a durable cross-session fact was learned, end your final message with a `LESSONS:` block as
the very last thing: one line per fact, `[project-slug] fact` or `[all] fact`. If nothing durable
was learned, omit the block. Subagents that may run in parallel must not have a `memory:` field.
