---
name: speckit-agentstandards-status
description: Show architecture-council participants, progress, usage, failures, and
  gate state.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: bbjwz
  source: extension:agentstandards
---

# Agentstandards Status Skill

# Show council status

Run `python3 .specify/extensions/agentstandards/scripts/python/agentstandards.py status --json` once from the repository root. Summarize the active run, pinned participant models and
underlying vendors, completed artifacts, physical provider calls, usage, estimated cost, optional
provider warnings, required-provider failures, and architecture gate state. Make no provider calls.
