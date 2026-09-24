"""Unit tests for bin/memory.

Every test runs against a throwaway MEMORY_ROOT. The LLM is replaced by a fake that returns
canned JSON, so the Reflector and the contradiction check are exercised without a network.
The one thing these tests cannot do is call Claude; `llm()` itself is covered by the
`MEMORY_LLM=none` path and by the fake.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import runpy
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import types
import urllib.error

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


def test_a_live_holder_keeps_its_lock_fresh(m, monkeypatch):
    """A `learn` holds the lock for hours. Its heartbeat keeps the lock from ever looking like a crashed holder's,
    so a Stop hook that arrives after ten minutes waits and gives up instead of breaking in."""
    monkeypatch.setattr(m, "LOCK_BEAT", 0.02)
    old = time.time() - 700
    with m.Lock():
        os.utime(m.LOCK, (old, old))          # as if the holder had worked for 700 s without a beat
        time.sleep(0.2)
        assert time.time() - m.LOCK.stat().st_mtime < 5
        with pytest.raises(m.LockBusy), m.Lock(wait=0.3):
            pass
        assert m.LOCK.exists()
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
    log = subprocess.run(["git", "-C", str(m.ROOT), "log", "--oneline"], capture_output=True, text=True, check=True).stdout
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
    (fake / "claude").write_text('#!/bin/sh\n[ "$MEMORY_REFLECT" = 1 ] || exit 3\n'
                                 'case " $* " in *" --no-session-persistence "*) ;; *) exit 4 ;; esac\necho ok\n')
    (fake / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    m = load(tmp_path / "r", monkeypatch, MEMORY_LLM="cli")
    assert m.llm("x").strip() == "ok"


def test_backfill_skips_transcripts_the_reflector_left_behind(m, tmp_path, monkeypatch):
    """Every `claude -p` call used to leave a transcript whose first user turn is the Reflector's instructions and a
    window of another transcript. A backfill reads only real sessions, and skips a folder holding none."""
    root = tmp_path / "projects"
    real = root / "-home-me-GitHub-p"
    real.mkdir(parents=True)
    transcript(real / "s.jsonl", [("user", "pin the image tag"), ("assistant", "done")], cwd="/home/me/GitHub/p")
    transcript(real / "r.jsonl", [("user", m.REFLECT_SYS + "\n\nUSER: pin the image tag"), ("assistant", "[]")], cwd="/tmp/tmpa")
    left = root / "-private-var-folders-x-T-tmpb"
    left.mkdir()
    transcript(left / "c.jsonl", [("user", m.CONTRA_SYS + "\n\nNEW: x"), ("assistant", "{}")], cwd="/private/var/folders/x/T/tmpb")
    calls = []
    monkeypatch.setattr(m, "llm", tracing_llm(calls))
    with m.db() as c:
        m.learn_transcripts(c, root)
        keys = {r[0] for r in c.execute("SELECT key FROM sources")}
    assert len(calls) == 1 and "pin the image tag" in calls[0] and "durable, reusable lessons" not in calls[0]
    assert keys == {f"transcript:{real / 's.jsonl'}"}


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
        m.upsert(c, "p", "alpha")
        c.commit()
    monkeypatch.setattr(m, "llm", fake_llm([], {"same": ["bogus"], "contradicts": ["bogus"]}))
    journal(m, ["[p] alpha beta"])
    run_ingest(m)
    with m.db() as c:
        assert c.execute("SELECT count(*) FROM lessons WHERE state='active'").fetchone()[0] == 2


# ------------------------------------------------------------------ adapters


def transcript(path, turns, cwd=None):
    with open(path, "w") as f:
        for role, text in turns:
            content = text if role == "user" else [{"type": "text", "text": text}]
            entry = {"type": role, "message": {"role": role, "content": content}}
            f.write(json.dumps({**entry, "cwd": cwd} if cwd else entry) + "\n")
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


def test_cursor_transcript_lines_are_read_like_claude_codes(m, tmp_path):
    """Cursor runs the same hooks and writes `role` where Claude Code writes `type`. Tool calls and its
    end-of-turn marker are not turns."""
    p = tmp_path / "cursor.jsonl"
    lines = [{"role": "user", "message": {"content": [{"type": "text", "text": "add a retry"}]}},
             {"role": "assistant", "message": {"content": [{"type": "text", "text": "done"}, {"type": "tool_use", "name": "Edit"}]}},
             {"type": "turn_ended", "status": "success"}]
    p.write_text("".join(json.dumps(x) + "\n" for x in lines))
    text, end = m.claude_code_turns(p)
    assert text == "USER: add a retry\n\nASSISTANT: done" and end == p.stat().st_size


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
    archive = next(m.ARCHIVE.glob("*.md")).read_text()
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


def test_check_docs_passes_on_this_tree(monkeypatch, capsys):
    """In-process, so tools/check_docs.py is measured like the tool itself."""
    monkeypatch.setattr(sys, "argv", ["check_docs.py"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(REPO / "tools" / "check_docs.py"), run_name="__main__")
    assert e.value.code == 0, capsys.readouterr().out


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
        found = [ln for ln in prompt.splitlines() if ln.startswith("[") and ln.endswith("]")]
        label = found[0].strip("[]") if found else "transcript"
        proj = prompt.split("Default project for this conversation: ", 1)[1].split("\n", 1)[0]
        return json.dumps([{"project": proj, "text": f"lesson from {label}"}])
    return f


def test_split_tagged_separates_lessons_from_prose(m):
    tagged, rest = m.split_tagged("- [p] one\n* [q] two\nplain line\n\n[bad slug!] x\n")
    assert tagged == [("p", "one"), ("q", "two")]
    assert rest == "plain line\n\n[bad slug!] x"
    assert m.split_tagged("[p] only\n") == ([("p", "only")], "")


def test_a_ticked_checkbox_is_not_a_project_tag(m):
    """A release checklist's `- [x] done` once filed its items under a project called `x`."""
    tagged, rest = m.split_tagged("- [x] shipped the release\n* [X] tagged it\n- [ ] still to do\n- [all] a real lesson\n")
    assert tagged == [("all", "a real lesson")]
    assert rest == "- [x] shipped the release\n* [X] tagged it\n- [ ] still to do"


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


def test_learn_repo_refuses_a_folder_that_does_not_exist(m, tmp_path):
    """A mistyped --repo used to exit 0 having read nothing, which passes for success. It fails before the lock."""
    with pytest.raises(SystemExit, match=r"no such folder: .*typo"):
        m.cmd_learn(types.SimpleNamespace(repo=[str(tmp_path / "typo")]))
    assert not m.LOCK.exists()


def test_learn_max_calls_stops_cleanly_and_the_next_run_carries_on(m, tmp_path, monkeypatch, capsys):
    """--max-calls spreads a long backfill out. A reflection costs one call, plus one per lesson it returns for the
    contradiction check to come; once the budget is spent the run stops like a usage limit, and the next carries on."""
    repo = git_repo(tmp_path / "alpha", "alpha")
    calls = []
    monkeypatch.setattr(m, "llm", tracing_llm(calls))
    monkeypatch.setattr(sys, "argv", ["memory", "learn", "--repo", str(repo), "--max-calls", "1"])
    with pytest.raises(SystemExit) as e:
        m.main()
    assert e.value.code == 1 and "its --max-calls budget of 1 is spent" in capsys.readouterr().err
    assert [p for p in calls if "<conversation>" in p and "[git history of alpha]" in p]
    assert not [p for p in calls if "[documentation of alpha]" in p]
    monkeypatch.setattr(sys, "argv", ["memory", "learn", "--repo", str(repo)])
    m.main()
    reflections = [p for p in calls if "<conversation>" in p]
    assert sum("[git history of alpha]" in p for p in reflections) == 1
    assert sum("[documentation of alpha]" in p for p in reflections) == 1
    with m.db() as c:
        texts = {r["text"] for r in c.execute("SELECT text FROM lessons")}
    assert {"never use --force", "lesson from git history of alpha", "lesson from documentation of alpha"} <= texts


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
    """The slug comes from the cwd recorded in the transcript. The folder name cannot be decoded:
    three hyphenated repositories ending in -model once all became `model`."""
    root = tmp_path / "projects"
    sessions = {"-home-me-GitHub-flood-risk-model": "/home/me/GitHub/flood-risk-model",
                "-home-me-GitHub-wind-risk-model": "/home/me/GitHub/wind-risk-model",
                "-home-me-GitHub-doc-ingestion--claude-worktrees-fervent-fermat-15cf91":
                    "/home/me/GitHub/doc-ingestion/.claude/worktrees/fervent-fermat-15cf91"}
    for enc, cwd in sessions.items():
        (root / enc).mkdir(parents=True)
        transcript(root / enc / "s1.jsonl", [("user", "x"), ("assistant", "y")], cwd=cwd)
    transcript(root / "-home-me-GitHub-flood-risk-model" / "s2.jsonl", [("user", "p"), ("assistant", "q")],
               cwd="/home/me/GitHub/flood-risk-model")
    (root / "-home-me-other-").mkdir()          # no transcript, so no recorded cwd: the folder name stands in
    monkeypatch.setattr(m, "llm", tracing_llm([]))
    assert [s for s, _ in m.claude_code_project_dirs(root)] == \
        ["doc-ingestion", "flood-risk-model", "wind-risk-model", "other"]
    with m.db() as c:
        m.learn_transcripts(c, root)
        assert {r[0]: r[1] for r in c.execute("SELECT project, votes FROM lessons")} == \
            {"flood-risk-model": 2, "wind-risk-model": 1, "doc-ingestion": 1}
        assert c.execute("SELECT count(*) FROM sources WHERE key LIKE 'transcript:%'").fetchone()[0] == 4


def test_hook_files_a_worktree_session_under_its_repository(m, tmp_path, monkeypatch):
    """The Stop hook and the backfill share project_of(), so both name a session the same way."""
    t = tmp_path / "t.jsonl"
    transcript(t, [("user", "x"), ("assistant", "y")])
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli"))
    monkeypatch.setattr(m, "llm", fake_llm([{"project": "", "text": "reflected"}], {}))
    p = tmp_path / "hook.json"
    p.write_text(json.dumps({"cwd": "/home/me/GitHub/Doc-Ingestion/.claude/worktrees/fervent-fermat-15cf91",
                             "transcript_path": str(t), "last_assistant_message": ""}))
    m.main.__globals__["sys"].argv = ["memory", "hook", "--input", str(p)]
    m.main()
    assert (m.COMPILED / "projects" / "doc-ingestion.md").read_text() == "- (1) reflected\n"
    assert m.project_of("/home/me/GitHub/flood-risk-model") == "flood-risk-model"
    assert m.project_of("/home/me/GitHub/doc-ingestion/.claude/worktrees/x/src") == "doc-ingestion"


def test_backfill_reads_every_window_and_a_hook_two_oldest_first(m, tmp_path, monkeypatch):
    """learn --transcripts reads a long session whole, in windows. A Stop hook reads at most two windows from its
    cursor, oldest first, and moves the cursor only past them, so a session that outran its stops while the lock
    was busy is caught up by the next stops, never skipped."""
    monkeypatch.setattr(m, "CFG", dict(m.CFG, transcript_chars=200))
    turns = [("user" if i % 2 == 0 else "assistant", f"marker{i:03d} " + "x" * 40) for i in range(40)]
    turns.append(("user", "y" * 450))                   # one turn longer than a window: cut, not dropped
    d = tmp_path / "projects" / "-home-me-GitHub-p"
    d.mkdir(parents=True)
    transcript(d / "s.jsonl", turns, cwd="/home/me/GitHub/p")
    shutil.copy(d / "s.jsonl", tmp_path / "hook.jsonl")
    calls = []
    monkeypatch.setattr(m, "llm", tracing_llm(calls))
    with m.db() as c:
        m.learn_transcripts(c, tmp_path / "projects")
        sent = "".join(p.split("<conversation>\n", 1)[1] for p in calls)
        assert all(f"marker{i:03d}" in sent for i in range(40)) and sent.count("y") == 450
        assert len(calls) >= 12
        calls.clear()
        hook, key = tmp_path / "hook.jsonl", f"transcript:{tmp_path / 'hook.jsonl'}"
        m.ingest_transcript(c, hook, "p")
        assert len(calls) == 2 and "marker000" in calls[0]             # oldest first, two windows
        assert 0 < int(m.cursor(c, key)) < hook.stat().st_size         # only past what was read
        for _ in range(30):                                            # the next stops catch up
            if int(m.cursor(c, key)) == hook.stat().st_size:
                break
            m.ingest_transcript(c, hook, "p")
        assert int(m.cursor(c, key)) == hook.stat().st_size
    sent = [p.split("<conversation>\n", 1)[1] for p in calls]
    assert all(sum(f"marker{i:03d}" in s for s in sent) == 1 for i in range(40)) and "".join(sent).count("y") == 450


def test_reflect_batches_never_cut_the_head_of_a_window(m, monkeypatch):
    """Headers and the label count against the window, so the Reflector's tail cut drops nothing."""
    monkeypatch.setattr(m, "CFG", dict(m.CFG, transcript_chars=300))
    calls = []
    monkeypatch.setattr(m, "llm", tracing_llm(calls))
    with m.db() as c:
        m.reflect_batches(c, [(f"commit c{i:03d}", f"fix {i}") for i in range(100)], "p", "git history of p")
    sent = "".join(calls)
    assert all(f"### commit c{i:03d}\nfix {i}\n" in sent for i in range(100))


def test_llm_uses_the_sdk_when_an_api_key_is_present(tmp_path, monkeypatch):
    """With a key, the Docker image and a native install with `anthropic` both reflect through the SDK."""
    sent = {}

    class Messages:
        def create(self, **kw):
            sent.update(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="[]"),
                                                  types.SimpleNamespace(type="thinking")])

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: types.SimpleNamespace(messages=Messages())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    m = load(tmp_path / "r", monkeypatch, MEMORY_LLM="auto")
    assert m.llm("hello", "sys", 10) == "[]"
    assert (sent["model"], sent["system"], sent["max_tokens"]) == (m.CFG["model"], "sys", 10)
    assert sent["messages"] == [{"role": "user", "content": "hello"}]
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "claude").write_text("#!/bin/sh\necho cli\n")
    (fakebin / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fakebin}:{os.environ['PATH']}")
    monkeypatch.setitem(sys.modules, "anthropic", None)  # a key but no package: native without `anthropic`
    assert m.llm("x").strip() == "cli"


def test_hook_runner_is_native_without_an_api_key_and_docker_with_one(tmp_path):
    """No key in the checkout's .env: bin/memory natively, through `claude -p`. A real key: the container."""
    repo = tmp_path / "repo"
    (repo / "hooks").mkdir(parents=True)
    for f in ("compile.sh", "runner.sh"):
        shutil.copy(REPO / "hooks" / f, repo / "hooks" / f)
    log = tmp_path / "calls.log"
    (repo / ".venv" / "bin").mkdir(parents=True)
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for exe in (repo / ".venv" / "bin" / "python3", fakebin / "docker"):
        exe.write_text(f'#!/bin/sh\necho "$(basename "$0") $*" >> {log}\n')
        exe.chmod(0o755)
    (tmp_path / "home" / "memory").mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ("MEMORY_RUNNER", "MEMORY_REFLECT")}
    env.update(HOME=str(tmp_path / "home"), PATH=f"{fakebin}:{os.environ['PATH']}")

    def runner():
        log.write_text("")
        subprocess.run(["bash", str(repo / "hooks" / "compile.sh")], env=env, check=True, timeout=5)
        return log.read_text()

    assert runner() == f"python3 {repo}/bin/memory ingest --wait 2\n"
    (repo / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-...\n")   # the .env.example placeholder is not a key
    assert runner() == f"python3 {repo}/bin/memory ingest --wait 2\n"
    (repo / ".env").write_text("MEMORY_EMBED=none\nANTHROPIC_API_KEY=sk-ant-api03-abc\n")
    assert runner() == "docker exec -i memory python3 /app/memory ingest --wait 2\n"


def test_container_home_is_the_host_home():
    """`learn --all` looks under Path.home(); in the container that must be the mounted host path,
    and git's identity must not live in a HOME that is no longer /root."""
    assert "- HOME=${HOME}" in (REPO / "docker-compose.yml").read_text()
    dockerfile = (REPO / "Dockerfile").read_text()
    assert "git config --global" not in dockerfile and "git config --system user.email" in dockerfile


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


def test_an_export_message_of_an_unknown_shape_is_empty_text(m):
    """An export is written by another program and can carry nulls. One odd message must read as no text: raising
    here would abort the ingest and roll back every conversation already read."""
    assert m.export_msg_text({"text": None, "content": None}) == ""
    assert m.export_msg_text({"content": {"text": "not a list"}}) == ""
    assert m.export_msg_text({"content": [{"type": "text", "text": None}, {"type": "text", "text": "kept"}]}) == "kept"


def test_vector_rank_stdlib_and_numpy_agree(m, monkeypatch):
    rows = [{"id": i, "embedding": m.array("f", v).tobytes()} for i, v in enumerate([[1, 0, 0], [0, 1, 0], [0.9, 0.1, 0]])]
    q = m.array("f", [1, 0, 0]).tobytes()
    fast = [r["id"] for r in m.vector_rank(q, rows, top=2)]
    monkeypatch.setitem(sys.modules, "numpy", None)      # force the stdlib path
    slow = [r["id"] for r in m.vector_rank(q, rows, top=2)]
    assert fast == slow == [0, 2]
    assert m.cosine(m.array("f", [1, 0]).tobytes(), m.array("f", [1, 0, 0]).tobytes()) == 0.0


# ------------------------------------------------------------------ Reflector failures


def failing_llm(calls, answered):
    """tracing_llm for the first `answered` calls, then no answer at all, as under a usage limit."""
    trace = tracing_llm(calls)
    return lambda prompt, system="", max_tokens=0: trace(prompt) if len(calls) < answered else None


def test_backfill_stops_at_a_failed_window_and_the_next_run_resumes_there(m, tmp_path, monkeypatch):
    """Windows reflected before the failure keep their lessons and move the cursor; the rest is offered
    again on the next run, and no turn is sent twice."""
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli", transcript_chars=200))
    d = tmp_path / "projects" / "-home-me-GitHub-p"
    d.mkdir(parents=True)
    transcript(d / "s.jsonl", [("user" if i % 2 == 0 else "assistant", f"marker{i:03d} " + "x" * 40) for i in range(40)],
               cwd="/home/me/GitHub/p")
    calls = []
    monkeypatch.setattr(m, "llm", failing_llm(calls, 3))
    with m.db() as c:
        with pytest.raises(m.ReflectorFailed) as e:
            m.learn_transcripts(c, tmp_path / "projects")
        assert len(calls) == 3 and len(e.value.new) == 3
        assert 0 < int(c.execute("SELECT cursor FROM sources").fetchone()[0]) < (d / "s.jsonl").stat().st_size
        monkeypatch.setattr(m, "llm", tracing_llm(calls))
        m.learn_transcripts(c, tmp_path / "projects")
    sent = [p.split("<conversation>\n", 1)[1] for p in calls]
    assert all(sum(f"marker{i:03d}" in s for s in sent) == 1 for i in range(40))


def test_learn_stops_on_a_failed_reflector_keeps_its_progress_and_resumes(m, tmp_path, monkeypatch, capsys):
    """Commits reflected before the failure stay; a doc whose prose was not reflected keeps its tagged
    line, counted once, and gets its prose on the rerun."""
    repo = git_repo(tmp_path / "alpha", "alpha")
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli"))
    calls = []
    monkeypatch.setattr(m, "llm", failing_llm(calls, 1))          # the commits are answered, the docs are not
    m.main.__globals__["sys"].argv = ["memory", "learn", "--repo", str(repo)]
    with pytest.raises(SystemExit) as e:
        m.main()
    assert e.value.code == 1 and "stopped early" in capsys.readouterr().err   # 1: the run did read something
    assert "lesson from git history of alpha" in (m.COMPILED / "projects" / "alpha.md").read_text()
    monkeypatch.setattr(m, "llm", tracing_llm(calls))
    m.main()
    with m.db() as c:
        votes = {r["text"]: r["votes"] for r in c.execute("SELECT text, votes FROM lessons")}
    assert votes["never use --force"] == 1 and "lesson from documentation of alpha" in votes
    assert sum("[git history of alpha]" in p for p in calls) == 1   # the commit window was not reflected again


def test_commit_cursor_after_a_failure_is_the_last_reflected_commit(m, tmp_path, monkeypatch):
    """Commits are chunked whole, blank lines in the body included, so the cursor is always a real commit."""
    repo = git_repo(tmp_path / "alpha", "alpha")
    git = ["git", "-C", str(repo), "commit", "-q", "--allow-empty"]
    subprocess.run([*git, "-m", "second: subject", "-m", "body paragraph one", "-m", "body paragraph two"], check=True)
    subprocess.run([*git, "-m", "third"], check=True)
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli", transcript_chars=60))   # one commit per window
    calls = []
    monkeypatch.setattr(m, "llm", failing_llm(calls, 2))
    with m.db() as c:
        with pytest.raises(m.ReflectorFailed):
            m.learn_repo(c, repo)
        cur = m.cursor(c, f"repo:{repo.resolve()}:commits")
    second = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD~1"], capture_output=True, text=True, check=True).stdout.strip()
    assert cur == second and "body paragraph two" in calls[1]


def test_llm_answers_none_on_sdk_errors_cli_errors_and_timeouts(tmp_path, monkeypatch):
    """Every way a call can fail comes back as None, which reflect() turns into ReflectorFailed; none
    raises through a whole run. `claude -p` can report an error with exit status 0, so its JSON is read."""
    class Messages:
        def create(self, **kw):
            raise RuntimeError("529 overloaded")

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: types.SimpleNamespace(messages=Messages())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    m = load(tmp_path / "r", monkeypatch, MEMORY_LLM="sdk")
    assert m.llm("x") is None
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    claude = fakebin / "claude"
    claude.write_text("#!/bin/sh\necho '{\"type\": \"result\", \"subtype\": \"success\", \"is_error\": true, "
                      "\"result\": \"Claude AI usage limit reached\"}'\n")
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fakebin}:{os.environ['PATH']}")
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="auto"))
    assert m.llm("x") is None                                    # the SDK failed, then the CLI said is_error
    with pytest.raises(m.ReflectorFailed):
        m.reflect("some text", "p", set())
    claude.write_text("#!/bin/sh\necho '{\"type\": \"result\", \"subtype\": \"success\", \"is_error\": false, \"result\": \"[]\"}'\n")
    assert m.llm("x") == "[]"

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("claude", 180)

    monkeypatch.setattr(m.subprocess, "run", timeout)
    assert m.llm("x") is None


def test_hook_still_journals_and_compiles_when_the_reflector_fails(m, tmp_path, monkeypatch):
    """A failed reflection must not cost the LESSONS block; the transcript is left for the next stop."""
    t = tmp_path / "t.jsonl"
    transcript(t, [("user", "x"), ("assistant", "y")])
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli"))
    monkeypatch.setattr(m, "llm", lambda *a, **k: None)
    p = hook_json(tmp_path, "LESSONS:\n[all] kept anyway\n", t)
    m.main.__globals__["sys"].argv = ["memory", "hook", "--input", str(p)]
    m.main()
    assert (m.COMPILED / "PLAYBOOK.md").read_text() == "- (1) kept anyway\n"
    with m.db() as c:
        assert c.execute("SELECT count(*) FROM sources WHERE key LIKE 'transcript:%'").fetchone()[0] == 0


def test_a_half_written_last_line_is_left_for_the_next_read(m, tmp_path):
    """Claude Code may still be writing the last line; the cursor must not move past it."""
    p = tmp_path / "t.jsonl"
    transcript(p, [("user", "hi")])
    whole = p.stat().st_size
    with open(p, "a") as f:
        f.write('{"type": "assistant", "message": {"content": "hal')
    assert m.claude_code_turns(p) == ("USER: hi", whole)
    with open(p, "a") as f:
        f.write('f"}}\n')
    assert m.claude_code_turns(p, whole) == ("ASSISTANT: half", p.stat().st_size)


# ------------------------------------------------------------------ the lock under a long learn


def test_lock_gives_up_with_lock_busy_and_tolerates_a_vanished_lock(m):
    """LockBusy is a SystemExit, so the CLI still exits with its message; leaving a lock someone removed is fine."""
    m.ROOT.mkdir(parents=True, exist_ok=True)
    m.LOCK.mkdir()
    with pytest.raises(m.LockBusy, match=r"held for all of 0\.2 s"), m.Lock(wait=0.2):
        pass
    assert issubclass(m.LockBusy, SystemExit)
    m.LOCK.rmdir()
    with m.Lock():
        shutil.rmtree(m.LOCK)        # someone removed it under us; releasing must still be quiet
    assert not m.LOCK.exists()


def test_ingest_wait_bounds_how_long_session_start_can_block(m):
    """A long `learn` holds the lock; the SessionStart hook's `ingest --wait 2` gives up rather than hold the session."""
    m.ROOT.mkdir(parents=True, exist_ok=True)
    m.LOCK.mkdir()
    m.main.__globals__["sys"].argv = ["memory", "ingest", "--wait", "0.2"]
    started = time.time()
    with pytest.raises(m.LockBusy):
        m.main()
    assert time.time() - started < 2


# ------------------------------------------------------------------ MCP layer, against a stand-in mcp package


def fake_mcp(monkeypatch, v2):
    """One server class standing in for mcp 2.x's MCPServer or 1.x's FastMCP; it records its tools and its run()."""
    class Server:
        def __init__(self, *args, **kwargs):
            self.args, self.kwargs, self.tools, self.runs = args, kwargs, {}, []
            Server.last = self

        def tool(self):
            def register(fn):
                self.tools[fn.__name__] = fn
                return fn
            return register

        def run(self, **kwargs):
            self.runs.append(kwargs)

    mod = types.ModuleType("mcp_stand_in")
    mod.MCPServer = mod.FastMCP = Server
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", mod if v2 else None)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", mod)
    return Server


def test_mcp_tools_answer_on_both_mcp_versions_and_transports(m, monkeypatch):
    """mcp 2.x takes host and port at run(), 1.x at construction; recall, remember and feedback work through either."""
    for v2, transport in ((True, "http"), (False, "http"), (True, "stdio")):
        srv_class = fake_mcp(monkeypatch, v2)
        m.cmd_mcp(types.SimpleNamespace(transport=transport, port=9999))
        srv = srv_class.last
        if transport == "stdio":
            assert srv.runs == [{"transport": "stdio"}]
        elif v2:
            assert srv.runs == [{"transport": "streamable-http", "host": "0.0.0.0", "port": 9999}] and srv.kwargs == {}
        else:
            assert srv.runs == [{"transport": "streamable-http"}] and srv.kwargs == {"host": "0.0.0.0", "port": 9999}
    tools = srv.tools
    assert tools["recall"]("anything") == "no matches"
    assert tools["remember"]("mcp fact", "p") == "saved to p"
    hit = tools["recall"]("mcp", "p")
    assert "[p] mcp fact" in hit
    assert tools["feedback"](hit.split()[0], False) == "ok"
    assert tools["feedback"]("nosuchid") == "no lesson has id nosuchid"     # never "ok" for a lesson that is not there
    assert tools["remember"]("no slug", "my project").startswith("not saved: ")
    with m.db() as c:
        assert c.execute("SELECT harmful FROM lessons").fetchone()[0] == 1


def test_mcp_tools_answer_busy_while_a_learn_holds_the_lock(m, monkeypatch):
    """A tool must not stop the server when a long `learn` holds the lock; a remembered lesson waits in the journal."""
    srv_class = fake_mcp(monkeypatch, True)
    m.cmd_mcp(types.SimpleNamespace(transport="stdio", port=0))
    tools = srv_class.last.tools
    monkeypatch.setattr(m, "LOCK_WAIT", 0.1)
    m.ROOT.mkdir(parents=True, exist_ok=True)
    m.LOCK.mkdir()
    assert "when the running learn ends" in tools["remember"]("kept for later", "p")
    assert tools["feedback"]("abc", True).startswith("busy")
    m.LOCK.rmdir()
    run_ingest(m)
    assert (m.COMPILED / "projects" / "p.md").read_text() == "- (1) kept for later\n"


def test_mcp_needs_the_mcp_package(m, monkeypatch):
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", None)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", None)
    with pytest.raises(SystemExit, match="pip install mcp"):
        m.cmd_mcp(types.SimpleNamespace(transport="stdio", port=0))


# ------------------------------------------------------------------ Reflector, embeddings and search edges


def test_llm_edges_sdk_without_its_package_json_that_is_not_the_result_and_no_reflector(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setitem(sys.modules, "anthropic", None)
    m = load(tmp_path / "r", monkeypatch, MEMORY_LLM="sdk")
    with pytest.raises(SystemExit, match="pip install anthropic"):
        m.llm("x")
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "claude").write_text("#!/bin/sh\necho '[1, 2]'\n")
    (fakebin / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fakebin}:/usr/bin:/bin")
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli"))
    assert m.llm("x").strip() == "[1, 2]"                  # JSON, but not the CLI's result object: it is the answer
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="auto"))
    assert m.llm("x") is None
    assert "no Reflector" in capsys.readouterr().err


def test_reflect_is_a_no_op_when_the_llm_is_off(m):
    """MEMORY_LLM=none is keyword-only by choice: no lessons, and not a failure."""
    assert m.reflect("some text", "p", set()) == []


def test_embed_batches_both_providers_and_never_fails_a_run(tmp_path, monkeypatch, capsys):
    """Voyage and OpenAI in batches of 64; no key, a network error, or a short answer all mean "embed later"."""
    calls = []

    def answer(req, timeout):
        body = json.loads(req.data)
        calls.append((req.full_url, req.headers["Authorization"], body["model"], len(body["input"])))
        return io.BytesIO(json.dumps({"data": [{"embedding": [1.0, 0.0]} for _ in body["input"]]}).encode())

    m = load(tmp_path, monkeypatch, MEMORY_EMBED="voyage", VOYAGE_API_KEY="pa-test")
    monkeypatch.setattr(m.urllib.request, "urlopen", answer)
    assert len(m.embed([f"t{i}" for i in range(70)])) == 70
    assert [c[3] for c in calls] == [64, 6]
    assert calls[0][:3] == ("https://api.voyageai.com/v1/embeddings", "Bearer pa-test", "voyage-3.5")
    monkeypatch.setattr(m, "CFG", dict(m.CFG, embed="openai"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert m.embed(["x"]) != [None]
    assert calls[-1][:3] == ("https://api.openai.com/v1/embeddings", "Bearer sk-test", "text-embedding-3-small")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert m.embed(["x"]) == [None]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def offline(req, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(m.urllib.request, "urlopen", offline)
    assert m.embed(["x", "y"]) == [None, None]
    monkeypatch.setattr(m.urllib.request, "urlopen", lambda req, timeout: io.BytesIO(b'{"data": []}'))
    assert m.embed(["x"]) == [None]
    assert m.embed([]) == []
    monkeypatch.setattr(m, "CFG", dict(m.CFG, embed="none"))
    assert m.embed(["x"]) == [None]
    err = capsys.readouterr().err
    assert "no embedding API key" in err and "embedding call failed" in err and "returned 0 vectors for 1" in err


def test_search_falls_back_to_keywords_when_the_query_cannot_be_embedded(tmp_path, monkeypatch):
    m = load(tmp_path, monkeypatch, MEMORY_EMBED="voyage")
    monkeypatch.setattr(m, "embed", lambda texts: [None] * len(texts))
    journal(m, ["[all] cat"])
    run_ingest(m)
    with m.db() as c:
        assert [r["text"] for r in m.search(c, "cat")] == ["cat"]


def test_vector_rank_falls_back_when_the_embeddings_differ_in_size(m):
    """numpy cannot stack vectors of two sizes; the stdlib path ranks them anyway."""
    pytest.importorskip("numpy")
    rows = [{"id": 0, "embedding": m.array("f", [1, 0]).tobytes()}, {"id": 1, "embedding": m.array("f", [1, 0, 0]).tobytes()}]
    assert [r["id"] for r in m.vector_rank(m.array("f", [1, 0]).tobytes(), rows)] == [0, 1]


def test_journal_write_steps_past_taken_names_and_gives_up_after_a_thousand(m, monkeypatch):
    monkeypatch.setattr(m.time, "time_ns", lambda: 7)
    d = m.JOURNAL / m.datetime.now().strftime("%Y-%m-%d")
    d.mkdir(parents=True)
    pid = os.getpid()
    (d / f"7-{pid}-t.md").write_text("taken")
    assert m.journal_write(["[all] a"], "t").name == f"8-{pid}-t.md"
    for n in range(1000):
        (d / f"{7 + n}-{pid}-t.md").touch()
    with pytest.raises(RuntimeError, match="unique filename"):
        m.journal_write(["[all] b"], "t")


def test_transcript_cwd_skips_junk_lines_and_files_without_one(m, tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text('not json\n[1, 2]\n{"type": "summary"}\n')
    b.write_text('{"type": "user", "cwd": "/home/me/GitHub/p"}\n')
    assert m.transcript_cwd([a]) is None
    assert m.transcript_cwd([a, b]) == "/home/me/GitHub/p"


# ------------------------------------------------------------------ untrusted input: slugs, odd lines, odd answers


def test_a_project_slug_is_a_name_never_a_path(m, monkeypatch):
    """The Reflector picks the slug, from text that merely passed through a session, and `compile_` makes it a
    filename. A slug that is a path would write outside the store, over whatever is already there."""
    monkeypatch.setattr(m, "llm", lambda *a, **k: json.dumps([{"project": "../../../escaped", "text": "one"},
                                                              {"project": "GoodSlug", "text": "two"}]))
    with m.db() as c:
        assert m.reflect("a conversation", "fallback", set()) == [("fallback", "one"), ("goodslug", "two")]
        m.upsert(c, "../../../escaped", "filed under a path by an older version")   # a store written before this fix
        m.upsert(c, "kept", "filed under a name")
        c.commit()
        m.compile_(c)
    assert not list(m.ROOT.parent.glob("*.md"))
    assert [p.name for p in (m.COMPILED / "projects").glob("*.md")] == ["kept.md"]


def test_a_transcript_line_of_an_unknown_shape_is_not_a_turn(m, tmp_path):
    """Transcripts are written by other programs. A line this version does not understand is no turn at all; an
    exception here would abort a backfill and roll back every window it had already paid for."""
    odd = [{"type": "user", "message": None},
           {"type": "user", "message": "not an object"},
           {"type": "user", "message": {"content": None}},
           {"type": "user", "message": {"content": 42}},
           {"type": "user", "message": {"content": [{"type": "text", "text": None}]}}]
    assert [m.line_turn(json.dumps(x).encode()) for x in odd] == [None] * len(odd)
    p = tmp_path / "mixed.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in [*odd, {"type": "user", "message": {"content": "real turn"}}]))
    text, end = m.claude_code_turns(p)
    assert text == "USER: real turn" and end == p.stat().st_size


def test_an_answer_that_opens_with_prose_still_yields_its_lessons(m):
    """first-`[`-to-last-`]` would start the slice inside the sentence and parse as nothing, and the cursor would
    move on past lessons the Reflector really did return."""
    assert m.parse_json('Looking at the [conversation] I found:\n[{"project": "p", "text": "a lesson"}]') == \
        [{"project": "p", "text": "a lesson"}]
    assert m.parse_json('{"same": ["abc"], "contradicts": []}') == {"same": ["abc"], "contradicts": []}
    assert m.parse_json("a sentence [with a bracket and no json") is None
    assert m.parse_json("") is None


def test_reconcile_ignores_an_answer_that_is_not_a_verdict(m):
    """The contradiction check sometimes answers with an array. That is no verdict; it must not end the run."""
    with m.db() as c:
        first, _ = m.upsert(c, "proj", "deploy with the blue script")
        second, _ = m.upsert(c, "proj", "deploy with the green script")
        c.commit()
        m.llm = lambda *a, **k: json.dumps([{"id": first, "verdict": "same"}])
        m.reconcile(c, second)
        assert [r["state"] for r in c.execute("SELECT state FROM lessons ORDER BY id")] == ["active", "active"]


# ------------------------------------------------------------------ what an unattended run tells its operator


def test_a_failed_cli_call_is_reported_by_its_reason_not_its_first_bytes(tmp_path, monkeypatch, capsys):
    """The CLI puts its reason in `result`, at the end of a JSON object whose head is counters. Reading the first
    bytes of that told the operator nothing: an expired login went unnoticed for two days."""
    fake = tmp_path / "fakebin"
    fake.mkdir()
    payload = json.dumps({"usage": {"input_tokens": 0, "cache_read_input_tokens": 0}, "modelUsage": {}, "x": "y" * 400,
                          "is_error": True, "result": "Failed to authenticate: OAuth session expired"})
    (fake / "claude").write_text(f"#!/bin/sh\ncat >/dev/null\nprintf '%s' '{payload}'\nexit 1\n")
    (fake / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    m = load(tmp_path / "r", monkeypatch, MEMORY_LLM="cli")
    assert m.llm("anything") is None
    assert "Failed to authenticate: OAuth session expired" in capsys.readouterr().err
    with pytest.raises(m.ReflectorFailed, match="Failed to authenticate"):
        m.reflect("some text", "proj", set())


def test_a_run_that_read_nothing_exits_differently_from_one_that_ran_out_of_budget(m, tmp_path, monkeypatch, capsys):
    """Exit 1 means "part-way through, run me again"; exit 2 means "I read nothing at all", which running again
    will not fix. A scheduled job logging "paused" twice a day for a week looked exactly like progress."""
    repo = git_repo(tmp_path / "alpha", "alpha")
    monkeypatch.setattr(m, "llm", lambda *a, **k: None)          # the Reflector answers nothing, from the first call
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli"))
    monkeypatch.setattr(sys, "argv", ["memory", "learn", "--repo", str(repo)])
    with pytest.raises(SystemExit) as e:
        m.main()
    assert e.value.code == 2 and "stopped early" in capsys.readouterr().err


def test_remember_saves_the_whole_lesson_or_says_why_it_cannot(m, tmp_path, monkeypatch, capsys):
    """The journal is read back with LESSON_RE, so a slug it does not match, or a second line, would vanish after
    the caller was told the lesson was saved."""
    monkeypatch.setattr(sys, "argv", ["memory", "remember", "a lesson\nwith a second line", "--project", "Proj"])
    m.main()
    with m.db() as c:
        assert [(r["project"], r["text"]) for r in c.execute("SELECT project, text FROM lessons")] == \
            [("proj", "a lesson with a second line")]
    monkeypatch.setattr(sys, "argv", ["memory", "remember", "spaces in the slug", "--project", "my project"])
    with pytest.raises(SystemExit, match="is not a project slug"):
        m.main()
    assert m.lesson_line("-proj", "leading dash")[1] and m.lesson_line("proj", "   ")[1] == "the lesson is empty"
    assert m.lesson_line("Proj", " two   spaces ") == ("[proj] two spaces", None)
    with m.db() as c:
        assert c.execute("SELECT count(*) FROM lessons").fetchone()[0] == 1   # only the first lesson was stored


def test_a_vote_for_a_lesson_that_is_not_there_is_not_ok(m, monkeypatch, capsys):
    """`vote` and the MCP `feedback` tool both reported success for any id at all, so a typo read as recorded."""
    with m.db() as c:
        kept, _ = m.upsert(c, "proj", "a real lesson")
        c.commit()
    monkeypatch.setattr(sys, "argv", ["memory", "vote", "nosuchid", "--helpful"])
    with pytest.raises(SystemExit, match="no lesson has id nosuchid"):
        m.main()
    monkeypatch.setattr(sys, "argv", ["memory", "vote", kept, "--helpful"])
    m.main()
    with m.db() as c:
        assert c.execute("SELECT helpful FROM lessons WHERE id=?", (kept,)).fetchone()[0] == 1


# ------------------------------------------------------------------ a run that is interrupted keeps what it read


def test_an_interrupted_learn_keeps_the_sources_it_finished(m, tmp_path, monkeypatch):
    """A `learn` used to be one transaction: a crash, a reboot or a Ctrl-C hours in discarded every lesson and every
    cursor it had earned. Each source is now committed as it is finished, so only the source in hand is lost."""
    root = tmp_path / "projects"
    for enc, cwd in [("-home-me-GitHub-alpha", "/home/me/GitHub/alpha"), ("-home-me-GitHub-beta", "/home/me/GitHub/beta")]:
        (root / enc).mkdir(parents=True)
        transcript(root / enc / "s1.jsonl", [("user", "x"), ("assistant", "y")], cwd=cwd)

    real = m.ingest_transcript
    def die_on_beta(c, path, project, backfill=False):
        if project == "beta": raise KeyboardInterrupt("the operator pressed Ctrl-C")   # not a ReflectorFailed
        return real(c, path, project, backfill)
    monkeypatch.setattr(m, "llm", tracing_llm([]))
    monkeypatch.setattr(m, "ingest_transcript", die_on_beta)

    with pytest.raises(KeyboardInterrupt), m.db() as c:
        m.learn_transcripts(c, root)

    with m.db() as c:                                          # a fresh connection: only committed work is visible
        assert [r[0] for r in c.execute("SELECT DISTINCT project FROM lessons")] == ["alpha"]
        assert c.execute("SELECT count(*) FROM sources WHERE key LIKE 'transcript:%'").fetchone()[0] == 1


def test_a_checkpoint_reconciles_before_it_commits(m, monkeypatch):
    """Committed lessons must be reconciled lessons: a checkpoint that saved without reconciling would leave
    duplicates no later run ever revisits."""
    seen = []
    monkeypatch.setattr(m, "reconcile", lambda c, i: seen.append(i))
    with m.db() as c:
        first, _ = m.upsert(c, "proj", "one lesson")
        assert m.checkpoint(c, [(first, True), ("old", False)]) == [(first, True), ("old", False)]
    assert seen == [first]                                     # only the new one, and before the commit
    with m.db() as c:
        assert c.execute("SELECT count(*) FROM lessons").fetchone()[0] == 1


# ------------------------------------------------------------------ every transcript this machine holds


def codex_rollout(path, cwd, turns):
    """A Codex rollout: a session header, then `response_item` message lines among the noise it really writes."""
    lines = [{"type": "session_meta", "payload": {"id": "s1", "cwd": cwd}},
             {"type": "turn_context", "payload": {"model": "gpt-x"}},
             {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                                   "content": [{"type": "input_text", "text": "Codex's own instructions"}]}}]
    for role, text in turns:
        lines.append({"type": "response_item", "payload": {"type": "message", "role": role,
                                                           "content": [{"type": "input_text", "text": text}]}})
        lines.append({"type": "response_item", "payload": {"type": "reasoning", "summary": []}})
        lines.append({"type": "event_msg", "payload": {"type": "task_started"}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    return path


def test_a_codex_rollout_reads_as_a_transcript(m, tmp_path):
    """A rollout is mostly tool calls, reasoning and world state. Its conversation is the `response_item` messages,
    and the `developer` role is Codex's own instructions rather than anything the operator said."""
    p = codex_rollout(tmp_path / "rollout.jsonl", "/tmp/somewhere", [("user", "add a retry"), ("assistant", "done")])
    text, end = m.claude_code_turns(p)
    assert text == "USER: add a retry\n\nASSISTANT: done" and end == p.stat().st_size
    assert m.line_cwd(json.dumps({"type": "session_meta", "payload": {"cwd": "/x"}}).encode()) == "/x"


def test_a_folder_name_that_encoded_a_path_is_decoded_against_the_filesystem(m, tmp_path):
    """Cursor names a folder for the working directory, turning '/' into '-', and records no cwd inside the
    transcript. A repository with a hyphen in its name is why the filesystem has to settle where the '/' were."""
    repo = tmp_path / "GitHub" / "doc-ingestion"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub-dir").mkdir()
    base = str(tmp_path).strip("/").replace("/", "-")
    assert m.decode_cwd(f"{base}-GitHub-doc-ingestion-sub-dir", "/") == str(repo / "sub-dir")
    assert m.decode_cwd(f"{base}-GitHub-doc-ingestion-worktree-that-is-gone", "/") == str(repo)   # deepest real path
    assert m.decode_cwd("nothing-here-at-all", "/") is None
    assert m.repo_of(str(repo / "sub-dir")) == "doc-ingestion" and m.repo_of(str(tmp_path)) is None


def test_the_backfill_reads_cursor_desktop_and_codex_as_well(m, tmp_path, monkeypatch):
    """Claude Code's folder holds the CLI, the editor extensions and the desktop app's Code tab. Cursor, Claude
    Desktop's agent mode and Codex keep their own, and a session run outside a repository belongs to its tool."""
    home = tmp_path / "home"
    repo = home / "GitHub" / "alpha"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(m.Path, "home", classmethod(lambda cls: home))

    claude = home / ".claude" / "projects" / "-x-alpha"
    claude.mkdir(parents=True)
    transcript(claude / "s.jsonl", [("user", "from claude code")], cwd=str(repo))

    enc = str(repo).strip("/").replace("/", "-")
    cursor = home / ".cursor" / "projects" / enc / "agent-transcripts" / "t1"
    cursor.mkdir(parents=True)
    transcript(cursor / "t1.jsonl", [("user", "from cursor")])
    (cursor / "subagents").mkdir()
    transcript(cursor / "subagents" / "sub.jsonl", [("user", "from a cursor subagent")])
    gone = home / ".cursor" / "projects" / "empty-window" / "agent-transcripts" / "t2"
    gone.mkdir(parents=True)
    transcript(gone / "t2.jsonl", [("user", "from a cursor window with no folder open")])
    (home / ".cursor" / "projects" / "a-folder-with-no-transcripts").mkdir()

    desktop = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions" / "a" / "b"
    desktop.mkdir(parents=True)
    transcript(desktop / "audit.jsonl", [("user", "from claude desktop")], cwd=str(desktop / "outputs"))

    codex_rollout(home / ".codex" / "sessions" / "2026" / "r.jsonl", str(repo), [("user", "from codex in the repo")])
    codex_rollout(home / ".codex" / "sessions" / "2026" / "s.jsonl", str(home / "Documents" / "friday"),
                  [("user", "from codex in a scratch folder")])
    transcript(home / ".codex" / "sessions" / "2026" / "left.jsonl",       # the Reflector's own, from before #10
               [("user", m.REFLECT_SYS[:80] + " ... a window of somebody else's transcript")])

    got = {}
    for slug, files in m.transcript_sources():
        got.setdefault(slug, []).extend(f.name for f in files)
    assert sorted(got["alpha"]) == ["r.jsonl", "s.jsonl", "sub.jsonl", "t1.jsonl"]   # Claude Code, Cursor and its
    assert got["cursor"] == ["t2.jsonl"]          # subagent's, and a Codex rollout, all run in the same repository
    assert got["claude-desktop"] == ["audit.jsonl"] and got["codex"] == ["s.jsonl"]   # no repository: the tool's own

    monkeypatch.setattr(m, "llm", tracing_llm([]))
    with m.db() as c:
        m.learn_transcripts(c)
        projects = {r[0] for r in c.execute("SELECT DISTINCT project FROM lessons")}
    assert projects == {"alpha", "cursor", "claude-desktop", "codex"}


def test_transcripts_from_reads_a_folder_you_name(m, tmp_path, monkeypatch):
    """`--transcripts-from` takes any folder of transcripts, in any of the shapes above."""
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    monkeypatch.setattr(m.Path, "home", classmethod(lambda cls: home))
    loose = tmp_path / "Archive"
    (loose / "old").mkdir(parents=True)
    transcript(loose / "old" / "one.jsonl", [("user", "an archived session")])
    monkeypatch.setattr(m, "llm", tracing_llm([]))
    monkeypatch.setattr(sys, "argv", ["memory", "learn", "--transcripts-from", str(loose)])
    m.main()
    with m.db() as c:
        assert [r[0] for r in c.execute("SELECT DISTINCT project FROM lessons")] == ["archive"]


# ------------------------------------------------------------------ recall, budget and handles


def test_a_lesson_with_an_accent_can_be_found_by_its_own_words(m):
    """ASCII-only tokens cut an accented word to a stump that matches nothing, so the lesson was unfindable by
    search, by MCP recall, and by the contradiction check that would have spotted it as a duplicate."""
    with m.db() as c:
        m.upsert(c, "proj", "prefer café-au-lait naming in the Überwachung module")
        m.upsert(c, "proj", "the naïve merge loses the second author")
        c.commit()
        assert [r["text"] for r in m.search(c, "café", "proj")][:1] == ["prefer café-au-lait naming in the Überwachung module"]
        assert [r["text"] for r in m.search(c, "Überwachung", "proj")][:1] == ["prefer café-au-lait naming in the Überwachung module"]
        assert [r["text"] for r in m.search(c, "naïve", "proj")][:1] == ["the naïve merge loses the second author"]
    assert m.fts_query("café Überwachung") == '"café" OR "Überwachung"'


def test_the_budget_counts_the_calls_it_actually_makes(m, tmp_path, monkeypatch, capsys):
    """A reflection used to charge one call plus one per lesson for the checks it might need. Most of those checks
    never happen — a lesson already in the store, or one with nothing to compare against, costs nothing — so a
    budget of 60 bought a fraction of the work it was given."""
    calls = []
    def counting_llm(prompt, system=m.REFLECT_SYS, *a, **k):
        calls.append(prompt)
        if system == m.CONTRA_SYS: return '{"same": [], "contradicts": []}'
        return json.dumps([{"project": "proj", "text": f"lesson {len(calls)} from the window"}])
    monkeypatch.setattr(m, "llm", counting_llm)
    monkeypatch.setattr(m, "CFG", dict(m.CFG, llm="cli"))
    root = tmp_path / "projects"
    for i in range(8):
        (root / f"-x-p{i}").mkdir(parents=True)
        transcript(root / f"-x-p{i}" / "s.jsonl", [("user", f"turn {i}"), ("assistant", "noted")], cwd=f"/x/p{i}")
    m.BUDGET.update(max=5, used=0)
    with m.db() as c, pytest.raises(m.ReflectorFailed, match="budget of 5 is spent"):
        m.learn_transcripts(c, root)
    assert len(calls) == 5 and m.BUDGET["used"] == 5      # exactly the budget, reflections and checks alike

    with m.db() as c:                                     # a check that would exceed the budget waits for next time
        m.upsert(c, "proj", "deploy with the blue script")
        second, _ = m.upsert(c, "proj", "deploy with the green script")   # a neighbour worth comparing against
        c.commit()
        before = len(calls)
        m.reconcile(c, second)
        assert len(calls) == before                       # no call made
        m.BUDGET.update(max=None)
        m.reconcile(c, second)
        assert len(calls) == before + 1                   # and with no budget set, the check happens


def test_a_database_handle_is_closed_when_its_block_ends(m):
    """The CLI gets away with leaving handles open because the process ends. The MCP server runs for as long as the
    editor does and opens one per tool call."""
    with m.db() as c:
        m.upsert(c, "proj", "a lesson")
    with pytest.raises(sqlite3.ProgrammingError, match=r"[Cc]losed database"):
        c.execute("SELECT 1")
    with pytest.raises(ValueError), m.db() as c2:        # an exception still closes it, and rolls back
        m.upsert(c2, "proj", "not kept")
        raise ValueError("something went wrong")
    with pytest.raises(sqlite3.ProgrammingError):
        c2.execute("SELECT 1")
    with m.db() as c3:
        assert [r[0] for r in c3.execute("SELECT text FROM lessons")] == ["a lesson"]


# ------------------------------------------------------------------ the lock, when two writers meet


def test_a_waiter_survives_the_lock_vanishing_between_its_mkdir_and_its_stat(m, monkeypatch):
    """The holder can release in the moment between a waiter's failed `mkdir` and the `stat` that asks how old the
    lock is. That `stat` used to raise FileNotFoundError at the waiter, which for a hook meant a lost run."""
    m.ROOT.mkdir(parents=True, exist_ok=True)
    m.LOCK.mkdir()
    attempts = []
    real_take = m.Lock.take
    def take(self):
        attempts.append(1)
        if len(attempts) == 1:
            shutil.rmtree(m.LOCK)                  # the holder lets go, right after our mkdir failed
            return False
        return real_take(self)
    monkeypatch.setattr(m.Lock, "take", take)
    with m.Lock(wait=1) as lk:
        assert lk.mine() and len(attempts) == 2
    assert not m.LOCK.exists()


def test_only_one_writer_breaks_a_crashed_holders_lock(m):
    """Two writers that both judge a lock stale must not both break it, or both would believe they hold what they
    create next, and each one's release would remove the other's lock."""
    m.ROOT.mkdir(parents=True, exist_ok=True)
    m.LOCK.mkdir()
    os.utime(m.LOCK, (0, 0))                       # untouched since 1970: its holder died
    m.BREAK.mkdir()                                # another writer is already breaking it
    with pytest.raises(m.LockBusy), m.Lock(wait=0.3):
        pass
    assert m.LOCK.exists()                         # left for the writer that got there first
    m.BREAK.rmdir()
    with m.Lock(wait=1) as lk:
        assert lk.mine() and not m.BREAK.exists()


def test_a_lock_that_is_gone_or_fresh_again_by_then_is_left_alone(m):
    """Taking the break lock costs a moment, and in that moment the lock may have been released, or taken and
    refreshed by a writer that is very much alive. Either way there is nothing to break."""
    m.ROOT.mkdir(parents=True, exist_ok=True)
    lk = m.Lock()
    lk.crashed_holders_lock()                      # released while we were taking the break lock
    assert not m.LOCK.exists() and not m.BREAK.exists()
    m.LOCK.mkdir()                                 # touched a moment ago: somebody is alive in there
    lk.crashed_holders_lock()
    assert m.LOCK.exists() and not m.BREAK.exists()
    m.LOCK.rmdir()


def test_a_holder_leaves_a_lock_that_is_no_longer_its_own(m, monkeypatch):
    """The lock carries its holder's token. Touching or removing one that has since been taken by somebody else is
    how a single broken lock used to cascade into no lock at all."""
    monkeypatch.setattr(m, "LOCK_BEAT", 0.01)
    with m.Lock() as lk:
        assert lk.mine()
        (m.LOCK / "owner").write_text("another writer")
        os.utime(m.LOCK, (0, 0))
        time.sleep(0.15)                           # many beats: none of them ours to make
        assert m.LOCK.stat().st_mtime == 0
    assert m.LOCK.exists() and (m.LOCK / "owner").read_text() == "another writer"
    shutil.rmtree(m.LOCK)


# ------------------------------------------------------------------ the scripts themselves


def load_tool(name):
    loader = importlib.machinery.SourceFileLoader(f"tool_{name}", str(REPO / "tools" / f"{name}.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_the_scripts_run_as_main(m, tmp_path, monkeypatch, capsys):
    """bin/memory and eval_recall.py do their job when run directly."""
    monkeypatch.setattr(sys, "argv", ["memory", "remember", "run as main", "--project", "p"])
    runpy.run_path(str(BIN), run_name="__main__")
    assert (m.COMPILED / "projects" / "p.md").read_text() == "- (1) run as main\n"
    q = tmp_path / "q.jsonl"
    q.write_text(json.dumps({"query": "main", "project": "p", "expect": ["run as main"]}) + "\n")
    monkeypatch.setattr(sys, "argv", ["eval_recall.py", str(q)])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(REPO / "tools" / "eval_recall.py"), run_name="__main__")
    assert e.value.code == 0 and "recall@8: 1/1" in capsys.readouterr().out


def test_check_docs_reports_every_kind_of_drift(tmp_path, monkeypatch, capsys):
    """Each check failing once: a stale count, a stale coverage gate, a version with no changelog section, a broken
    link, a home path, an email address. External links, anchors, placeholders and images are left alone."""
    cd = load_tool("check_docs")
    for name in cd.PROSE:
        (tmp_path / name).write_text("fine\n")
    (tmp_path / "README.md").write_text("5 tests. The coverage gate is 80 per cent. [a](missing.md) [b](https://example.com) [c](#top)\n")
    (tmp_path / "CHANGELOG.md").write_text("## [0.1.0]\n")
    (tmp_path / "CITATION.cff").write_text('version: "9.9.9"\n')
    (tmp_path / ".coveragerc").write_text("[report]\nfail_under = 100\n")
    home = "/" + "Users" + "/someone"
    address = "someone" + "@" + "mail.test"
    (tmp_path / "notes.txt").write_text(f"see {home}/x, not /Users/<you>/y or /home/me/z; mail {address}, not noreply@anthropic.com\n")
    (tmp_path / "pic.png").write_bytes(home.encode())
    monkeypatch.setattr(cd, "REPO", tmp_path)
    monkeypatch.setattr(cd, "collected_tests", lambda: 7)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert cd.main() == 1
    out = capsys.readouterr().out
    assert "::error::README.md: says 5 tests, pytest collects 7" in out
    assert "README.md: says coverage gate 80, .coveragerc says 100" in out
    assert "CHANGELOG.md has no section for CITATION.cff version 9.9.9" in out
    assert "README.md: broken link missing.md" in out and "example.com" not in out
    assert "notes.txt:1: host-specific home path" in out and "pic.png" not in out
    assert "notes.txt:1: email address" in out and out.count("email address") == 1
    assert "6 problem(s)" in out


def test_check_docs_stops_when_pytest_cannot_collect(monkeypatch):
    cd = load_tool("check_docs")
    monkeypatch.setattr(cd.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout="no summary", stderr="boom"))
    with pytest.raises(SystemExit, match="could not collect tests"):
        cd.collected_tests()


def test_eval_recall_refuses_no_questions_and_finds_memory_beside_itself(m, tmp_path, monkeypatch):
    """In the image eval_recall.py sits beside `memory` in /app; with neither layout present it says so."""
    ev = load_tool("eval_recall")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n")
    with pytest.raises(SystemExit, match="no questions"):
        ev.main([str(empty)])
    app = tmp_path / "app"
    app.mkdir()
    shutil.copy(BIN, app / "memory")
    monkeypatch.setattr(ev, "REPO", tmp_path / "nowhere")
    monkeypatch.setattr(ev, "__file__", str(app / "eval_recall.py"))
    assert ev.load_memory().__name__ == "memory_cli"
    monkeypatch.setattr(ev, "__file__", str(tmp_path / "eval_recall.py"))
    with pytest.raises(SystemExit, match="no bin/memory"):
        ev.load_memory()


def test_init_store_makes_a_private_git_store_and_is_safe_to_rerun(tmp_path):
    root = tmp_path / "store"
    env = {**os.environ, "MEMORY_ROOT": str(root), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for _ in range(2):
        out = subprocess.run(["bash", str(REPO / "tools" / "init_store.sh")], env=env, capture_output=True, text=True, check=True).stdout
    assert out == f"store ready at {root}\n"
    assert all((root / d).is_dir() for d in ("journal/claude-ai", "compiled/projects", "archive", "exports"))
    assert (root / ".gitignore").read_text().split() == [".lock/", "memory.db*", "hook.log", "*.tmp", "exports/"]
    log = subprocess.run(["git", "-C", str(root), "log", "--format=%s"], capture_output=True, text=True, check=True).stdout
    assert log == "init store\n"


def test_bootstrap_dry_run_touches_nothing(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path)}
    out = subprocess.run(["bash", str(REPO / "tools" / "bootstrap.sh"), "--dry-run"], env=env, capture_output=True, text=True, check=True).stdout
    assert out.startswith("would copy") and not any(tmp_path.iterdir())
