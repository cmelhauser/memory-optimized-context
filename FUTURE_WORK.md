# Future work

What is known to be open: what is next, what is waiting and on what, and what to watch. This file is the public roadmap: when an item is
done, delete it here and say so in `CHANGELOG.md`; when a new gap is found, add it. Nothing here is a promise,
and a release follows `RELEASING.md`. Session-by-session handoffs are not kept in the repository.

## Next

Each item can start as soon as what blocks it is cleared; both need an install that is running and reading real sessions.

1. **Get `helpful` votes recorded.** `memory vote --helpful` and the MCP `feedback` tool exist, and `examples/global-CLAUDE.md`
   has the sentences that tell Claude to use it, but no lesson has a `helpful` vote yet, so scoring runs on repetition
   alone. Next: put those sentences in the global `CLAUDE.md`, and after a month count `helpful` votes with `memory status`;
   if there are still none, drop `helpful` from the roadmap. Blocked by: a live install with the MCP server on.
2. **Validate the ChatGPT and Gemini adapters on real exports.** They are tested against fixtures built from the documented
   export formats. Next: request both exports (the README says how), run `memory learn --export FILE`, and fix anything
   the fixtures lacked, with a test. Blocked by: the operator requesting the exports.

## Waiting

- **Revisit the tuning, not before May 2027.** Measured on 29 Oct 2026 over 4,565 active lessons, the oldest six weeks old: a
  lesson with one vote falls below `min_score=0.15` only after about 246 days (`0.5 ** (age / 90) < 0.15`), so age cannot
  prune anything before mid-May 2027; only harmful votes archive sooner. Next, then: read how many lessons would be pruned
  and whether the survivors still read as useful, and decide whether `half_life_days` or `min_score` moves. Changing one is a
  MINOR or PATCH release: no store needs migrating.
- **The long tail under the line cap, if embeddings are adopted.** `compile_` already caps each project file at
  `max_lines=150`, best score first, so a big project does not crowd out a small one, and the cap is the context budget every
  session in that project pays, so it stays. In the largest project (1,663 active lessons) the file holds about everything
  with 8 or more votes; 747 lessons with 2 to 6 votes and 751 with one are reached by `search` and the MCP `recall`. The
  real fix is merging near-duplicates by meaning, which needs embeddings and so would be opt-in.

## Watch

- **The Reflector's output.** Its instructions say status (a merge, a release, a passing run) is not a lesson. Look at a week
  of new lessons for one-off facts that slip through, and tighten `REFLECT_SYS` if they do. Its first forty characters
  detect the Reflector's own transcripts, so they must not change.
- **The release workflow's signing retry.** It shipped in v1.1.2, whose run passed; at each release, check whether a retry
  step fired, since it has not yet been seen to.
- **Third-party limits.** The Reflector depends on `claude -p` being logged in, or on an API key; when either lapses
  the nightly job writes `needs-attention` and `memory status` says so.

## Ideas, not started

- Retry or back off inside the tool when the Reflector is rate-limited, instead of stopping the run.
- A `memory doctor` command that checks the hooks, the lock, the login and the schedule in one place.
- Python 3.11 in the CI matrix (3.10, 3.12 and 3.13 run today; 3.11 sits between the floor and the image's version).

## Won't do

See `docs/decisions/`: no fine-tuning, no vector server, no self-hosted OAuth, and `bin/memory` stays one file with
no runtime dependencies beyond the standard library.
