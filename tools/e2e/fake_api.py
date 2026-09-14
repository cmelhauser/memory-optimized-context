"""Stand-in for the Anthropic Messages API, for tools/e2e.sh. Logs every prompt; answers with one
traceable lesson. Usage: fake_api.py PORT LOGFILE; point ANTHROPIC_BASE_URL at it."""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[2]


def answer(prompt):
    if "CANDIDATES:" in prompt:
        return '{"same": [], "contradicts": []}'
    m = re.search(r"Default project for this conversation: (\S+)", prompt)
    proj = m.group(1) if m else "all"
    return json.dumps([{"project": proj, "text": f"sdk lesson for {proj}"}])


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        prompt = body["messages"][0]["content"]
        with open(LOG, "a") as f:
            f.write(json.dumps({"path": self.path, "key": self.headers.get("x-api-key"), "prompt": prompt}) + "\n")
        out = {"id": "msg_e2e", "type": "message", "role": "assistant", "model": body["model"],
               "content": [{"type": "text", "text": answer(prompt)}], "stop_reason": "end_turn",
               "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
