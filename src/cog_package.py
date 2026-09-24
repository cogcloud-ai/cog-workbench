"""Read a Cog package and derive what a client can do with it.

This is the INSPECT half of the reference client (starting-point doc §6.2):
pure reading — COG.md frontmatter, the manifest ([tool.cog] in
pixi.toml, or cog.yaml), installation state (model.json if
present), and example bundles. No runtime is involved and nothing is invoked.

Vocabulary note (Travis, 2026-08-08): the harness is part of the runtime INSIDE
a complete Cog. This client is not a harness and not a runner — it is what an
invocation environment embeds to be a competent consumer of what Cogs declare.
"""
import json
import re
import toml_compat as tomllib  # tomllib on 3.11+, honest fallback below
from pathlib import Path

import yaml

OVERLAYS = Path(__file__).resolve().parent.parent / "overlays"

# Tasks a workbench may run even though they aren't interfaces: the Cog's own
# conventional binding/verification machinery. Never arbitrary commands.
CONVENTIONAL_TASKS = ("resolve", "use", "check", "eval", "test", "bundle")

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


class PackageError(Exception):
    pass


# ---------------------------------------------------------------- manifest --
# The profile manifest lives in ONE of: pixi.toml under [tool.cog] (the
# default since cog-smith's migrate; `version`/`summary` fall back to
# [workspace] version/description) or a standalone cog.yaml. Same rules as
# cog-smith's smith_manifest.py.

def _pixi_manifest(root):
    p = Path(root) / "pixi.toml"
    if not p.exists():
        return None
    try:
        with open(p, "rb") as f:
            doc = tomllib.load(f)
    except (ValueError, OSError):
        return None
    tool = doc.get("tool")
    if not (isinstance(tool, dict) and isinstance(tool.get("cog"), dict)):
        return None
    m = dict(tool["cog"])
    ws = doc.get("workspace") or doc.get("project") or {}
    if "version" not in m and ws.get("version") is not None:
        m["version"] = ws["version"]
    if "summary" not in m and ws.get("description") is not None:
        m["summary"] = ws["description"]
    return m


def manifest_path(root):
    """pixi.toml or cog.yaml, whichever carries the manifest; else None."""
    root = Path(root)
    if _pixi_manifest(root) is not None:
        return root / "pixi.toml"
    if (root / "cog.yaml").exists():
        return root / "cog.yaml"
    return None


def read_manifest(root):
    """(manifest, path). Raises PackageError when neither form is present
    or the file is unreadable."""
    root = Path(root)
    m = _pixi_manifest(root)
    if m is not None:
        return m, root / "pixi.toml"
    cy = root / "cog.yaml"
    if not cy.exists():
        raise PackageError(f"{root} is not a Cog package (no pixi.toml "
                           f"[tool.cog] and no cog.yaml)")
    try:
        return (yaml.safe_load(cy.read_text()) or {}), cy
    except yaml.YAMLError as e:
        raise PackageError(f"cog.yaml is not valid YAML: {e}")


def load_package(path):
    """Load a Cog package directory into a structured, read-only view."""
    root = Path(path).expanduser().resolve()
    manifest, _ = read_manifest(root)

    frontmatter, readme_body = {}, None
    cogmd = root / "COG.md"
    if cogmd.exists():
        text = cogmd.read_text()
        m = FRONTMATTER_RE.match(text)
        if m:
            try:
                frontmatter = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                frontmatter = {"_error": "frontmatter is not valid YAML"}
            readme_body = text[m.end():].strip()
        else:
            readme_body = text.strip()

    binding = None
    binding_path = root / "model.json"
    if binding_path.exists():
        try:
            binding = json.loads(binding_path.read_text())
        except json.JSONDecodeError:
            binding = {"_error": "model.json is not valid JSON"}

    examples = []
    exdir = root / "examples"
    if exdir.is_dir():
        examples = sorted(p.name for p in exdir.glob("*.json"))

    return {
        "root": str(root),
        "name": root.name,
        "manifest": manifest,
        "frontmatter": frontmatter,
        "readme_body": readme_body,
        "binding": binding,          # installation state; may be absent
        "examples": examples,
    }


def _http_base(endpoint):
    """http://127.0.0.1:8091/ask -> http://127.0.0.1:8091"""
    m = re.match(r"^(https?://[^/]+)", str(endpoint or ""))
    return m.group(1) if m else None


def affordances(pkg):
    """Derive interaction affordances from DECLARED parts only.

    Each affordance carries a `gap` field when the derivation had to guess —
    those notes are the raw material for the gap scorecard in DECISIONS.md,
    the concrete record of where the portable contract was not enough for a
    generic client.
    """
    m = pkg["manifest"]
    interfaces = m.get("interfaces") or []
    io_block = m.get("io") or {}
    accepts = io_block.get("accepts") or []
    out = []

    # --- task panel: an http-json entry point that accepts task-shaped work --
    http = next((i for i in interfaces
                 if i.get("kind") == "http-json" and i.get("endpoint")), None)
    if http:
        gap = None
        if not accepts:
            gap = ("no io.accepts declared — task shape assumed from the "
                   "http-json entry point")
        elif "task_request" not in accepts:
            gap = f"io.accepts={accepts} has no ratified vocabulary; treating as task-shaped"
        out.append({
            "type": "task",
            "interface": http.get("name"),
            "endpoint": http["endpoint"],
            "health_url": (_http_base(http["endpoint"]) or "") + "/health",
            "produces": io_block.get("produces") or [],
            "examples": pkg["examples"],
            "input_schema": None,   # none is declarable today — the headline gap
            "gap": gap,
        })

    # --- chat panel: an openai-compatible entry point IS chat-shaped ---------
    oa = next((i for i in interfaces if i.get("kind") == "openai-compatible"), None)
    if oa:
        endpoint = oa.get("endpoint")
        out.append({
            "type": "chat",
            "interface": oa.get("name"),
            "endpoint": endpoint,
            "address_install_time": oa.get("address") == "install-time",
            "served_model_id": oa.get("served_model_id"),
            "api_key_env": oa.get("api_key_env"),
            "gap": ("chat-shape inferred from interface kind; io.accepts has no "
                    "ratified conversability vocabulary (direct_message/task_thread)"),
        })

    # --- future: conversation-shaped io on a non-model Cog -------------------
    if any(v in accepts for v in ("direct_message", "task_thread")):
        out.append({
            "type": "chat-io",
            "via": "default entry point, client-held thread (§6.6)",
            "gap": "declared conversability exists but no envelope for chat turns is ratified",
        })

    # --- commands ------------------------------------------------------------
    cmds = [i for i in interfaces if i.get("kind") == "command"]
    if cmds:
        out.append({
            "type": "commands",
            "commands": [{"name": c.get("name"), "task": c.get("task"),
                          "run": f"pixi run {c.get('task')}"} for c in cmds],
            "gap": None,
        })

    # --- lineage card for model-carrying Cogs --------------------------------
    model = m.get("model")
    if isinstance(model, dict):
        card = {"type": "model",
                "name": model.get("name"),
                "quantization": model.get("quantization"),
                "runtime": model.get("runtime"),
                "revision": model.get("revision"),
                "weights_sha256": (model.get("weights") or {}).get("sha256"),
                "gap": None}
        if model.get("base") or model.get("specialization"):
            card["lineage"] = {
                "effective_id": model.get("effective_id"),
                "base": model.get("base"),
                "specialization": model.get("specialization"),
            }
        out.append(card)

    return out


def input_schema(pkg):
    """The PROPOSED input contract (GAPS #2), with provenance.

    Precedence: a manifest-declared `context.input_schema` wins (that is the
    real proposal); a workbench overlay keyed by Cog id fills in for packages
    that predate the proposal; otherwise the examples remain the only template.
    """
    m = pkg["manifest"]
    declared = (m.get("context") or {}).get("input_schema")
    if declared:
        path = Path(pkg["root"]) / declared
        if path.exists():
            try:
                return {"source": "manifest", "path": declared,
                        "schema": json.loads(path.read_text())}
            except json.JSONDecodeError as e:
                return {"source": "manifest", "path": declared,
                        "error": f"declared input schema is not valid JSON: {e}"}
    cog_id = str(m.get("id") or "")
    overlay = OVERLAYS / cog_id.replace("/", "--") / "input-schema.json"
    if overlay.exists():
        return {"source": "overlay", "path": str(overlay),
                "schema": json.loads(overlay.read_text())}
    return {"source": "none", "schema": None,
            "gap": "no input schema declared and no overlay ships for this Cog — "
                   "examples are the only template"}


def _pixi_tasks(root):
    toml_path = Path(root) / "pixi.toml"
    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        return (tomllib.load(f).get("tasks")) or {}


def operations(pkg):
    """Runnable operations, derived from declarations only.

    - every `command` interface -> a one-shot Run button;
    - every endpoint-bearing interface with a `task` -> a Start/Stop service;
    - the Cog's conventional binding tasks (resolve/use/check/eval/test/bundle)
      that exist in its pixi.toml -> Run buttons with an optional args box;
    - each locally-sourced declared satisfier -> a "start dependency" service
      chained from ITS default interface, so the whole stack (model -> resolve
      -> serve) is operable from buttons.
    """
    m = pkg["manifest"]
    root = pkg["root"]
    tasks = _pixi_tasks(root)
    interfaces = m.get("interfaces") or []
    ops, seen = [], set()

    for i in interfaces:
        task = i.get("task")
        if not task or task in seen:
            continue
        seen.add(task)
        if i.get("endpoint") and i.get("kind") in ("http-json", "openai-compatible"):
            base = re.match(r"^(https?://[^/]+)", i["endpoint"])
            ops.append({"mode": "service", "name": i.get("name"), "task": task,
                        "root": root, "endpoint": i["endpoint"],
                        "health_url": (base.group(1) + "/health") if base else None,
                        "label": f"{i.get('name')} ({i.get('kind')})"})
        else:
            ops.append({"mode": "run", "name": i.get("name"), "task": task,
                        "root": root, "label": f"{i.get('name')} (command)",
                        "args_hint": ""})

    for task in CONVENTIONAL_TASKS:
        if task in tasks and task not in seen:
            seen.add(task)
            hint = {"resolve": "--satisfier <path> --endpoint <url> | --dry-run",
                    "use": "<preset> --endpoint <url>",
                    "eval": "--baseline", "bundle": "--repo <path> ..."}.get(task, "")
            ops.append({"mode": "run", "name": task, "task": task, "root": root,
                        "label": f"{task} (binding/verification)", "args_hint": hint})

    for r in m.get("requires") or []:
        if not isinstance(r, dict):
            continue
        for spec in ([r.get("satisfied_by")] if r.get("satisfied_by") else [])                 + (r.get("also_satisfied_by") or []):
            src = spec.get("source")
            if not src:
                continue
            dep_root = (Path(root) / src).resolve()
            try:
                dep, _ = read_manifest(dep_root)
            except PackageError:
                continue
            default = next((i for i in dep.get("interfaces") or []
                            if i.get("default") and i.get("task")), None)
            if not default:
                continue
            key = f"dep::{dep.get('id')}"
            if key in seen:
                continue
            seen.add(key)
            ops.append({"mode": "service", "name": f"dependency: {dep.get('id')}",
                        "task": default["task"], "root": str(dep_root),
                        "endpoint": default.get("endpoint"),
                        "health_url": ((default.get("endpoint") or "").rstrip("/")
                                       + "/models" if default.get("endpoint") else None),
                        "label": f"start {dep.get('id')} ({default.get('kind')})",
                        "dependency": True,
                        # satisfiers of one requirement are ALTERNATIVES —
                        # bring-up needs any one of them, not all of them
                        "capability": r.get("capability")})
    return ops


SKIP_DIRS = {".git", ".pixi", "node_modules", "__pycache__", ".venv", "venv",
             "_to_delete", "_xfer2", ".cache", "var", "overlays"}


def browse(path, scan_depth=3, max_visits=2000):
    """Directory listing + a bounded scan for Cog packages, for the open
    dialog. Read-only METADATA only — directory names and manifest headers,
    never file contents. (The §1 rejection of server-side file browsing was
    about pulling file CONTENT into invoke payloads; finding packages to open
    is the same authority /api/package?path= already has.)"""
    root = Path(path or ".").expanduser().resolve()
    if not root.is_dir():
        raise PackageError(f"{root} is not a directory")
    try:
        children = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError as e:
        raise PackageError(f"cannot list {root}: {e}")
    subdirs = [{"name": p.name, "path": str(p),
                "is_cog": manifest_path(p) is not None,
                "is_git": (p / ".git").exists()}
               for p in children
               if not p.name.startswith(".") and p.name not in SKIP_DIRS]

    cogs, visits, queue = [], 0, [(root, 0)]
    while queue and visits < max_visits:
        d, depth = queue.pop(0)
        visits += 1
        if manifest_path(d) is not None:
            entry = {"path": str(d), "name": d.name}
            try:
                m, _ = read_manifest(d)
                entry.update({"id": m.get("id"), "kind": m.get("kind"),
                              "version": m.get("version"),
                              "summary": (m.get("summary") or "").strip()})
            except Exception:
                entry["error"] = "manifest unreadable"
            cogs.append(entry)
            continue                      # a Cog is a leaf; don't descend
        if depth >= scan_depth:
            continue
        try:
            queue.extend((p, depth + 1) for p in sorted(d.iterdir())
                         if p.is_dir() and not p.is_symlink()
                         and not p.name.startswith(".")
                         and p.name not in SKIP_DIRS)
        except OSError:
            pass
    return {"dir": str(root), "dir_is_git": (root / ".git").exists(),
            "parent": str(root.parent) if root.parent != root else None,
            "subdirs": subdirs, "cogs": cogs, "truncated": bool(queue)}


def derivations(pkg):
    """The x-cog-param `derive` blocks of this Cog's input schema (possibly
    from an overlay). This is the AUTHORITATIVE list — the server refuses any
    derive request whose id is not in it, the same rule runnable operations
    follow. Returns [] when the extension is absent (the degraded path)."""
    s = input_schema(pkg)
    schema = s.get("schema") or {}
    x = schema.get("x-cog-param") or {}
    if x.get("v") != 1:
        return []
    out = []
    for d in x.get("derive") or []:
        if isinstance(d, dict) and d.get("id") and d.get("task") \
                and isinstance(d.get("argv"), list):
            out.append(d)
    return out


def binding_mtime(path):
    """mtime of the installation-state record (model.json), or None.

    A running service reads its binding ONCE at process start; comparing this
    against a process's started_ts is how the workbench detects "the binding
    changed under a running service — restart it to pick the change up."
    """
    p = Path(path).expanduser().resolve() / "model.json"
    try:
        return round(p.stat().st_mtime, 3)
    except OSError:
        return None


def card(pkg):
    """The inspector card: everything a surface needs to render a Cog legibly."""
    m = pkg["manifest"]
    reqs = []
    for r in m.get("requires") or []:
        if not isinstance(r, dict):
            continue
        entry = {"capability": r.get("capability"),
                 "locality": r.get("locality", "any"),
                 "satisfiers": []}
        for spec in ([r.get("satisfied_by")] if r.get("satisfied_by") else []) \
                + (r.get("also_satisfied_by") or []):
            entry["satisfiers"].append({"cog": spec.get("cog"),
                                        "version": spec.get("version"),
                                        "source": spec.get("source")})
        reqs.append(entry)

    binding = pkg.get("binding")
    binding_summary = None
    if isinstance(binding, dict) and "_error" not in binding:
        sat = binding.get("satisfier") or {}
        binding_summary = {
            "endpoint": binding.get("endpoint"),
            "model": binding.get("model"),
            "locality": binding.get("locality"),
            "pinned": binding.get("pinned"),
            "satisfier": sat.get("cog") or sat.get("deployment") or sat.get("source"),
            "declared": sat.get("declared"),
        }
    elif isinstance(binding, dict):
        binding_summary = {"error": binding["_error"]}

    return {
        "id": m.get("id"),
        "version": m.get("version"),
        "kind": m.get("kind"),
        "summary": (m.get("summary") or "").strip(),
        "owner": m.get("owner"),
        "license": m.get("license"),
        "schema": m.get("schema"),
        "locality": m.get("locality"),
        "io": m.get("io"),
        "prohibits": m.get("prohibits") or [],
        "provides": m.get("provides") or [],
        "requires": reqs,
        "interfaces": [{"name": i.get("name"), "kind": i.get("kind"),
                        "endpoint": i.get("endpoint"),
                        "address": i.get("address"),
                        "default": bool(i.get("default"))}
                       for i in (m.get("interfaces") or [])],
        "evaluation_fixtures": (m.get("evaluation") or {}).get("fixtures") or [],
        "binding": binding_summary,   # installation state, clearly separated
        "examples": pkg["examples"],
        "affordances": affordances(pkg),
        "operations": operations(pkg),
        "input_schema": input_schema(pkg),
        "root": pkg["root"],
    }
