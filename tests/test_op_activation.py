"""Bulk activation and portable installation records; no provider inference."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import test_suite as fixtures
from workbench_suite import Suite, package_digest

ROOT = fixtures.ROOT


class ActivationTests(unittest.TestCase):
    setUp = fixtures.SuiteTests.setUp
    seed_model = fixtures.SuiteTests.seed_model
    harness = fixtures.SuiteTests.harness

    def test_whole_builder_activates_each_consumer_once_and_then_is_current(self):
        b = self.harness(); ref = {'binding_id': b['binding_id'], 'revision': 1}
        # Clone consumers so tests never install bindings into working packages.
        base = Path(self.temp.name)
        for name in ('cog-author', 'cog-build-evaluator', 'cog-build-candidate', 'cog-verify-candidate', 'op-cog-builder'):
            shutil.copytree(ROOT / name, base / name, ignore=shutil.ignore_patterns('.git', '.pixi', '__pycache__', 'runs', '.op-composition.json'))
        result = self.suite.activate_op(base / 'op-cog-builder', ref)
        self.assertEqual({r['composition']['consumer']['id'] for r in result['consumers']},
                         {'openteams/cog-author', 'openteams/cog-build-evaluator'})
        self.assertEqual({r['status'] for r in result['consumers']}, {'activated'})
        self.assertTrue(any(len(r['steps']) > 1 for r in result['consumers']))
        again = self.suite.activate_op(base / 'op-cog-builder', ref)
        self.assertEqual({r['status'] for r in again['consumers']}, {'already-current'})
        for r in result['consumers']:
            doc = json.loads(Path(r['path']).read_text())
            self.assertFalse(Path(doc['composition']['path']).is_absolute())
            self.assertFalse(Path(doc['state']).is_absolute())
            self.assertNotIn('record_path', doc['composition'])

    def test_preflight_failure_does_not_write_earlier_consumer_activation(self):
        b = self.harness(); ref = {'binding_id': b['binding_id'], 'revision': 1}
        base = Path(self.temp.name)
        for name in ('cog-author', 'cog-build-evaluator', 'cog-build-candidate', 'cog-verify-candidate', 'op-cog-builder'):
            shutil.copytree(ROOT / name, base / name, ignore=shutil.ignore_patterns('.git', '.pixi', '__pycache__', 'runs', '.op-composition.json'))
        original = self.suite.activation
        def fail_last(context, selected):
            if Path(context).name == 'cog-build-evaluator':
                raise ValueError('incompatible binding')
            return original(context, selected)
        with patch.object(self.suite, 'activation', side_effect=fail_last), self.assertRaisesRegex(ValueError, 'incompatible'):
            self.suite.activate_op(base / 'op-cog-builder', ref)
        self.assertFalse((base / 'cog-author/.op-composition.json').exists())

    def test_binding_records_move_with_workspace_and_still_check_revocation(self):
        b = self.harness(); ref = {'binding_id': b['binding_id'], 'revision': 1}
        old = self.suite.workspace
        with tempfile.TemporaryDirectory() as directory:
            moved = Path(directory)
            for name in ('cog-turn-harness', 'cog-openrouter'):
                shutil.copytree(old / name, moved / name, ignore=shutil.ignore_patterns('.git', '.pixi', '__pycache__', 'runs', 'var'))
            state = moved / 'state'; shutil.copytree(self.suite.state, state)
            relocated = Suite(moved, state, journal=lambda x: None)
            self.assertEqual(relocated.load(ref)['binding'], b)
            relocated.revoke(ref)
            with self.assertRaisesRegex(ValueError, 'revoked'):
                relocated.load(ref)


class BehaviorDigestTests(unittest.TestCase):
    def test_evidence_and_prose_do_not_invalidate_but_every_behavior_directory_does(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pixi.toml').write_text('[tasks]\n')
            before = package_digest(root)
            for name in ('README.md', 'COG.md', 'pixi.lock', 'tests/new.py', 'examples/new.json', 'evals/new.json'):
                path = root / name; path.parent.mkdir(exist_ok=True); path.write_text('evidence or prose')
                self.assertEqual(package_digest(root), before, name)
            for folder in ('context', 'src', 'scripts', 'binding', 'contracts'):
                path = root / folder / 'behavior'; path.parent.mkdir(exist_ok=True); path.write_text('new behavior')
                after = package_digest(root)
                self.assertNotEqual(after, before, folder)
                before = after
