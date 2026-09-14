#!/usr/bin/env python3
"""Documentation must match the tree.

Checks, each re-derived from the repository rather than trusted:
  1. Every count of tests stated in prose equals the number pytest collects.
  2. CITATION.cff `version` has a matching `## [version]` section in CHANGELOG.md.
  3. Every relative Markdown link resolves to a file in the tree.
  4. No tracked file contains a host-specific home path (`/Users/<name>`, `/home/<name>`), except
     the placeholders `/Users/<you>` and `/home/me`. The Compose file uses ${HOME}; the hooks use $HOME.
  5. The coverage gate in .coveragerc and the number quoted in prose agree.
  6. No tracked file contains an email address, except `noreply@anthropic.com` and the reserved
     example domains. The repository is public; contact details stay out of it.
Exit 1 on the first class of failure found, after printing all of them.
"""
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
PROSE = ["README.md", "AGENTS.md", "CLAUDE.md", "CHANGELOG.md", "CONTRIBUTING.md", "RELEASING.md"]
EMAIL = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")
EMAIL_OK = re.compile(r"noreply@anthropic\.com|[\w.%+-]+@example\.(?:com|org|net)")


def tracked_files():
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, check=False)
    if out.returncode == 0 and out.stdout.strip():
        return [REPO / p for p in out.stdout.split()]
    return [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]


def collected_tests():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], capture_output=True, text=True, cwd=REPO, check=False)
    m = re.search(r"(\d+) tests? collected", out.stdout) or re.search(r":\s*(\d+)\s*$", out.stdout.strip(), re.M)
    if not m:
        sys.exit(f"could not collect tests:\n{out.stdout}\n{out.stderr}")
    return int(m.group(1))


def main():
    errors = []
    n_tests = collected_tests()
    for name in PROSE:
        text = (REPO / name).read_text()
        for m in re.finditer(r"\b(\d+) tests\b", text):
            if int(m.group(1)) != n_tests:
                errors.append(f"{name}: says {m.group(1)} tests, pytest collects {n_tests}")
        for m in re.finditer(r"\bcoverage gate (?:is |at )(\d+) per cent\b", text):
            gate = re.search(r"fail_under\s*=\s*(\d+)", (REPO / ".coveragerc").read_text()).group(1)
            if m.group(1) != gate:
                errors.append(f"{name}: says coverage gate {m.group(1)}, .coveragerc says {gate}")

    version = re.search(r'^version:\s*"?([^"\n]+)"?', (REPO / "CITATION.cff").read_text(), re.M).group(1)
    if f"## [{version}]" not in (REPO / "CHANGELOG.md").read_text():
        errors.append(f"CHANGELOG.md has no section for CITATION.cff version {version}")

    for p in tracked_files():
        if p.suffix != ".md":
            continue
        text = p.read_text(errors="ignore")
        for m in re.finditer(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
            target = m.group(1)
            if re.match(r"^[a-z]+://|^mailto:", target):
                continue
            if not (p.parent / target).exists():
                errors.append(f"{p.relative_to(REPO)}: broken link {target}")

    home = re.compile(r"/(?:Users|home)/(?!<you>|me\b)[A-Za-z0-9_.-]+")
    for p in tracked_files():
        if p.suffix in (".jpeg", ".jpg", ".png", ".svg", ".zip"):
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if home.search(line):
                errors.append(f"{p.relative_to(REPO)}:{i}: host-specific home path")
            for address in EMAIL.findall(line):
                if not EMAIL_OK.fullmatch(address):
                    errors.append(f"{p.relative_to(REPO)}:{i}: email address")

    for e in errors:
        print("::error::" + e if "GITHUB_ACTIONS" in __import__("os").environ else e)
    print(f"check_docs: {n_tests} tests, version {version}, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
