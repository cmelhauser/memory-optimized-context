"""Build a stand-in HOME for tools/e2e.sh: Claude Code transcripts (one long, one from a worktree) and a
git repository with a hyphenated name. Usage: fixture.py HOME"""
import json
import subprocess
import sys
from pathlib import Path

home = Path(sys.argv[1])


def encoded(p):
    return str(p).replace("/", "-").replace(".", "-")


def transcript(path, cwd, turns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for i, t in enumerate(turns):
            role = "user" if i % 2 == 0 else "assistant"
            content = t if role == "user" else [{"type": "text", "text": t}]
            f.write(json.dumps({"type": role, "cwd": str(cwd), "message": {"role": role, "content": content}}) + "\n")


hail = home / "GitHub" / "us-hail-cat-model"
worktree = home / "GitHub" / "doc-ingestion" / ".claude" / "worktrees" / "fervent-fermat-15cf91"
projects = home / ".claude" / "projects"
transcript(projects / encoded(hail) / "long.jsonl", hail, [f"M{i:03d} " + "hail modelling detail " * 28 for i in range(160)])
transcript(projects / encoded(worktree) / "w.jsonl", worktree, ["please fix the parser", "fixed the parser"])

hail.mkdir(parents=True)
(hail / "README.md").write_text("# us-hail-cat-model\n\n- [us-hail-cat-model] tagged fact from the README\n\nProse.\n")
git = ["git", "-C", str(hail)]
subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
for i in range(3):
    (hail / f"f{i}").write_text(str(i))
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", f"commit {i}: calibrate hail curve"], check=True)
