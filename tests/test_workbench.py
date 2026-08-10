"""Workbench-specific tests: runnable operations, process management, and the
proposed input-schema contract with overlay precedence."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cog_package  # noqa: E402
import proc_manager  # noqa: E402


MANIFEST = {
    "schema": "openteams/cog-manifest [0.1]",
    "id": "openteams/test-runner", "version": "0.1.0", "kind": "context",
    "summary": "t", "owner": "t@x", "license": "BSD-3-Clause",
    "io": {"accepts": ["task_request"], "produces": ["brief"]},
    "interfaces": [
        {"name": "web-api", "kind": "http-json",
         "endpoint": "http://127.0.0.1:9993/ask", "task": "serve", "default": True},
        {"name": "cli", "kind": "command", "task": "ask"},
    ],
}

PIXI = """\
[workspace]
name = "t"
[tasks]
serve = "python3 -c 'import time; print(\\"serving\\", flush=True); time.sleep(30)'"
ask = "python3 -c 'print(\\"asked\\")'"
resolve = "python3 -c 'print(\\"resolved\\")'"
quick = "python3 -c 'print(\\"line1\\"); print(\\"line2\\")'"
"""


def write_pkg(tmp, manifest=MANIFEST, pixi=PIXI, input_schema=None):
    root = Path(tmp)
    (root / "cog.yaml").write_text(yaml.safe_dump(manifest))
    (root / "pixi.toml").write_text(pixi)
    if input_schema is not None:
        (root / "context").mkdir(exist_ok=True)
        (root / "context" / "input-schema.json").write_text(json.dumps(input_schema))
    return root


class TestOperations(unittest.TestCase):
    def test_interfaces_and_conventional_tasks_become_ops(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = cog_package.load_package(write_pkg(tmp))
            ops = cog_package.operations(pkg)
        by_task = {o["task"]: o for o in ops}
        self.assertEqual(by_task["serve"]["mode"], "service")
        self.assertEqual(by_task["ask"]["mode"], "run")
        self.assertEqual(by_task["resolve"]["mode"], "run")   # conventional
        self.assertNotIn("quick", by_task)   # declared nowhere -> not an op

    def test_dependency_ops_derived_from_satisfiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            dep_root = Path(tmp) / "dep"
            dep_root.mkdir()
            (dep_root / "cog.yaml").write_text(yaml.safe_dump({
                "id": "openteams/test-model", "version": "0.1.0", "kind": "model",
                "interfaces": [{"name": "web-api", "kind": "openai-compatible",
                                "endpoint": "http://127.0.0.1:9990/v1",
                                "task": "serve", "default": True}],
                "provides": ["model-endpoint/openai-compatible"]}))
            m = dict(MANIFEST)
            m["requires"] = [{"capability": "model-endpoint/openai-compatible",
                              "satisfied_by": {"cog": "openteams/test-model",
                                               "source": "../dep"}}]
            main_root = Path(tmp) / "main"
            main_root.mkdir()
            (main_root / "cog.yaml").write_text(yaml.safe_dump(m))
            (main_root / "pixi.toml").write_text(PIXI)
            ops = cog_package.operations(cog_package.load_package(main_root))
        dep_ops = [o for o in ops if o.get("dependency")]
        self.assertEqual(len(dep_ops), 1)
        self.assertEqual(dep_ops[0]["mode"], "service")
        self.assertEqual(dep_ops[0]["task"], "serve")
        self.assertIn("test-model", dep_ops[0]["name"])

    def test_real_forge_cog_gets_full_chain(self):
        forge = ROOT.parent / "cog-forge" / "cog-release-notes"
        if not (forge / "cog.yaml").exists():
            self.skipTest("forge not present")
        ops = cog_package.operations(cog_package.load_package(forge))
        modes = {(o["task"], o["mode"]) for o in ops if not o.get("dependency")}
        self.assertIn(("serve", "service"), modes)
        self.assertIn(("resolve", "run"), modes)
        # both declared satisfiers (base + LoRA) become startable dependencies
        deps = [o for o in ops if o.get("dependency")]
        self.assertGreaterEqual(len(deps), 1)


class TestInputSchema(unittest.TestCase):
    def test_manifest_declaration_wins(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        m = dict(MANIFEST)
        m["context"] = {"input_schema": "context/input-schema.json"}
        with tempfile.TemporaryDirectory() as tmp:
            pkg = cog_package.load_package(write_pkg(tmp, m, input_schema=schema))
            s = cog_package.input_schema(pkg)
        self.assertEqual(s["source"], "manifest")
        self.assertEqual(s["schema"]["properties"]["x"]["type"], "string")

    def test_overlay_fills_in_for_forge_cogs(self):
        forge = ROOT.parent / "cog-forge" / "cog-ci-failure-analyst"
        if not (forge / "cog.yaml").exists():
            self.skipTest("forge not present")
        s = cog_package.input_schema(cog_package.load_package(forge))
        self.assertEqual(s["source"], "overlay")
        ev = s["schema"]["properties"]["evidence"]
        self.assertEqual(ev["x-cog-input"]["builder"], "file-items")
        self.assertEqual(
            ev["items"]["properties"]["content"]["x-cog-input"]["source"], "file")

    def test_no_schema_is_an_explicit_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = cog_package.input_schema(cog_package.load_package(write_pkg(tmp)))
        self.assertEqual(s["source"], "none")
        self.assertIn("gap", s)


class TestBrowse(unittest.TestCase):
    """The open dialog's backend: directory metadata + a bounded Cog scan."""

    def _tree(self, tmp):
        root = Path(tmp)
        (root / "a").mkdir()
        (root / "a" / "cog.yaml").write_text(yaml.safe_dump(
            {"id": "openteams/cog-a", "kind": "context", "version": "0.1.0",
             "summary": "the a cog"}))
        (root / "b" / "deep").mkdir(parents=True)
        (root / "b" / "deep" / "cog.yaml").write_text("id: openteams/cog-b\n")
        (root / ".hidden").mkdir()
        (root / ".hidden" / "cog.yaml").write_text("id: nope\n")
        (root / "_to_delete").mkdir()
        (root / "plain").mkdir()
        return root

    def test_scan_finds_cogs_and_skips_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = cog_package.browse(self._tree(tmp))
        ids = {c.get("id") for c in b["cogs"]}
        self.assertEqual(ids, {"openteams/cog-a", "openteams/cog-b"})
        names = {d["name"]: d["is_cog"] for d in b["subdirs"]}
        self.assertEqual(names, {"a": True, "b": False, "plain": False})
        self.assertIsNotNone(b["parent"])

    def test_cog_is_a_leaf_and_bad_dir_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp)
            (root / "a" / "nested").mkdir()
            (root / "a" / "nested" / "cog.yaml").write_text("id: inner\n")
            b = cog_package.browse(root)
            self.assertNotIn("inner", {c.get("id") for c in b["cogs"]})
            with self.assertRaises(cog_package.PackageError):
                cog_package.browse(root / "does-not-exist")


class TestBindingStaleness(unittest.TestCase):
    """A service reads its binding record once at start; the workbench compares
    model.json's mtime with the process's started_ts to flag stale services."""

    def test_no_record_means_no_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(cog_package.binding_mtime(write_pkg(tmp)))

    def test_record_mtime_reported_and_orders_against_start(self):
        pm = proc_manager.ProcessManager()
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp)
            snap = pm.start(root, "serve")
            self.assertIn("started_ts", snap)
            time.sleep(0.05)
            (root / "model.json").write_text("{}")   # resolve ran AFTER start
            mtime = cog_package.binding_mtime(root)
            self.assertIsNotNone(mtime)
            self.assertGreater(mtime, snap["started_ts"])   # -> stale
            pm.stop(snap["key"])


class TestTomlCompat(unittest.TestCase):
    """The fallback parser (no tomllib before Python 3.11) must read the exact
    subset our pixi.toml files use, and refuse [tasks] shapes it can't."""

    def test_fallback_reads_real_pixi_toml(self):
        import toml_compat
        text = (ROOT / "pixi.toml").read_text()
        tasks = toml_compat._fallback_parse(text)["tasks"]
        self.assertIn("serve", tasks)
        self.assertTrue(tasks["serve"].startswith("python "))

    def test_fallback_handles_escaped_quotes(self):
        import toml_compat
        tasks = toml_compat._fallback_parse(PIXI)["tasks"]
        self.assertIn('print("serving", flush=True)', tasks["serve"])

    def test_fallback_lenient_outside_tasks_strict_inside(self):
        import toml_compat
        ok = '[workspace]\nplatforms = ["a", "b"]\n[tasks]\nx = "echo hi"\n'
        self.assertEqual(toml_compat._fallback_parse(ok)["tasks"]["x"], "echo hi")
        bad = '[tasks]\nx = { cmd = "echo hi" }\n'
        with self.assertRaises(ValueError):
            toml_compat._fallback_parse(bad)


class TestProcessManager(unittest.TestCase):
    def test_fallback_command_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp)
            cmd, shell, tier = proc_manager.resolve_command(root, "quick")
        self.assertTrue(shell)
        self.assertIn("fallback", tier)
        self.assertIn("line1", cmd)

    def test_undeclared_task_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp)
            with self.assertRaises(ValueError):
                proc_manager.resolve_command(root, "rm-rf-everything")

    def test_run_capture_and_exit(self):
        pm = proc_manager.ProcessManager()
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp)
            snap = pm.start(root, "quick")
            for _ in range(50):
                if not pm.status(snap["key"])["running"]:
                    break
                time.sleep(0.1)
            logs = pm.logs(snap["key"])
        self.assertIn("line1", logs["lines"])
        self.assertIn("line2", logs["lines"])
        self.assertEqual(logs["returncode"], 0)

    def test_service_start_stop_and_double_start_refused(self):
        pm = proc_manager.ProcessManager()
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp)
            snap = pm.start(root, "serve")
            time.sleep(0.4)
            self.assertTrue(pm.status(snap["key"])["running"])
            with self.assertRaises(ValueError):
                pm.start(root, "serve")
            r = pm.stop(snap["key"])
            self.assertTrue(r["stopped"])
            time.sleep(0.2)
            self.assertFalse(pm.status(snap["key"])["running"])

    def test_journal_called(self):
        events = []
        pm = proc_manager.ProcessManager(journal=events.append)
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp)
            snap = pm.start(root, "quick")
            for _ in range(50):
                if not pm.status(snap["key"])["running"]:
                    break
                time.sleep(0.1)
        kinds = [e["event"] for e in events]
        self.assertIn("start", kinds)
        self.assertIn("exit", kinds)


if __name__ == "__main__":
    unittest.main()
