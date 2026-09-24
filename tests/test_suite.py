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
    def seed_model(self, locality="cloud"):
        b=json.loads((ROOT/'cog-turn-harness/tests/model-binding.json').read_text())
        b.update(binding_id='binding-author-model',revision=1,features=['text-generation','json-output'],locality=locality)
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
    def test_local_model_can_be_composed_without_cloud_permission(self):
        self.seed_model(locality='local')
        request=json.loads((ROOT/'cog-turn-harness/examples/bind-request.json').read_text())
        request['configuration']['locality']='local'
        request['requirement']['allowed_localities']=['local']
        binding=self.suite.bind('cog-turn-harness',request)
        self.assertEqual(binding['locality'],'local')
        self.suite.compose('cog-author',{'binding_id':binding['binding_id'],'revision':1})
        row=next(x for x in self.suite.bindings() if x['reference']['binding_id']==binding['binding_id'])
        self.assertEqual(row['locality'],'local')

    def test_harness_cannot_mislabel_cloud_model_as_local(self):
        self.seed_model(locality='cloud')
        request=json.loads((ROOT/'cog-turn-harness/examples/bind-request.json').read_text())
        request['configuration']['locality']='local'
        request['requirement']['allowed_localities']=['local']
        with self.assertRaisesRegex(ValueError,'locality must match'):
            self.suite.bind('cog-turn-harness',request)

    def test_public_qwen_provider_is_discoverable(self):
        rows=self.suite.select({'capability':'model-endpoint/openai-compatible','accepted_compositions':['model']})
        self.assertIn('openteams/cog-qwen',[row['id'] for row in rows])

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

class CodeSuiteTests(unittest.TestCase):
    def test_native_code_build_and_evidence(self):
        with tempfile.TemporaryDirectory(prefix='.suite-code-',dir=ROOT) as folder:
            suite=Suite(ROOT,Path(folder)/'state',journal=lambda x:None)
            request=json.loads((ROOT/'cog-author/examples/code-author-bundle.json').read_text())
            payload=json.loads((ROOT/'cog-author/examples/code-authored-payload.json').read_text())
            envelope={'envelope':1,'ok':True,'error':None,'problems':[],'cog':{'id':'openteams/cog-author','version':'0.1.0'},'payload':payload,'binding':None}
            import hashlib
            contract=payload['contract']
            request['contract_sha256']=digest(contract)
            payload['contract']=None
            payload['contract_sha256']=request['contract_sha256']
            row=next(f for f in payload['files'] if f['path']=='context/input-schema.json')
            content=row.pop('content');sha=hashlib.sha256(content.encode()).hexdigest()
            request['materials']=[{'path':'schema.json','content':content,'sha256':sha}]
            row.update(material_ref='schema.json',material_sha256=sha)
            expanded=suite.source_snapshot(request,envelope)
            self.assertEqual(expanded['contract'],contract)
            self.assertTrue(all('content' in f for f in expanded['files']))
            target=Path(folder)/request['identity']['name']
            suite.package(request,envelope,target)
            manifest=suite.manifest(target)
            self.assertEqual(manifest['kind'],'code')
            self.assertEqual(manifest['requires'],[])
            self.assertNotIn('workbench_composition',manifest.get('extensions',{}))
            self.assertEqual(suite.verify(target,'test')['exit_code'],0)
            plan=json.loads((ROOT/'cog-build-evaluator/context/output-example.json').read_text())
            for case in plan['test_cases']:
                case['criterion_ids']=['length'];case['expected_behavior']='Return length of notes.'
            plan['assessments']=[{'criterion_id':'length','status':'not_tested','rationale':'Not executed.','evidence_ids':[],'evidence_quote':''}]
            plan_env={**envelope,'cog':{'id':'openteams/cog-build-evaluator','version':'0.1.0'},'payload':plan}
            result=suite.evaluate(target,request,envelope,plan_env)
            self.assertEqual(result['evidence_scope'],'native-code')
            rows=result['review_request']['evidence'];self.assertEqual(len(rows),4)
            for row in rows:
                observed=json.loads(row['text'])['observed_envelope']
                self.assertEqual(observed['binding']['kind'],'code')
                self.assertEqual(observed['payload']['length'],len(json.loads(row['text'])['input']['notes']))
            original_call=suite.call
            def warned(root,task,args=(),**kwargs):
                value=original_call(root,task,args,**kwargs)
                if task=='run':
                    observed=json.loads(value['stdout'])
                    observed['problems']=[{'check':'expected-warning','detail':'Must be judged by evaluator.','severity':'warn'}]
                    value['stdout']=json.dumps(observed)
                return value
            with patch.object(suite,'call',side_effect=warned):
                warning_result=suite.evaluate(target,request,envelope,plan_env)
            row=warning_result['review_request']['evidence'][0]
            self.assertEqual(row['status'],'passed')  # observation only, not acceptance
            text=json.loads(row['text'])
            self.assertTrue(text['observed_envelope']['problems'])
            self.assertIn('not accepted behavior',text['execution_status_scope'])
            (target/'src/task_logic.py').write_text('# tampered')
            with self.assertRaisesRegex(ValueError,'no longer matches'):
                suite.evaluate(target,request,envelope,plan_env)

    def test_code_brief_handoff_preserves_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            suite=Suite(ROOT,Path(tmp)/'state',journal=lambda x:None)
            request=json.loads((ROOT/'cog-op-designer/examples/sample-bundle.json').read_text())
            payload=json.loads((ROOT/'cog-op-designer/context/output-example.json').read_text())
            payload['cog_briefs'][0]['cog_kind']='code'
            env={'envelope':1,'ok':True,'error':None,'problems':[],'cog':{'id':'openteams/cog-op-designer','version':'0.1.0'},'payload':payload,'binding':None}
            result=suite.handoff(request,env)
            self.assertEqual(result['requests'][0]['bundle']['kind'],'code')
            suite.bridge('cog-author','prepare',{'bundle':result['requests'][0]['bundle']})

    def test_legacy_unbound_code_choice_is_not_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            suite=Suite(ROOT,Path(tmp)/'state',journal=lambda x:None)
            request=json.loads((ROOT/'cog-op-designer/examples/sample-bundle.json').read_text())
            payload=json.loads((ROOT/'cog-op-designer/context/output-example.json').read_text())
            for step in payload['steps']:
                if step['choice']['kind']=='new':
                    step['choice'].update(kind='code',brief_id=None)
            payload['cog_briefs']=[]
            env={'envelope':1,'ok':True,'error':None,'problems':[],'cog':{'id':'openteams/cog-op-designer','version':'0.1.0'},'payload':payload,'binding':None}
            with self.assertRaisesRegex(ValueError,'Legacy code choices'):
                suite.handoff(request,env)

    def test_native_capture_can_preserve_large_envelopes(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            suite=Suite(ROOT,Path(tmp)/'state',journal=lambda x:None)
            body=json.dumps({'payload':{'text':'x'*40000}})
            with patch('workbench_suite.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=body,stderr='')):
                result=suite.call('cog-author','ask',expect_json=False,stdout_limit=None)
            self.assertEqual(json.loads(result['stdout'])['payload']['text'],'x'*40000)
