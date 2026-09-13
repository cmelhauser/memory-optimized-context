# Research notes

What was checked on 13 September 2026 before settling the design, and what each finding changed.
Sources are named; where a URL is given it was the page read.

## Retrieval over code: vectors lost

Anthropic removed the embedding pipeline and local vector store from Claude Code in May 2025 and
replaced it with grep, glob and read. Cursor, Windsurf, Cline, Devin and Sourcegraph Amp moved
the same way. An Amazon Science paper at AAAI 2026 measured agentic keyword search at 94.5 per
cent of RAG faithfulness with no vector store. The structural reason: chunking severs a
function's meaning across its signature, body, imports and callers; grep works with the file
and symbol names that are already there.

**Changed:** code and scripts are not indexed by this system at all. Claude Code greps them
live. Only distilled lessons go in the store.

## Memory as files

Anthropic's memory tool for the API is a directory of files the model creates, reads, updates
and deletes, run client-side. Claude Code's auto memory (v2.1.59, February 2026) is a
`MEMORY.md` index plus topic files per repository; the first 200 lines load at session start;
`autoMemoryDirectory` relocates it; AutoDream consolidates it during idle periods.
(https://code.claude.com/docs/en/memory)

**Changed:** compiled output is markdown, capped at 150 lines per file to stay under the
200-line import truncation. Native auto-memory directories are left alone, because AutoDream
already writes there and a second writer would race it.

## Context collapse

*Agentic Context Engineering* (Zhang et al., ICLR 2026, https://arxiv.org/abs/2510.04618)
names two failure modes of self-rewriting memory: brevity bias, where summaries drop domain
detail, and context collapse, where iterative rewriting erodes it over time. Its remedy is
append-only delta updates by a separate Reflector and Curator, with periodic dedupe and pruning
rather than regeneration. Reported gains: +10.6 per cent on agent benchmarks, 82.3 per cent
lower adaptation latency than GEPA.

**Changed:** the original nightly "LLM rewrites the semantic tier" job was deleted. Lessons are
appended and voted; the compiler sorts and caps; nothing regenerates the store.

## ADD-only and temporal validity

Mem0 (https://github.com/mem0ai/mem0) reports that never overwriting a fact, only adding, keeps
history intact and roughly doubles extraction throughput. Zep/Graphiti
(https://github.com/getzep/graphiti) timestamps every fact so the reader knows when it was true.

**Changed:** `upsert` never updates `text`; contradictions set `superseded_by` on the older row
rather than deleting it; `first_seen` and `last_seen` are kept on every row.

## Benchmarks are vendor-reported

Mem0 reports 92.5 on LoCoMo and 94.4 on LongMemEval at about 6,900 tokens per query. BEAM,
built so that no current architecture saturates it, puts the same system at 64.1 at 1M tokens
and 48.6 at 10M.

**Changed:** nothing in the code; a lot in the expectations. The eval harness in `eval/` exists
so that this repository's own numbers are measured, not quoted.

## Self-hosted OAuth for claude.ai connectors

Reports open in September 2026: configured auth headers not sent on the initial connection,
OAuth callbacks failing inside Claude's endpoint before token exchange, authless servers failing
on dynamic client registration.

**Changed:** no MCP-over-HTTPS path to claude.ai. claude.ai reads `compiled/` and writes
`journal/claude-ai/` through the Google Drive connector, which needs nothing hosted.

## Existing tools considered

| Tool | Verdict |
|---|---|
| basic-memory (https://github.com/basicmachines-co/basic-memory) | closest fit; markdown over MCP, Claude Code plugin. Not adopted because native auto memory plus a 400-line file covered it with fewer moving parts |
| Letta (https://github.com/letta-ai/letta) | agent-managed memory OS; heavier than the need |
| Cognee (https://github.com/topoteretes/cognee) | open-source graph memory; graph not needed at this scale |
| Zep | self-hosted Community Edition retired; fails the sovereignty requirement |
| Mem0 | graph features behind a paid tier; ADD-only pattern borrowed, code not |

## Embeddings, if ever

`voyage-3.5` as the default model; a reranker over BM25 as the cheaper alternative on a
keyword-dense corpus; Anthropic's contextual retrieval (prepend a context sentence to each chunk
before embedding) as the single best upgrade if chunked documents are ever indexed. None of
that is on by default here. The trigger to turn embeddings on is three keyword-search misses on
lessons known to exist.
