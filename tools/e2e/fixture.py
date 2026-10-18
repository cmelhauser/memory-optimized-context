"""Build a stand-in HOME for tools/e2e.sh: Claude Code transcripts (one long, one from a worktree) and a
git repository with a hyphenated name. Usage: fixture.py HOME"""
import json
import subprocess
import sys
from pathlib import Path

home = Path(sys.argv[1])


def encoded(p):
    """A directory name as Claude Code spells it under ~/.claude/projects."""
    return str(p).replace("/", "-").replace(".", "-")


def transcript(path, cwd, turns):
    """Write a Claude Code transcript: alternating user and assistant turns, recorded as run in `cwd`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i, t in enumerate(turns):
            role = "user" if i % 2 == 0 else "assistant"
            content = t if role == "user" else [{"type": "text", "text": t}]
            f.write(json.dumps({"type": role, "cwd": str(cwd), "message": {"role": role, "content": content}}) + "\n")


repo = home / "GitHub" / "flood-risk-model"
worktree = home / "GitHub" / "doc-ingestion" / ".claude" / "worktrees" / "fervent-fermat-15cf91"
projects = home / ".claude" / "projects"
transcript(projects / encoded(repo) / "long.jsonl", repo, [f"M{i:03d} " + "flood modelling detail " * 27 for i in range(160)])
transcript(projects / encoded(worktree) / "w.jsonl", worktree, ["please fix the parser", "fixed the parser"])

repo.mkdir(parents=True)
(repo / "README.md").write_text("# flood-risk-model\n\n- [flood-risk-model] tagged fact from the README\n\nProse.\n", encoding="utf-8")
git = ["git", "-C", str(repo)]
subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
for i in range(3):
    (repo / f"f{i}").write_text(str(i), encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", f"commit {i}: calibrate the flood curve"], check=True)
