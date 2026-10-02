---
name: speckit-atlassian-constitution-after-edit
description: Report constitution publication and review state
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: bbjwz
  source: atlassian:commands/constitution-after-edit.md
---

Run:

```text
uv run --script .specify/extensions/atlassian/scripts/run.py --project . constitution status --after-edit
```

Report whether the constitution has local changes, awaits push, awaits publication or awaits approval. Do not claim that saving the file published it. Committing/pushing follows the project working agreements; push to the registered constitution review branch. Never continue into feature work until its guard passes.