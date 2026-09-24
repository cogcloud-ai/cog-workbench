#!/usr/bin/env python3
"""Cog client CLI — a generic consumer of what Cogs declare.

    pixi run show   -- <path-to-cog>            # inspector card + affordances
    pixi run ask    -- <path> --bundle f.json   # invoke the task entry point
    pixi run chat   -- <path>                   # client-held-thread chat REPL
    pixi run health -- <path>                   # probe declared health surfaces

No Cog-specific code: everything rendered or invoked comes from the package's
own declarations. Where the portable contract forced a guess, the output says
so ("gap:") — those lines are the original client's gap record, live.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cog_package  # noqa: E402
import cog_invoke  # noqa: E402


def cmd_show(args):
    pkg = cog_package.load_package(args.path)
    c = cog_package.card(pkg)
    if args.json:
        print(json.dumps(c, indent=2))
        return 0
    print(f"{c['id']}  v{c['version']}  [{c['kind']}]")
    if c["summary"]:
        print(f"  {c['summary']}")
    print(f"  owner: {c['owner']}   license: {c['license']}   schema: {c['schema']}")
    if c["io"]:
        print(f"  io: accepts={c['io'].get('accepts')} produces={c['io'].get('produces')}")
    print("  entry points:")
    for i in c["interfaces"]:
        mark = " (default)" if i["default"] else ""
        where = i.get("endpoint") or (f"address: {i['address']}" if i.get("address") else "")
        print(f"    - {i['name']} [{i['kind']}]{mark}  {where}")
    for r in c["requires"]:
        sats = ", ".join(f"{s['cog']} {s['version'] or ''}".strip() for s in r["satisfiers"])
        print(f"  requires: {r['capability']} (locality: {r['locality']})  <- {sats}")
    if c["prohibits"]:
        print(f"  prohibits: {', '.join(c['prohibits'])}")
    if c["binding"]:
        b = c["binding"]
        if b.get("error"):
            print(f"  binding: INVALID — {b['error']}")
        else:
            print(f"  binding: {b['satisfier']}  at {cog_invoke.redact_endpoint(b['endpoint'])}"
                  f"  locality={b['locality']} pinned={b['pinned']}"
                  + ("" if b.get("declared") in (None, True) else "  DECLARED=False"))
    else:
        print("  binding: none (run the Cog's resolve/use to bind)")
    print("  affordances:")
    for a in c["affordances"]:
        line = {"task": lambda a: f"invoke via {a['interface']} at {a['endpoint']}"
                                  + (f"  examples: {', '.join(a['examples'])}" if a["examples"] else ""),
                "chat": lambda a: f"chat via {a['interface']}"
                                  + (f" at {a['endpoint']}" if a.get("endpoint")
                                     else "  (address supplied at install time)"),
                "chat-io": lambda a: f"conversation-shaped io ({a['via']})",
                "commands": lambda a: "commands: " + ", ".join(x["run"] for x in a["commands"]),
                "model": lambda a: f"model: {a.get('name')}"
                                   + (f" (composed: {a['lineage']['effective_id']})"
                                      if a.get("lineage") else ""),
                }.get(a["type"], lambda a: a["type"])(a)
        print(f"    - [{a['type']}] {line}")
        if a.get("gap"):
            print(f"        gap: {a['gap']}")
    return 0


def _task_affordance(pkg):
    for a in cog_package.affordances(pkg):
        if a["type"] == "task":
            return a
    sys.exit("this Cog declares no task-shaped http entry point — nothing generic to invoke")


def cmd_ask(args):
    pkg = cog_package.load_package(args.path)
    a = _task_affordance(pkg)
    raw = sys.stdin.read() if args.bundle == "-" else Path(args.bundle).read_text()
    bundle = json.loads(raw)
    r = cog_invoke.invoke_task(a["endpoint"], bundle)
    if args.json:
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] and not r["problems"] else 1
    if r.get("transport_error"):
        sys.exit(f"transport: {r['transport_error']} — is the Cog serving? "
                 f"(its manifest says {a['endpoint']})")
    if r.get("error"):
        detail = r.get("detail")
        if isinstance(detail, list):
            detail = "\n  - " + "\n  - ".join(map(str, detail))
        sys.exit(f"{r['error']} (HTTP {r['status']}): {detail}")
    b = r.get("binding") or {}
    rec = b.get("record") or {}
    print(f"payload [{r['payload_key']}] from {rec.get('model') or '?'} via "
          f"{cog_invoke.redact_endpoint(rec.get('endpoint'))} "
          f"(identity: {b.get('model_identity')}, pinned: {rec.get('pinned')})\n")
    print(json.dumps(r["payload"], indent=2))
    if r["problems"]:
        print("\nintegrity problems:")
        for p in r["problems"]:
            print(f"  - {p}")
    for g in r["gaps"]:
        print(f"gap: {g}")
    return 0 if not r["problems"] else 2


def cmd_chat(args):
    pkg = cog_package.load_package(args.path)
    chat = next((a for a in cog_package.affordances(pkg) if a["type"] == "chat"), None)
    if not chat:
        sys.exit("this Cog declares no openai-compatible entry point — no chat surface")
    endpoint = args.endpoint or chat.get("endpoint")
    if not endpoint:
        sys.exit("this deployment descriptor carries no address — pass --endpoint")
    model = chat.get("served_model_id")
    print(f"chat with {model or 'the served model'} at "
          f"{cog_invoke.redact_endpoint(endpoint)} — client-held thread, "
          f"stateless Cog turns (§6.6). Ctrl-D to end.")
    messages = []          # THE thread. It lives here, not in the Cog.
    while True:
        try:
            user = input("> ").strip()
        except EOFError:
            print()
            return 0
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        r = cog_invoke.chat_turn(endpoint, messages, model=model,
                                 api_key_env=chat.get("api_key_env"))
        if not r.get("ok"):
            print(f"  [turn failed: {r.get('transport_error') or r.get('error')}]")
            messages.pop()
            continue
        messages.append({"role": "assistant", "content": r["text"]})
        print(r["text"])


def cmd_health(args):
    pkg = cog_package.load_package(args.path)
    ok_all, any_probe = True, False
    for a in cog_package.affordances(pkg):
        if a["type"] == "task":
            any_probe = True
            r = cog_invoke.health(a["health_url"])
            ok_all &= r["ok"]
            print(f"[{'ok' if r['ok'] else 'DOWN'}] {a['interface']} {a['health_url']}"
                  + ("" if r["ok"] else f"  — {r.get('error') or r.get('status')}"))
        if a["type"] == "chat" and a.get("endpoint"):
            any_probe = True
            r = cog_invoke.model_health(a["endpoint"])
            ok_all &= r["ok"]
            print(f"[{'ok' if r['ok'] else 'DOWN'}] {a['interface']} {a['endpoint']}"
                  + ("" if r["ok"] else f"  — {r.get('error') or r.get('status')}"))
    if not any_probe:
        print("no probeable entry points declared")
        return 1
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser(prog="cog-client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show");  p.add_argument("path"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("ask");   p.add_argument("path"); p.add_argument("--bundle", required=True); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_ask)
    p = sub.add_parser("chat");  p.add_argument("path"); p.add_argument("--endpoint"); p.set_defaults(fn=cmd_chat)
    p = sub.add_parser("health"); p.add_argument("path"); p.set_defaults(fn=cmd_health)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
