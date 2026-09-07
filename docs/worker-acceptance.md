# Worker routing acceptance — 2026-09-07

Scope: skill-directed dispatch and the installed Python ledger. This does not test
every provider error or claim autonomous runtime interception of all Codex calls.

| Path | Evidence | Result |
| --- | --- | --- |
| Web success | Real `chatgpt_web_turn`, high; returned metadata identified gpt-5.6-sol/high. Parent reviewed the accounting advice. Runtime duration 39.849 s. | Passed; baseline unknown, savings unknown. |
| Web cancellation → Luna | A real owned Web job was observed running, cancelled, then observed cancelled with no active slot. Ledger selected Luna. Native subagent was requested as gpt-5.6-luna/max and returned three slice edge cases. Parent executed them in Node; exact match. | Passed; controlled cancellation, not natural outage. Native billing usage unavailable. |
| Web unavailable → Luna unavailable → Parent | Injected unavailable outcomes in an isolated ledger session. Routes were Web → Luna → Parent. Parent verified the interval arithmetic. | Passed; failures were injected, not real provider outages. |
| Cooldown and accounting | Python unit tests cover persistence across reopening, session isolation, exact expiry, duplicate records, reservation collisions, unresolved cancellation, negative savings and unknown usage. | Passed. |

For the cancellation probe, the precommitted assumed baseline was 100–300 Parent
token-equivalents. Estimated delegation overhead was 300–600 for Web and 300–700 for
Luna. The displayed net range was **−1,200 to −300**, not a savings claim. Total
observed elapsed time was 59.2 s including time until Parent read the Luna result.
The probe intentionally delegates a tiny task; ordinary triage should keep it local.

Raw local acceptance evidence is excluded from Git under `reports/acceptance-20260907/`.
The reproducible offline checks are:

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py"
```

The per-call card is shown in the conversation by the skill. It is not a dashboard
injected into Codex UI and not a measurement of hidden reasoning, cache or billing.
