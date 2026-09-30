---
name: speckit-agentstandards-gate
description: Refuse task generation unless the active feature has a valid READY architecture
  gate.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: bbjwz
  source: extension:agentstandards
---

# Agentstandards Gate Skill

# Enforce the architecture gate

Run `python3 .specify/extensions/agentstandards/scripts/python/agentstandards.py gate --json` before task generation. A nonzero result is a hard stop: do not create, update, or
infer `tasks.md`. Tell the user whether the council is missing, awaiting human decisions, blocked by
required validators, or invalid. Continue only when the saved aggregate gate is `READY`.
