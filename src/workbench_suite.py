"""Cog tool suite: explicit selection/admission, composition and building handoffs.

No Op scheduling or management. Local package code is trusted by the owner;
only declared interfaces/conventional checks and declared host adapters run.
"""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import cog_package
import toml_compat as tomllib

CONTRACT = 'openteams/satisfier-binding [0.1-draft]'
HERE = Path(__file__).resolve().parents[1]


def require(ok, detail):
    if not ok:
        raise ValueError(detail)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def clean(envelope):
    require(isinstance(envelope, dict) and envelope.get('envelope') == 1 and envelope.get('ok') is True
            and not envelope.get('error') and not envelope.get('problems'), 'A clean envelope v1 is required; inspect problems before proceeding.')
    return envelope['payload']


def package_digest(root):
    root = Path(root)
    paths = []
    for name in ('COG.md', 'cog.yaml', 'pixi.toml', 'pixi.lock', 'engine.json'):
        if (root/name).is_file(): paths.append(root/name)
    for name in ('src', 'scripts', 'context', 'binding', 'contracts', 'tests', 'evals', 'examples'):
        if (root/name).is_dir():
            paths += [p for p in (root/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    require(all(not p.is_symlink() and p.resolve().is_relative_to(root.resolve()) for p in paths), 'Package execution files must stay within the package.')
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})


class Suite:
    def __init__(self, workspace=None, state=None, journal=None):
        self.workspace = Path(workspace or HERE.parent).resolve()
        self.state = Path(state or HERE/'var/suite').absolute()
        require(not self.state.is_symlink(), 'State may not be a symlink.')
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(self.state.stat().st_uid == os.getuid() and self.state.stat().st_mode & 0o077 == 0, 'Suite state must be owner-only (mode 700).')
        self._journal = journal

    def journal(self, event, **fields):
        entry = {'event': event, **fields}
        if self._journal:
            self._journal(entry)
        else:
            path = HERE/'var/activity.jsonl'; path.parent.mkdir(exist_ok=True)
            with path.open('a') as f: f.write(json.dumps({'ts': time.time(), **entry})+'\n')

    def root(self, path):
        root = Path(path)
        if not root.is_absolute(): root = self.workspace/root
        root = root.resolve()
        require(root.is_relative_to(self.workspace), 'Package must be inside this workbench workspace.')
        return root

    def manifest(self, root):
        return cog_package.read_manifest(self.root(root))[0]

    def catalog(self):
        rows = []
        for root in sorted(self.workspace.iterdir()):
            if not root.is_dir() or not (root/'COG.md').is_file(): continue
            try:
                m = self.manifest(root)
                io = m.get('io') or {}
                ext = (m.get('extensions') or {}).get('satisfier_binding')
                provider = json.loads(self.file(root, ext['declaration']).read_text()) if ext else None
                rows.append({'id': m['id'], 'version': str(m.get('version', '')), 'summary': m.get('summary', ''),
                    'accepts': io.get('accepts', []), 'produces': io.get('produces', []),
                    'capabilities': [provider['capability']] if provider else io.get('produces', []),
                    'fingerprint': package_digest(root), 'path': str(root), 'provider': provider,
                    'composition': (m.get('extensions') or {}).get('workbench_composition')})
            except (ValueError, KeyError, OSError, cog_package.PackageError):
                continue
        return rows

    def file(self, root, relative):
        path = Path(root)/relative
        require(not Path(relative).is_absolute() and path.resolve().is_relative_to(Path(root).resolve()), 'Declared file must stay inside its package.')
        return path

    def call(self, root, task, args=(), timeout=240, expect_json=True):
        root = self.root(root); m = self.manifest(root)
        allowed = {x.get('task') for x in m.get('interfaces', [])} | {'test', 'eval', 'check'}
        host = (m.get('extensions') or {}).get('workbench_host', {})
        allowed |= set(host.get('tasks', {}).values())
        require(task in allowed, 'Operation is not declared by this package.')
        with (root/'pixi.toml').open('rb') as f: tasks = tomllib.load(f).get('tasks', {})
        declared = tasks.get(task)
        if isinstance(declared, dict): declared = declared.get('cmd')
        require(isinstance(declared, str), 'Task has no supported command declaration.')
        argv = shlex.split(declared)
        require(argv and not any(x in (';', '&&', '|', '||', '>', '<') for x in argv), 'Suite operations require an argv-compatible declared task.')
        python = root/'.pixi/envs/default/bin/python'
        if argv[0] in ('python', 'python3'):
            argv[0] = str(python) if python.is_file() else sys.executable
        self.journal('suite-operation-start', cog=m['id'], task=task)
        env = {k:v for k,v in os.environ.items() if not k.startswith('PIXI_')}
        try:
            result = subprocess.run(argv + [str(x) for x in args], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            self.journal('suite-operation-timeout', cog=m['id'], task=task)
            raise ValueError('Declared operation timed out.') from None
        self.journal('suite-operation-exit', cog=m['id'], task=task, exit_code=result.returncode)
        if not expect_json:
            return {'exit_code': result.returncode, 'stdout': result.stdout[-30000:], 'stderr': result.stderr[-5000:]}
        try: value = json.loads(result.stdout)
        except ValueError: raise ValueError('Declared operation did not return JSON; check its environment and installation.') from None
        if result.returncode != 0:
            detail = (value.get('error') or {}).get('detail') if isinstance(value.get('error'), dict) else value.get('error')
            raise ValueError(detail or 'Declared operation failed.')
        return value

    def documents(self, values):
        # Caller owns returned TemporaryDirectory until all child processes finish.
        temp = tempfile.TemporaryDirectory(prefix='cog-suite-')
        paths = {}
        for name, value in values.items():
            path = Path(temp.name)/(name+'.json'); path.write_text(json.dumps(value)); paths[name] = str(path)
        return temp, paths

    def bridge(self, root, operation, document):
        m = self.manifest(root)
        ext = (m.get('extensions') or {}).get('workbench_composition')
        require(ext and ext['contract'] == 'openteams/context-composition [0.1-draft]', 'Context Cog has not opted into external composition.')
        iface = next((x for x in m['interfaces'] if x['name'] == ext['bridge_interface']), None)
        require(iface and iface['kind'] == 'command', 'Missing declared composition bridge.')
        temp, paths = self.documents({'input': document})
        with temp:
            return self.call(root, iface['task'], [operation, '--request', paths['input']])

    def select(self, requirement):
        matches = []
        for row in self.catalog():
            card = row['provider']
            if not card or card['capability'] != requirement['capability']: continue
            if not set(card['compositions']) & set(requirement['accepted_compositions']): continue
            matches.append({'id':row['id'], 'path':row['path'], 'compositions':card['compositions'],
                            'configuration_schema':card['configuration_schema'], 'credential_schema':card['credential_schema'],
                            'status':'configurable-provider-not-qualified'})
        return matches

    def path(self, ref):
        require(isinstance(ref, dict) and isinstance(ref.get('binding_id'), str) and type(ref.get('revision')) is int and ref['revision'] > 0, 'Invalid binding reference.')
        return self.state/(digest(ref['binding_id'])+'-'+str(ref['revision'])+'.json')

    def save(self, folder, value):
        dest = self.state/folder; dest.mkdir(exist_ok=True, mode=0o700)
        path = dest/(str(uuid.uuid4())+'.json')
        with path.open('x') as f: json.dump(value, f, indent=2)
        os.chmod(path, 0o600)
        return str(path)

    def load(self, ref):
        path = self.path(ref)
        require(path.is_file() and not path.is_symlink() and not path.with_suffix('.revoked').exists(), 'Binding is missing or revoked.')
        entry = json.loads(path.read_text()); checksum = entry.pop('sha256')
        require(digest(entry) == checksum, 'Binding record integrity failure.')
        require(package_digest(self.root(entry['path'])) == entry['package_sha256'], 'Provider package changed; create a new binding revision.')
        b = entry['binding']
        require({'binding_id':b['binding_id'],'revision':b['revision']} == ref and b['state'] == 'admitted', 'Stored binding reference mismatch.')
        if entry.get('host_state'):
            observed = clean(self.call(entry['path'], 'inspect-binding', ['--state-dir', entry['host_state'], '--binding-id', ref['binding_id'], '--revision', ref['revision']]))
            require(observed == b, 'Gateway admission changed or was revoked.')
        if b['model_binding']:
            dep = self.load(b['model_binding'])
            self.compatible(dep['binding'], entry['model_requirement'])
        return entry

    @staticmethod
    def compatible(binding, req):
        require(binding['state'] == 'admitted' and binding['composition'] in req['accepted_compositions'], 'Composition does not satisfy requirement.')
        require(binding['capability'] == req['capability'] and set(req['features']) <= set(binding['features']), 'Binding lacks required capability/features.')
        require(binding['locality'] in req['allowed_localities'], 'Binding locality is not permitted.')
        require(req['model_id'] is None or binding['model'] and binding['model']['id'] == req['model_id'], 'Model identity does not satisfy requirement.')
        q = binding['qualification']
        require(not req['identity_verified'] or q['identity_verified'], 'Verified identity required.')
        require(not req['revision_pinned'] or q['revision_pinned'], 'Pinned model revision required.')
        require(req['evidence_level'] == 'declaration' or q['level'] == 'probe', 'Probe evidence required.')

    def bind(self, root, request):
        root = self.root(root)
        card = clean(self.call(root, 'card'))
        require(card['provider'] == request['provider'], 'Selected provider identity mismatch.')
        before = package_digest(root)
        temp, files = self.documents({'request':request})
        with temp:
            candidate_env = self.call(root, card['binding_interface'], ['--request',files['request']])
            candidate = clean(candidate_env)
            require(candidate['status'] == 'candidate' and not candidate['problems'] and candidate['request_id'] == request['request_id'], 'Provider did not return the requested candidate.')
            b = copy.deepcopy(candidate['binding'])
            for field, expected in {'provider':request['provider'],'binding_id':request['binding_id'],'revision':request['revision'],
                'requirement_id':request['requirement']['id'],'configuration':request['configuration'],
                'credential_refs':request['credential_refs'],'state':'candidate','admission':None}.items():
                require(b[field] == expected, 'Candidate correlation failed: '+field)
            test = dict(b,state='admitted'); self.compatible(test,request['requirement'])
            require(b['composition'] in card['compositions'], 'Provider composition declaration mismatch.')
            model_requirement = card['model_requirement']
            if b['composition'] == 'harness':
                require(b['model_binding'] == request['configuration']['model_binding'], 'Harness model reference mismatch.')
                dep = self.load(b['model_binding']); self.compatible(dep['binding'], model_requirement)
            host_state = None
            if b['composition'] == 'model':
                require(card['provider']['id'] == 'openteams/cog-openrouter', 'No host adapter is installed for this model provider.')
                host_state = str(self.state/'openrouter')
                candidate_file=Path(temp.name)/'candidate.json'; candidate_file.write_text(json.dumps(candidate_env))
                b = clean(self.call(root,'admit',['--request',files['request'],'--candidate',candidate_file,
                    '--state-dir',host_state,'--gateway-url',request['configuration']['gateway_base_url']]))
            else:
                # Host independently re-invokes the installed provider's inspection,
                # compares all semantic fields and applies its own admission policy.
                fresh = clean(self.call(root,card['binding_interface'],['--request',files['request']]))
                require(fresh == candidate, 'Qualification changed between candidate and host inspection.')
                require(b['qualification']['level'] == 'declaration' and not b['qualification']['identity_verified'] and not b['qualification']['revision_pinned'], 'Unsupported qualification claim.')
                require(b['invocation'] == {'protocol':'cog-harness-turn-command-v1','address':'cog-command:turn'}, 'Unsupported turn transport.')
                b['state']='admitted'
                b['admission']={'resolver_id':'openteams/cog-workbench/0.2.0','checks':[{'check':'host-admission','passed':True,'detail':'Exact request, declaration, local inspection, composition, locality, features and model dependency checked; declaration evidence only.'}]}
            require(before == package_digest(root), 'Provider changed during admission.')
            entry={'request':request,'binding':b,'path':str(root),'package_sha256':before,'model_requirement':model_requirement,
                   'host_state':host_state,'candidate_sha256':digest(candidate_env)}
            entry['sha256']=digest(entry)
            ref={'binding_id':b['binding_id'],'revision':b['revision']}; path=self.path(ref)
            with (self.state/'.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                revisions=list(self.state.glob(digest(ref['binding_id'])+'-*.json'))
                previous=max((int(x.stem.rsplit('-',1)[1]) for x in revisions),default=0)
                require(ref['revision'] == previous+1 and not path.exists(), 'Binding must use the next unused revision.')
                with path.open('x') as f: json.dump(entry,f,indent=2)
                os.chmod(path,0o600)
        self.journal('suite-binding-admitted', binding=ref, provider=card['provider'])
        return b

    def revoke(self, ref):
        entry=self.load(ref)
        if entry.get('host_state'):
            clean(self.call(entry['path'],'revoke',['--state-dir',entry['host_state'],'--binding-id',ref['binding_id'],'--revision',ref['revision']]))
        self.path(ref).with_suffix('.revoked').touch(mode=0o600)
        self.journal('suite-binding-revoked',binding=ref)
        return {'revoked':ref}

    def compose(self, context, ref):
        root=self.root(context); manifest=self.manifest(root)
        ext=(manifest.get('extensions') or {}).get('workbench_composition')
        require(ext is not None, 'Context does not declare external composition support.')
        entry=self.load(ref); b=entry['binding']
        req={'capability':'agentic-harness/chat','accepted_compositions':ext['accepted_compositions'],
             'features':ext['required_features'],'allowed_localities':ext['allowed_localities'],'model_id':None,
             'evidence_level':'declaration','identity_verified':False,'revision_pinned':False}
        self.compatible(b,req)
        require(manifest.get('memory') == 'none' and ext['tools']=='none', 'Only stateless context Cogs without tool grants are supported.')
        # Inseparable vendor harnesses have explicitly weaker isolation and are
        # admitted only for composed-system use, never bare-model evaluations.
        if b['composition']=='model+harness':
            require(ext['evidence_scope']=='composed-system', 'Subscription harness cannot provide bare-model evaluation evidence.')
        value={'composition':1,'consumer':{'id':manifest['id'],'version':str(manifest['version'])},'path':str(root),
               'context_sha256':package_digest(root),'binding':ref,'model_binding':b['model_binding'],
               'evidence_scope':'composed-system','checks':'packaged-before-and-after'}
        value['sha256']=digest(value)
        path=self.save('compositions',value)
        self.journal('suite-composed',consumer=value['consumer'],binding=ref)
        return {'record_path':path,**value}

    def invoke(self, composition, bundle):
        value=copy.deepcopy(composition);value.pop('record_path',None)
        checksum=value.pop('sha256')
        require(digest(value)==checksum, 'Composition record integrity failure.')
        root=self.root(value['path'])
        require(package_digest(root)==value['context_sha256'], 'Context package changed; recompose before invoking.')
        entry=self.load(value['binding']);b=entry['binding']
        require(value['model_binding']==b['model_binding'], 'Composition dependency mismatch.')
        prepared=self.bridge(root,'prepare',{'bundle':bundle})
        require(prepared['consumer']==value['consumer'],'Context identity mismatch.')
        request={'document_kind':'harness_turn_request','contract':CONTRACT,'request_id':str(uuid.uuid4()),
                 'binding':value['binding'],'model_binding':b['model_binding'],**prepared,'tool_grant_refs':[],'thread_ref':None}
        documents={'turn':request,'binding':b}
        if b['model_binding']: documents['model']=self.load(b['model_binding'])['binding']
        temp,files=self.documents(documents)
        with temp:
            args=['--request',files['turn'],'--binding',files['binding']]
            if 'model' in files: args+=['--model-binding',files['model']]
            response=self.call(entry['path'],'turn',args,timeout=660)
        output=clean(response)
        require(response['cog']==b['provider'] and response['binding']==b, 'Turn provider provenance mismatch.')
        require(output['request_id']==request['request_id'] and output['binding']==request['binding'] and output['model_binding']==request['model_binding'], 'Turn response correlation failed.')
        require(not output['tool_uses'],'Unexpected tool activity.')
        self.load(value['binding'])  # Revocation or package changes during turn fail closed.
        provenance={'composition':value,'harness':b,'model':documents.get('model'), 'provider_response_binding':response['binding'],'provider_observations':response.get('provider_observations'),
                    'evidence_scope':'composed-system','model_identity_verified':False}
        result=self.bridge(root,'finish',{'bundle':bundle,'result':output['result'],'provenance':provenance})
        record={'consumer':value['consumer'],'request_sha256':digest(bundle),'result_sha256':digest(result),'provenance':provenance,
                'problems':result['problems'],'request_id':request['request_id']}
        record_path=self.save('runs',record)
        self.journal('suite-invoked',consumer=value['consumer'],binding=value['binding'],run_record=record_path,problem_count=len(result['problems']))
        return result

    def handoff(self, request, envelope):
        payload=clean(envelope)
        require(envelope['cog']=={'id':'openteams/cog-op-designer','version':'0.1.0'}, 'Expected Op designer result.')
        validated=self.bridge('cog-op-designer','finish',{'bundle':request,'result':payload,'provenance':envelope.get('binding') or {'source':'imported-review'}})
        clean(validated)
        require(payload['classification']=='proposed','Only a proposed design can produce building briefs.')
        # Re-check reuse against current catalog, not merely the model's input snapshot.
        current={x['id']:x for x in self.catalog()}
        for step in payload['steps']:
            choice=step['choice']
            if choice['kind']=='existing':
                require(choice['cog_id'] in current and current[choice['cog_id']]['fingerprint']==choice['catalog_fingerprint'],'Suggested existing Cog has changed or disappeared.')
        requests=[]
        for brief in payload['cog_briefs']:
            relevant=[s for s in payload['steps'] if s['id'] in brief['step_ids']]
            bundle={'operation':'design','brief':brief['brief'],'contract':None,'identity':None,
                    'materials':[{'path':'op-design.json','content':json.dumps({'goal':payload['goal'],'constraints':request['constraints'],
                    'success_criteria':request['success_criteria'],'steps':relevant,'artifacts':payload['artifacts'],'prohibits':brief['prohibits']})}], 'feedback':[]}
            requests.append({'name':brief['name'],'brief_id':brief['id'],'bundle':bundle})
        value={'handoff':1,'status':'awaiting-cog-contract-design','proposal_sha256':digest(envelope),'requests':requests}
        path=self.save('handoffs',value);self.journal('suite-design-handoff',path=path,count=len(requests))
        return {'path':path,**value}

    def package(self, request, envelope, destination):
        """Accepted authored snapshot -> full Smith package; never a starter-only handoff."""
        root=self.root(destination)
        require(root.name == request['identity']['name'], 'Destination folder must match the Cog name.')
        require(not root.exists() and not root.is_symlink(),'Package destination must not exist.')
        clean(envelope)
        temp,files=self.documents({'request':request,'envelope':envelope})
        with temp:
            draft=Path(temp.name)/'draft'
            result=self.call('cog-author','export-draft',['--request',files['request'],'--envelope',files['envelope'],'--out',draft],expect_json=False)
            require(result['exit_code']==0,'Author export rejected the source snapshot.')
            handoff=json.loads((draft/'handoff.json').read_text())
            # Smith creates into a staging sibling. Final destination stays absent on failure.
            stage=Path(temp.name)/request['identity']['name']
            result=self.call('cog-smith','new',['--from-request',draft/'smith-request.json','--dir',stage,'--envelope'])
            clean(result)
            for relative in handoff['source_paths']:
                source=draft/'source'/relative
                target=stage/relative
                require(source.is_file() and not source.is_symlink() and source.resolve().is_relative_to((draft/'source').resolve()),'Invalid exported source path.')
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            import yaml
            m=yaml.safe_load((stage/'cog.yaml').read_text())
            for req in m.get('requires',[]):req['locality']=handoff['contract']['locality']
            m['evaluation']['fixtures']=handoff['fixture_paths']
            # Opt the built context into the same explicitly declared bridge.
            (stage/'scripts').mkdir(exist_ok=True)
            shutil.copyfile(HERE/'bridges/context_bridge.py',stage/'scripts/context_bridge.py')
            m.setdefault('extensions',{})['workbench_composition']={
                'contract':'openteams/context-composition [0.1-draft]','bridge_interface':'composition',
                'accepted_compositions':['harness','model+harness'],
                'required_features':['context/per-turn','memory/none','json-output'],
                'allowed_localities':['local'] if handoff['contract']['locality']=='local' else ['local','cloud'],
                'tools':'none','checks':'packaged-before-and-after','evidence_scope':'composed-system'}
            m['interfaces'].append({'name':'composition','kind':'command','task':'composition','audience':'lifecycle'})
            with (stage/'pixi.toml').open('a') as f:
                f.write('\n[tasks.composition]\ncmd = "python scripts/context_bridge.py"\n')
            (stage/'cog.yaml').write_text(yaml.safe_dump(m,sort_keys=False))
            # The checker is a declared Smith operation; generated Python is not run here.
            check=self.call('cog-smith','check',[stage,'--envelope'])
            clean(check)
            require(not root.exists(),'Package destination was created during packaging.')
            root.mkdir(parents=True)
            try:
                for child in stage.iterdir(): shutil.move(str(child),root/child.name)
            except Exception:
                # Retain partial artifacts for review; never claim successful packaging.
                raise ValueError('Package transfer failed; inspect the incomplete destination.') from None
            (root/'BUILD-HANDOFF.json').write_text(json.dumps({'contract':handoff['contract'],'author_envelope_sha256':digest(envelope),'status':'packaged-not-runtime-tested'},indent=2))
        self.journal('suite-packaged',path=str(root),author_envelope_sha256=digest(envelope))
        return {'path':str(root),'status':'packaged-not-runtime-tested','check':check}

    def verify(self, root, operation):
        require(operation in ('check','test','eval','install'),'Unsupported verification operation.')
        if operation=='install':
            root=self.root(root);self.manifest(root)
            require((root/'pixi.toml').is_file(),'No declared Pixi environment.')
            pixi=shutil.which('pixi') or str(Path.home()/'.pixi/bin/pixi')
            require(Path(pixi).is_file(),'Install Pixi before installing Cog environments.')
            self.journal('suite-environment-install-start',path=str(root))
            result=subprocess.run([pixi,'install'],cwd=root,env={k:v for k,v in os.environ.items() if not k.startswith('PIXI_')},capture_output=True,text=True,timeout=600)
            self.journal('suite-environment-install-exit',path=str(root),exit_code=result.returncode)
            return {'operation':'install','path':str(root),'exit_code':result.returncode,'stdout':result.stdout[-5000:],'stderr':result.stderr[-5000:]}
        if operation=='check':return self.call('cog-smith','check',[self.root(root),'--envelope'])
        result=self.call(root,operation,timeout=600,expect_json=False)
        record={'path':str(self.root(root)),'package_sha256':package_digest(self.root(root)), 'operation':operation,**result}
        path=self.save('checks',record)
        return {'record_path':path,**record}

    def bindings(self):
        values=[]
        for path in self.state.glob('*.json'):
            try:
                value=json.loads(path.read_text());b=value['binding']
                ref={'binding_id':b['binding_id'],'revision':b['revision']}
                try:self.load(ref);status='admitted'
                except ValueError:status='unavailable-or-changed'
                values.append({'reference':ref,'provider':b['provider'],'composition':b['composition'],'model':b['model'],'status':status})
            except (ValueError,KeyError):continue
        return values

    def evaluate(self, root, author_request, author_envelope, plan_envelope, ref):
        root=self.root(root)
        authored=clean(author_envelope);plan=clean(plan_envelope)
        require(author_envelope['cog']=={'id':'openteams/cog-author','version':'0.1.0'} and
                plan_envelope['cog']=={'id':'openteams/cog-build-evaluator','version':'0.1.0'}, 'Wrong author or evaluator identity.')
        validated=self.bridge('cog-author','finish',{'bundle':author_request,'result':authored,'provenance':{'source':'evaluation-preflight'}})
        clean(validated)
        require(authored['classification']=='authored', 'Evaluation requires a complete authored candidate.')
        for row in authored['files']:
            path=self.file(root,row['path'])
            require(path.is_file() and path.read_text()==row['content'], 'Packaged source no longer matches the evaluated candidate.')
        bundle={'operation':'plan','contract':authored['contract'],'files':authored['files'],'evidence':[]}
        clean(self.bridge('cog-build-evaluator','finish',{'bundle':bundle,'result':plan,'provenance':{'source':'evaluation-plan-preflight'}}))
        require(plan['classification']=='planned','Expected an evaluation plan.')
        composition=self.compose(root,ref)
        candidate=digest({'contract':authored['contract'],'files':sorted(authored['files'],key=lambda x:x['path'])})
        evidence=[]
        for case in plan['test_cases']:
            try:
                result=self.invoke(composition,case['input'])
            except ValueError as exc:
                result={'envelope':1,'cog':composition['consumer'],'task':'ask','ok':False,'payload':None,
                        'error':{'code':'case-invocation-failed','detail':str(exc)},
                        'problems':[{'check':'case-invocation-failed','detail':str(exc),'severity':'error'}],
                        'binding':{'composition':composition,'evidence_scope':'composed-system'}}
                self.journal('suite-case-failed',case_id=case['id'],consumer=composition['consumer'])
            # Execution status is bounded to envelope/check completion. The review
            # Cog still assesses expected behavior; this never grants acceptance.
            status='passed' if result['ok'] and not result['problems'] and not result['error'] else 'failed'
            text=json.dumps({'case_id':case['id'],'input':case['input'],'expected_behavior':case['expected_behavior'],
                             'observed_envelope':result,'execution_status_scope':'Envelope and packaged checks only; criterion acceptance remains for review.'},ensure_ascii=False)
            for criterion in case['criterion_ids']:
                evidence.append({'id':case['id']+':'+criterion,'criterion_id':criterion,'candidate_sha256':candidate,
                                 'kind':'execution','status':status,'text':text})
        review={**bundle,'operation':'review','evidence':evidence}
        self.bridge('cog-build-evaluator','prepare',{'bundle':review})
        value={'status':'executed-awaiting-independent-review','evidence_scope':'composed-system','review_request':review}
        path=self.save('evaluations',value)
        self.journal('suite-evaluation-cases',path=str(root),case_count=len(plan['test_cases']),record_path=path)
        return {'record_path':path,**value}
