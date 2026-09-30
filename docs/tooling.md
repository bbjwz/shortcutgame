# Governed toolchain

## Source-only boundary

Git is authoritative for specifications, plans, tasks, acceptance criteria,
architecture decisions, and delivery definitions. The public
`spec-kit-atlassian`, `agentstandards-atlassian`, and `speckit-delivery`
repositories are used strictly as guest-accessible source dependencies.

Their pinned source is vendored under `.specify/extensions/` and their local
Codex skills are installed under `.agents/skills/`. The project deliberately
contains no tenant binding, Atlassian credentials, repository variables or
secrets for these tools, active GitHub Actions integration workflows, delivery
runner policy, live remote writes, or upstream publishing configuration.

## Pinned sources

The machine-readable record is `.specify/sources.yml`. Spec Kit is pinned to
1.0.12 because the current reviewed Spec Kit Delivery candidate declares
`requires.speckit_version: ==1.0.12`. Do not upgrade Spec Kit independently;
first update and validate the delivery extension's compatibility contract.

Agentstandards is installed from its v0.1.1 release catalogs. The two Atlassian
companions are installed from public source archives built from their pinned
commits. Spec Kit Delivery is installed from commit
`55f59b4a986b1faaf9a1b6ab482868087bb1a9be`; that implementation is still an
unmerged candidate and must not be represented as a released or accepted
component.

## Local use

The vendored code can be inspected, tested, and developed locally. Commands
that would authenticate to Atlassian, publish to Jira or Confluence, depend on
a remote trusted runner, or modify an upstream repository are outside this
project's current boundary. Activating any such behavior requires a new,
explicit user instruction and a separate review of the proposed credentials
and external effects.

## Agentstandards activation

Bundle installation and offline gating make no provider calls. Before the
first council, run `$speckit-agentstandards-init` and select exact Codex and
Anthropic model IDs. Store provider credentials only in environment variables.
Running the council is an explicit paid-call action; CI must remain offline.
