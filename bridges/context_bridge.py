"""Declared context-Cog bridge: execute its own checks around external turns.

Canonical source: cog-workbench/bridges/context_bridge.py. Installed explicitly
as scripts/context_bridge.py in opting-in Cogs; no changes to Smith machinery.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import cog_core


def process(operation, document):
    bundle = document['bundle']
    problems = cog_core.validate_input(bundle)
    if problems:
        raise ValueError('Context input failed packaged checks: ' + json.dumps(problems))
    if operation == 'prepare':
        return {'consumer': cog_core.SELF_ID,
                'context': [{'id': 'packaged-context', 'content': cog_core.load_context()}],
                'task': {'input': cog_core.task_logic.render_input(bundle), 'output_schema': cog_core.OUTPUT_SCHEMA}}
    result = document['result']
    if not isinstance(result, dict):
        raise ValueError('Context output must be a JSON object.')
    # Preserve semantic problems; the building workflow's Gate decides acceptance.
    problems = cog_core.validate_output(result, bundle)
    return cog_core._envelope('ask', True, payload=result, problems=problems,
                              binding=document['provenance'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'finish'])
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    try:
        result = process(args.operation, json.loads(Path(args.request).read_text()))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({'error': str(exc)})); sys.exit(1)
    print(json.dumps(result))
