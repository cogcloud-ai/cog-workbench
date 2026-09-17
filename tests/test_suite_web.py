import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import suite_web

class SuiteWebTests(unittest.TestCase):
    def handler(self,host='127.0.0.1:8071',token=None,origin=None):
        headers={'Host':host}
        if token:headers['X-Cog-Workbench']=token
        if origin:headers['Origin']=origin
        return SimpleNamespace(headers=headers,server=SimpleNamespace(server_port=8071),_send=Mock())
    def test_rebinding_host_rejected(self):
        for host in ('attacker.example:8071','127.0.0.1:9999','user@127.0.0.1:8071'):
            handler=self.handler(host)
            self.assertTrue(suite_web.get(handler,'/studio',{},None));self.assertEqual(handler._send.call_args.args[0],403)
    def test_token_and_origin_required(self):
        for handler in (self.handler(),self.handler(token='wrong'),self.handler(token=suite_web.TOKEN,origin='https://attacker.example')):
            self.assertTrue(suite_web.post(handler,'/api/suite/action',{},None));self.assertEqual(handler._send.call_args.args[0],403)
    def test_old_routes_unaffected(self):
        handler=self.handler();self.assertFalse(suite_web.get(handler,'/api/package',{},None));self.assertFalse(suite_web.post(handler,'/api/invoke',{},None))

if __name__=='__main__':unittest.main()
