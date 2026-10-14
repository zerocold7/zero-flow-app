"""A stand-in for llama-server, for tests: a real process that answers /health and
/v1/chat/completions on the --port it is given, and ignores every other argument.

    FAKE_LLAMA_ARGS_FILE   write the command-line arguments here (one per line)
    FAKE_LLAMA_DELAY       seconds to wait before listening (a model loading)
    FAKE_LLAMA_CRASH_AFTER exit after answering this many chat requests
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

args = sys.argv[1:]
if os.environ.get("FAKE_LLAMA_ARGS_FILE"):
    with open(os.environ["FAKE_LLAMA_ARGS_FILE"], "w", encoding="utf-8") as f:
        f.write("\n".join(args))
port = int(args[args.index("--port") + 1])
time.sleep(float(os.environ.get("FAKE_LLAMA_DELAY", "0")))
crash_after = int(os.environ.get("FAKE_LLAMA_CRASH_AFTER", "0"))
answered = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self.reply({"status": "ok"})
        else:
            self.send_error(404)

    def do_POST(self):
        global answered
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        said = request["messages"][-1]["content"].split("Input Raw String: ")[-1].split("\n")[0]
        self.reply({"choices": [{"message": {"content": f"Answer to: {said}"}}]})
        answered += 1
        if crash_after and answered >= crash_after:
            os._exit(3)


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
