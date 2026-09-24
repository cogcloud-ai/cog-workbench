"""System One composition: decision Cogs compose with `system-one/decisions`
bindings (cog-typesafe, cog-system-one-adapter), never with chat harnesses,
and chat context Cogs never compose with System One bindings. Model-free: the
provider's turn is replaced with a recorded System One result."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from workbench_suite import Suite, clean, digest, package_digest
ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ('cog-typesafe', 'cog-system-one-adapter', 'cog-brief-router', 'cog-turn-harness', 'cog-openrouter')


@unittest.skipUnless(all((ROOT / name / 'COG.md').is_file() for name in REQUIRED), 'System One siblings not checked out')
class SystemOneCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='suite-s1-')
        self.addCleanup(self.temp.cleanup)
        self.suite = Suite(ROOT, Path(self.temp.name) / 'state', journal=lambda x: None)

    def seed_model(self):
        b = json.loads((ROOT / 'cog-turn-harness/tests/model-binding.json').read_text())
        b.update(binding_id='binding-model', revision=1, features=['text-generation', 'json-output'], locality='cloud')
        root = ROOT / 'cog-openrouter'
        entry = {'request': {}, 'binding': b, 'path': str(root), 'package_sha256': package_digest(root),
                 'model_requirement': None, 'host_state': None, 'candidate_sha256': 'test-only'}
        entry['sha256'] = digest(entry)
        self.suite.path({'binding_id': 'binding-model', 'revision': 1}).write_text(json.dumps(entry))
        return {'binding_id': 'binding-model', 'revision': 1}

    def adapter_binding(self):
        model = self.seed_model()
        request = json.loads((ROOT / 'cog-system-one-adapter/examples/bind-request.json').read_text())
        request['configuration'].update(model_binding=model, locality='cloud')
        request['requirement']['allowed_localities'] = ['cloud']
        return self.suite.bind('cog-system-one-adapter', request)

    def test_both_system_one_providers_are_discoverable(self):
        rows = self.suite.select({'capability': 'system-one/decisions',
                                  'accepted_compositions': ['model+harness', 'harness']})
        self.assertEqual({r['id'] for r in rows}, {'openteams/cog-typesafe', 'openteams/cog-system-one-adapter'})
        rows = self.suite.select({'capability': 'agentic-harness/chat', 'accepted_compositions': ['harness']})
        self.assertNotIn('openteams/cog-system-one-adapter', {r['id'] for r in rows})

    def test_adapter_binding_composes_and_invokes_a_decision_cog(self):
        b = self.adapter_binding()
        self.assertEqual((b['composition'], b['capability'], b['state']), ('harness', 'system-one/decisions', 'admitted'))
        ref = {'binding_id': b['binding_id'], 'revision': b['revision']}
        composition = self.suite.compose('cog-brief-router', ref)
        self.assertEqual(composition['model_binding'], {'binding_id': 'binding-model', 'revision': 1})
        bundle = json.loads((ROOT / 'cog-brief-router/examples/sample-bundle.json').read_text())
        answers = json.loads((ROOT / 'cog-brief-router/examples/sample-result.json').read_text())
        answers['answer_source'] = 'llm-adapter'
        original, seen = self.suite.call, []

        def call(root, task, args=(), **kwargs):
            if task != 'turn':
                return original(root, task, args, **kwargs)
            request = json.loads(Path(args[args.index('--request') + 1]).read_text())
            binding = json.loads(Path(args[args.index('--binding') + 1]).read_text())
            seen.append(request)
            self.assertIn('--model-binding', args)
            return {'envelope': 1, 'ok': True, 'error': None, 'problems': [], 'cog': binding['provider'],
                    'binding': binding, 'payload': {'document_kind': 'harness_turn_result', 'contract': request['contract'],
                    'request_id': request['request_id'], 'binding': request['binding'],
                    'model_binding': request['model_binding'], 'result': answers, 'tool_uses': []}}

        with patch.object(self.suite, 'call', side_effect=call):
            result = self.suite.invoke(composition, bundle)
        payload = clean(result)
        self.assertEqual(payload['decision']['recommendation'], 'decision')
        self.assertEqual(payload['answered_by'], {'model': 'illustrative-fixture', 'answer_source': 'llm-adapter'})
        self.assertEqual(result['binding']['evidence_scope'], 'composed-system')
        self.assertEqual(result['binding']['harness']['harness']['id'], 'typesafe/system-one-adapter')
        turn = seen[0]
        self.assertEqual(turn['context'], [])
        self.assertEqual(set(turn['task']), {'state', 'questions'})
        self.assertNotIn('cog_kind', json.dumps(turn['task']['state']))

    def test_answers_that_do_not_fit_fail_the_invocation(self):
        b = self.adapter_binding()
        composition = self.suite.compose('cog-brief-router', {'binding_id': b['binding_id'], 'revision': 1})
        bundle = json.loads((ROOT / 'cog-brief-router/examples/sample-bundle.json').read_text())
        answers = json.loads((ROOT / 'cog-brief-router/examples/sample-result.json').read_text())
        del answers['answers']['rules_suffice']
        original = self.suite.call

        def call(root, task, args=(), **kwargs):
            if task != 'turn':
                return original(root, task, args, **kwargs)
            request = json.loads(Path(args[args.index('--request') + 1]).read_text())
            binding = json.loads(Path(args[args.index('--binding') + 1]).read_text())
            return {'envelope': 1, 'ok': True, 'error': None, 'problems': [], 'cog': binding['provider'],
                    'binding': binding, 'payload': {'document_kind': 'harness_turn_result', 'contract': request['contract'],
                    'request_id': request['request_id'], 'binding': request['binding'],
                    'model_binding': request['model_binding'], 'result': answers, 'tool_uses': []}}

        with patch.object(self.suite, 'call', side_effect=call):
            result = self.suite.invoke(composition, bundle)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'answers-invalid')

    def test_capabilities_never_cross(self):
        b = self.adapter_binding()
        with self.assertRaisesRegex(ValueError, 'capability'):
            self.suite.compose('cog-author', {'binding_id': b['binding_id'], 'revision': 1})
        request = json.loads((ROOT / 'cog-turn-harness/examples/bind-request.json').read_text())
        request['configuration']['model_binding'] = {'binding_id': 'binding-model', 'revision': 1}
        chat = self.suite.bind('cog-turn-harness', request)
        with self.assertRaisesRegex(ValueError, 'capability'):
            self.suite.compose('cog-brief-router', {'binding_id': chat['binding_id'], 'revision': 1})

    def test_a_model_binding_is_never_composed_directly(self):
        model = self.seed_model()
        with self.assertRaises(ValueError):
            self.suite.compose('cog-brief-router', model)


if __name__ == '__main__':
    unittest.main()
