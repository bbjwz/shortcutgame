---
name: speckit-agentstandards-architect
description: Run the complete multi-vendor architecture council and pause for human
  decisions.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: bbjwz
  source: extension:agentstandards
---

# Agentstandards Architect Skill

# Run the architecture council

Run `python3 .specify/extensions/agentstandards/scripts/python/agentstandards.py architect --json` once from the repository root. Do not inspect or send source code, diffs, task files,
or implementation artifacts to external providers. The runner owns the allowlist, secret scan,
provider calls, retries, transcripts, and resumability.

When the phase is `awaiting_human`, show the absolute decision-manifest path. Explain that the user
must review the cited council artifacts, complete every selection and rationale, set `status` to
`approved`, and add `decided_by` and `decided_at`. Then direct them to
`$speckit-agentstandards-resume`. Do not make decisions for the user.
