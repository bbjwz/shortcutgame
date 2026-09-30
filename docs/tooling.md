# Governed toolchain

## Ownership boundaries

Git is authoritative for specifications, plans, tasks, acceptance criteria,
architecture decisions, and delivery definitions. Jira owns operational work
state. Confluence publishes readable feature and council views. Agentstandards
is the sole architecture-readiness authority; its Atlassian companion only
publishes observed evidence and reconciles explicitly authorized decisions.

## Pinned sources

The machine-readable record is `.specify/sources.yml`. Spec Kit is pinned to
1.0.12 because the current reviewed Spec Kit Delivery candidate declares
`requires.speckit_version: ==1.0.12`. Do not upgrade Spec Kit independently;
first update and validate the delivery extension's compatibility contract.

Agentstandards is installed from its v0.1.1 release catalogs. The two Atlassian
companions are installed from explicit-allowlist archives built from their
merged commits. Spec Kit Delivery is installed from commit
`55f59b4a986b1faaf9a1b6ab482868087bb1a9be`; that implementation is still an
unmerged candidate and must not be represented as a released or accepted
component.

## Atlassian activation

The repository contains non-secret tenant configuration and a manually
dispatched worker. Before the first live synchronization:

1. Create an Atlassian API token for `barthisagent@gmail.com` and store
   `ATLASSIAN_EMAIL` and `ATLASSIAN_API_TOKEN` only in the GitHub environment
   `atlassian-sandbox` and an approved local secret store.
2. Set repository variables `SPECKIT_ATLASSIAN_REF` and
   `AGENTSTANDARDS_ATLASSIAN_REF` to the full SHAs in `.specify/sources.yml`.
3. Enable GitHub Actions to create pull requests.
4. After the first Spec Kit feature exists, run the Atlassian `init` command
   for that feature, review the generated binding, and commit it.
5. Run offline preview, authenticated preview, and doctor. Then manually
   dispatch one sandbox sync and inspect every Jira/Confluence result.
6. Verify a second sync is a no-op and exercise human edits, task completion,
   task removal, and concurrent page edits before enabling a schedule.

The committed workflow has no schedule by design. A browser login does not
provide the API token required by the CLI worker.

## Delivery activation

The local Delivery skills, preset, and workflow are installed, but public CI
evidence generation is intentionally inactive. The repository includes the
privacy-preserving candidate workflows: without `DELIVERY_RUNNER_SHA`, the
configuration job reports inactivity and evidence jobs skip.

Only set `DELIVERY_RUNNER_SHA` after a human has reviewed and approved a runner
revision that uploads an allowlisted `attestation.json` and scrubs raw command
output, HTTP bodies, screenshots, traces, speaker notes, and presentations.
The currently recorded trust candidate is not enabled. Branch protection,
the `delivery-audit` environment, exact-digest reviews, and final human
acceptance remain separate required controls.

## Agentstandards activation

Bundle installation and offline gating make no provider calls. Before the
first council, run `$speckit-agentstandards-init` and select exact Codex and
Anthropic model IDs. Store provider credentials only in environment variables.
Running the council is an explicit paid-call action; CI must remain offline.
