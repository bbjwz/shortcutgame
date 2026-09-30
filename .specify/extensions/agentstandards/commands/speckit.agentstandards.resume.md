---
description: Resume after human decisions, compile the master plan, and validate the architecture.
scripts:
  sh: scripts/bash/agentstandards.sh resume --json
  ps: scripts/powershell/agentstandards.ps1 resume --json
  py: scripts/python/agentstandards.py resume --json
---

# Resume the architecture council

Run `{SCRIPT}` once from the repository root.

If the gate is `READY`, report the master-plan and gate-report paths and state that task generation
is now permitted. If the gate is `BLOCKED`, identify the blocking required validators from the gate
report. The human must either remediate the architecture and start a new run, or set the decision
manifest to `exception` and record the blocking validator artifact IDs, rationale, approver, and
timestamp before resuming again. Never invent an exception or approval.
