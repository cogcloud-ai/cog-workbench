"""Read a Cog package and derive what a client can do with it.

This is the INSPECT half of the reference client (starting-point doc §6.2):
pure reading — COG.md frontmatter, cog.yaml, installation state (model.json if
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


def load_package(path):
    """Load a Cog package directory into a structured, read-only view."""
    root = Path(path).expanduser().resolve()
    manifest_path = root / "cog.yaml"
    if not manifest_path.exists():
        raise PackageError(f"{root} is not a Cog package (no cog.yaml)")
    try:
        manifest = yaml.safe_load(manifest_path.read_text()) or {}
    except yaml.YAMLError as e:
        raise PackageError(f"cog.yaml is not valid YAML: {e}")

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
    those notes are the raw material for GAPS.md, the concrete record of where
    the portable contract was not enough for a generic client.
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
            if not (dep_root / "cog.yaml").exists():
                continue
            try:
                dep = yaml.safe_load((dep_root / "cog.yaml").read_text()) or {}
            except yaml.YAMLError:
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
                        "dependency": True})
    return ops


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
