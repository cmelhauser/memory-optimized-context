#!/bin/bash
# Nightly catch-up: `learn --transcripts --max-calls N`, run by tools/install_nightly.sh's scheduler.
#
# Why it exists: a Stop hook that cannot get the store's lock leaves its transcript's cursor where it was, and a
# session whose last stops lost that race has its final turns read by nothing else. This reads them. A hook that
# loses the race is rare since a hook stopped holding the lock across a Reflector call, so a run is usually a few
# minutes and a few dozen calls.
#
# Exit status of the run, as in `memory learn`:
#   0  everything was read                       the usual night
#   1  stopped part-way, work done               a spent budget or a usage limit; tomorrow carries on
#   2  the Reflector answered nothing at all     shouts (log, alert file, notification) and stays scheduled
#
# Settings, all optional: CALLS (the budget, 60), MEMORY_PYTHON (the interpreter; else this checkout's .venv,
# else python3), MEMORY_STATE_DIR (the log and the alert file; else ~/.local/share/memory-optimized-context),
# RETRY_WAIT (seconds between tries while a hook holds the lock, 60).
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${MEMORY_STATE_DIR:-$HOME/.local/share/memory-optimized-context}"
LOG="$DIR/backfill.log"
ALERT="$DIR/needs-attention"
CALLS="${CALLS:-60}"
RETRY_WAIT="${RETRY_WAIT:-60}"
PY="${MEMORY_PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$REPO/.venv/bin/python3" ]; then PY="$REPO/.venv/bin/python3"; else PY=python3; fi
fi
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$DIR"
out=$(mktemp)
trap 'rm -f "$out"' EXIT

echo "== $(date '+%F %T') nightly catch-up start (learn --transcripts --max-calls $CALLS)" >> "$LOG"
rc=1
for _ in 1 2 3 4 5 6; do
  "$PY" "$REPO/bin/memory" learn --transcripts --max-calls "$CALLS" 2>&1 | tee "$out" >> "$LOG"
  rc=${PIPESTATUS[0]}
  grep -q "lock was held" "$out" || break
  sleep "$RETRY_WAIT"                                           # a hook or another run holds the store; try again
done

alert () {   # alert "what happened" "what to do": the log, the alert file, and a notification where there is one
  why=$(grep -E '^(memory|\[memory\]|Traceback|[A-Za-z]*Error)' "$out" | tail -n 1 | cut -c1-300)
  { echo "== $(date '+%F %T') STOPPED: $1"
    echo "==   ${why:-no reason was logged} (exit $rc)"
    echo "==   $2"
  } >> "$LOG"
  { date '+%F %T'; echo "$1"; echo "$why"; } > "$ALERT"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'display notification "The catch-up did not run as it should. See backfill.log." with title "memory nightly catch-up"' >/dev/null 2>&1 || true
  fi
}

case "$rc" in
  0) rm -f "$ALERT"; echo "== $(date '+%F %T') nightly catch-up finished: everything read" >> "$LOG" ;;
  2) alert "the Reflector answered nothing at all, so this run read nothing." \
           "Check it with: echo 'Say OK' | claude -p --output-format json --no-session-persistence. An expired login or a spent monthly limit is the usual cause. The job stays scheduled." ;;
  *)
    # 1 is a spent budget or a usage limit, which `learn` reports and tomorrow resumes. Anything else is not: an
    # interpreter that is missing (127) or crashed, or a store whose lock was held through every try.
    if [ "$rc" -ge 3 ] || grep -q "Traceback" "$out" || grep -q "lock was held" "$out"; then
      alert "the catch-up failed for a reason that is not a spent budget." \
            "Run it by hand to see why: $0. The job stays scheduled."
    else
      rm -f "$ALERT"       # the Reflector answered, or this run would have exited 2
      echo "== $(date '+%F %T') nightly catch-up stopped part-way (exit $rc); tomorrow carries on" >> "$LOG"
    fi ;;
esac
exit "$rc"
