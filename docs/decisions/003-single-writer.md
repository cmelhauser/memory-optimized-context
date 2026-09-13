# 003. One writer per file

**Context.** Parallel subagents, concurrent sessions, Drive sync, AutoDream and a nightly job
all wanted to edit `MEMORY.md`.

**Decision.** Journals are write-once files. `compiled/` and the database are written only by
`bin/memory` under a `mkdir` lock. Native Claude Code memory directories are never written.

**Consequences.** No lost updates, no conflict copies, no torn reads. The cost is a bounded lag:
a journal written during a compile lands in the next compile.

**Would reopen it.** Nothing foreseeable. This is the invariant the test suite protects.
