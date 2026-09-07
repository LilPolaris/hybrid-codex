# Official MCP task queue / 官方 MCP 任务队列

The queue is independent of the old browser bridge. It does not launch ChatGPT turns,
extract browser output or change Parent routing. A user-started ChatGPT batch invokes
MCP tools through the official connector. / 队列独立于旧浏览器桥接；由用户启动网页批次，
通过官方连接器调用工具。

## Install / 安装

Requirements: Python 3.11+, Bun, the pinned submodule and its installed dependencies.
If dependencies are missing, initialize the submodule and run
`bun install --frozen-lockfile --ignore-scripts` in `vendor/cursor-chatgpt-web`.
This queue imports the installed MCP SDK, not the browser runtime.

```sh
python scripts/setup.py queue
python scripts/setup.py skill
```

The private manifest is `$CODEX_HOME/worker-metrics/queue-bridge.json`, defaulting to
`~/.codex/worker-metrics/queue-bridge.json`. It contains executable paths, no API keys.
Queue data is under `worker-metrics/queue`; it includes task prompts, command text and
results, so keep that directory private. The installer does not modify Parent config.

## Connect ChatGPT / 连接网页

Official references: [Developer mode](https://developers.openai.com/api/docs/guides/developer-mode)
and [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

This installer can reuse an existing tunnel-client binary and runtime key reference from
the local launcher configuration. Use a **separate tunnel** so the old runtime is preserved:

```sh
python scripts/connect_queue.py --tunnel-id YOUR_SEPARATE_TUNNEL_ID
python scripts/connect_queue.py --status
```

If valid admin credentials are already configured for tunnel-client, omitting
`--tunnel-id` creates/reuses the `hybrid-task-queue` alias in the verified workspace scope.
If an admin key environment variable is absent, create a tunnel in
[Platform settings](https://platform.openai.com/settings/organization/tunnels) instead.
Never paste keys into chat. The existing runtime key needs access to the new tunnel.

In ChatGPT, enable Developer mode, create a developer app, choose **Connection → Tunnel**
and select or paste the tunnel ID (not a guessed ordinary MCP HTTP URL),
refresh its tool catalog and select it in a conversation. Honor ChatGPT's own tool
confirmation settings; local installation does not suppress them.

The manifest's `command` plus `mcp_args` is also usable as the stdio target of an
independently configured official tunnel. `--access full` exposes read_path, write_file
and execute_command. Without it, write and command tools are absent.

## Use / 使用

Create `task.json` locally (or let Codex generate it):

```json
{
  "id":"parser-check-1",
  "session":"my-codex-task",
  "title":"Check parser",
  "prompt":"Inspect the parser in this project, fix the specified bug and run focused tests. Submit changed paths, results and uncertainties.",
  "cwd":"D:/my-project",
  "baseline":null
}
```

Use a real project and a concrete task. Unknown token estimates stay null.

```sh
python scripts/queue.py enqueue --input task.json
```

In the connected ChatGPT conversation send:

> Use Hybrid Task Queue to claim tasks in session my-codex-task. Complete each assigned
> task using its tools, submit concise results and continue until the batch is empty.
> Respect cancellation; do not launch detached processes.

Create `session.json` with `{"session":"my-codex-task","wait_ms":30000}`:

```sh
python scripts/queue.py watch --input session.json
python scripts/queue.py status --input session.json --details
```

Watch reads local SQLite and prints changes. It returns after at most 60 seconds;
Codex can invoke it again while continuing independent work. It never wakes ChatGPT.

Parent checks actual changes/tests, then reviews using a local file containing
`{"id":"parser-check-1","accepted":true,"overhead":null}`:

```sh
python scripts/queue.py review --input review.json
```

The resulting card is displayed in chat. Net savings is an assumed Parent baseline
minus estimated total delegation overhead. Include failed attempts, result reading and
verification; it is not measured billing savings. For multi-provider fallback, use the
skill's existing meter across the whole chain and do not double-count the queue card.

## Cancellation and access / 取消与权限

- `cancel` on a queued job is immediate. On a claimed job it requests cancellation and
  rejects new local operations. The worker acknowledges only after operations stop.
- Timed-out/killed commands remain uncertain because partial side effects are possible.
  Parent checks processes and files, then uses `resolve-operation`; `resolve-task` can
  close a stranded lease after terminal state is confirmed. Never reassign by age alone.
- Faults cool down only the affected session. `fault` accepts auth/quota/unavailable/transient.
- Full mode is OS-user access, including absolute paths outside cwd. The working directory
  is not an access boundary. Only connect this private app to the intended account/workspace.
- The connector exposes worker actions; enqueue/review/recovery remain local Parent CLI
  actions. File writes require a prior SHA256 or null for creation. Operation IDs prevent
  accidental replay, but arbitrary full-access shell commands are not an OS sandbox.

## Verify / 验证

```sh
bun test tests/queue-bridge.test.ts
python -X utf8 -m unittest discover -s tests -p "test_*.py"
```

Tests use a standard MCP client to perform real temporary-directory file writes, shell
execution, result submission and Parent review. They cover cancellation/timeouts,
leases and deduplication. They do **not** prove that a particular ChatGPT account has
connected. Verify tunnel process/health/readiness and a real user-started ChatGPT task
separately before claiming account-level acceptance.

### Live acceptance / 实际验收 (2026-09-07)

A user-started ChatGPT conversation claimed the acceptance job through a separate
official tunnel, wrote `acceptance.txt` in a temporary directory, ran a strict content
comparison and submitted its result. The final command exited 0 and read back exactly
`official-mcp-ok`. An earlier command failed because of PowerShell quoting; the worker
reported that failure and retried successfully. Codex independently checked the actual
file and SHA256, checked that all recorded operations were done, and accepted the job.
Both the new queue tunnel and the existing tunnel were healthy and ready during setup.
No specific ChatGPT model or reasoning tier was inferred from the worker name.
Token savings were left unknown because this setup acceptance had no defensible baseline.

用户启动的真实 ChatGPT 批次已完成领取、写文件、命令验证和结果提交，Codex 已复核
实际文件及操作记录并验收。此记录验证本次账号连接；不代表其他账号自动连接成功，
也不代表网页可自动唤醒。测试套件另有 7 项队列测试与 17 项 Python 测试通过。
