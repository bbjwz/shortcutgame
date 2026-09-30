# Shortcut Game working agreement

This repository uses GitHub Spec Kit as the authoritative feature workflow.

1. Establish or update the project constitution with `$speckit-constitution`.
2. Create a feature with `$speckit-specify`, clarify it, and produce the plan.
3. Run the Agentstandards council after planning. Complete the human decision
   manifest and reach a verified `READY` gate before generating tasks.
4. Generate and analyze tasks. Publish feature planning and task state through
   Spec Kit Atlassian only after an offline preview and an authenticated doctor
   check have passed.
5. Use Spec Kit Delivery to approve the demonstration baseline before
   implementation, then demonstrate, verify, present, and obtain human
   acceptance on the exact implementation revision.

Agentstandards Atlassian is a reporting and decision-reconciliation companion.
It must not replace the Agentstandards readiness gate or initiate paid model
calls. Git remains authoritative for specifications, plans, tasks, architecture
artifacts, and delivery evidence definitions. Jira owns assignment, priority,
scheduling, and delivery status. Confluence publishes readable views.

Never commit provider keys, Atlassian tokens, browser state, raw delivery
evidence, or generated presentations. Remote Atlassian writes must run through
the pinned serialized GitHub Actions worker. Council model calls and live
Atlassian writes require explicit human initiation.
