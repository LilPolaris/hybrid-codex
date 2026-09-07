# Compatibility patch

Pinned upstream: `Rakeem-C/cursor-chatgpt-web`
`b3733e277f5523909845a5555c11a122e4900742` (2.1.8).

The patch was tested with an existing Windows Codex Web GPT 4.0.8 launcher and
Bun 1.4.0. It does not patch or reinstall the user's existing launcher.

Changes:

1. Recognize launcher descriptor v2, retaining profile, loopback endpoint,
   owned surface, partition and helper identity checks.
2. Handle `prepared_selected`, `send_activated`, `submitted` and corresponding
   acknowledgments. Fresh worker conversations reject unexpected reuse.
3. Serialize preparation until submission, allowing generation to overlap.
4. Replace senior-specialist MCP instructions with subordinate read-only worker
   rules; nonempty `tools` and `toolResults` are rejected by the MCP schema.
5. Update descriptor/helper fixtures for the compatible protocol.

Prepare the checked-out backend without touching user configuration:

```sh
python -c "import sys; sys.path.insert(0, 'scripts'); import setup; setup.prepare_backend(setup.find_bun())"
```

Run the focused suite:

```sh
bun test ./tests/preparation-gate.test.ts ./vendor/cursor-chatgpt-web/tests/launcher-helper-client.test.ts ./vendor/cursor-chatgpt-web/tests/launcher-browser-host.test.ts ./vendor/cursor-chatgpt-web/tests/cursor-specialist.test.ts ./vendor/cursor-chatgpt-web/tests/cursor-v2.test.ts ./vendor/cursor-chatgpt-web/tests/cursor-mcp-protocol.test.ts
```

The original integration passed 36 tests across those files. These are protocol
and task-pool tests, not proof of a logged-in ChatGPT session.

The upstream full TypeScript check was not green in the tested environment:
`browser-worker.ts` has a DOM callback type mismatch, `browser-login.test.ts` has
literal-type expectation errors, and `cursor-mcp-protocol.test.ts` has a Writable
type mismatch. Those files were not changed to hide the errors.

No original host-specific logs, config snapshots, process IDs, or restart/rollback
scripts are part of the public repository. Keep future live reports out of Git.
