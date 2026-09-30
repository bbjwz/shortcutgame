---
description: Refuse task generation unless the active feature has a valid READY architecture gate.
scripts:
  sh: scripts/bash/agentstandards.sh gate --json
  ps: scripts/powershell/agentstandards.ps1 gate --json
  py: scripts/python/agentstandards.py gate --json
---

# Enforce the architecture gate

Run `{SCRIPT}` before task generation. A nonzero result is a hard stop: do not create, update, or
infer `tasks.md`. Tell the user whether the council is missing, awaiting human decisions, blocked by
required validators, or invalid. Continue only when the saved aggregate gate is `READY`.
