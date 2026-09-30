---
description: Configure the project-scoped multi-vendor architecture council.
scripts:
  sh: scripts/bash/agentstandards.sh init
  ps: scripts/powershell/agentstandards.ps1 init
  py: scripts/python/agentstandards.py init
---

# Configure Agentstandards

Collect exact model IDs for Codex and Anthropic. Anthropic is mandatory. Ask whether the user wants
Google or any OpenAI-compatible provider, including Abacus or OpenRouter. For each optional provider,
collect a stable participant ID, transport, explicit underlying vendor, exact model, API-key
environment-variable name, base URL, and optional token pricing. Never request or write a secret.

Run `{SCRIPT}` with:

- `--codex-model` and `--anthropic-model`;
- limit flags when the user changes the defaults;
- one `--provider-json` value per optional participant, matching the documented configuration
  fields.

Do not use an automatic or unknown routed model. Report the saved participants, models, vendors,
limits, and configuration path. Treat `$ARGUMENTS` as preferences supplied by the user.
