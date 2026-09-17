import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench_suite import Suite,clean,digest,package_digest
ROOT=Path(__file__).resolve().parents[2]

class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='suite-test-');self.addCleanup(self.temp.cleanup)
        self.suite=Suite(ROOT,Path(self.temp.name)/'state',journal=lambda x:None)
    def seed_model(self):
        b=json.loads((ROOT/'cog-turn-harness/tests/model-binding.json').read_text())
        b.update(binding_id='binding-author-model',revision=1,features=['text-generation','json-output'])
        root=ROOT/'cog-openrouter'
        entry={'request':{},'binding':b,'path':str(root),'package_sha256':package_digest(root),'model_requirement':None,'host_state':None,'candidate_sha256':'test-only'}
        entry['sha256']=digest(entry);ref={'binding_id':b['binding_id'],'revision':b['revision']}
        self.suite.path(ref).write_text(json.dumps(entry));return ref
    def harness(self):
        self.seed_model();request=json.loads((ROOT/'cog-turn-harness/examples/bind-request.json').read_text())
        return self.suite.bind('cog-turn-harness',request)
    def test_catalog_and_selection_preserve_composition(self):
        rows=self.suite.select({'capability':'model-endpoint/openai-compatible','accepted_compositions':['model']})
        self.assertIn('openteams/cog-openrouter',[x['id'] for x in rows]);self.assertNotIn('openteams/cog-chatgpt',[x['id'] for x in rows])
        rows=self.suite.select({'capability':'agentic-harness/chat','accepted_compositions':['model+harness']})
        self.assertEqual({x['id'] for x in rows},{'openteams/cog-chatgpt','openteams/cog-claude'})
    def test_harness_requires_admitted_model(self):
        request=json.loads((ROOT/'cog-turn-harness/examples/bind-request.json').read_text())
        with self.assertRaises(ValueError):self.suite.bind('cog-turn-harness',request)
    def test_admit_compose_revoke(self):
        b=self.harness();ref={'binding_id':b['binding_id'],'revision':b['revision']}
        composition=self.suite.compose('cog-op-designer',ref)
        self.assertTrue(Path(composition['record_path']).is_file())
        self.assertEqual(composition['model_binding'],{'binding_id':'binding-author-model','revision':1})
        self.suite.revoke(ref)
        with self.assertRaises(ValueError):self.suite.load(ref)
    def test_revoked_model_invalidates_harness(self):
        b=self.harness();self.suite.revoke({'binding_id':'binding-author-model','revision':1})
        with self.assertRaises(ValueError):self.suite.load({'binding_id':b['binding_id'],'revision':1})
    def test_duplicate_revision_rejected(self):
        self.harness()
        request=json.loads((ROOT/'cog-turn-harness/examples/bind-request.json').read_text())
        with self.assertRaises(ValueError):self.suite.bind('cog-turn-harness',request)
    def test_corrupt_record_rejected(self):
        ref=self.seed_model();p=self.suite.path(ref);value=json.loads(p.read_text());value['binding']['model']['id']='different';p.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.suite.load(ref)
    def test_context_checks_before_and_after(self):
        b=self.harness();c=self.suite.compose('cog-op-designer',{'binding_id':b['binding_id'],'revision':1})
        bundle=json.loads((ROOT/'cog-op-designer/examples/sample-bundle.json').read_text());output=json.loads((ROOT/'cog-op-designer/context/output-example.json').read_text())
        original=self.suite.call;calls=[]
        def call(root,task,args=(),**kwargs):
            if task!='turn':return original(root,task,args,**kwargs)
            calls.append(task);request=json.loads(Path(args[args.index('--request')+1]).read_text());binding=json.loads(Path(args[args.index('--binding')+1]).read_text())
            return {'envelope':1,'ok':True,'error':None,'problems':[],'cog':binding['provider'],'binding':binding,'payload':{'document_kind':'harness_turn_result','contract':request['contract'],'request_id':request['request_id'],'binding':request['binding'],'model_binding':request['model_binding'],'result':output,'tool_uses':[]}}
        with patch.object(self.suite,'call',side_effect=call):
            result=self.suite.invoke(c,bundle);self.assertEqual(clean(result),output)
            self.assertEqual(result['binding']['evidence_scope'],'composed-system')
            output['steps'][0]['inputs']=['invented'];result=self.suite.invoke(c,bundle);self.assertTrue(result['problems'])
            with self.assertRaises(ValueError):self.suite.invoke(c,{'goal':'missing fields'})
        self.assertEqual(len(calls),2)
    def test_tampered_composition(self):
        b=self.harness();c=self.suite.compose('cog-op-designer',{'binding_id':b['binding_id'],'revision':1});c['consumer']['version']='wrong'
        with self.assertRaises(ValueError):self.suite.invoke(c,{})
    def test_clean_gate(self):
        for value in ({'envelope':1,'ok':True,'problems':[{'check':'failed'}]}, {'envelope':1,'ok':False},{}):
            with self.assertRaises(ValueError):clean(value)
    def test_no_freeform_task(self):
        with self.assertRaises(ValueError):self.suite.call('cog-op-designer','rm',[])
    def test_paths_stay_in_workspace(self):
        with self.assertRaises(ValueError):self.suite.root('/private/tmp/outside-cog')
    def test_op_handoff(self):
        request=json.loads((ROOT/'cog-op-designer/examples/sample-bundle.json').read_text());payload=json.loads((ROOT/'cog-op-designer/context/output-example.json').read_text())
        env={'envelope':1,'ok':True,'error':None,'problems':[],'cog':{'id':'openteams/cog-op-designer','version':'0.1.0'},'payload':payload,'binding':None}
        result=self.suite.handoff(request,env);self.assertEqual(result['requests'][0]['bundle']['operation'],'design');self.assertIsNone(result['requests'][0]['bundle']['contract'])
        self.suite.bridge('cog-author','prepare',{'bundle':result['requests'][0]['bundle']})
    def test_contract_bridge_copies_match(self):
        expected=(ROOT/'cog-workbench/bridges/context_bridge.py').read_bytes()
        for name in ('cog-op-designer','cog-author','cog-build-evaluator'):self.assertEqual((ROOT/name/'scripts/context_bridge.py').read_bytes(),expected)
        runtime=(ROOT/'cog-turn-harness/src/turn_runtime.py').read_bytes()
        for name in ('cog-chatgpt','cog-claude'):self.assertEqual((ROOT/name/'src/turn_runtime.py').read_bytes(),runtime)


    def test_full_source_packaging_and_evaluation_handoff(self):
        folder=Path(tempfile.mkdtemp(prefix='.suite-integration-',dir=ROOT));self.addCleanup(shutil.rmtree,folder)
        request=json.loads((ROOT/'cog-author/examples/author-bundle.json').read_text())
        payload=json.loads((ROOT/'cog-author/examples/authored-payload.json').read_text())
        author={'envelope':1,'ok':True,'error':None,'problems':[],'cog':{'id':'openteams/cog-author','version':'0.1.0'},'payload':payload,'binding':None}
        target=folder/request['identity']['name']
        package=self.suite.package(request,author,target)
        self.assertEqual((target/'src/task_logic.py').read_text(),next(x['content'] for x in payload['files'] if x['path']=='src/task_logic.py'))
        self.assertEqual(self.suite.verify(target,'test')['exit_code'],0)
        with self.assertRaises(ValueError):self.suite.package(request,author,target)
        plan={'envelope':1,'ok':True,'error':None,'problems':[],'cog':{'id':'openteams/cog-build-evaluator','version':'0.1.0'},'payload':json.loads((ROOT/'cog-build-evaluator/context/output-example.json').read_text()),'binding':None}
        b=self.harness();ref={'binding_id':b['binding_id'],'revision':1}
        with patch.object(self.suite,'invoke',return_value={'envelope':1,'ok':True,'error':None,'problems':[],'payload':{'abstained':True,'actions':[]},'binding':{'fixture':True}}):
            result=self.suite.evaluate(target,request,author,plan,ref)
        self.assertEqual(result['status'],'executed-awaiting-independent-review')
        self.assertTrue(result['review_request']['evidence'])
        with patch.object(self.suite,'invoke',side_effect=ValueError('synthetic failure')):
            failed=self.suite.evaluate(target,request,author,plan,ref)
        self.assertTrue(all(row['status']=='failed' for row in failed['review_request']['evidence']))
        unsupported=copy.deepcopy(plan)
        unsupported['payload']['test_cases'][0]['input']={'construction':'Build and execute a test matrix.'}
        with patch.object(self.suite,'invoke') as invoke:
            with self.assertRaises(ValueError):self.suite.evaluate(target,request,author,unsupported,ref)
            invoke.assert_not_called()
        (target/'src/task_logic.py').write_text('# changed source')
        with self.assertRaises(ValueError):self.suite.evaluate(target,request,author,plan,ref)

if __name__=='__main__':unittest.main()
