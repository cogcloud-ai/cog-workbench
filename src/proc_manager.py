"""Managed processes for the workbench: run a Cog's declared tasks with a
button instead of a copy-paste.

Fills GAPS follow-on: v0 rendered `pixi run <task>` as text because executing
someone's tasks is an authority question. The workbench takes the position that
an INVOCATION ENVIRONMENT holds exactly that authority (it is the §6.6
"surround"), with guardrails:

  - only tasks the Cog DECLARES as interfaces (plus its conventional binding
    tasks) are runnable — never arbitrary commands;
  - commands resolve through pixi when the Cog's locked environment is usable
    on this machine, else fall back to the task string parsed from pixi.toml
    run on system python — the same two-tier rule cog-forge's run-checks.sh
    uses, and the UI labels which tier ran;
  - one running instance per (cog, task); services get start/stop; every run
    is journaled.
"""
import os
import shutil
import shlex
import signal
import subprocess
import threading
import time
import toml_compat as tomllib  # tomllib on 3.11+, honest fallback below
from collections import deque
from pathlib import Path


def _env_python(root):
    p = Path(root) / ".pixi" / "envs" / "default" / "bin" / "python"
    if not p.exists():
        return None
    try:
        subprocess.run([str(p), "-c", ""], capture_output=True, timeout=10)
        return str(p)
    except Exception:
        return None


def resolve_command(root, task):
    """(argv_or_cmd, shell, tier). Prefer the Cog's own locked env via pixi;
    fall back to the raw task string from pixi.toml on this machine's python."""
    root = Path(root)
    toml_path = root / "pixi.toml"
    if not toml_path.exists():
        raise ValueError(f"{root} has no pixi.toml — no tasks to run")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    tasks = data.get("tasks") or {}
    if task not in tasks:
        raise ValueError(f"task {task!r} is not declared in {root.name}/pixi.toml")

    pixi = shutil.which("pixi")
    if not pixi:
        installed = Path.home() / ".pixi" / "bin" / "pixi"
        if installed.is_file():
            pixi = str(installed)
    if pixi and _env_python(root):
        return [pixi, "run", "--frozen", task], False, "pixi (locked env)"

    cmd = tasks[task]
    if isinstance(cmd, dict):
        cmd = cmd.get("cmd", "")
    return str(cmd), True, "fallback (task string on system python)"


def _child_env():
    """Environment for child Cog processes: the workbench may itself be running
    under `pixi run serve`, which exports PIXI_* activation variables. Passing
    those through makes pixi warn about competing manifests (and is the same
    cross-contamination class as cog-demo's activation-env finding), so they
    are scrubbed — each Cog's pixi resolves its OWN manifest from cwd."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PIXI_")}


def run_capture(root, task, argv, timeout=90):
    """Run a declared task ONE-SHOT with extra argv tokens and capture output.

    Used by declared derivation (x-cog-param): `argv` items are DATA — they
    are passed as tokens (pixi tier) or shell-quoted (fallback tier), never
    interpolated as shell text. The task itself still goes through
    resolve_command, so only tasks declared in the Cog's pixi.toml can run.
    Returns (returncode, tail_of_output, tier).
    """
    cmd, shell, tier = resolve_command(root, task)
    argv = [str(a) for a in (argv or [])]
    if shell:
        cmd = cmd + " " + " ".join(shlex.quote(a) for a in argv)
    else:
        cmd = cmd + ["--"] + argv
    try:
        r = subprocess.run(cmd, shell=shell, cwd=str(root), env=_child_env(),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=timeout)
        out = r.stdout or ""
        return r.returncode, out[-4000:], tier
    except subprocess.TimeoutExpired:
        return None, f"[timed out after {timeout}s]", tier


GIT_REFS_MAX = 400


def git_refs(repo):
    """Client capability `git-ref`: enumerate refs of a LOCAL repo, read-only,
    one fixed argv — never a shell, never a Cog-supplied command. Returns
    {"refs": [{name, kind, date}], "head": str|None} or {"error": ...}."""
    repo = Path(repo).expanduser().resolve()
    if not (repo / ".git").exists():
        return {"error": f"{repo} is not a git repository"}
    base = ["git", "-C", str(repo)]
    try:
        r = subprocess.run(
            base + ["for-each-ref", "--sort=-creatordate",
                    "--format=%(refname:short)\t%(refname)\t%(creatordate:iso-strict)",
                    "refs/heads", "refs/tags"],
            capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return {"error": (r.stderr or "git for-each-ref failed").strip()[:300]}
        refs = []
        for line in r.stdout.splitlines()[:GIT_REFS_MAX]:
            parts = line.split("\t")
            if parts and parts[0]:
                refs.append({"name": parts[0],
                             "kind": ("tag" if len(parts) > 1
                                      and parts[1].startswith("refs/tags/") else "branch"),
                             "date": parts[2] if len(parts) > 2 else ""})
        h = subprocess.run(base + ["rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        head = h.stdout.strip() if h.returncode == 0 else None
        hd = subprocess.run(base + ["log", "-1", "--format=%cI", "HEAD"],
                            capture_output=True, text=True, timeout=15)
        head_date = hd.stdout.strip() if hd.returncode == 0 else None
        return {"refs": refs, "head": head, "head_date": head_date}
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"error": str(e)[:300]}


class Proc:
    def __init__(self, pid_key, root, task, tier, popen):
        self.key = pid_key
        self.root = str(root)
        self.task = task
        self.tier = tier
        self.popen = popen
        self.started_at = time.time()
        self.lines = deque(maxlen=800)
        self.line_count = 0

    def snapshot(self):
        rc = self.popen.poll()
        return {"key": self.key, "root": self.root, "task": self.task,
                "tier": self.tier, "pid": self.popen.pid,
                "running": rc is None, "returncode": rc,
                "started_ts": round(self.started_at, 3),
                "uptime_s": round(time.time() - self.started_at, 1),
                "line_count": self.line_count}


class ProcessManager:
    def __init__(self, journal=None):
        self._procs = {}
        self._lock = threading.Lock()
        self._journal = journal        # callable(dict) or None

    @staticmethod
    def key_for(root, task):
        return f"{Path(root).resolve()}::{task}"

    def start(self, root, task, extra_args=None):
        root = Path(root).resolve()
        key = self.key_for(root, task)
        with self._lock:
            existing = self._procs.get(key)
            if existing and existing.popen.poll() is None:
                raise ValueError(f"{root.name}:{task} is already running (pid "
                                 f"{existing.popen.pid}) — stop it first")

            cmd, shell, tier = resolve_command(root, task)
            if extra_args:
                if shell:
                    cmd = f"{cmd} {extra_args}"
                else:
                    cmd = cmd + ["--"] + shlex.split(str(extra_args))

            popen = subprocess.Popen(
                cmd, shell=shell, cwd=str(root), env=_child_env(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True)
            proc = Proc(key, root, task, tier, popen)
            self._procs[key] = proc

        threading.Thread(target=self._pump, args=(proc,), daemon=True).start()
        if self._journal:
            self._journal({"event": "start", "cog": root.name, "task": task,
                           "tier": tier, "pid": popen.pid})
        return proc.snapshot()

    def _pump(self, proc):
        for line in proc.popen.stdout:
            proc.lines.append(line.rstrip("\n"))
            proc.line_count += 1
        rc = proc.popen.wait()
        proc.lines.append(f"[exit {rc}]")
        proc.line_count += 1
        if self._journal:
            self._journal({"event": "exit", "cog": Path(proc.root).name,
                           "task": proc.task, "returncode": rc})

    def stop(self, key):
        with self._lock:
            proc = self._procs.get(key)
        if not proc or proc.popen.poll() is not None:
            return {"stopped": False, "reason": "not running"}
        try:
            os.killpg(os.getpgid(proc.popen.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.popen.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.popen.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self._journal:
            self._journal({"event": "stop", "cog": Path(proc.root).name,
                           "task": proc.task})
        return {"stopped": True}

    def status(self, key):
        proc = self._procs.get(key)
        return proc.snapshot() if proc else None

    def logs(self, key, tail=200):
        proc = self._procs.get(key)
        if not proc:
            return None
        return {"lines": list(proc.lines)[-tail:], **proc.snapshot()}

    def list(self):
        return [p.snapshot() for p in self._procs.values()]

    def stop_all(self):
        for key in list(self._procs):
            self.stop(key)
