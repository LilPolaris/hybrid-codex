# Hybrid Codex

Codex owns requirements, architecture, writes, tests and acceptance. Automatically assess
bounded routine subtasks using `.agents/skills/web-workers/SKILL.md`: highest available
Web mode first, native gpt-5.6-luna with max reasoning second, Parent last. Trivial local
lookups stay local. Web and Luna workers only analyze focused
context and report evidence. At most five run concurrently. Parent rechecks important claims.
Never enable local tools for Web workers, change the Parent base URL, or start another browser daemon.
