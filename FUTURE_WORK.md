# Future work

What is known to be open, in the order it will be picked up. This file is the public roadmap: when an item is
done, delete it here and say so in `CHANGELOG.md`; when a new gap is found, add it. Nothing here is a promise,
and a release follows `RELEASING.md`. Session-by-session handoffs are not kept in the repository.

## Next

1. **Revisit the tuning in spring 2027, not before.** Measured on 29 Oct 2026 over a store of 4,565 active lessons whose oldest
   is six weeks old: a lesson with one vote falls below `min_score=0.15` only after about 246 days
   (`0.5 ** (age / 90) < 0.15`), so pruning cannot act on one-vote lessons before mid-May 2027; only a second harmful vote
   archives sooner. There is nothing to tune yet. When the oldest lessons near that age, read how many would be pruned and
   whether the survivors still read as useful, then decide whether `half_life_days` or `min_score` moves. Changing one is
   a MINOR or PATCH release: no store needs migrating.
2. **The line cap is per file already; leave it.** `compile_` writes at most `max_lines=150` lines per project file, best score
   first, so a big project does not crowd out a small one. In the largest project (1,663 active lessons) the file holds
   everything with 7 or more votes; about 900 lessons with 2 to 6 votes are reached by `search` and the MCP `recall`. The cap is
   the context budget every session in that project pays, so raising it for one project costs more than it gains. A real
   fix for the long tail is merging near-duplicates by meaning, which needs embeddings and so would be opt-in; start it
   only if embeddings are adopted (see `README.md`).
3. **Get `helpful` votes recorded.** `memory vote --helpful` and the MCP `feedback` tool exist, but no lesson
   has a `helpful` vote yet, so scoring runs on repetition alone. Decide whether recall should prompt for feedback,
   or whether the signal is not worth chasing.
4. **Validate the ChatGPT and Gemini adapters on real exports.** They are tested against fixtures built from the
   documented export formats. The first real export may show a field the fixtures lack; fix it with a test.

## Watch

- **The Reflector's output.** Its instructions now say status (a merge, a release, a passing run) is not a lesson.
  Look at a week of new lessons for one-off facts that slip through, and tighten `REFLECT_SYS` if they do. Its first
  forty characters detect the Reflector's own transcripts, so they must not change.
- **The release workflow's signing retry.** Each Sigstore signing step is tried twice. It has only run in CI
  syntax checks, never on a tag; the next release is its first real use.
- **Third-party limits.** The Reflector depends on `claude -p` being logged in, or on an API key; when either lapses
  the nightly job writes `needs-attention` and `memory status` says so.

## Ideas, not started

- Retry or back off inside the tool when the Reflector is rate-limited, instead of stopping the run.
- A `memory doctor` command that checks the hooks, the lock, the login and the schedule in one place.
- Python 3.11 in the CI matrix (3.10, 3.12 and 3.13 run today; 3.11 sits between the floor and the image's version).

## Won't do

See `docs/decisions/`: no fine-tuning, no vector server, no self-hosted OAuth, and `bin/memory` stays one file with
no runtime dependencies beyond the standard library.
