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
        import yaml
        requirement = base / 'cog-build-evaluator/cog.yaml'
        value = yaml.safe_load(requirement.read_text())
        value['extensions']['workbench_composition']['required_features'].append('unsupported-review-feature')
        requirement.write_text(yaml.safe_dump(value))
        with self.assertRaisesRegex(ValueError, 'features'):
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

    def test_external_state_is_refused_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / 'state'
            with self.assertRaisesRegex(ValueError, 'Suite state'):
                Suite(ROOT, outside)
            self.assertFalse(outside.exists())

    def test_repair_selects_manifest_and_custom_state(self):
        command = self.suite.repair_command(ROOT / 'cog-author', {'binding_id': 'x', 'revision': 1})
        self.assertIn('--manifest-path', command)
        self.assertIn(str(self.suite.state), command)

    def test_current_absolute_record_loads_and_legacy_digest_has_migration_hint(self):
        b = self.harness(); ref = {'binding_id': b['binding_id'], 'revision': 1}
        path = self.suite.path(ref)
        entry = json.loads(path.read_text()); entry.pop('sha256')
        entry['path'] = str(self.suite.root(entry['path']))
        entry['sha256'] = fixtures.digest(entry); path.write_text(json.dumps(entry))
        self.assertEqual(self.suite.load(ref)['binding'], b)
        entry.pop('sha256'); entry['package_sha256'] = 'legacy-format'
        entry['sha256'] = fixtures.digest(entry); path.write_text(json.dumps(entry))
        with self.assertRaisesRegex(ValueError, 're-admit.*reactivate'):
            self.suite.load(ref)


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
