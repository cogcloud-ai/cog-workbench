#!/usr/bin/env python3
"""cog-workbench — the gap-filled invocation environment.

    pixi run serve -- --path ../cog-forge/cog-release-notes

Everything cog-client v0 did (inspect, generic invoke, chat, health), plus the
GAPS filled by proposal:

  - schema-driven input forms (manifest `context.input_schema`, else overlay);
  - RUNNABLE operations — the Cog's declared tasks behind buttons, with live
    logs, including its dependency chain (start model -> resolve -> serve);
  - a working chat surface that can stand its own stack up first;
  - an activity journal (the §6.6 audit surround, minimal form).

Loopback only, no auth. The workbench holds real authority (it starts
processes), which is exactly what an invocation environment is — see
DECISIONS.md for the guardrails and tradeoffs.
"""
import argparse
import json
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cog_package  # noqa: E402
import cog_invoke  # noqa: E402
import proc_manager  # noqa: E402

HERE = Path(__file__).resolve().parent
UI = HERE / "ui.html"
VAR = HERE.parent / "var"
DEFAULT_PATH = None
MAX_BODY = 4 << 20


def journal(entry):
    VAR.mkdir(exist_ok=True)
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
    with open(VAR / "activity.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


PM = proc_manager.ProcessManager(journal=journal)


def _load(path):
    if not path:
        raise cog_package.PackageError("no ?path= given")
    return cog_package.load_package(path)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, content_type="application/json"):
        body = (payload if isinstance(payload, bytes)
                else json.dumps(payload, indent=2).encode())
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _q(self):
        parsed = urllib.parse.urlsplit(self.path)
        return parsed.path, dict(urllib.parse.parse_qsl(parsed.query))

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        route, q = self._q()
        try:
            if route == "/":
                html = UI.read_text()
                preload = q.get("path") or DEFAULT_PATH or ""
                html = html.replace("__PRELOAD_PATH__", json.dumps(preload))
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            if route == "/api/package":
                return self._send(200, cog_package.card(_load(q.get("path"))))
            if route == "/api/example":
                pkg = _load(q.get("path"))
                name = q.get("name", "")
                if name not in pkg["examples"]:
                    return self._send(404, {"error": "unknown example"})
                content = (Path(pkg["root"]) / "examples" / name).read_text()
                return self._send(200, {"name": name, "content": content})
            if route == "/api/health":
                pkg = _load(q.get("path"))
                results = []
                for a in cog_package.affordances(pkg):
                    if a["type"] == "task":
                        results.append({"interface": a["interface"],
                                        **cog_invoke.health(a["health_url"])})
                    if a["type"] == "chat" and a.get("endpoint"):
                        results.append({"interface": a["interface"],
                                        **cog_invoke.model_health(a["endpoint"])})
                return self._send(200, {"results": results})
            if route == "/api/op/logs":
                r = PM.logs(q.get("key", ""), tail=int(q.get("tail", "200")))
                return self._send(200 if r else 404, r or {"error": "unknown process"})
            if route == "/api/procs":
                return self._send(200, {"procs": PM.list()})
            if route == "/api/activity":
                path = VAR / "activity.jsonl"
                lines = []
                if path.exists():
                    lines = path.read_text().strip().splitlines()[-int(q.get("tail", "50")):]
                return self._send(200, {"entries": [json.loads(x) for x in lines]})
            return self._send(404, {"error": "not-found"})
        except cog_package.PackageError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:                                # pragma: no cover
            return self._send(500, {"error": "internal", "detail": repr(e)})

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        route, _ = self._q()
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._send(400, {"error": "bad content length"})
            body = json.loads(self.rfile.read(length).decode("utf-8", "replace"))

            if route == "/api/invoke":
                pkg = _load(body.get("path"))
                task = next((a for a in cog_package.affordances(pkg)
                             if a["type"] == "task"), None)
                if not task:
                    return self._send(400, {"error": "no task-shaped entry point declared"})
                r = cog_invoke.invoke_task(task["endpoint"], body.get("bundle"))
                b = (r.get("binding") or {})
                journal({"event": "invoke", "cog": pkg["name"],
                         "ok": r.get("ok"), "problems": len(r.get("problems") or []),
                         "identity": b.get("model_identity"),
                         "model": ((b.get("record") or {}).get("model"))})
                return self._send(200, r)

            if route == "/api/chat":
                pkg = _load(body.get("path"))
                chat = next((a for a in cog_package.affordances(pkg)
                             if a["type"] == "chat"), None)
                if not chat:
                    return self._send(400, {"error": "no openai-compatible entry point declared"})
                endpoint = body.get("endpoint") or chat.get("endpoint")
                if not endpoint:
                    return self._send(400, {"error": "deployment descriptor carries no "
                                                     "address — supply one in the endpoint box"})
                r = cog_invoke.chat_turn(endpoint, body.get("messages") or [],
                                         model=chat.get("served_model_id"),
                                         api_key_env=chat.get("api_key_env"))
                journal({"event": "chat-turn", "cog": pkg["name"], "ok": r.get("ok"),
                         "model_echoed": r.get("model_echoed")})
                return self._send(200, r)

            if route == "/api/op/start":
                # Guardrail: root+task must come from THIS package's derived
                # operations, never a free-form command.
                pkg = _load(body.get("path"))
                ops = cog_package.operations(pkg)
                op = next((o for o in ops if o["root"] == str(Path(body.get("root", "")).resolve())
                           and o["task"] == body.get("task")), None)
                if not op:
                    return self._send(400, {"error": "that (root, task) is not a declared "
                                                     "operation of this Cog"})
                try:
                    snap = PM.start(op["root"], op["task"],
                                    extra_args=(body.get("args") or "").strip() or None)
                except ValueError as e:
                    return self._send(409, {"error": str(e)})
                return self._send(200, snap)

            if route == "/api/op/stop":
                return self._send(200, PM.stop(body.get("key", "")))

            return self._send(404, {"error": "not-found"})
        except json.JSONDecodeError as e:
            return self._send(400, {"error": "invalid json", "detail": str(e)})
        except cog_package.PackageError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:                                # pragma: no cover
            return self._send(500, {"error": "internal", "detail": repr(e)})

    def log_message(self, fmt, *a):
        sys.stderr.write("  %s\n" % (fmt % a))


def main():
    global DEFAULT_PATH
    ap = argparse.ArgumentParser(prog="cog-workbench")
    ap.add_argument("--port", type=int, default=8071)
    ap.add_argument("--path", help="Cog package to preload in the UI")
    args = ap.parse_args()
    DEFAULT_PATH = args.path
    print(f"cog-workbench on http://127.0.0.1:{args.port}"
          + (f"  (preloading {args.path})" if args.path else ""))
    try:
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    finally:
        PM.stop_all()


if __name__ == "__main__":
    main()
