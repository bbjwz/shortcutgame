# Shortcut Game working agreement

This repository uses GitHub Spec Kit as the authoritative feature workflow.

1. Establish or update the project constitution with `$speckit-constitution`.
2. Create a feature with `$speckit-specify`, clarify it, and produce the plan.
3. Run the Agentstandards council after planning. Complete the human decision
   manifest and reach a verified `READY` gate before generating tasks.
4. Generate and analyze tasks.
5. Use Spec Kit Delivery to approve the demonstration baseline before
   implementation, then demonstrate, verify, present, and obtain human
   acceptance on the exact implementation revision.

The public `spec-kit-atlassian`, `agentstandards-atlassian`, and
`speckit-delivery` repositories are consumed strictly as a guest through their
vendored source code. They are not activated as hosted services or upstream
collaborations. Do not configure an Atlassian tenant, credentials, repository
secrets or variables, privileged CI workflows, trusted runners, live remote
writes, upstream pull requests, releases, or administrative access unless the
user explicitly changes this boundary.

Git remains authoritative for specifications, plans, tasks, architecture
artifacts, and delivery evidence definitions. Never commit provider keys,
Atlassian tokens, browser state, raw delivery evidence, or generated
presentations. Council model calls require explicit human initiation.
