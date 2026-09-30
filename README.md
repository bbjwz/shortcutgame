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

## Atlassian

The non-secret tenant configuration targets:

- Jira site: `https://barthisagent.atlassian.net`
- Jira project: `SCRUM`
- Confluence space: `The Agent of Bart` (`65822`)

No API token is stored in this repository. See [docs/tooling.md](docs/tooling.md)
for the remaining secret and sandbox-validation steps.

## Validate the setup

```sh
uv run --no-project --with PyYAML python scripts/verify-tooling.py
```
