"""Install the skill or attach an existing launcher as a specialist MCP.

Python 3.11+. No login, daemon installation, or Parent provider routing changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PIN = 'b3733e277f5523909845a5555c11a122e4900742'
TOOLS = ['chatgpt_web_turn', 'chatgpt_web_batch', 'chatgpt_web_status', 'chatgpt_web_cancel']


def codex_home() -> Path:
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser().resolve()


def bridge_home() -> Path:
    return Path(os.environ.get('CURSOR_CHATGPT_WEB_HOME') or
                os.environ.get('CODEX_CHATGPT_WEB_HOME') or
                Path.home() / '.codex-chatgpt-web').expanduser().resolve()


def backup(path: Path, home: Path) -> Path | None:
    if not path.exists():
        return None
    dest = home / 'backups' / 'hybrid-codex' / datetime.now().strftime('%Y%m%d-%H%M%S-%f') / path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, dest)
    else:
        shutil.copy2(path, dest)
    return dest


def install_skill(home: Path) -> Path:
    source = ROOT / '.agents' / 'skills' / 'web-workers'
    target = home / 'skills' / 'web-workers'
    files = [source / 'SKILL.md', source / 'agents' / 'openai.yaml',
             source / 'scripts' / 'worker_meter.py', source / 'references' / 'meter.md']
    if all((target / p.relative_to(source)).is_file() and
           (target / p.relative_to(source)).read_bytes() == p.read_bytes() for p in files):
        return target
    saved = backup(target, home)
    if saved:
        print(f'Previous skill backed up: {saved}')
    for p in files:
        dest = target / p.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
    return target


def find_bun(explicit: str | None = None) -> str:
    if explicit and not Path(explicit).is_file():
        raise RuntimeError(f'Explicit Bun executable does not exist: {explicit}')
    candidates = [explicit, shutil.which('bun')]
    config = bridge_home() / 'config.json'
    if config.exists():
        command = json.loads(config.read_text(encoding='utf-8')).get('runtimeCommand', [])
        if command:
            candidates.append(command[0])
    for item in candidates:
        if item and Path(item).is_file():
            return str(Path(item).resolve())
    raise RuntimeError('Bun not found. Put Bun on PATH or supply --bun /absolute/path/to/bun.')


def prepare_backend(bun: str) -> None:
    vendor = ROOT / 'vendor' / 'cursor-chatgpt-web'
    if not (vendor / 'src' / 'cli.ts').exists():
        raise RuntimeError('Initialize the pinned submodule first: git submodule update --init')
    head = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN:
        raise RuntimeError(f'Unexpected upstream revision {head}; expected {PIN}. No patch applied.')
    patch = str(ROOT / 'patches' / 'cursor-chatgpt-web.patch')
    reverse = subprocess.run(['git', '-C', str(vendor), 'apply', '--reverse', '--check', patch],
                             capture_output=True)
    if reverse.returncode:
        subprocess.run(['git', '-C', str(vendor), 'apply', '--check', patch], check=True)
        subprocess.run(['git', '-C', str(vendor), 'apply', patch], check=True)
    subprocess.run([bun, 'install', '--frozen-lockfile', '--ignore-scripts'], cwd=vendor, check=True)


def mcp_table(bun: str) -> dict:
    vendor = ROOT / 'vendor' / 'cursor-chatgpt-web'
    result = {'command': bun, 'args': [str(vendor / 'src' / 'cli.ts'), 'cursor-mcp'],
              'cwd': str(vendor), 'startup_timeout_sec': 30, 'tool_timeout_sec': 600,
              'enabled_tools': TOOLS}
    # Child MCP must use the same launcher directory as the installer when customized.
    for name in ['CURSOR_CHATGPT_WEB_HOME', 'CODEX_CHATGPT_WEB_HOME']:
        if os.environ.get(name):
            result.setdefault('env', {})[name] = str(bridge_home())
            break
    return result


def add_mcp(text: str, server: dict) -> str:
    config = tomllib.loads(text)
    existing = config.get('mcp_servers', {}).get('chatgpt-web')
    if existing is not None:
        if existing == server:
            return text
        raise RuntimeError('chatgpt-web already exists with different settings; refusing to overwrite it.')
    lines = ['\n# Hybrid Codex: explicit Web workers; Parent routing is unchanged.', '[mcp_servers.chatgpt-web]']
    for key, value in server.items():
        if key != 'env':
            lines.append(f'{key} = {json.dumps(value, ensure_ascii=False)}')
    if server.get('env'):
        lines.append('[mcp_servers.chatgpt-web.env]')
        lines.extend(f'{key} = {json.dumps(value)}' for key, value in server['env'].items())
    result = text.rstrip() + '\n' + '\n'.join(lines) + '\n'
    parsed = tomllib.loads(result)
    parsed['mcp_servers'].pop('chatgpt-web')
    if not parsed['mcp_servers'] and 'mcp_servers' not in config:
        parsed.pop('mcp_servers')
    if parsed != config:
        raise RuntimeError('Unexpected unrelated config change; refusing to write.')
    return result


def existing_launcher() -> dict:
    path = bridge_home() / 'config.json'
    if not path.exists():
        raise RuntimeError('Existing codex-chatgpt-web login/launcher required. This tool does not install a daemon.')
    config = json.loads(path.read_text(encoding='utf-8'))
    if config.get('browserHost') != 'launcher':
        raise RuntimeError('This compatibility package requires an existing launcher browserHost.')
    descriptor = Path(config.get('browserHostDescriptorPath', '')).expanduser()
    if not descriptor.is_file() or json.loads(descriptor.read_text(encoding='utf-8')).get('version') != 2:
        raise RuntimeError('Expected launcher descriptor v2. Start the existing compatible launcher first.')
    return config


def install_backend(home: Path, bun: str) -> None:
    existing_launcher()
    path = home / 'config.toml'
    before = path.read_text(encoding='utf-8') if path.exists() else ''
    after = add_mcp(before, mcp_table(bun))  # Detect conflicts before doing any backend writes.
    prepare_backend(bun)
    if after == before:
        print('MCP already configured; user config unchanged.')
        return
    saved = backup(path, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Check for concurrent Codex settings edits before committing.
    current = path.read_text(encoding='utf-8') if path.exists() else ''
    if current != before:
        raise RuntimeError('Codex config changed during setup. Retry after reviewing the current settings.')
    fd, temporary = tempfile.mkstemp(prefix='hybrid-codex-', suffix='.toml', dir=home)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(after)
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    print(f'MCP installed. Previous config backup: {saved or "not needed (new file)"}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['skill', 'backend', 'doctor'])
    parser.add_argument('--bun', help='Absolute path to an existing Bun executable')
    args = parser.parse_args()
    home = codex_home()
    if args.action == 'skill':
        print(f'User skill installed: {install_skill(home)}')
    elif args.action == 'backend':
        install_backend(home, find_bun(args.bun))
    else:
        path = home / 'config.toml'
        config = tomllib.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        print(json.dumps({'skill_installed': (home/'skills/web-workers/SKILL.md').is_file(),
                          'mcp_configured': 'chatgpt-web' in config.get('mcp_servers', {}),
                          'parent_model': config.get('model'),
                          'parent_base_url_override_present': 'openai_base_url' in config,
                          'bun': find_bun(args.bun)}, indent=2))
        existing_launcher()
        print('Static configuration checks passed. This does not prove login or live Worker success.')


if __name__ == '__main__':
    main()
