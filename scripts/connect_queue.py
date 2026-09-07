"""Connect the installed queue through the official tunnel-client managed runtime.

Reuses existing credential references, never prints key contents, and leaves the
original tunnel runtime unchanged. With no --tunnel-id, admin tunnel creation is used.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess


def run(command, timeout=90):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            timeout=timeout, creationflags=0x08000000 if os.name == 'nt' else 0)
    if result.returncode:
        message = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', result.stderr or result.stdout)
        raise RuntimeError(message[:2000])
    return json.loads(result.stdout)


def mcp_command(manifest):
    # tunnel-client parses shell words even on Windows; this is not a cmd.exe command.
    # Forward slashes keep its parser from consuming Windows path separators.
    return shlex.join([str(s).replace('\\','/') for s in [manifest['command'],*manifest['mcp_args']]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tunnel-id', help='Existing separate tunnel to use instead of creating one')
    parser.add_argument('--alias', default='hybrid-task-queue')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    home = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')
    bridge = Path(os.environ.get('CURSOR_CHATGPT_WEB_HOME') or
                  os.environ.get('CODEX_CHATGPT_WEB_HOME') or Path.home()/'.codex-chatgpt-web')
    old = json.loads((bridge/'config.json').read_text(encoding='utf-8'))['tunnel']
    manifest = json.loads((home/'worker-metrics/queue-bridge.json').read_text(encoding='utf-8'))
    binary = old['binaryPath']
    if not args.status:
        command = [binary, 'runtimes', 'connect', '--alias', args.alias,
                   '--name', 'Hybrid Task Queue', '--description', 'User-started ChatGPT MCP local task execution',
                   '--profile', args.alias, '--profile-dir', str(home/'worker-metrics/tunnel-profiles'),
                   '--runtime-api-key', 'file:'+old['runtimeKeyFile'],
                   '--mcp-command', mcp_command(manifest), '--json']
        if args.tunnel_id:
            if args.tunnel_id == old['tunnelId']:
                raise RuntimeError('Use a separate tunnel ID; the existing launcher tunnel stays unchanged')
            command += ['--tunnel-id', args.tunnel_id]
        else:
            status = run([binary,'runtimes','status',old['alias'],'--json'])
            remote = status.get('remote') or {}
            key, flag = ('workspace_ids','--workspace-id') if remote.get('workspace_ids') else ('organization_ids','--organization-id')
            for value in remote.get(key,[]):
                command += [flag,value]
            if not remote.get('organization_ids') and not remote.get('workspace_ids'):
                raise RuntimeError('No verified tunnel scope; supply a separate --tunnel-id')
        run(command)
    status = run([binary,'runtimes','status',args.alias,'--json'])
    safe = {k:status.get(k) for k in ['alias','tunnel_id','process_running','healthy','ready',
                                    'runtime_state','remote_error','ui_url']}
    (home/'worker-metrics/queue-tunnel-status.json').write_text(json.dumps(safe,indent=2),encoding='utf-8')
    print(json.dumps(safe,indent=2))


if __name__ == '__main__':
    main()
