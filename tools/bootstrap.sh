#!/bin/bash
# One-time: create ~/GitHub/memory-optimized-context from this folder and publish it as a public
# GitHub repository under the current `gh` login. Requires `gh auth login` to have been run.
#
#   bash bootstrap.sh            create + push
#   bash bootstrap.sh --dry-run  show what would happen
set -euo pipefail
src="$(cd "$(dirname "$0")/.." && pwd)"
dest="$HOME/GitHub/memory-optimized-context"
name="memory-optimized-context"

if [ "${1:-}" = "--dry-run" ]; then
  echo "would copy $src -> $dest, git init, commit, then: gh repo create $name --public --source $dest --push"
  exit 0
fi
command -v gh >/dev/null || { echo "install GitHub CLI: brew install gh && gh auth login"; exit 1; }
[ -e "$dest" ] && { echo "$dest already exists; refusing to overwrite"; exit 1; }

mkdir -p "$HOME/GitHub"
rsync -a --exclude .git  --exclude '.venv' --exclude '__pycache__' "$src/" "$dest/"
cd "$dest"
git init -q -b main
git add -A
git commit -qm "v0.1.0: single-file parallel-safe memory for Claude"
gh repo create "$name" --public --source . --remote origin --push \
  --description "A single-file, parallel-safe long-term memory for Claude" \
  --homepage "https://github.com/cmelhauser/memory-optimized-context"
gh repo edit --enable-issues --enable-wiki=false --delete-branch-on-merge
echo
echo "Published. Next, as README.md \"Install\" describes:"
echo "  tools/init_store.sh     # the store, ~/memory"
echo "  the hooks from hooks/settings.snippet.json: native by default, the container once .env holds a key"
echo "Tag only as RELEASING.md describes, once CI is green on main."
