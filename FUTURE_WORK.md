# Future work

What is known to be open, in the order it will be picked up. This file is the public roadmap: when an item is
done, delete it here and say so in `CHANGELOG.md`; when a new gap is found, add it. Nothing here is a promise,
and a release follows `RELEASING.md`. Session-by-session handoffs are not kept in the repository.

## Next

1. **Judge the tuning on a month of real use.** The scoring constants (`half_life_days=90`, `min_score=0.15`,
   `max_lines=150`) were chosen once and reviewed once. Pruning has not yet acted on real data, because no lesson
   is old enough to fall below `min_score`. Read `memory status` and the nightly log, then decide whether any
   constant moves. Changing one is a MINOR or PATCH release: no store needs migrating.
2. **A project with more lessons than the cap hides the rest.** `compile_` writes the top 150 lines per project;
   a project with far more active lessons shows only its best, and the others are reached by `search` and the MCP
   `recall`. Options: a per-project cap that favours recent lessons, or merging near-duplicates by meaning (which
   needs embeddings, so it would be opt-in).
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
