# Per-delegation routing and visible accounting

Use `scripts/worker_meter.py` relative to this installed skill. It uses Python 3.11+
standard library only. Supply JSON through stdin or a UTF-8 file; do not shell-interpolate
prompts. Default state is `$CODEX_HOME/worker-metrics/ledger.sqlite` (or ~/.codex).
Only store IDs, numeric ranges and short metadata; never prompts, source or credentials.
The helper selects routes and records outcomes; Parent calls actual tools and verifies
results. It does not launch a daemon or change the Parent provider.

## Before each bounded subtask

Run `python -X utf8 <skill>/scripts/worker_meter.py plan` with JSON:

```json
{"session":"stable-current-task-id","task":"log-review-1",
 "baseline":[800,1500],"basis":"Assumed incremental Parent reading and analysis; excludes shared context",
 "available_modes":["instant","medium","high"],"luna_available":true}
```

Obtain available modes from actual Web status and Luna availability from native tool
metadata. Use a stable session ID across compaction/resumption, unique subtask IDs, and
reuse the subtask ID during fallback. A repeated plan never changes the original baseline.
For the first call supply a reasoned range of Parent work this subtask would otherwise
require, excluding work already done. This is a counterfactual assumption, not measured
reasoning. If no defensible range exists use `baseline:null` and explain uncertainty.
Never invent baseline numbers from worker output or multiply worker usage by a savings factor.

Honor `route`: web (returned mode), luna (native gpt-5.6-luna/max), parent, wait or done.
Immediately before dispatch call `start` with session/task/id/route/model/evidence.
Only dispatch after reservation succeeds. It prevents duplicate launches of the same
subtask across ledger clients. A running reservation survives interruptions: inspect
the actual owned job handle, never infer termination from elapsed time or a stale row.
After actual completion `record` finalizes that same attempt ID.
Web outages cool down within this session: auth 30 min, quota 60 min, unavailable 10 min,
transient 60 sec. Other subtasks skip that provider while cooling; other sessions are
unaffected. Expiration allows a probe on the next subtask. Do not repeatedly call status
while a known Web cooldown is active: reuse the previous capability snapshot for plan,
then refresh status if plan chooses Web. Refresh modes and plan again if availability changed.
The helper conservatively permits one attempt per provider per subtask; don't retry by
inventing a new subtask ID. The skill's optional corrected retry is not needed in this flow.
Pool congestion is not an account failure: wait or pass unavailable modes for that plan,
without recording a provider fault. Never label a normal running job as transient failure.

## After every attempt

Measure elapsed time around the actual tool call (including completion waits). Record:

```json
{"session":"stable-current-task-id","task":"log-review-1","id":"unique-attempt-id",
 "route":"web","model":"gpt-5.6-sol/high (tool-confirmed)","outcome":"accepted",
 "seconds":24.6,"overhead":[300,600],"usage_tokens":null,"evidence":"live"}
```

Use `record` as the command. Outcomes: accepted (Parent checked and adopted), rejected,
auth, quota, unavailable, transient, cancelled, unresolved. Record an unavailable tool
as an attempt with zero elapsed if no call was made, but include any preparation overhead.
All provider attempts, including failures, belong to the same subtask. `usage_tokens` is
optional provider-reported usage only; absent usage stays null. Native Luna consumes
native account usage too, so Parent savings do not equal account savings.

`overhead` is an estimated range for extra Parent tokens spent preparing/delegating,
reading tool output, verification and retries. Include the ledger calls and the visible
meter message. Do not include ordinary Parent implementation costs that both paths share.
For Parent fallback record only extra delegation overhead, not the baseline work itself.
Use null when unknown. Text length is a rough proxy, not measured token usage; mark any
such assumption in `basis`. Hidden reasoning, cache reuse and context replay remain unknown.

For unresolved jobs, record `unresolved`; plan returns wait. Recheck the same owned
handle. Only after confirmed termination use `resolve` with session/task/id and
`terminal_confirmed:true`, then plan again. Never cancel unrelated jobs or fake an outage.
Use a separate session and `evidence:"injected-test"` for fault-injection acceptance tests.

## Show the user a number each time

After each record, copy its `card` into a concise commentary message. The card identifies
route, cumulative attempt time and net estimated Parent savings. Include the notice on
the first card and in the final result. During fallback show pending savings and the
failure reason; show the final range once Parent accepts an outcome. Negative numbers
mean extra cost and must remain negative. Unknown is not zero. No local HTML report needed.

Formula after adoption: `[baseline_low - overhead_high, baseline_high - overhead_low]`,
summing overhead across all attempts. If only Parent succeeds, benefit is zero. If all
attempts are still pending/rejected, don't claim final savings. Partial adoption must be
split into distinct bounded tasks before estimating; don't claim full benefit for a fragment.
`summary` with `{"session":"..."}` retrieves per-task cards for the final reply.
These are incremental Parent token-equivalent scenarios, not billed savings or quota percentages.
