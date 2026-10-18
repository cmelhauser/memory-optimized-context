# 002. Files first; SQLite for state and search; no vector server

**Context.** The first plan centred a vector database. Research (see `docs/research.md`) showed
the field moving to files plus grep for code and to markdown for memory.

**Decision.** SQLite with FTS5 is the system of record for lessons, votes, state and cursors.
Markdown (`journal/`, `compiled/`, `archive/`, committed to the store's git) is the readable,
diffable output and input; `compiled/` is generated from the database. Embeddings are optional,
stored as blobs, compared in Python; no extension loading, no server.

**Amended 18 October 2026.** The first draft called the database a derived index that could be
deleted and rebuilt. It cannot: supersession, `helpful` and `harmful` votes, every cursor and the
owed contradiction checks live only there.

**Consequences.** The store is readable, diffable and editable by hand. Cosine over a few
thousand rows is milliseconds. Nothing to keep running.

**Would reopen it.** More than ~50,000 active lessons, or a measured recall gap that BM25 plus
a reranker cannot close.
