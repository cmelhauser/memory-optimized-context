# 002. Files first; SQLite as a derived index; no vector server

**Context.** The first plan centred a vector database. Research (see `docs/research.md`) showed
the field moving to files plus grep for code and to markdown for memory.

**Decision.** Markdown in a git repository is the source of truth. SQLite with FTS5 is a derived
index that can be deleted and rebuilt. Embeddings are optional, stored as blobs, compared in
Python; no extension loading, no server.

**Consequences.** The store is readable, diffable and editable by hand. Cosine over a few
thousand rows is milliseconds. Nothing to keep running.

**Would reopen it.** More than ~50,000 active lessons, or a measured recall gap that BM25 plus
a reranker cannot close.
