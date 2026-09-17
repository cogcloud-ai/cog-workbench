"""Goal-first workbench surface. Long operations use local, inspectable jobs."""
import json
from pathlib import Path
import threading
import uuid
from workbench_suite import Suite, clean

JOBS={}
LOCK=threading.Lock()
TOKEN=uuid.uuid4().hex
MANAGER=None


def local_host(handler):
    from urllib.parse import urlsplit
    try:
        host=urlsplit('http://'+handler.headers.get('Host',''))
        return host.hostname in ('127.0.0.1','localhost') and host.port==handler.server.server_port and not host.username and not host.password
    except ValueError:
        return False


def start(suite, body):
    action=body.get('action')
    require_actions={'bind','invoke','handoff','package','verify','revoke','evaluate','gateway'}
    if action not in require_actions:raise ValueError('Unknown suite action.')
    ident=str(uuid.uuid4())
    with LOCK:JOBS[ident]={'status':'working','action':action}
    def work():
        try:
            if action=='bind':result=suite.bind(body['provider'],body['request'])
            elif action=='revoke':result=suite.revoke(body['binding'])
            elif action=='gateway':
                import shlex
                entry=suite.load(body['binding'])
                if not entry.get('host_state') or MANAGER is None:raise ValueError('Select an admitted OpenRouter model.')
                from urllib.parse import urlsplit
                port=urlsplit(entry['binding']['configuration']['gateway_base_url']).port
                # Fixed host-owned state path and validated integer port; no user command.
                result=MANAGER.start(entry['path'],'serve',extra_args='--state-dir '+shlex.quote(entry['host_state'])+' --port '+str(port))
            elif action=='evaluate':result=suite.evaluate(body['path'],body['author_request'],body['author_envelope'],body['plan_envelope'],body['binding'])
            elif action=='invoke':
                composition=suite.compose(body['context'],body['binding'])
                result=suite.invoke(composition,body['bundle'])
            elif action=='handoff':result=suite.handoff(body['request'],body['envelope'])
            elif action=='package':result=suite.package(body['request'],body['envelope'],body['destination'])
            else:result=suite.verify(body['path'],body['operation'])
            path=suite.save('jobs',{'action':action,'result':result})
            with LOCK:JOBS[ident]={'status':'done','result':result,'record_path':path}
        except Exception as exc:
            suite.journal('suite-job-failed',job=ident,action=action,error_type=type(exc).__name__)
            with LOCK:JOBS[ident]={'status':'failed','error':str(exc) if isinstance(exc,ValueError) else 'Operation failed; inspect its inputs and environment.'}
    threading.Thread(target=work,daemon=True).start()
    return {'job':ident}


def get(handler,route,q,journal):
    if (route=='/studio' or route.startswith('/api/suite/')) and not local_host(handler):
        handler._send(403,{'error':'Loopback host required.'});return True
    if route=='/studio':
        html=(Path(__file__).parent/'studio.html').read_text().replace('__SUITE_TOKEN__',TOKEN)
        handler._send(200,html.encode(),'text/html; charset=utf-8');return True
    if not route.startswith('/api/suite/'):return False
    suite=Suite(journal=journal)
    if route=='/api/suite/catalog':result={'catalog':suite.catalog(),'bindings':suite.bindings()}
    elif route=='/api/suite/job':
        with LOCK:result=JOBS.get(q.get('id'),{'status':'missing'})
    else:result={'error':'not-found'}
    handler._send(200,result);return True


def post(handler,route,body,journal):
    if route!='/api/suite/action':return False
    # New write surface is same-origin and session-token protected. Browser
    # clients cannot use this endpoint as a cross-site local execution proxy.
    if not local_host(handler) or handler.headers.get('X-Cog-Workbench')!=TOKEN:
        handler._send(403,{'error':'Reload the workbench page before submitting.'});return True
    origin=handler.headers.get('Origin')
    if origin and origin!='http://'+handler.headers.get('Host',''):
        handler._send(403,{'error':'Origin mismatch.'});return True
    try:handler._send(202,start(Suite(journal=journal),body))
    except ValueError as exc:handler._send(400,{'error':str(exc)})
    return True
