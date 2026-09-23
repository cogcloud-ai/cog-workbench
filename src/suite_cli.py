"""Command entry point for the Cog tool suite; JSON in/out for reusable workflows."""
import argparse
import json
from pathlib import Path
import sys
from workbench_suite import Suite


def read(path):return json.loads(Path(path).read_text())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace');p.add_argument('--state')
    sub=p.add_subparsers(dest='op',required=True)
    sub.add_parser('catalog');sub.add_parser('bindings')
    s=sub.add_parser('select');s.add_argument('--requirement',required=True)
    b=sub.add_parser('bind');b.add_argument('--provider',required=True);b.add_argument('--request',required=True)
    c=sub.add_parser('compose');c.add_argument('--context',required=True);c.add_argument('--binding-id',required=True);c.add_argument('--revision',type=int,required=True)
    c=sub.add_parser('activate-composition');c.add_argument('--context',required=True);c.add_argument('--binding-id',required=True);c.add_argument('--revision',type=int,required=True)
    r=sub.add_parser('revoke');r.add_argument('--binding-id',required=True);r.add_argument('--revision',type=int,required=True)
    i=sub.add_parser('invoke');i.add_argument('--composition',required=True);i.add_argument('--bundle',required=True)
    h=sub.add_parser('handoff');h.add_argument('--request',required=True);h.add_argument('--envelope',required=True)
    b=sub.add_parser('package');b.add_argument('--request',required=True);b.add_argument('--envelope',required=True);b.add_argument('--destination',required=True)
    b=sub.add_parser('snapshot');b.add_argument('--request',required=True);b.add_argument('--envelope',required=True)
    e=sub.add_parser('evaluate');e.add_argument('--cog',required=True);e.add_argument('--author-request',required=True);e.add_argument('--author-envelope',required=True);e.add_argument('--plan-envelope',required=True);e.add_argument('--binding-id');e.add_argument('--revision',type=int)
    for op in ('check','test','eval','install'):
        c=sub.add_parser(op);c.add_argument('--cog',required=True)
    args=p.parse_args();suite=Suite(args.workspace,args.state)
    try:
        if args.op=='catalog':result=suite.catalog()
        elif args.op=='bindings':result=suite.bindings()
        elif args.op=='select':result=suite.select(read(args.requirement))
        elif args.op=='bind':result=suite.bind(args.provider,read(args.request))
        elif args.op=='compose':result=suite.compose(args.context,{'binding_id':args.binding_id,'revision':args.revision})
        elif args.op=='activate-composition':result=suite.activate_composition(args.context,{'binding_id':args.binding_id,'revision':args.revision})
        elif args.op=='revoke':result=suite.revoke({'binding_id':args.binding_id,'revision':args.revision})
        elif args.op=='invoke':result=suite.invoke(read(args.composition),read(args.bundle))
        elif args.op=='handoff':result=suite.handoff(read(args.request),read(args.envelope))
        elif args.op=='package':result=suite.package(read(args.request),read(args.envelope),args.destination)
        elif args.op=='snapshot':result=suite.source_snapshot(read(args.request),read(args.envelope))
        elif args.op=='evaluate':result=suite.evaluate(args.cog,read(args.author_request),read(args.author_envelope),read(args.plan_envelope),{'binding_id':args.binding_id,'revision':args.revision} if args.binding_id else None)
        else:result=suite.verify(args.cog,args.op)
        print(json.dumps(result,indent=2))
        if isinstance(result,dict) and (result.get('exit_code',0)!=0 or result.get('ok') is False):
            return 1
        return 0
    except (ValueError,KeyError,OSError) as exc:
        print(json.dumps({'error':str(exc)}));return 1

if __name__=='__main__':sys.exit(main())
