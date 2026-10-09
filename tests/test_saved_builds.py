"""Saved build discovery and native continuation, no provider calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from workbench_suite import Suite

class SavedBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.builder=self.root/'op-cog-builder';self.builder.mkdir()
        self.suite=Suite(self.root,self.root/'state',journal=lambda _:None)
        self.cycle=self.builder/'cycles/demo';self.run=self.cycle/'phases/0000/package/runs/child';self.run.mkdir(parents=True)
        self.write(self.run/'input.json',{})
        self.write(self.run/'pending/design.json',{'run_id':'child','artifact':{'kind':'cog-contract'},'payload_sha256':'test','artifact_sha256':'test'})
        self.write(self.run/'track.json',{'input_request':str(self.run/'input.json'),'steps':[{'id':'design','status':'awaiting-decision'}]})
        self.write(self.cycle/'cycle.json',{'status':'awaiting-decision','input_request':str(self.root/'native-input.json'),'phases':[{'run_dir':str(self.run),'package':str(self.run.parents[1])}]})
    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def test_reload_reads_native_gate_without_process_memory(self):
        other=Suite(self.root,self.root/'state',journal=lambda _:None)
        value=other.inspect_builder('demo')
        self.assertTrue(value['actions']['decide']);self.assertFalse(value['actions']['resume'])
        self.assertEqual(value['pending']['artifact']['kind'],'cog-contract')
        self.assertEqual(other.builder_runs()[0]['current_step'],'design')
    def test_rejection_and_exhaustion_offer_no_continuation(self):
        for status in ('rejected','refused','budget-exhausted','completed'):
            self.write(self.cycle/'cycle.json',{'status':status,'phases':[]})
            self.assertEqual(self.suite.inspect_builder('demo')['actions'],{'decide':False,'resume':False})
            with self.assertRaises(ValueError):self.suite.resume_builder('demo')
    def test_interrupted_phase_is_discovered(self):
        self.write(self.cycle/'cycle.json',{'status':'running','phases':[{'package':str(self.run.parents[1])}]})
        self.assertEqual(self.suite.inspect_builder('demo')['track']['input_request'],str(self.run/'input.json'))
    def test_identity_and_evidence_cannot_escape_workspace(self):
        with self.assertRaises(ValueError):self.suite.inspect_builder('../../outside')
        with self.assertRaises(ValueError):self.suite.builder_document('/etc/passwd')
    def test_decision_uses_declared_smith_helper_then_native_cycle(self):
        def call(root,task,args):
            self.assertEqual((root,task),('cog-smith','op-decide'))
            self.assertIn('--reject-artifact',args);self.assertIn('--reason',args)
            Path(args[args.index('--output')+1]).write_text('{}')
            return {}
        with patch.object(self.suite,'call',side_effect=call),patch.object(self.suite,'builder_operation',return_value={'status':'rejected'}) as operation:
            result=self.suite.resume_builder('demo',{'verdict':'reject','by':'learner','reason':'Wrong contract','step':'design','artifact_sha256':'test','run_id':'child'})
            self.assertEqual(result['status'],'rejected');self.assertIn('--decision',operation.call_args.args[0])
    def test_stale_gate_cannot_accept_unseen_artifact(self):
        with patch.object(self.suite, 'call') as helper, patch.object(self.suite, 'builder_operation') as operation:
            with self.assertRaisesRegex(ValueError, 'displayed Gate changed'):
                self.suite.resume_builder('demo', {'verdict': 'accept', 'by': 'learner',
                    'step': 'design', 'artifact_sha256': 'old', 'run_id': 'child'})
        helper.assert_not_called(); operation.assert_not_called()

    def test_changed_provider_revision_refuses_resume(self):
        binding={'binding_id':'original','revision':1}
        self.write(self.cycle/'workbench-binding.json',binding)
        for consumer in ('cog-author','cog-build-evaluator'):
            self.write(self.root/consumer/'.op-composition.json',{'composition':{'binding':{'binding_id':'other','revision':1}}})
        with patch.object(self.suite,'load',return_value={}),patch.object(self.suite,'builder_operation') as operation:
            with self.assertRaisesRegex(ValueError,'provider revision changed'):
                self.suite.resume_builder('demo',{'verdict':'accept','by':'learner','step':'design','artifact_sha256':'test','run_id':'child'})
        operation.assert_not_called()

    def test_builder_command_is_declared_fixed_and_scrubs_pixi(self):
        (self.builder/'pixi.toml').write_text('[tasks]\ncycle="python src/op_cycle.py"\n')
        python=self.builder/'.pixi/envs/default/bin/python';python.parent.mkdir(parents=True);python.touch()
        with patch.dict(os.environ,{'PIXI_PROJECT_ROOT':'wrong'}),patch('workbench_suite.subprocess.run',return_value=subprocess.CompletedProcess([],3,'{"status":"awaiting-decision"}','')) as run:
            result=self.suite.builder_operation(['--resume','literal $(unchanged)'])
            self.assertEqual(result['exit_code'],3);self.assertNotIn('PIXI_PROJECT_ROOT',run.call_args.kwargs['env'])
            self.assertEqual(run.call_args.args[0][-1],'literal $(unchanged)')
        (self.builder/'pixi.toml').write_text('[tasks]\ncycle="sh arbitrary"\n')
        with self.assertRaises(ValueError):self.suite.builder_operation([])

    def test_interrupted_first_turn_keeps_binding_and_missing_activation_has_command(self):
        binding={'binding_id':'original','revision':1}
        def interrupt(args):
            path=args[1]
            self.write(self.cycle/'cycle.json',{'status':'running','input_request':path,'phases':[]})
            raise OSError('interrupted first turn')
        with patch.object(self.suite,'activate_op'),patch.object(self.suite,'builder_operation',side_effect=interrupt),self.assertRaises(OSError):
            self.suite.start_builder({'brief':'fictional'},binding)
        other=Suite(self.root,self.root/'state',journal=lambda _:None)
        self.assertEqual(other.inspect_builder('demo')['binding'],binding)
        (self.root/'cog-author').mkdir()
        with patch.object(other,'load',return_value={}),patch.object(other,'builder_operation') as operation:
            with self.assertRaisesRegex(ValueError,'activate-op --op op-cog-builder.*--binding-id original --revision 1'):
                other.resume_builder('demo')
        operation.assert_not_called()
        for consumer in ('cog-author','cog-build-evaluator'):
            self.write(self.root/consumer/'.op-composition.json',{'composition':{'binding':{'binding_id':'new','revision':2}}})
        with patch.object(other,'load',return_value={}),patch.object(other,'builder_operation') as operation,self.assertRaisesRegex(ValueError,'provider revision changed'):
            other.resume_builder('demo')
        operation.assert_not_called()

    def test_changed_provider_package_explains_why_new_build_is_required(self):
        self.write(self.cycle/'workbench-binding.json',{'binding_id':'original','revision':1})
        with patch.object(self.suite,'load',side_effect=ValueError('Provider package or fingerprint format changed')),self.assertRaisesRegex(ValueError,'Start a new build'):
            self.suite.resume_builder('demo')

    def test_missing_admission_retains_gate_and_evidence_but_disables_continuation(self):
        request=self.suite.state/'build-inputs/input.json'
        self.write(request,{'brief':'fictional'})
        self.write(self.cycle/'cycle.json',{'status':'paused','input_request':str(request),'phases':[{'run_dir':str(self.run),'package':str(self.run.parents[1])}]})
        self.write(self.run/'review.json',{'payload':{'reason':'Retained synthetic evidence'}})
        track=json.loads((self.run/'track.json').read_text())
        track['steps'].append({'id':'review','status':'passed','envelope':str(self.run/'review.json')})
        self.write(self.run/'track.json',track)
        for status in ('paused','completed'):
            state=json.loads((self.cycle/'cycle.json').read_text());state['status']=status;self.write(self.cycle/'cycle.json',state)
            run=self.suite.inspect_builder('demo')
            self.assertEqual(run['status'],status);self.assertIn('receipt is missing',run['binding_problem'])
            self.assertEqual(run['pending']['run_id'],'child')
            self.assertEqual(run['evidence']['review']['payload']['reason'],'Retained synthetic evidence')
            self.assertEqual(run['actions'],{'resume':False,'decide':False})
            self.assertEqual(self.suite.builder_runs()[0]['status'],status)
            with patch.object(self.suite,'builder_operation') as invoke,self.assertRaisesRegex(ValueError,'receipt is missing'):
                self.suite.resume_builder('demo')
            invoke.assert_not_called()

    def test_legacy_builder_without_input_identity_is_refused_after_start_and_on_resume(self):
        self.write(self.cycle/'cycle.json',{'status':'running','phases':[]})
        with patch.object(self.suite,'activate_op'),patch.object(self.suite,'builder_operation',return_value={'cycle_dir':str(self.cycle),'status':'running'}),self.assertRaisesRegex(ValueError,'Update the public builder'):
            self.suite.start_builder({'brief':'fictional'},{'binding_id':'original','revision':1})
        run=self.suite.inspect_builder('demo')
        self.assertIn('metadata is missing',run['binding_problem']);self.assertFalse(run['actions']['resume'])
        with patch.object(self.suite,'builder_operation') as invoke,self.assertRaisesRegex(ValueError,'metadata is missing'):
            self.suite.resume_builder('demo')
        invoke.assert_not_called()

    def test_malformed_receipt_is_displayed_separately_from_native_cycle(self):
        request=self.suite.state/'build-inputs/input.json';self.write(request,{})
        self.write(Path(str(request)+'.binding.json'),[])
        self.write(self.cycle/'cycle.json',{'status':'running','input_request':str(request),'phases':[]})
        value=self.suite.inspect_builder('demo')
        self.assertEqual(value['status'],'running');self.assertIn('Invalid binding reference',value['binding_problem'])
        self.assertEqual(value['actions'],{'decide':False,'resume':False})
