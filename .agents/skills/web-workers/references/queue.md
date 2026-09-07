# Official MCP task queue

This is the default route for newly delegated work. Use ChatGPT Developer mode with
Secure MCP Tunnel to connect the stdio server. No automated ChatGPT input, DOM extraction,
browser daemon, or Parent provider change. User starts a batch in ChatGPT. Do not promise
that the app will wake itself or keep running indefinitely. The legacy browser tool is
not the transport for this route and its read-only restrictions remain unchanged.

## Local installation

From this repository run `python scripts/setup.py queue` and `python scripts/setup.py skill`.
Setup saves a nonsecret manifest in `$CODEX_HOME/worker-metrics/queue-bridge.json` with
the absolute Bun executable, script, data directory and full-access MCP command array.
Read that manifest rather than guessing paths in other projects. The repository and its
installed SDK dependency must remain available. The MCP process is started by tunnel-client;
do not expose a public unauthenticated command server.

Invoke the executable with `[script, action, '--data', data]`; send JSON via stdin.
Actions `enqueue`, `status`, `watch`, `cancel`, `review`, `fault`, `operations`,
`resolve-operation`, `resolve-task` are Parent-only local CLI actions. Only the official
connector receives worker tools. Never attach the Parent CLI management actions to it.

## Workflow

1. Parent does a minimal scope check and enqueues:

```json
{"id":"unique-subtask-id","session":"current-Codex-task-id","title":"Check parser",
 "prompt":"Concrete task, constraints, files and acceptance checks. Return concise evidence.",
 "cwd":"D:/project","baseline":[800,1500]}
```

Choose a defensible baseline before dispatch or use null. Explain its assumptions in
the prompt/Parent task note; do not infer savings from worker output. Reuse the same
task ID on retry; conflicting reuse is rejected. SQLite persists the queue and cooldowns.
Send only task-relevant material and authorize local operations within the user's request.

2. Tell the user to start the connected ChatGPT app with:

> Use Hybrid Task Queue. Claim tasks for session CURRENT_TASK_ID, execute the assigned
> work with its tools, submit results and continue until this batch is empty. Respect
> cancellation and do not create detached processes. Do not claim tests passed without
> executing them. Use the highest available model suitable for tool calls.

Model selection happens in ChatGPT; queue metadata is not verification of actual model
or effort. Do not call the old browser transport to simulate this user-started turn.

3. Parent watches its local queue, e.g. `watch` with `{"session":"...","wait_ms":30000}`.
This reads SQLite, not ChatGPT. It prints changes and ends after at most 60 seconds.
Parent can continue useful separate work and recheck the same task ID later.

4. Workers claim tasks and receive a lease; all reads/writes/commands require that lease.
Full mode has OS-user filesystem and shell access, including absolute paths outside cwd:
cwd is a working directory, not a sandbox. Use the tools only for the assigned task.
Writes use expected SHA256 to avoid accidental overwrites; operation IDs deduplicate
retries. Commands max out at 60 seconds with bounded output. Submit changed paths, tests,
evidence and unresolved issues. Parent rechecks decisive evidence and calls `review`:

```json
{"id":"unique-subtask-id","accepted":true,"overhead":[300,600]}
```

Copy `card` into the conversation after completion. Overhead includes preparation,
result reading, ledger calls, verification and failed attempts. Null stays unknown.
The baseline minus total overhead is a scenario estimate, not billed usage or quota.
Elapsed time includes queueing. Worker tool execution does not prove a specific model
ran it; distinguish real ChatGPT calls from local MCP test-client calls.

## Faults, cancellation and fallback

`fault` takes session and reason: auth (30 min), quota (60 min), unavailable (10 min),
transient (60 sec). While cooling, claim returns no task. Do not label an unstarted
ChatGPT batch as a provider outage. Queueing alone is not a failed generation.

Cancel unclaimed tasks immediately. Claimed tasks become cancel_requested; heartbeat
reports cancellation and new worker operations are rejected. In-flight commands are
terminated, but remain uncertain until Parent checks effects and actual process state.
Do not reassign based on heartbeat age. If the worker cannot acknowledge termination,
inspect the actual handle; then `resolve-operation` (id, operation, terminal_confirmed,
note) and `resolve-task` (id, terminal_confirmed, note) allow Parent to close stranded work.
Lease revocation rejects stale workers. Background child processes are forbidden by the
worker instructions; full access is not a process sandbox and Parent must inspect effects.

After confirmed cancellation or rejection, use native Luna max, then Parent if needed.
Request native model `gpt-5.6-luna`, `reasoning_effort="max"`, `fork_turns="none"` with
focused context using the current task's subagent tool when supported; don't create a
new user-visible task. If exact selection is unavailable, Parent takes over and reports it.
Keep the existing meter's same session/subtask for the whole fallback chain so failures
are deducted. For multi-provider chains the meter card is authoritative; don't add the
queue-only card a second time. For Web-only work the queue review card is sufficient.
The helper does not launch native agents; Parent invokes the current task's native tool.
