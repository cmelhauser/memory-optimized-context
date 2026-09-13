"""Unit tests for bin/memory.

Every test runs against a throwaway MEMORY_ROOT. The LLM is replaced by a fake that returns
canned JSON, so the Reflector and the contradiction check are exercised without a network.
The one thing these tests cannot do is call Claude; `llm()` itself is covered by the
`MEMORY_LLM=none` path and by the fake.
"""
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO / "bin" / "memory"


def load(root, monkeypatch, **env):
    """Import bin/memory fresh with MEMORY_ROOT pointed at `root`."""
    monkeypatch.setenv("MEMORY_ROOT", str(root))
    monkeypatch.setenv("MEMORY_LLM", env.pop("MEMORY_LLM", "none"))
    monkeypatch.delenv("MEMORY_DB", raising=False)
    monkeypatch.delenv("MEMORY_REFLECT", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    loader = importlib.machinery.SourceFileLoader("memory_under_test", str(BIN))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def m(tmp_path, monkeypatch):
    return load(tmp_path, monkeypatch)


def journal(m, lines, sub="claude-ai", name="n.md"):
    d = m.JOURNAL / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(lines) + "\n")


def run_ingest(m):
    with m.Lock(), m.db() as c:
        new = m.ingest_journal(c)
        m.post_ingest(c, new)
        c.commit()
        m.compile_(c)
        c.commit()
    return new


# ------------------------------------------------------------------ store


def test_lesson_id_is_stable_under_whitespace_case_and_trailing_period(m):
    a = m.lid("all", "Never pass GID=20.")
    b = m.lid("all", "  never   pass gid=20 ")
    assert a == b
    assert m.lid("other", "Never pass GID=20.") != a


def test_upsert_is_add_only_and_counts_votes(m):
    with m.db() as c:
        i1, new1 = m.upsert(c, "all", "x")
        i2, new2 = m.upsert(c, "all", "x")
        assert i1 == i2 and new1 and not new2
        assert c.execute("SELECT votes FROM lessons").fetchone()[0] == 2


def test_upsert_reactivates_an_archived_lesson(m):
    with m.db() as c:
        i, _ = m.upsert(c, "all", "x")
        c.execute("UPDATE lessons SET state='archived' WHERE id=?", (i,))
        m.upsert(c, "all", "x")
        assert c.execute("SELECT state FROM lessons WHERE id=?", (i,)).fetchone()[0] == "active"


def test_db_can_live_outside_root(tmp_path, monkeypatch):
    m = load(tmp_path / "root", monkeypatch, MEMORY_DB=str(tmp_path / "elsewhere" / "memory.db"))
    with m.db():
        pass
    assert (tmp_path / "elsewhere" / "memory.db").exists()
    assert not (tmp_path / "root" / "memory.db").exists()


# ------------------------------------------------------------------ lock


def test_lock_serialises_writers(m):
    order = []

    def worker(n):
        with m.Lock():
            order.append(("in", n))
            time.sleep(0.05)
            order.append(("out", n))

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # never two "in" without an "out" between them
    depth = 0
    for kind, _ in order:
        depth += 1 if kind == "in" else -1
        assert depth in (0, 1)
    assert not m.LOCK.exists()


def test_stale_lock_is_broken(m):
    m.ROOT.mkdir(parents=True, exist_ok=True)
    m.LOCK.mkdir()
    old = time.time() - 700
    os.utime(m.LOCK, (old, old))
    with m.Lock(wait=1):
        pass
    assert not m.LOCK.exists()


# ------------------------------------------------------------------ journal + compile


def test_journal_ingest_dedupes_and_compiles(m):
    journal(m, ["[all] Never pass GID=20", "[db-server] Pin every tag"], name="a.md")
    journal(m, ["[all] Never pass GID=20"], name="b.md")
    run_ingest(m)
    assert (m.COMPILED / "PLAYBOOK.md").read_text() == "- (2) Never pass GID=20\n"
    assert (m.COMPILED / "projects" / "db-server.md").read_text() == "- (1) Pin every tag\n"


def test_journal_files_are_ingested_once(m):
    journal(m, ["[all] once"])
    assert sum(1 for _, n in run_ingest(m) if n) == 1
    assert run_ingest(m) == []


def test_journal_write_never_appends(m):
    p1 = m.journal_write(["[all] a"], "t")
    p2 = m.journal_write(["[all] b"], "t")
    assert p1 != p2 and p1.read_text() == "[all] a\n" and p2.read_text() == "[all] b\n"
    assert m.journal_write([], "t") is None


def test_compile_is_atomic_and_removes_empty_projects(m):
    journal(m, ["[gone] temporary"])
    run_ingest(m)
    assert (m.COMPILED / "projects" / "gone.md").exists()
    with m.db() as c:
        c.execute("UPDATE lessons SET state='archived'")
        c.commit()
        m.compile_(c)
    assert not (m.COMPILED / "projects" / "gone.md").exists()
    assert not list(m.COMPILED.glob("**/*.tmp"))


def test_compile_caps_lines_and_sorts_by_score(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch, MEMORY_MAX_LINES="2")
    journal(m, ["[all] low"], name="a.md")
    journal(m, ["[all] high", "[all] mid"], name="b.md")
    journal(m, ["[all] high"], name="c.md")
    journal(m, ["[all] high", "[all] mid"], name="d.md")
    run_ingest(m)
    text = (m.COMPILED / "PLAYBOOK.md").read_text().splitlines()
    assert text == ["- (3) high", "- (2) mid"]


def test_git_commit_on_compile_when_repo_present(m):
    subprocess.run(["git", "init", "-q", str(m.ROOT)], check=True)
    subprocess.run(["git", "-C", str(m.ROOT), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(m.ROOT), "config", "user.name", "t"], check=True)
    journal(m, ["[all] committed"])
    run_ingest(m)
    log = subprocess.run(["git", "-C", str(m.ROOT), "log", "--oneline"], capture_output=True, text=True).stdout
    assert "compile" in log


# ------------------------------------------------------------------ search


def test_search_is_keyword_and_project_scoped(m):
    journal(m, ["[all] maxconn=4000 during the migration", "[charts] Chart uses log scale", "[other] maxconn unrelated"])
    run_ingest(m)
    with m.db() as c:
        assert [r["project"] for r in m.search(c, "maxconn", project="charts")] == ["all"]
        assert len(m.search(c, "maxconn")) == 2
        assert m.search(c, "") == []


def test_search_all_shows_superseded_but_not_merged(m):
    with m.db() as c:
        a, _ = m.upsert(c, "p", "alpha one")
        b, _ = m.upsert(c, "p", "alpha two")
        c.execute("UPDATE lessons SET state='superseded' WHERE id=?", (a,))
        c.execute("UPDATE lessons SET state='merged' WHERE id=?", (b,))
        c.commit()
        assert {r["id"] for r in m.search(c, "alpha", include_archived=True)} == {a}
        assert m.search(c, "alpha") == []


def test_hybrid_search_uses_embeddings_when_enabled(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch, MEMORY_EMBED="voyage")
    vec = {"cat": [1.0, 0.0], "dog": [0.0, 1.0], "feline": [0.9, 0.1]}
    monkeypatch.setattr(m, "embed", lambda ts: [m.array("f", vec.get(t, [0.5, 0.5])).tobytes() for t in ts])
    journal(m, ["[all] cat", "[all] dog"])
    run_ingest(m)
    with m.db() as c:
        assert c.execute("SELECT count(*) FROM lessons WHERE embedding IS NOT NULL").fetchone()[0] == 2
        assert m.search(c, "feline")[0]["text"] == "cat"
    assert m.cosine(m.array("f", [1, 0]).tobytes(), m.array("f", [1, 0]).tobytes()) == pytest.approx(1.0)
    assert m.cosine(b"", b"") == 0.0


# ------------------------------------------------------------------ reflect + reconcile (fake LLM)


def fake_llm(reflect_json, contra_json):
    def f(prompt, system="", max_tokens=0):
        return json.dumps(contra_json if "CANDIDATES:" in prompt else reflect_json)
    return f


def test_reflect_parses_and_defaults_project(m, monkeypatch):
    monkeypatch.setattr(m, "llm", fake_llm([{"project": "", "text": "a"}, {"text": "b"}, {"nope": 1}], {}))
    assert m.reflect("some text", "proj", set()) == [("proj", "a"), ("proj", "b")]
    assert m.reflect("   ", "proj", set()) == []


def test_parse_json_tolerates_prose_and_garbage(m):
    assert m.parse_json('Here you go: [{"a": 1}] thanks') == [{"a": 1}]
    assert m.parse_json("no json here") is None
    assert m.parse_json("") is None
    assert m.parse_json("[not, valid]") is None


def test_llm_none_mode_returns_none(m):
    assert m.llm("x") is None


def test_llm_cli_failure_is_handled(tmp_path, monkeypatch):
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "claude").write_text("#!/bin/sh\necho boom >&2\nexit 1\n")
    (fake / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    m = load(tmp_path / "r", monkeypatch, MEMORY_LLM="cli")
    assert m.llm("x") is None


def test_llm_cli_success_and_recursion_guard(tmp_path, monkeypatch):
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "claude").write_text('#!/bin/sh\n[ "$MEMORY_REFLECT" = 1 ] || exit 3\necho ok\n')
    (fake / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    m = load(tmp_path / "r", monkeypatch, MEMORY_LLM="cli")
    assert m.llm("x").strip() == "ok"


def test_contradiction_supersedes_older_and_keeps_it_searchable(m, monkeypatch):
    with m.db() as c:
        old, _ = m.upsert(c, "node", "maxconn=4000 during the migration")
        c.commit()
    monkeypatch.setattr(m, "llm", fake_llm([], {"same": [], "contradicts": [old]}))
    journal(m, ["[node] maxconn=1024 post-migration"])
    run_ingest(m)
    with m.db() as c:
        row = c.execute("SELECT state, superseded_by FROM lessons WHERE id=?", (old,)).fetchone()
        assert row["state"] == "superseded" and row["superseded_by"]
        assert [r["text"] for r in m.search(c, "maxconn")] == ["maxconn=1024 post-migration"]
        assert len(m.search(c, "maxconn", include_archived=True)) == 2
    assert "4000" not in (m.COMPILED / "projects" / "node.md").read_text()


def test_same_merges_votes_into_the_older_lesson(m, monkeypatch):
    with m.db() as c:
        old, _ = m.upsert(c, "p", "pin image tags")
        c.commit()
    monkeypatch.setattr(m, "llm", fake_llm([], {"same": [old], "contradicts": []}))
    journal(m, ["[p] always pin every image tag"])
    run_ingest(m)
    with m.db() as c:
        assert c.execute("SELECT votes FROM lessons WHERE id=?", (old,)).fetchone()[0] == 2
        assert c.execute("SELECT count(*) FROM lessons WHERE state='merged'").fetchone()[0] == 1
    assert (m.COMPILED / "projects" / "p.md").read_text() == "- (2) pin image tags\n"


def test_reconcile_ignores_ids_not_among_candidates(m, monkeypatch):
    with m.db() as c:
        old, _ = m.upsert(c, "p", "alpha")
        c.commit()
    monkeypatch.setattr(m, "llm", fake_llm([], {"same": ["bogus"], "contradicts": ["bogus"]}))
    journal(m, ["[p] alpha beta"])
    run_ingest(m)
    with m.db() as c:
        assert c.execute("SELECT count(*) FROM lessons WHERE state='active'").fetchone()[0] == 2


# ------------------------------------------------------------------ adapters


def transcript(path, turns):
    with open(path, "w") as f:
        for role, text in turns:
            content = text if role == "user" else [{"type": "text", "text": text}]
            f.write(json.dumps({"type": role, "message": {"role": role, "content": content}}) + "\n")
        f.write("not json\n")
        f.write(json.dumps({"type": "system", "message": {"content": "ignored"}}) + "\n")


def test_claude_code_transcript_is_parsed_incrementally(m, tmp_path):
    p = tmp_path / "t.jsonl"
    transcript(p, [("user", "hi"), ("assistant", "hello")])
    text, end = m.claude_code_turns(p)
    assert text == "USER: hi\n\nASSISTANT: hello"
    with open(p, "a") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "more"}}) + "\n")
    text2, end2 = m.claude_code_turns(p, end)
    assert text2 == "USER: more" and end2 > end


def test_ingest_transcript_stores_cursor(m, tmp_path, monkeypatch):
    p = tmp_path / "t.jsonl"
    transcript(p, [("user", "set maxconn"), ("assistant", "done")])
    monkeypatch.setattr(m, "llm", fake_llm([{"project": "node", "text": "maxconn=1024"}], {}))
    with m.db() as c:
        new = m.ingest_transcript(c, p, "node")
        assert new and new[0][1]
        cur = c.execute("SELECT cursor FROM sources WHERE key=?", (f"transcript:{p}",)).fetchone()[0]
        assert int(cur) == p.stat().st_size
        assert m.ingest_transcript(c, p, "node") == []  # nothing new after the cursor


def test_export_ingest_is_idempotent_per_updated_at(m, tmp_path, monkeypatch):
    exp = tmp_path / "conversations.json"
    conv = [{"uuid": "u1", "name": "Db Server!", "updated_at": "2026-09-13T10:00:00Z",
             "chat_messages": [{"sender": "human", "text": "migration done"}, {"sender": "assistant", "text": "ok"}]}]
    exp.write_text(json.dumps(conv))
    calls = []

    def f(prompt, system="", max_tokens=0):
        calls.append(prompt)
        return json.dumps([{"project": "db-server", "text": "maxconn=1024 post-migration"}])

    monkeypatch.setattr(m, "llm", f)
    with m.db() as c:
        assert len(m.ingest_export(c, exp)) == 1
        assert m.ingest_export(c, exp) == []
        conv[0]["updated_at"] = "2026-09-14T10:00:00Z"
        exp.write_text(json.dumps(conv))
        m.ingest_export(c, exp)
    assert len(calls) == 2
    assert "Default project for this conversation: db-server" in calls[0]


# ------------------------------------------------------------------ prune


def test_prune_archives_by_decay_and_harm(m):
    journal(m, ["[all] fresh", "[all] stale", "[all] harmful"])
    run_ingest(m)
    with m.db() as c:
        c.execute("UPDATE lessons SET last_seen='2020-01-01T00:00:00+00:00' WHERE text='stale'")
        c.execute("UPDATE lessons SET harmful=2 WHERE text='harmful'")
        c.commit()
        assert m.prune(c) == 2
        c.commit()
        m.compile_(c)
    assert (m.COMPILED / "PLAYBOOK.md").read_text() == "- (1) fresh\n"
    archive = list(m.ARCHIVE.glob("*.md"))[0].read_text()
    assert "stale" in archive and "harmful" in archive


def test_score_decays_with_age(m):
    now = time.time()
    row = {"votes": 4, "helpful": 0, "harmful": 0, "last_seen": m.NOW()}
    assert m.score(row, now) == pytest.approx(4.0, rel=1e-3)
    old = dict(row, last_seen="2000-01-01T00:00:00+00:00")
    assert m.score(old, now) < 0.01


# ------------------------------------------------------------------ commands + hooks


def hook_json(tmp_path, msg, transcript_path=None):
    j = {"session_id": "s", "cwd": "/tmp/x/chart-dashboard", "last_assistant_message": msg}
    if transcript_path:
        j["transcript_path"] = str(transcript_path)
    p = tmp_path / "hook.json"
    p.write_text(json.dumps(j))
    return p


def test_cmd_hook_journals_lessons_and_derives_project(m, tmp_path):
    p = hook_json(tmp_path, "Done.\n\nLESSONS:\n[chart-dashboard] log scale\n[all] gid rule\nnot a lesson\n")
    m.main.__globals__["sys"].argv = ["memory", "hook", "--role", "sub", "--input", str(p)]
    m.main()
    assert (m.COMPILED / "projects" / "chart-dashboard.md").read_text() == "- (1) log scale\n"
    assert (m.COMPILED / "PLAYBOOK.md").read_text() == "- (1) gid rule\n"
    assert len(list(m.JOURNAL.glob("**/*-sub.md"))) == 1


def test_cmd_hook_reflects_transcript_when_llm_available(m, tmp_path, monkeypatch):
    t = tmp_path / "t.jsonl"
    transcript(t, [("user", "x"), ("assistant", "y")])
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli"))
    monkeypatch.setattr(m, "llm", fake_llm([{"project": "all", "text": "reflected"}], {}))
    p = hook_json(tmp_path, "no block here", t)
    m.main.__globals__["sys"].argv = ["memory", "hook", "--input", str(p)]
    m.main()
    assert (m.COMPILED / "PLAYBOOK.md").read_text() == "- (1) reflected\n"


def test_cmd_hook_is_inert_inside_reflection(m, tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_REFLECT", "1")
    p = hook_json(tmp_path, "LESSONS:\n[all] should not land\n")
    m.main.__globals__["sys"].argv = ["memory", "hook", "--input", str(p)]
    m.main()
    assert not m.COMPILED.exists()


def test_parallel_hook_processes_do_not_lose_updates(m, tmp_path):
    p = hook_json(tmp_path, "LESSONS:\n[all] racey\n")
    env = {**os.environ, "MEMORY_ROOT": str(m.ROOT), "MEMORY_LLM": "none"}
    procs = [subprocess.Popen([sys.executable, str(BIN), "hook", "--role", "sub", "--input", str(p)], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(6)]
    assert all(pr.wait() == 0 for pr in procs)
    with m.db() as c:
        assert c.execute("SELECT votes FROM lessons").fetchone()[0] == 6
    assert (m.COMPILED / "PLAYBOOK.md").read_text() == "- (6) racey\n"
    assert not m.LOCK.exists()


def test_cli_ingest_search_remember_vote(m, capsys):
    argv = m.main.__globals__["sys"].argv
    m.main.__globals__["sys"].argv = ["memory", "remember", "manual fact", "--project", "p"]
    m.main()
    m.main.__globals__["sys"].argv = ["memory", "compile"]
    m.main()
    m.main.__globals__["sys"].argv = ["memory", "search", "manual", "--project", "p"]
    m.main()
    out = capsys.readouterr().out
    assert "[p] manual fact" in out
    lesson_id = out.split()[0]
    m.main.__globals__["sys"].argv = ["memory", "vote", lesson_id, "--harmful"]
    m.main()
    m.main.__globals__["sys"].argv = ["memory", "vote", lesson_id, "--harmful"]
    m.main()
    assert not (m.COMPILED / "projects" / "p.md").exists()  # harmful x2 archives
    m.main.__globals__["sys"].argv = ["memory", "ingest"]
    m.main()
    m.main.__globals__["sys"].argv = argv


def test_mcp_tools_are_registered(m, monkeypatch):
    pytest.importorskip("mcp")
    captured = {}

    class Args:
        transport = "stdio"
        port = 0

    def fake_run(self, *a, **k):
        captured["ran"] = True

    try:
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server
    monkeypatch.setattr(Server, "run", fake_run)
    with m.db() as c:
        m.upsert(c, "all", "an mcp lesson")
        c.commit()
    m.cmd_mcp(Args())
    assert captured["ran"]


def test_hook_scripts_pass_through_to_runner(m, tmp_path):
    """journal.sh and compile.sh must invoke MEMORY_RUNNER and return immediately."""
    log = tmp_path / "runner.log"
    runner = tmp_path / "runner.sh"
    runner.write_text(f'#!/bin/sh\necho "$@" >> {log}\ncat > /dev/null\n')
    runner.chmod(0o755)
    env = {**os.environ, "MEMORY_RUNNER": str(runner), "HOME": str(tmp_path)}
    (tmp_path / "memory").mkdir()
    subprocess.run(["bash", str(REPO / "hooks" / "journal.sh"), "sub"], input="{}", text=True, env=env, check=True, timeout=5)
    subprocess.run(["bash", str(REPO / "hooks" / "compile.sh")], env=env, check=True, timeout=5)
    time.sleep(0.5)
    text = log.read_text()
    assert "hook --role sub" in text and "ingest" in text


def test_sqlite_fts5_available():
    sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")


# ------------------------------------------------------------------ tools


def test_eval_recall_reports_hits_and_misses(m, tmp_path, capsys):
    journal(m, ["[all] Never pass GID=20", "[node] maxconn=1024 post-migration"])
    run_ingest(m)
    q = tmp_path / "q.jsonl"
    q.write_text(json.dumps({"query": "GID", "project": "all", "expect": ["GID=20"]}) + "\n"
                 + json.dumps({"query": "maxconn", "project": "node", "expect": ["4000"]}) + "\n")
    sys.path.insert(0, str(REPO / "tools"))
    import eval_recall
    assert eval_recall.main([str(q), "--min", "0.9"]) == 1
    out = capsys.readouterr().out
    assert "recall@8: 1/2" in out and "miss: maxconn" in out
    assert eval_recall.main([str(q), "--min", "0.5"]) == 0


def test_check_docs_passes_on_this_tree():
    r = subprocess.run([sys.executable, str(REPO / "tools" / "check_docs.py")], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------ learn adapters


def git_repo(path, name):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / "README.md").write_text(f"# {name}\nRun with --safe.\n")
    (path / "CLAUDE.md").write_text(f"- [{name}] never use --force\n\nProse about {name}.\n")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init: decide on --safe by default"], check=True)
    return path


def tracing_llm(calls):
    """Returns one lesson naming the label it was given, so each source can be traced."""
    def f(prompt, system="", max_tokens=0):
        calls.append(prompt)
        if "CANDIDATES:" in prompt:
            return '{"same": [], "contradicts": []}'
        found = [l for l in prompt.splitlines() if l.startswith("[") and l.endswith("]")]
        label = found[0].strip("[]") if found else "transcript"
        proj = prompt.split("Default project for this conversation: ", 1)[1].split("\n", 1)[0]
        return json.dumps([{"project": proj, "text": f"lesson from {label}"}])
    return f


def test_split_tagged_separates_lessons_from_prose(m):
    tagged, rest = m.split_tagged("- [p] one\n* [q] two\nplain line\n\n[bad slug!] x\n")
    assert tagged == [("p", "one"), ("q", "two")]
    assert rest == "plain line\n\n[bad slug!] x"
    assert m.split_tagged("[p] only\n") == ([("p", "only")], "")


def test_learn_repo_reads_commits_and_docs_incrementally(m, tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "alpha", "alpha")
    calls = []
    monkeypatch.setattr(m, "llm", tracing_llm(calls))
    with m.db() as c:
        new = m.learn_repo(c, repo)
        c.commit()
        texts = {r["text"] for r in c.execute("SELECT text FROM lessons")}
        assert "never use --force" in texts                       # tagged line, no LLM
        assert "lesson from git history of alpha" in texts
        assert "lesson from documentation of alpha" in texts
        assert sum(1 for _, n in new if n) == 3
        assert m.learn_repo(c, repo) == []                        # nothing changed
        (repo / "x").write_text("x")
        subprocess.run(["git", "-C", str(repo), "add", "x"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fix: rotate keys weekly"], check=True)
        before = len(calls)
        m.learn_repo(c, repo)
        assert len(calls) > before and "rotate keys weekly" in calls[before] and "init:" not in calls[before]
        (repo / "README.md").write_text("# alpha\nchanged\n")
        before = len(calls)
        m.learn_repo(c, repo)
        assert "changed" in calls[before] and "CLAUDE.md" not in calls[before]


def test_learn_repo_on_a_plain_folder_still_reads_docs(m, tmp_path, monkeypatch):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "README.md").write_text("no git here\n")
    monkeypatch.setattr(m, "llm", tracing_llm([]))
    with m.db() as c:
        assert sum(1 for _, n in m.learn_repo(c, d) if n) == 1
        assert c.execute("SELECT project FROM lessons").fetchone()[0] == "plain"


def test_learn_notes_ingests_tagged_lines_and_reflects_prose(m, tmp_path, monkeypatch):
    notes = tmp_path / "notes"
    (notes / "sub").mkdir(parents=True)
    (notes / "a.md").write_text("[all] Prefer blunt answers\n\nWe decided the node runs on the spare host.\n")
    (notes / "sub" / "b.txt").write_text("[node] maxconn=1024 post-migration\n")
    (notes / "c.md").write_text("[only] tagged\n")
    calls = []
    monkeypatch.setattr(m, "llm", tracing_llm(calls))
    with m.db() as c:
        new = m.learn_notes(c, notes)
        assert sum(1 for _, n in new if n) == 4
        assert len(calls) == 1 and "a.md" in calls[0] and "c.md" not in calls[0]
        assert m.learn_notes(c, notes) == []
        assert c.execute("SELECT count(*) FROM lessons WHERE project='notes'").fetchone()[0] == 1


def test_learn_transcripts_backfills_claude_code_dirs(m, tmp_path, monkeypatch):
    root = tmp_path / "projects"
    d = root / "-Users-me-GitHub-alpha"
    d.mkdir(parents=True)
    transcript(d / "s1.jsonl", [("user", "x"), ("assistant", "y")])
    transcript(d / "s2.jsonl", [("user", "p"), ("assistant", "q")])
    (root / "-Users-me-other-").mkdir()
    monkeypatch.setattr(m, "llm", tracing_llm([]))
    assert [s for s, _ in m.claude_code_project_dirs(root)] == ["alpha", "other"]
    with m.db() as c:
        new = m.learn_transcripts(c, root)
        assert sum(1 for _, n in new if n) == 1           # both sessions yield the same traced lesson
        assert c.execute("SELECT votes FROM lessons").fetchone()[0] == 2
        assert c.execute("SELECT count(*) FROM sources WHERE key LIKE 'transcript:%'").fetchone()[0] == 2


def test_learn_all_and_cli(m, tmp_path, monkeypatch, capsys):
    repos = tmp_path / "GitHub"
    git_repo(repos / "alpha", "alpha")
    (repos / "notagit").mkdir()
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "conversations.json").write_text(json.dumps([{"uuid": "u", "name": "Beta", "updated_at": "1",
        "chat_messages": [{"sender": "human", "content": [{"type": "text", "text": "hi"}]}, {"sender": "assistant", "text": "yo"}]}]))
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "n.md").write_text("[all] from notes\n")
    monkeypatch.setattr(m, "llm", tracing_llm([]))
    monkeypatch.setattr(m.Path, "home", classmethod(lambda cls: tmp_path))
    m.main.__globals__["sys"].argv = ["memory", "learn", "--all", "--repos", str(repos), "--notes", str(notes), "--exports", str(exports)]
    m.main()
    with m.db() as c:
        projects = {r[0] for r in c.execute("SELECT DISTINCT project FROM lessons")}
    assert projects == {"alpha", "beta", "all"}
    assert (m.COMPILED / "PLAYBOOK.md").read_text() == "- (1) from notes\n"
    m.main.__globals__["sys"].argv = ["memory", "learn", "--repo", str(repos / "alpha"), "--transcripts"]
    m.main()
    err = capsys.readouterr().err
    assert "learn: +0 new" in err


def test_export_message_text_handles_both_shapes(m):
    assert m.export_msg_text({"text": "a"}) == "a"
    assert m.export_msg_text({"content": [{"type": "text", "text": "b"}, {"type": "tool_use"}]}) == "b"
    assert m.export_msg_text({}) == ""


def test_vector_rank_stdlib_and_numpy_agree(m, monkeypatch):
    rows = [{"id": i, "embedding": m.array("f", v).tobytes()} for i, v in enumerate([[1, 0, 0], [0, 1, 0], [0.9, 0.1, 0]])]
    q = m.array("f", [1, 0, 0]).tobytes()
    fast = [r["id"] for r in m.vector_rank(q, rows, top=2)]
    monkeypatch.setitem(sys.modules, "numpy", None)      # force the stdlib path
    slow = [r["id"] for r in m.vector_rank(q, rows, top=2)]
    assert fast == slow == [0, 2]
    assert m.cosine(m.array("f", [1, 0]).tobytes(), m.array("f", [1, 0, 0]).tobytes()) == 0.0
