"""MCP over streamable HTTP on 127.0.0.1:8765. `mcp_http.py wait` polls until it answers; with no
argument it lists the tools and calls recall."""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8765/mcp"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "e2e", "version": "0"}}}


def post(obj, sid=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if sid:
        h["Mcp-Session-Id"] = sid
    with urllib.request.urlopen(urllib.request.Request(URL, json.dumps(obj).encode(), h), timeout=10) as r:
        body = r.read().decode()
        sid = r.headers.get("mcp-session-id") or sid
    msgs = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]
    return sid, msgs or ([json.loads(body)] if body.strip() else [])


if sys.argv[1:] == ["wait"]:
    for _ in range(120):
        try:
            post(INIT)
            sys.exit(0)
        except OSError:
            time.sleep(0.5)
    sys.exit(1)

sid, _ = post(INIT)
post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
_, msgs = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
names = {t["name"] for t in msgs[0]["result"]["tools"]}
_, msgs = post({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "recall", "arguments": {"query": "lesson hail", "project": "us-hail-cat-model"}}}, sid)
out = msgs[0]["result"]["content"][0]["text"]
print(f"     tools={sorted(names)} recall -> {out.splitlines()[0][:90]}")
sys.exit(0 if {"recall", "remember", "feedback"} <= names and "us-hail-cat-model" in out else 1)
