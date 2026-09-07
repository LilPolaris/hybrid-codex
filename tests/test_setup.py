import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest

SPEC = importlib.util.spec_from_file_location('hybrid_setup', Path(__file__).parents[1]/'scripts/setup.py')
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_mcp_preserves_existing_provider_and_features(self):
        before = 'model = "native-model"\nopenai_base_url = "https://example.invalid/v1"\n[features]\nmulti_agent = true\n[mcp_servers.existing]\ncommand = "existing"\n'
        server = {'command': '/path with spaces/bun', 'args': ['/repo/cli.ts', 'cursor-mcp'],
                  'env': {'CODEX_CHATGPT_WEB_HOME': '/a/custom/home'}}
        after = setup.add_mcp(before, server)
        parsed = tomllib.loads(after)
        self.assertEqual(parsed['mcp_servers'].pop('chatgpt-web'), server)
        self.assertEqual(parsed, tomllib.loads(before))
        self.assertEqual(setup.add_mcp(after, server), after)

    def test_conflicting_mcp_is_not_overwritten(self):
        with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
            setup.add_mcp('[mcp_servers.chatgpt-web]\ncommand="another"\n', {'command': 'new'})

    def test_new_config_is_valid(self):
        self.assertEqual(tomllib.loads(setup.add_mcp('', {'command': 'bun'})),
                         {'mcp_servers': {'chatgpt-web': {'command': 'bun'}}})

    def test_skill_is_idempotent_and_backs_up_an_existing_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = setup.install_skill(home)
            expected = (target/'SKILL.md').read_bytes()
            setup.install_skill(home)
            self.assertFalse((home/'backups').exists())
            (target/'SKILL.md').write_text('previous user skill', encoding='utf-8')
            setup.install_skill(home)
            self.assertEqual((target/'SKILL.md').read_bytes(), expected)
            snapshots = list((home/'backups').glob('hybrid-codex/*/web-workers/SKILL.md'))
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0].read_text(), 'previous user skill')


if __name__ == '__main__':
    unittest.main()
