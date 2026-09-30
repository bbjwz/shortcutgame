## Mandatory Agentstandards gate

Before performing any part of task generation, run this command from the repository root:

```text
uv run --script .specify/extensions/agentstandards/scripts/python/agentstandards.py gate
```

If it exits nonzero, stop immediately. Do not create or modify `tasks.md`. Report the gate reason and
direct the user to `$speckit-agentstandards-architect`, `$speckit-agentstandards-resume`, or the active
decision manifest as appropriate.

If and only if the gate exits successfully, continue with the core task-generation command below.

{CORE_TEMPLATE}
