"""MCP over stdio against `bin/memory mcp`: initialize, list the tools, call recall. Usage: mcp_stdio.py BIN"""
import json
import signal
import subprocess
import sys

signal.alarm(60)
p = subprocess.Popen([sys.executable, sys.argv[1], "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, text=True)


def send(o):
    p.stdin.write(json.dumps(o) + "\n")
    p.stdin.flush()


def recv():
    while True:
        line = p.stdout.readline()
        if not line:
            sys.exit("eof from server")
        m = json.loads(line)
        if "id" in m:
            return m


send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "e2e", "version": "0"}}})
recv()
send({"jsonrpc": "2.0", "method": "notifications/initialized"})
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
names = {t["name"] for t in recv()["result"]["tools"]}
send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
      "params": {"name": "recall", "arguments": {"query": "lesson hail", "project": "us-hail-cat-model"}}})
out = recv()["result"]["content"][0]["text"]
p.kill()
print(f"     tools={sorted(names)} recall -> {out.splitlines()[0][:90]}")
sys.exit(0 if {"recall", "remember", "feedback"} <= names and "us-hail-cat-model" in out else 1)
