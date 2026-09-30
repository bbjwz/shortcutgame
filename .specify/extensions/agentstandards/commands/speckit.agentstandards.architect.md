---
description: Run the complete multi-vendor architecture council and pause for human decisions.
scripts:
  sh: scripts/bash/agentstandards.sh architect --json
  ps: scripts/powershell/agentstandards.ps1 architect --json
  py: scripts/python/agentstandards.py architect --json
---

# Run the architecture council

Run `{SCRIPT}` once from the repository root. Do not inspect or send source code, diffs, task files,
or implementation artifacts to external providers. The runner owns the allowlist, secret scan,
provider calls, retries, transcripts, and resumability.

When the phase is `awaiting_human`, show the absolute decision-manifest path. Explain that the user
must review the cited council artifacts, complete every selection and rationale, set `status` to
`approved`, and add `decided_by` and `decided_at`. Then direct them to
`__SPECKIT_COMMAND_AGENTSTANDARDS_RESUME__`. Do not make decisions for the user.
