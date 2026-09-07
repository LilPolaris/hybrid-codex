"""Use the installed queue manifest. JSON from --input UTF-8 file or stdin.

Default output is a compact inline card. --details returns structured evidence.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enqueue','status','watch','cancel','review','fault',
                                         'operations','resolve-operation','resolve-task'])
    parser.add_argument('--input', type=Path)
    parser.add_argument('--details', action='store_true')
    args = parser.parse_args()
    home = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')
    manifest = json.loads((home/'worker-metrics/queue-bridge.json').read_text(encoding='utf-8'))
    raw = args.input.read_text(encoding='utf-8-sig') if args.input else sys.stdin.read()
    value = json.loads(raw)
    command = [manifest['command'],manifest['script'],args.action,'--data',manifest['data']]
    # Watch produces incremental JSON lines; pass them through without buffering.
    if args.action == 'watch':
        p = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr,
                             text=True,encoding='utf-8',creationflags=0x08000000 if os.name=='nt' else 0)
        p.stdin.write(json.dumps(value));p.stdin.close()
        for line in p.stdout:
            show(json.loads(line),args.details)
        sys.exit(p.wait())
    p = subprocess.run(command,input=json.dumps(value),capture_output=True,text=True,encoding='utf-8',
                       creationflags=0x08000000 if os.name=='nt' else 0)
    if p.returncode:
        print(p.stderr,file=sys.stderr);sys.exit(p.returncode)
    show(json.loads(p.stdout),args.details)


def show(value, details):
    if details:
        print(json.dumps(value,ensure_ascii=False,indent=2),flush=True)
    else:
        for row in value if isinstance(value,list) else [value]:
            print(row.get('card',json.dumps(row,ensure_ascii=False)),flush=True)


if __name__=='__main__':
    main()
