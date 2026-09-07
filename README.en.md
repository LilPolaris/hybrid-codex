# Hybrid Codex

[简体中文](README.md) | **English**

## Current: official MCP task queue

Codex queues tasks and reviews results. You start a batch in ChatGPT Developer mode;
the connected app claims tasks, reads/writes local files, runs commands and submits
results through MCP. No browser answer scraping is used.

```text
Codex → local queue ← ChatGPT Developer mode
           ↓                 ↓
     status + estimates   local tools
           ↑                 ↓
      Parent review ← MCP result submission
```

- Full mode uses the local OS user's permissions; it is not a directory sandbox.
- Persistent queue, operation deduplication, file version checks, cancellation and cooldowns.
- Inline estimated net Parent token savings; unknown remains unknown, not billing usage.
- Native Luna max then Parent fallback after confirmed worker termination.
- The user starts ChatGPT batches; background monitoring reads the local queue. No promise
  of automatic ChatGPT wakeup or indefinite execution.

With repository dependencies already installed:

```sh
python scripts/setup.py queue
python scripts/setup.py skill
python scripts/connect_queue.py --tunnel-id YOUR_SEPARATE_TUNNEL_ID
```

Then connect **Hybrid Task Queue** in ChatGPT Developer mode. See the
[task queue guide](docs/task-queue.md) for setup, operation and verification. On
2026-09-07, local tests and live ChatGPT acceptance passed: the official tunnel carried
file writes, command execution and result submission, independently checked by Codex.
Other accounts still need their own connection acceptance.

## Historical browser integration (not for new tasks)

The material below preserves the previous architecture and installation records for
maintenance. Use the official MCP queue above for new work, not the old browser workflow.

**Native Codex handles planning, implementation and acceptance. ChatGPT Web handles bounded, read-only investigations in parallel.**

Native Codex is the parent. ChatGPT Web provides subordinate, read-only workers
through MCP. This repository packages a reusable user skill, a pinned specialist
backend, and compatibility patches for an existing launcher. No LazyCodex required.

```text
Native Codex Parent → native Codex backend
├─ Native tools: search, shell, edits, tests
├─ Native subagents: planning, implementation, verification
└─ Explicit chatgpt-web MCP
   → Existing Codex Web GPT launcher
   → ChatGPT Web workers (up to 5)
```

## Features

- `chatgpt_web_turn`: one focused reading or analysis task.
- `chatgpt_web_batch`: up to five independent tasks; preparation and submission are queued, while generation can overlap.
- `chatgpt_web_status`: inspect slots, tasks and queues in the current MCP runtime.
- `chatgpt_web_cancel`: cancel jobs owned by the current task.
- `$web-workers`: guides Parent through local search, context preparation, delegation, result collection and verification.

Suitable work includes code reading, module summaries, dependency inspection, call
tracing, log analysis, test failure classification and edge-case enumeration.
Parent retains requirements, architecture, key trade-offs, repository writes, test
execution and final judgment.

## Requirements and boundaries

This project is an **integration layer for an existing installation**, not a ChatGPT
login tool or browser daemon installer.

- Python 3.11+, Git and Bun.
- An installed and logged-in [codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web) launcher.
- Previously verified combination: Windows, launcher/runtime 4.0.8, descriptor v2 and Bun 1.4.0. The specialist upstream declares Bun 1.3.14; other versions and platforms need verification.
- Parent should use its native provider. This project **does not set or change `openai_base_url`** or create a second daemon.
- Web workers receive only the material Parent supplies and have no local tools. This is not an OS-level sandbox.
- Calls send selected text to the logged-in ChatGPT account. Do not send credentials, entire repositories or unrelated conversations.

If the root `openai_base_url` still points to an old local bridge, follow the
[migration notes (Chinese)](docs/architecture.md) to inspect and disconnect Parent
routing first. Do not restore the entire Parent bridge to fix a worker failure.

## Installation

```sh
git clone --recurse-submodules https://github.com/LilPolaris/hybrid-codex.git
cd hybrid-codex
```

**If you already have a working `chatgpt-web` MCP and want the skill across projects:**

```sh
python scripts/setup.py skill
```

The skill installs to `$CODEX_HOME/skills/web-workers`, or
`~/.codex/skills/web-workers` when CODEX_HOME is unset. Existing versions are backed
up first; reinstalling identical content does not create another backup. Parent and
MCP configuration remain unchanged.

**If you have a compatible launcher and login but have not connected the specialist MCP:**

```sh
python scripts/setup.py backend
python scripts/setup.py skill
python scripts/setup.py doctor
```

`backend` checks the pinned upstream commit, applies this repository's patch, installs
locked dependencies and appends the MCP table. It backs up configuration before
writing and refuses to overwrite a differently configured MCP with the same name.
It does not run upstream setup, serve or install-codex, or change login or launcher
configuration.

If Bun is not on PATH, setup reuses runtimeCommand from the existing launcher config.
You can also pass `--bun /absolute/path/to/bun`. Custom installations use the existing
`CURSOR_CHATGPT_WEB_HOME` or `CODEX_CHATGPT_WEB_HOME` setting.

Open a new Codex task after installation. If the tool or skill list is still stale,
fully restart Codex.

## Usage

In any project or file task:

> $web-workers Use three read-only workers to investigate the login middleware, frontend login flow and test coverage. Select the relevant context, collect and verify the important claims, then decide what to change.

For a single file:

> $web-workers Read the relevant excerpts of my specified file, summarize its responsibilities and edge cases, and verify the findings.

Parent first searches and reads locally, then prepares:

```text
TASK / GOAL / SCOPE / RELEVANT CODE
CONSTRAINTS / QUESTIONS / OUTPUT FORMAT
```

During ordinary work, Parent automatically identifies bounded reading, analysis and
drafting tasks whose results are easy to verify. You do not need to name the skill
every time. The default order is:

**Highest available Web mode → native `gpt-5.6-luna` / `max` → Parent.**

Prefer using the ample Web allowance for eligible reasoning, including decomposition
proposals, benefit estimates and preliminary quality review. Positive estimated net
savings is not a dispatch requirement. Parent retains necessary local actions, key
decisions and final verification.

Web status is checked first. The first available mode in
`pro → extra-high → high → medium → instant` is selected. “Highest” means reasoning
mode, not remaining usage quota. Web `luna` is not native Luna max.
Fallback reasons are briefly reported. Only a diagnosed transient or input problem
gets one corrected retry, preventing repeated failed attempts.

This is a skill-based delegation policy. It depends on the host loading the skill
and exposing the required tools; it is not a background routing service.
Prefer batch for 2–5 independent investigations. Grep and file lookup tool actions stay
local; delegate analysis of their results to Web where feasible. Important claims follow:
worker claim → Parent inspects code or runtime
results → verification → decision.

### Per-delegation numbers and failure cooldowns

Before dispatch, the skill records an estimated baseline for Parent work. After each
attempt it shows an inline message, for example:

> Delegation log-review | web/high → luna/max | 24.6s | estimated net Parent savings −200…+1,000 tokens

This is a format example. The range deducts preparation, returned context, verification
and failed-attempt overhead. Negative values mean potentially greater token cost.
Unknown values remain unknown; worker usage is never counted directly as savings.
These are not actual billing, quota or account-wide savings. Native Luna also consumes
native account usage.

Within a task, authentication failures cool down for 30 minutes, exhausted quota for
60 minutes, unavailable tools for 10 minutes and transient failures for 60 seconds.
Other subtasks skip that provider during cooldown. SQLite state survives resumption;
separate tasks remain independent. Running or unresolved jobs block duplicate dispatch.

No local report needs to be opened. Setup installs the ledger helper with the skill.
Its default database is `$CODEX_HOME/worker-metrics/ledger.sqlite`; only identifiers,
numbers and brief status metadata are recorded. See the
[accounting workflow](.agents/skills/web-workers/references/meter.md).

## Verification

```sh
python -m unittest discover -s tests -p "test_*.py"
python scripts/setup.py doctor
bun scripts/smoke.ts status
```

The last two commands check static configuration and MCP connectivity;
**they do not prove successful Web generation**. These commands make real ChatGPT requests:

```sh
bun scripts/smoke.ts single
bun scripts/smoke.ts batch
```

Script records go to the ignored `reports/` directory. After script checks, invoke
tools through `$web-workers` in a normal Codex task to verify session loading and
Parent's review workflow.

Public summary of earlier local acceptance records: native Parent/high, a native
subagent, all four MCP tools after restart, a real single-worker run and a real
three-worker run passed. In one three-task run, all generation windows overlapped
for 11.923 seconds. This is a recorded observation, not a performance guarantee.
Private configuration, login data, session IDs and full logs are not published.

Independent routing and cooldown tests cover Web success, Luna fallback, Parent fallback,
cooldown expiry, duplicate records, running-job reservations and negative savings.
Report live tool acceptance and injected failures separately: fault injection does not
mean the account experienced a real outage.
See the [acceptance record](docs/worker-acceptance.md) for live calls, cancellation and fallback scope.

## Source and maintenance

- `.agents/skills/web-workers/`: publishable, installable skill source.
- `scripts/setup.py`: user-level skill installation and MCP integration with an existing launcher.
- `scripts/smoke.ts`: standalone MCP connectivity and optional live smoke checks.
- `vendor/cursor-chatgpt-web/`: pinned upstream Git submodule.
- `patches/cursor-chatgpt-web.patch`: v2 launcher/helper compatibility, preparation gating and read-only MCP policy.

The submodule intentionally retains working-tree patches; the parent repository
ignores its dirty state. Inspect them with `git -C vendor/cursor-chatgpt-web diff`.
Do not update the submodule directly to latest. The installer refuses to apply the
patch to a different revision. Upstream repository-wide typechecking has known
errors; this project does not claim that all upstream tests pass. See the
[compatibility notes](docs/compatibility.md).

## License and acknowledgments

MIT. This project builds on the specialist MCP from
[Rakeem-C/cursor-chatgpt-web](https://github.com/Rakeem-C/cursor-chatgpt-web) and the
browser/launcher capabilities of
[miuuyy/codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web).
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for copyright notices.
This is a community integration project with no official affiliation with OpenAI.
