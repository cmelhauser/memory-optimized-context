#!/bin/bash
# Create the memory store at $MEMORY_ROOT (default ~/memory). The store is its own private git
# repository, separate from this code repository, so a `git push` here can never publish your
# lessons. Safe to re-run.
set -euo pipefail
root="${MEMORY_ROOT:-$HOME/memory}"
mkdir -p "$root/journal/claude-ai" "$root/compiled/projects" "$root/archive" "$root/exports"
if [ ! -d "$root/.git" ]; then
  git -C "$root" init -q
  printf '.lock/\nmemory.db*\nhook.log\n*.tmp\n' > "$root/.gitignore"
  git -C "$root" add -A && git -C "$root" commit -qm "init store" || true
fi
echo "store ready at $root"
