"""Model-free tests for the reference client: package inspection, affordance
derivation from declared parts, and generic envelope interpretation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cog_package  # noqa: E402
import cog_invoke  # noqa: E402


CONTEXT_COG = {
    "schema": "openteams/cog-manifest [0.1]",
    "id": "openteams/test-context", "version": "0.1.0", "kind": "context",
    "summary": "test", "owner": "t@x", "license": "BSD-3-Clause",
    "io": {"accepts": ["task_request"], "produces": ["brief"]},
    "prohibits": ["post_anything"],
    "requires": [{"capability": "model-endpoint/openai-compatible", "locality": "any",
                  "satisfied_by": {"cog": "openteams/m", "version": ">=0.1.0",
                                   "source": "../m"}}],
    "interfaces": [
        {"name": "web-api", "kind": "http-json",
         "endpoint": "http://127.0.0.1:9991/ask", "default": True},
        {"name": "cli", "kind": "command", "task": "ask"},
        {"name": "health", "kind": "command", "task": "check"},
    ],
    "evaluation": {"fixtures": ["evals/smoke.fixture.yaml"]},
}

MODEL_COG = {
    "schema": "openteams/cog-manifest [0.1]",
    "id": "openteams/test-model", "version": "0.1.0", "kind": "model",
    "summary": "m", "owner": "t@x", "license": "BSD-3-Clause",
    "model": {"name": "Test-3B", "quantization": "Q4",
              "weights": {"sha256": "ab" * 32}, "runtime": "llama.cpp"},
    "interfaces": [{"name": "web-api", "kind": "openai-compatible",
                    "endpoint": "http://127.0.0.1:9990/v1",
                    "served_model_id": "test-3b", "default": True}],
    "provides": ["model-endpoint/openai-compatible"],
}

DESCRIPTOR_COG = {
    "schema": "openteams/cog-manifest [0.1]",
    "id": "openteams/test-deploy", "version": "0.1.0", "kind": "model",
    "summary": "d", "owner": "t@x", "license": "BSD-3-Clause",
    "locality": "customer-vpc",
    "model": {"name": "Big/Model", "runtime": "vllm", "revision": None},
    "interfaces": [{"name": "web-api", "kind": "openai-compatible",
                    "address": "install-time", "served_model_id": "Big/Model",
                    "api_key_env": "K", "default": True}],
    "provides": ["model-endpoint/openai-compatible"],
}


def write_pkg(tmp, manifest, examples=(), binding=None, cogmd=True):
    root = Path(tmp)
    (root / "cog.yaml").write_text(yaml.safe_dump(manifest))
    if cogmd:
        (root / "COG.md").write_text(
            f"---\ntype: cog [0.1]\nname: {root.name}\nversion: \"0.1.0\"\n"
            f"manifest: cog.yaml\nmanifest_schema: {manifest['schema']}\n---\n\n# Hi\n\nBody.")
    if examples:
        (root / "examples").mkdir()
        for name, content in examples:
            (root / "examples" / name).write_text(json.dumps(content))
    if binding is not None:
        (root / "model.json").write_text(json.dumps(binding))
    return root


class TestInspect(unittest.TestCase):
    def test_card_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp, CONTEXT_COG, examples=[("a.json", {"x": 1})])
            card = cog_package.card(cog_package.load_package(root))
        self.assertEqual(card["id"], "openteams/test-context")
        self.assertEqual(card["kind"], "context")
        self.assertEqual(card["prohibits"], ["post_anything"])
        self.assertEqual(card["examples"], ["a.json"])
        self.assertEqual(card["requires"][0]["satisfiers"][0]["cog"], "openteams/m")
        self.assertEqual([i["name"] for i in card["interfaces"] if i["default"]],
                         ["web-api"])

    def test_not_a_cog(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(cog_package.PackageError):
                cog_package.load_package(tmp)

    def test_binding_summary_present_and_separated(self):
        binding = {"endpoint": "http://127.0.0.1:1/v1", "model": "m",
                   "locality": "local", "pinned": True,
                   "satisfier": {"cog": "openteams/m", "declared": True}}
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp, CONTEXT_COG, binding=binding)
            card = cog_package.card(cog_package.load_package(root))
        self.assertEqual(card["binding"]["satisfier"], "openteams/m")
        self.assertTrue(card["binding"]["pinned"])

    def test_no_binding_is_none_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp, CONTEXT_COG)
            card = cog_package.card(cog_package.load_package(root))
        self.assertIsNone(card["binding"])


class TestAffordances(unittest.TestCase):
    def _aff(self, manifest, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_pkg(tmp, manifest, **kw)
            return cog_package.affordances(cog_package.load_package(root))

    def test_context_cog_gets_task_commands_no_chat(self):
        aff = self._aff(CONTEXT_COG, examples=[("a.json", {})])
        types = {a["type"] for a in aff}
        self.assertIn("task", types)
        self.assertIn("commands", types)
        self.assertNotIn("chat", types)
        task = next(a for a in aff if a["type"] == "task")
        self.assertEqual(task["endpoint"], "http://127.0.0.1:9991/ask")
        self.assertEqual(task["health_url"], "http://127.0.0.1:9991/health")
        self.assertEqual(task["examples"], ["a.json"])
        self.assertIsNone(task["input_schema"])   # the headline gap, explicit

    def test_model_cog_gets_chat_and_lineage_no_task(self):
        aff = self._aff(MODEL_COG)
        types = {a["type"] for a in aff}
        self.assertIn("chat", types)
        self.assertIn("model", types)
        self.assertNotIn("task", types)
        chat = next(a for a in aff if a["type"] == "chat")
        self.assertEqual(chat["served_model_id"], "test-3b")
        self.assertFalse(chat["address_install_time"])

    def test_descriptor_chat_needs_address(self):
        aff = self._aff(DESCRIPTOR_COG)
        chat = next(a for a in aff if a["type"] == "chat")
        self.assertTrue(chat["address_install_time"])
        self.assertIsNone(chat["endpoint"])
        self.assertEqual(chat["api_key_env"], "K")

    def test_undeclared_io_is_a_named_gap(self):
        m = dict(CONTEXT_COG)
        m.pop("io")
        aff = self._aff(m)
        task = next(a for a in aff if a["type"] == "task")
        self.assertIn("io.accepts", task["gap"])

    def test_composed_model_lineage_surfaces(self):
        m = dict(MODEL_COG,
                 model={"effective_id": "eff",
                        "base": {"cog": "openteams/base", "sha256": "ab" * 32},
                        "specialization": {"type": "lora", "sha256": "cd" * 32},
                        "runtime": {"name": "llama.cpp", "version": "1",
                                    "adapter_mode": "separate"}})
        aff = self._aff(m)
        model = next(a for a in aff if a["type"] == "model")
        self.assertEqual(model["lineage"]["effective_id"], "eff")


class TestEnvelopeInterpretation(unittest.TestCase):
    def _fake_response(self, payload):
        return mock.patch.object(cog_invoke, "_post_json",
                                 return_value=(200, payload, 0.01, None))

    def test_payload_key_discovered_and_gap_recorded(self):
        env = {"notes": {"title": "t"}, "raw": "...", "problems": [],
               "latency_s": 1.0, "binding": {"model_identity": "verified"}}
        with self._fake_response(env):
            r = cog_invoke.invoke_task("http://x/ask", {})
        self.assertTrue(r["ok"])
        self.assertEqual(r["payload_key"], "notes")
        self.assertEqual(r["payload"], {"title": "t"})
        self.assertTrue(any("heuristically" in g for g in r["gaps"]))

    def test_problems_with_200_is_a_named_gap(self):
        env = {"brief": {}, "problems": ["x cites unknown evidence"],
               "raw": "", "binding": {}}
        with self._fake_response(env):
            r = cog_invoke.invoke_task("http://x/ask", {})
        self.assertEqual(r["problems"], ["x cites unknown evidence"])
        self.assertTrue(any("HTTP 200" in g for g in r["gaps"]))

    def test_error_envelope_passthrough(self):
        with mock.patch.object(cog_invoke, "_post_json",
                               return_value=(422, {"error": "invalid-bundle",
                                                   "detail": ["missing id"]}, 0.01, None)):
            r = cog_invoke.invoke_task("http://x/ask", {})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "invalid-bundle")

    def test_transport_failure(self):
        with mock.patch.object(cog_invoke, "_post_json",
                               return_value=(None, None, 0.01, "ConnectionRefused")):
            r = cog_invoke.invoke_task("http://x/ask", {})
        self.assertFalse(r["ok"])
        self.assertIn("ConnectionRefused", r["transport_error"])

    def test_chat_turn_parses_openai_shape(self):
        payload = {"model": "m", "choices": [{"message": {"content": "hi there"}}]}
        with mock.patch.object(cog_invoke, "_post_json",
                               return_value=(200, payload, 0.01, None)):
            r = cog_invoke.chat_turn("http://x/v1", [{"role": "user", "content": "hi"}])
        self.assertTrue(r["ok"])
        self.assertEqual(r["text"], "hi there")

    def test_redact_endpoint(self):
        self.assertEqual(cog_invoke.redact_endpoint("https://u:p@h/v1"), "https://h/v1")


class TestRealForgePackages(unittest.TestCase):
    """Optional: exercises the legacy "forge" Cogs (internal packages, not part
    of the suite) when a checkout happens to sit beside this repo; skipped
    otherwise."""
    FORGE = Path(__file__).resolve().parent.parent.parent / "cog-forge"

    def test_release_notes_card(self):
        if not (self.FORGE / "cog-release-notes" / "cog.yaml").exists():
            self.skipTest("optional legacy forge packages (not part of the suite) not present")
        card = cog_package.card(cog_package.load_package(self.FORGE / "cog-release-notes"))
        types = {a["type"] for a in card["affordances"]}
        self.assertIn("task", types)
        self.assertIn("commands", types)
        self.assertEqual(card["kind"], "context")

    def test_collab_descriptor_card(self):
        if not (self.FORGE / "cog-collab-qwen35b" / "cog.yaml").exists():
            self.skipTest("optional legacy forge packages (not part of the suite) not present")
        card = cog_package.card(cog_package.load_package(self.FORGE / "cog-collab-qwen35b"))
        chat = next(a for a in card["affordances"] if a["type"] == "chat")
        self.assertTrue(chat["address_install_time"])


if __name__ == "__main__":
    unittest.main()
