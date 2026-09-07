---
name: web-workers
description: Delegate tasks through an official ChatGPT MCP queue with local file and command tools, inline token estimates, cooldowns and native Luna max fallback; Parent verifies results.
---

# Default: official MCP queue

For new tasks use [the official MCP queue workflow](references/queue.md). Parent queues
bounded work; a user-started ChatGPT conversation claims it through the connector, uses
local tools and submits structured results. Parent checks actual changes and tests.
The full-access queue is explicitly user-authorized; it has OS-user read/write/command
access, not a workspace sandbox. Keep actions within the assigned task and respect the
ChatGPT connector's own confirmations. Never automate approval clicks.

Prefer delegating eligible analysis, decomposition, code changes and preliminary review
to this queue. Preserve native Parent requirements, key decisions and final acceptance.
Use highest available tool-capable ChatGPT mode; actual mode selection is in ChatGPT.
Unavailable queue work falls back to native gpt-5.6-luna/max, then Parent, after ensuring
the queued worker cannot still modify the same files. Display the inline meter after
each completed attempt; unknown savings stay unknown. Do not create score/review loops.

Install the queue manifest once, then use its absolute command paths from any project.
No browser scraping, automated prompt submission, Parent base URL changes, or second
browser daemon. Do not confuse local queue monitoring with waking a ChatGPT conversation.

For maintenance of the previous read-only connector only, see [legacy notes](references/legacy-browser.md). Do not invoke that route for new delegation.
