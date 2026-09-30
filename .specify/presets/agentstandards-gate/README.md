# Agentstandards Task Gate preset

This preset wraps Spec Kit's `speckit.tasks` command with the persisted Agentstandards architecture
gate. Task generation proceeds only when the active feature has a valid `READY` aggregate gate.

The preset requires the `agentstandards` extension because its wrapper invokes the extension's
offline gate command. Install the extension first; Spec Kit also reports this dependency from the
published `preset.yml`.

## Install from the v0.1.1 release

```bash
specify extension add agentstandards \
  --from https://github.com/bbjwz/agentstandards/releases/download/v0.1.1/agentstandards-0.1.1.zip

specify preset add \
  --from https://github.com/bbjwz/agentstandards/releases/download/v0.1.1/agentstandards-gate-0.1.1.zip
```

For a catalog-backed installation of the complete extension, preset, and workflow stack, use the
[Agentstandards bundle](../../bundles/agentstandards/README.md).

## Use the gate

Run `$speckit-agentstandards-init` once, then run `$speckit-agentstandards-architect` after
`$speckit-plan`. Complete the generated human decision manifest and run
`$speckit-agentstandards-resume`. After the aggregate architecture gate becomes `READY`, invoke
`$speckit-tasks` normally; the preset performs the offline gate check before the core task command.

If the gate is missing, stale, invalid, or blocked, the wrapper stops without creating or modifying
`tasks.md`. No provider call is made by the task gate itself.
