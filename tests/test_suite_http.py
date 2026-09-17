"""Actual context/CLI-harness/HTTP-model roundtrip against a synthetic gateway."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench_suite import Suite,digest,package_digest,clean
ROOT=Path(__file__).resolve().parents[2]

class HTTPCompositionTests(unittest.TestCase):
    def test_three_components_and_observed_provenance(self):
        output=json.loads((ROOT/'cog-op-designer/context/output-example.json').read_text())
        model=json.loads((ROOT/'cog-turn-harness/tests/model-binding.json').read_text())
        model['binding_id']='binding-author-model';model['revision']=1
        model['credential_refs']={'api_key':'env:OPENROUTER_API_KEY','gateway_token':'env:OPENROUTER_COG_TOKEN'}
        observed=[]
        class Gateway(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                observed.append((self.path,self.headers.get('Authorization'),body))
                result={'model':model['model']['id'],'choices':[{'message':{'content':json.dumps(output)}}],
                        'cog_binding':{'binding_id':'binding-author-model','revision':1,'outcome':'completed','deviations':[],
                                       'observed_model':model['model']['id'],'observed_provider':'synthetic-upstream','run_record':'synthetic-run.json'}}
                data=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(('127.0.0.1',0),Gateway)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'OPENROUTER_COG_TOKEN':'synthetic-test-token'}):
                s=Suite(ROOT,Path(tmp)/'state',journal=lambda x:None)
                model['invocation']={'protocol':'openai-chat-completions-v1','address':f'http://127.0.0.1:{server.server_port}/bindings/binding-author-model/1/v1'}
                entry={'request':{},'binding':model,'path':str(ROOT/'cog-openrouter'),'package_sha256':package_digest(ROOT/'cog-openrouter'),'host_state':None,'model_requirement':None,'candidate_sha256':'fixture-only'}
                entry['sha256']=digest(entry);s.path({'binding_id':'binding-author-model','revision':1}).write_text(json.dumps(entry))
                binding=s.bind('cog-turn-harness',json.loads((ROOT/'cog-turn-harness/examples/bind-request.json').read_text()))
                composition=s.compose('cog-op-designer',{'binding_id':binding['binding_id'],'revision':1})
                result=s.invoke(composition,json.loads((ROOT/'cog-op-designer/examples/sample-bundle.json').read_text()))
                self.assertEqual(clean(result),output)
                self.assertEqual(result['binding']['provider_observations']['gateway']['run_record'],'synthetic-run.json')
                self.assertEqual(result['binding']['model']['composition'],'model')
                self.assertEqual(result['binding']['harness']['composition'],'harness')
                self.assertEqual(len(observed),1);self.assertEqual(observed[0][1],'Bearer synthetic-test-token')
                self.assertIn('reviewable',observed[0][2]['messages'][0]['content'].lower())
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':unittest.main()
