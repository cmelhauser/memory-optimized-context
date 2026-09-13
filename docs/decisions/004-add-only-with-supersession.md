# 004. ADD-only, with supersession instead of deletion

**Context.** Contradictions are inevitable (`maxconn=4000` during a migration, `maxconn=1024` after).

**Decision.** New lessons are added. A contradiction marks the older lesson `superseded_by` the
newer. A restatement merges votes into the older survivor. Pruning marks `archived`. No row is
ever deleted.

**Consequences.** `search --all` is a complete history. Compiled output shows only what is
current. Mistakes by the contradiction checker are reversible with one `UPDATE`.

**Would reopen it.** Store size, which at one row per lesson is not a realistic concern.
