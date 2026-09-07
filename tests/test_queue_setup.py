import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import shlex

SPEC=importlib.util.spec_from_file_location('setup_queue',Path(__file__).parents[1]/'scripts/setup.py')
setup=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
CONNECT_SPEC=importlib.util.spec_from_file_location('connect_queue',Path(__file__).parents[1]/'scripts/connect_queue.py')
connect=importlib.util.module_from_spec(CONNECT_SPEC)
CONNECT_SPEC.loader.exec_module(connect)


class QueueSetupTests(unittest.TestCase):
    def test_manifest_full_access_without_parent_config_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            (home/'config.toml').write_text('model="unchanged"\n')
            path=setup.install_queue(home,'/existing/bun')
            manifest=json.loads(path.read_text())
            self.assertEqual(manifest['access'],'full')
            self.assertIn('--access',manifest['mcp_args'])
            self.assertEqual((home/'config.toml').read_text(),'model="unchanged"\n')
            setup.install_queue(home,'/existing/bun')
            self.assertFalse((home/'backups').exists())

    def test_tunnel_command_keeps_windows_paths_and_spaces(self):
        manifest={'command':r'C:\Tools With Spaces\bun.exe',
                  'mcp_args':[r'D:\My Repo\queue-bridge.ts','mcp','--data',r'C:\User Data\queue','--access','full']}
        words=shlex.split(connect.mcp_command(manifest))
        self.assertEqual(words,['C:/Tools With Spaces/bun.exe','D:/My Repo/queue-bridge.ts',
                                'mcp','--data','C:/User Data/queue','--access','full'])


if __name__=='__main__':unittest.main()
