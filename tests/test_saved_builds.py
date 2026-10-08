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
        self.write(self.run/'pending/design.json',{'artifact':{'kind':'cog-contract'},'payload_sha256':'test','artifact_sha256':'test'})
        self.write(self.run/'track.json',{'input_request':str(self.run/'input.json'),'steps':[{'id':'design','status':'awaiting-decision'}]})
        self.write(self.cycle/'cycle.json',{'status':'awaiting-decision','phases':[{'run_dir':str(self.run),'package':str(self.run.parents[1])}]})
    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def test_reload_reads_native_gate_without_process_memory(self):
        other=Suite(self.root,self.root/'state',journal=lambda _:None)
        value=other.inspect_builder('demo')
        self.assertTrue(value['actions']['decide']);self.assertFalse(value['actions']['resume'])
        self.assertEqual(value['pending']['artifact']['kind'],'cog-contract')
        self.assertEqual(other.builder_runs()[0]['current_step'],'design')
    def test_rejection_and_exhaustion_offer_no_continuation(self):
        for status in ('rejected','budget-exhausted','completed'):
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
            result=self.suite.resume_builder('demo',{'verdict':'reject','by':'learner','reason':'Wrong contract'})
            self.assertEqual(result['status'],'rejected');self.assertIn('--decision',operation.call_args.args[0])
    def test_builder_command_is_declared_fixed_and_scrubs_pixi(self):
        (self.builder/'pixi.toml').write_text('[tasks]\ncycle="python src/op_cycle.py"\n')
        python=self.builder/'.pixi/envs/default/bin/python';python.parent.mkdir(parents=True);python.touch()
        with patch.dict(os.environ,{'PIXI_PROJECT_ROOT':'wrong'}),patch('workbench_suite.subprocess.run',return_value=subprocess.CompletedProcess([],3,'{"status":"awaiting-decision"}','')) as run:
            result=self.suite.builder_operation(['--resume','literal $(unchanged)'])
            self.assertEqual(result['exit_code'],3);self.assertNotIn('PIXI_PROJECT_ROOT',run.call_args.kwargs['env'])
            self.assertEqual(run.call_args.args[0][-1],'literal $(unchanged)')
        (self.builder/'pixi.toml').write_text('[tasks]\ncycle="sh arbitrary"\n')
        with self.assertRaises(ValueError):self.suite.builder_operation([])
