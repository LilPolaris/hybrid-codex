import { Client } from '../vendor/cursor-chatgpt-web/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../vendor/cursor-chatgpt-web/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dir, '..');
const action = process.argv[2] ?? 'status';
if (!['status', 'single', 'batch'].includes(action)) throw new Error('Use status, single, or batch.');
if (action !== 'status' && process.env.CURSOR_CHATGPT_WEB_SIMULATE === '1') {
  throw new Error('Refusing a simulated run for a real smoke check. Unset CURSOR_CHATGPT_WEB_SIMULATE.');
}
const client = new Client({ name: 'hybrid-codex-smoke', version: '1.0.0' });
const transport = new StdioClientTransport({ command: process.execPath,
  args: [resolve(root, 'vendor/cursor-chatgpt-web/src/cli.ts'), 'cursor-mcp'], stderr: 'inherit' });
const unpack = (r: any) => r.structuredContent ?? JSON.parse(r.content.find((x: any) => x.type === 'text').text);
const evidence: Record<string, unknown> = { action, at: new Date().toISOString() };
let connected = false;
const ownedJobs = new Set<string>();
try {
  await client.connect(transport); connected = true;
  const catalog = await client.listTools();
  const names = catalog.tools.map(x => x.name).sort();
  if (JSON.stringify(names) !== JSON.stringify(['chatgpt_web_batch', 'chatgpt_web_cancel', 'chatgpt_web_status', 'chatgpt_web_turn'])) {
    throw new Error('Unexpected MCP tool catalog');
  }
  evidence.tools = names;
  evidence.before = unpack(await client.callTool({ name: 'chatgpt_web_status', arguments: {} }));
  if (action !== 'status') {
    const makePrompt = (task: string) => `TASK: ${task}\nGOAL: read-only smoke check.\nSCOPE: supplied text only.\nRELEVANT CODE: function take(xs,n){return xs.slice(0,n)}\nCONSTRAINTS: READ / ANALYZE / REPORT; no tools, no writes; Parent verifies.\nQUESTIONS: ${task}\nOUTPUT FORMAT: two short bullets; do not claim local execution.`;
    const nonce = Date.now().toString(36);
    const args = action === 'single'
      ? { mode: 'instant', queue: false, jobId: `hybrid-smoke-${nonce}`, prompt: makePrompt('What does take([1,2,3],-1) return? Name one boundary test.') }
      : { mode: 'medium', tasks: [
          { id: `hybrid-${nonce}-negative`, prompt: makePrompt('Explain negative n and suggest a boundary test.') },
          { id: `hybrid-${nonce}-zero`, prompt: makePrompt('Explain zero and oversized n and suggest tests.') },
          { id: `hybrid-${nonce}-mutation`, prompt: makePrompt('Does this function mutate xs? What happens to nested object references?') },
        ] };
    if (action === 'single') ownedJobs.add(`hybrid-smoke-${nonce}`);
    evidence.input = args;
    try {
      const response = await client.callTool({ name: action === 'single' ? 'chatgpt_web_turn' : 'chatgpt_web_batch', arguments: args }, undefined, { timeout: 600_000 });
      evidence.response = response;
      if (response.isError) throw new Error('MCP returned an error; inspect the saved response.');
      const data = unpack(response);
      for (const item of data.results ?? [data]) {
        ownedJobs.add(item.jobId);
        if (!item.answer || item.awaitingTools || item.toolCalls?.length) throw new Error('Worker did not finish a read-only answer.');
      }
    } finally {
      const status = unpack(await client.callTool({ name: 'chatgpt_web_status', arguments: {} }));
      evidence.after = status;
      for (const job of status.jobs ?? []) {
        if (job.jobId.includes(`hybrid-${nonce}-`)) ownedJobs.add(job.jobId);
        if (ownedJobs.has(job.jobId) && ['queued', 'running', 'awaiting_tools'].includes(job.status)) {
          await client.callTool({ name: 'chatgpt_web_cancel', arguments: { jobId: job.jobId } });
        }
      }
    }
  }
  console.log(`${action}: passed${action === 'status' ? ' (MCP/static status only; no ChatGPT generation)' : ' (real Worker response; Parent must still verify claims)'}`);
} catch (error) {
  evidence.error = String(error); process.exitCode = 1; console.error(error);
} finally {
  mkdirSync(resolve(root, 'reports'), { recursive: true });
  const path = resolve(root, `reports/smoke-${action}-${Date.now()}.json`);
  writeFileSync(path, JSON.stringify(evidence, null, 2));
  if (connected) await client.close();
  console.log(`Evidence: ${path}`);
}
