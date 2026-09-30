# Shortcut Game Constitution

## Core Principles

### I. Specification Before Implementation

Every product behavior change MUST begin with a Spec Kit feature specification containing
testable user scenarios, requirements, acceptance criteria, and explicit exclusions. The
specification MUST be clarified before planning whenever material ambiguity remains. Implementation
MUST NOT begin from an informal request alone. Documentation-only, repository-maintenance, and
tooling-repair changes MAY use a focused pull request without a feature specification when they do
not alter product behavior.

Rationale: written, testable intent prevents implementation details from silently defining the
product.

### II. Architecture Readiness Before Tasks

Every feature plan MUST undergo the Agentstandards architecture council before implementation
tasks are generated. Required human decisions MUST be recorded in the decision manifest, and the
offline verifier MUST report a current `READY` or explicitly approved exception state. A council
report, provider response, or Jira/Confluence representation alone does not satisfy the gate.
Provider model calls MUST be explicitly initiated by a human with exact model IDs and bounded
limits.

Rationale: task generation is meaningful only after architecture conflicts and trade-offs have
been resolved against the current plan.

### III. Evidence-Based Quality

Every implementation MUST include verification proportional to its risk, including relevant unit,
integration, contract, end-to-end, lint, type, and build checks. Acceptance evidence MUST assert
observable behavior and side effects; a page load, screenshot, process start, HTTP success status,
or passing check alone MUST NOT be represented as proof of the intended outcome. Failed, deferred,
or inaccessible checks MUST remain visible and MUST NOT be converted into success claims.

Rationale: delivery claims must be reproducible and supported by evidence that tests the promised
behavior.

### IV. Human Authority and Git Ownership

Git MUST remain authoritative for specifications, plans, tasks, architecture artifacts, source
code, and delivery definitions. Agents MUST work through reviewable branches and pull requests and
MUST NOT approve their own architecture decisions, delivery baselines, or final acceptance.
External systems MAY display or schedule work only when explicitly activated; they MUST NOT replace
Git artifacts or the human approval gates.

Rationale: durable version history and independent approval keep automated work inspectable and
reversible.

### V. Security, Privacy, and Least Privilege

Secrets, provider keys, Atlassian tokens, browser state, raw private evidence, and generated
presentations MUST NOT be committed. Public dependencies MUST be pinned to reviewed source
revisions and consumed with the minimum upstream access required. `spec-kit-atlassian`,
`agentstandards-atlassian`, and `speckit-delivery` are guest/source-only upstream dependencies: the
project MUST NOT require collaborator access, repository administration, upstream branches,
releases, or pull requests to use them. Their pinned source MAY be installed, configured, and run
with the full capabilities required by this project against project-owned GitHub, Jira, Confluence,
and delivery resources. Credentials MUST remain in approved secret stores. Live writes and
privileged workflows MUST use reviewed source pins, pass the package's preview and diagnostic gates,
and be explicitly initiated or enabled by an authorized human. Project-defined commands MUST run
only in an environment appropriate for their trust level because delivery execution is not a
sandbox.

Rationale: public source availability grants no upstream privilege, while guest status must not
prevent explicitly authorized use of that source against resources owned by this project.

## Project Constraints and Quality Standards

- GitHub Spec Kit is the authoritative feature workflow. Spec Kit and installed extensions MUST
  remain compatible with the pinned versions recorded in `.specify/sources.yml`.
- Agentstandards is the sole architecture-readiness authority. Companion integrations MUST NOT
  fabricate, weaken, or replace its verifier result.
- Spec Kit Atlassian and Agentstandards Atlassian MAY publish to the configured project-owned tenant
  only after offline preview, authenticated preview, doctor, and a reviewed sandbox round trip.
- Spec Kit Delivery MAY execute demonstrations and CI verification only with reviewed source and
  runner pins that preserve private evidence and publish only explicitly allowlisted artifacts.
- Every requirement and task included in an approved delivery baseline MUST map to one or more
  executable or inspectable assertions, including a regression scenario.
- Generated evidence and presentations MUST remain outside Git unless a reviewed policy explicitly
  classifies a specific artifact as safe and necessary to commit.
- Dependencies and generated artifacts MUST be reviewed for licensing, secrets, private data, and
  reproducibility before publication.
- Complexity, new services, and new privileged integrations MUST be justified in the feature plan;
  the simplest design satisfying the approved requirements MUST be preferred.

## Development Workflow and Gates

1. Establish or amend this constitution when project-wide governance changes.
2. Run Spec Kit specification, clarification, and planning for each product behavior change.
3. Configure and run Agentstandards after planning. Resolve the human decision manifest and obtain
   a verifier-backed readiness result before generating tasks.
4. Generate and analyze dependency-ordered tasks only after the architecture gate is satisfied.
5. Map obligations to delivery demonstrations and obtain human approval of the exact baseline
   before implementation.
6. Implement on a `codex/<descriptive-name>` branch, run the relevant verification suite, review
   the diff for secrets and unrelated changes, and publish a draft pull request.
7. Demonstrate, verify, and present the exact implementation revision. Final acceptance MUST come
   from an authorized human and MUST match the reviewed evidence digest and revision.

Any failed mandatory gate stops progression. Bypassing a wrapper, omitting evidence, losing access
to an external dependency, or changing scope does not convert a blocked state into approval.

## Governance

This constitution supersedes conflicting repository guidance. Amendments MUST be proposed in a
reviewable pull request that explains the motivation, affected principles, migration impact, and
required follow-up work. An authorized human MUST approve governance changes.

Constitution versions follow semantic versioning:

- MAJOR for incompatible principle removals, weakened gates, or redefinitions of authority.
- MINOR for new principles, gates, or materially expanded mandatory guidance.
- PATCH for clarifications that do not change obligations.

Compliance MUST be reviewed during specification, planning, pull-request review, and final delivery
acceptance. Exceptions MUST be explicit, narrow, time-bounded where applicable, linked to the
affected evidence, and approved by an authorized human; silent or inferred exceptions are invalid.

**Version**: 1.0.0 | **Ratified**: 2026-09-30 | **Last Amended**: 2026-09-30
