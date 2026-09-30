# Shortcut Game

Shortcut Game is bootstrapped with a governed specification-to-delivery
workflow for Codex:

- GitHub Spec Kit 1.0.12 in Codex skills mode
- Agentstandards 0.1.1 for architecture council and task gating
- Spec Kit Atlassian 0.1.0 for Jira and Confluence publication
- Agentstandards Atlassian 0.1.0 for council visibility and human decisions
- Spec Kit Delivery 0.1.0 for demonstrations, evidence, presentations, and
  acceptance gating

Spec Kit is intentionally pinned to 1.0.12 because the reviewed delivery
extension currently requires that exact version. Source revisions and trust
status are recorded in [docs/tooling.md](docs/tooling.md).

## Guest source-only boundary

`spec-kit-atlassian`, `agentstandards-atlassian`, and `speckit-delivery` are
public repositories used here only as pinned, vendored source code. This
project does not request or rely on upstream write access, repository
administration, an Atlassian tenant binding, API credentials, GitHub
repository variables or secrets, privileged workflows, a trusted runner, or
live Jira/Confluence writes.

Their source is available under `.specify/extensions/`, with local Codex skills
under `.agents/skills/`. Installing the source does not activate its networked
integrations.

## Start a feature

Run these Codex skills from the repository root:

```text
$speckit-constitution
$speckit-specify
$speckit-clarify
$speckit-plan
$speckit-agentstandards-init
$speckit-agentstandards-architect
$speckit-agentstandards-resume
$speckit-tasks
$speckit-analyze
$speckit-delivery-plan
$speckit-implement
$speckit-delivery-demo
$speckit-delivery-present
$speckit-delivery-verify
```

The Agentstandards task gate and Delivery implementation gate are installed as
wrappers, so bypassing their explicit commands does not turn a blocked result
into approval.

## Validate the setup

```sh
uv run --no-project --with PyYAML python scripts/verify-tooling.py
```
