"""Exercise the shipped Studio script with a minimal DOM and no provider calls."""
import shutil
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is required for the Studio script regression')
class StudioBindingTests(unittest.TestCase):
    def test_decision_bindings_are_not_offered_for_chat_actions(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8').split('<script>')[1].split('</script>')[0];
const elements = new Map();
function element() { return {value:'', options:[], disabled:false,
  replaceChildren() { this.options=[]; this.value=''; },
  append(option) { this.options.push(option); if (!this.value) this.value=option.value; }
}; }
const buttons=['design','handoff','contract','author','evalplan','package','cases','review'];
const document={
  getElementById(id) { if (!elements.has(id)) elements.set(id,element()); return elements.get(id); },
  createElement() { return element(); },
  querySelectorAll(selector) { return selector==='button' ? buttons.map(id=>document.getElementById(id)) : []; }
};
let rows=[];
const context=vm.createContext({document, setInterval:()=>{}, fetch:async()=>({ok:true,json:async()=>({ok:true,catalog:[],bindings:rows,runs:[]})})});
function binding(id,capability,composition='harness',status='admitted') {
  return {reference:{binding_id:id,revision:1},provider:{id:'test/'+id},capability,composition,status};
}
(async()=>{
  vm.runInContext(source,context);
  await new Promise(resolve=>setImmediate(resolve));
  await vm.runInContext('loadBuilds()',context);
  assert.equal(elements.get('acceptBuild').disabled,true);
  assert.equal(elements.get('resumeBuild').disabled,true);
  vm.runInContext("activeBuild={actions:{decide:true,resume:false}};buildControls()",context);
  assert.equal(elements.get('acceptBuild').disabled,false);
  assert.equal(elements.get('resumeBuild').disabled,true);
  vm.runInContext("activeBuild={actions:{decide:false,resume:false}};buildControls()",context);
  assert.equal(elements.get('acceptBuild').disabled,true);
  vm.runInContext("handoff={requests:[{}]}; contract={kind:'context'}; author={}; evalPlan={}; packaged='p'; evidence={};",context);
  rows=[binding('decision','system-one/decisions')];
  await vm.runInContext('refresh()',context);
  assert.equal(elements.get('binding').options.length,0);
  for (const id of ['design','contract','author','evalplan','cases','review']) assert.equal(elements.get(id).disabled,true,id);
  assert.equal(elements.get('package').disabled,false);
  rows.push(binding('chat','agentic-harness/chat'),binding('revoked','agentic-harness/chat','harness','revoked'));
  await vm.runInContext('refresh()',context);
  assert.equal(elements.get('binding').options.length,1);
  assert.equal(JSON.parse(elements.get('binding').value).binding_id,'chat');
  for (const id of ['design','contract','author','evalplan','cases','review']) assert.equal(elements.get(id).disabled,false,id);
  rows=[binding('decision','system-one/decisions')];
  await vm.runInContext('refresh()',context);
  assert.equal(elements.get('design').disabled,true);
  vm.runInContext("contract.kind='code'; controls();",context);
  assert.equal(elements.get('cases').disabled,false);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', script, str(ROOT / 'src/studio.html')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
