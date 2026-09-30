# Agentstandards Spec Kit extension

Agentstandards inserts a multi-vendor architecture council between `$speckit-plan` and
`$speckit-tasks`. Codex orchestrates every run, Anthropic is the mandatory external reviewer, and
optional providers can add explicitly identified underlying vendors.

## Commands

- `$speckit-agentstandards-init` configures exact participants, models, limits, and credentials by
  environment-variable name.
- `$speckit-agentstandards-architect` runs planning, critique, and synthesis before pausing for a
  human decision.
- `$speckit-agentstandards-resume` compiles approved decisions and runs final validation.
- `$speckit-agentstandards-status` reports progress, cost, failures, and gate state without paid
  calls.
- `$speckit-agentstandards-gate` validates the saved gate before task generation.

Every inference uses a fresh conversation context. External providers receive only allowlisted
architecture artifacts, never source code, diffs, task files, or implementation artifacts. Required
Codex and Anthropic validator disagreement keeps the task gate closed unless a human records an
explicit, auditable exception.

## Privacy

Visible prompts and outputs are persisted beneath `specs/<feature>/architecture/` for auditability.
They exclude secrets, headers, hidden reasoning, and provider-internal state, but can still contain
confidential architecture information. Review these files before committing or sharing the project.

Full installation, configuration, operation, and security documentation is available in the
[Agentstandards repository](https://github.com/bbjwz/agentstandards).
