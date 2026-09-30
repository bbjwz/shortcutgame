---
description: Show architecture-council participants, progress, usage, failures, and gate state.
scripts:
  sh: scripts/bash/agentstandards.sh status --json
  ps: scripts/powershell/agentstandards.ps1 status --json
  py: scripts/python/agentstandards.py status --json
---

# Show council status

Run `{SCRIPT}` once from the repository root. Summarize the active run, pinned participant models and
underlying vendors, completed artifacts, physical provider calls, usage, estimated cost, optional
provider warnings, required-provider failures, and architecture gate state. Make no provider calls.
