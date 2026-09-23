import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import test_suite as fixtures
ROOT = fixtures.ROOT
from workbench_suite import digest

spec = importlib.util.spec_from_file_location('composed_usage', ROOT/'cog-workbench/bridges/composed_usage.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class ComposedUsageTests(unittest.TestCase):
    # Reuse fixture setup without inheriting and rerunning its entire test suite.
    setUpBase = fixtures.SuiteTests.setUp
    seed_model = fixtures.SuiteTests.seed_model
    harness = fixtures.SuiteTests.harness

    def setUp(self):
        self.setUpBase()
        self.clone_temp = tempfile.TemporaryDirectory(prefix='cog-author-test-', dir=ROOT)
        self.addCleanup(self.clone_temp.cleanup)
        self.root = Path(self.clone_temp.name)
        shutil.copytree(ROOT/'cog-author', self.root, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git', '.pixi', '__pycache__', '.op-composition.json', 'runs'))
        (self.root/'.pixi').symlink_to(ROOT/'cog-author/.pixi', target_is_directory=True)
        b = self.harness()
        self.ref = {'binding_id': b['binding_id'], 'revision': b['revision']}
        self.suite.activate_composition(self.root, self.ref)
        self.bundle = json.loads((self.root/'examples/sample-bundle.json').read_text())
        self.output = json.loads((self.root/'context/output-example.json').read_text())
        self.original = self.suite.call

    def fake_call(self, root, task, args=(), **kwargs):
        if task != 'turn':
            return self.original(root, task, args, **kwargs)
        request = json.loads(Path(args[args.index('--request')+1]).read_text())
        binding = json.loads(Path(args[args.index('--binding')+1]).read_text())
        return {'envelope':1, 'ok':True, 'error':None, 'problems':[], 'cog':binding['provider'], 'binding':binding,
            'payload':{'document_kind':'harness_turn_result','contract':request['contract'],
                       'request_id':request['request_id'],'binding':request['binding'],
                       'model_binding':request['model_binding'],'result':self.output,'tool_uses':[]}}

    def invoke(self):
        with patch.object(self.suite, 'call', side_effect=self.fake_call):
            return adapter.invoke(self.root, self.bundle, suite_type=lambda **kw: self.suite)

    def test_consumer_identity_checks_and_revocation(self):
        result = self.invoke()
        self.assertTrue(result['ok'])
        self.assertEqual(result['problems'], [])
        self.assertEqual(result['cog']['id'], 'openteams/cog-author')
        self.assertEqual(result['task'], 'ask-composed')
        self.assertEqual(result['binding']['composition']['binding'], self.ref)
        self.suite.revoke(self.ref)
        with self.assertRaisesRegex(ValueError, 'revoked'):
            self.invoke()

    def test_stale_consumer_refused(self):
        with (self.root/'context/system.md').open('a') as f:
            f.write('\nchanged\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.invoke()

    def test_stale_host_refused(self):
        path = self.root/'.op-composition.json'
        config = json.loads(path.read_text());config.pop('sha256')
        config['host_sha256'] = '0'*64;config['sha256'] = digest(config)
        path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'host changed'):
            self.invoke()

    def test_consumer_change_during_turn_refused(self):
        call = self.fake_call
        def mutate(root, task, args=(), **kwargs):
            result = call(root, task, args, **kwargs)
            if task == 'turn':
                with (self.root/'context/system.md').open('a') as f:
                    f.write('\nchanged while model was running\n')
            return result
        with patch.object(self.suite, 'call', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'during the turn'):
                adapter.invoke(self.root, self.bundle, suite_type=lambda **kw: self.suite)
