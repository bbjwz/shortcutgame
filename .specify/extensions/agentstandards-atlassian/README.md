# Agentstandards Atlassian

Show every recorded architect/critic pass and human decision in **the existing Jira project
board and one accordion-style Confluence feature page**. This independently installable
companion publishes council evidence; Agentstandards remains the only authority for readiness.
It does not require the Spec Kit Atlassian integration, but safely shares its feature containers.

**Status: development preview.** See [validation status](docs/VALIDATION.md). A live sandbox
round trip is required before production use or community release.

## What it shows

- One Jira Council Run task per run and a decision request when human input is required.
- Existing board statuses, separate council phase/outcome, and preserved previous runs.
- All 13 registry personas × every configured provider × independent/disclosed passes.
- A generated pipeline image, recorded output, findings, objections, proposals, and evidence links.
- Native Confluence Expand sections for architects, critics, synthesis, human decisions,
  master plan, validation, operational warnings, and previous runs.
- Explicit stale/unverified states. A READY report alone is insufficient: the pinned core's
  offline verifier must accept the evidence. Original blocking verdicts survive an exception.
- Last-observed progress only. The current core does not expose every active provider call;
  unobserved cells are never labeled as currently running.
- Raw provider transcripts are not published. Ordinary synchronization makes no paid model calls.

## Install

```sh
specify extension add --dev /path/to/agentstandards-atlassian
uv run --script .specify/extensions/agentstandards-atlassian/scripts/run.py --help
```

The package pins Agentstandards 0.1.1's implementation to an immutable Git commit. It reads
versioned core artifacts and imports the core's offline verifier; it never executes a core
script from an untrusted feature checkout. It does not change the existing Agentstandards repo.

Initialize from a consuming project's feature branch:

```sh
uv run --script .specify/extensions/agentstandards-atlassian/scripts/run.py --project . init \
  --feature specs/001-feature --repository OWNER/REPOSITORY \
  --site https://YOUR-SITE.atlassian.net --jira-project PROJECT --space-id SPACE_ID
```

Existing matching feature bindings are reused. Review and commit configuration, register it
on the trusted default branch, configure the worker, and run preview/doctor before publishing.
See [onboarding](docs/ONBOARDING.md) and [decision setup](docs/DECISIONS.md).

## Human decision path

1. Complete Agentstandards planning/critique/synthesis through its normal human checkpoint.
2. Publish the run and review its Confluence evidence and Jira decision request.
3. Record selected proposal IDs and rationale in the configured Jira decision payload field.
4. An authorized human uses the configured approval transition.
5. `reconcile-decisions` checks the actor, event, digest, selections, and edit history and opens
   a focused manifest/audit draft PR targeting the feature branch.
6. After review and incorporation, explicitly resume Agentstandards locally or through a
   separately authorized manual council workflow. Synchronization never initiates paid calls.
7. Publish the core-verified outcome, including READY WITH EXCEPTION when applicable.

Approvals cannot target stale/superseded inputs. Missing conflict selections fail. Exceptions
must reference every required blocking validator. Changes after approval require reapproval.
GitHub decision PRs need schema checks, not an already-passing READY gate.

## Development

```sh
uv sync --extra test --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -m pytest
uv build
uv run python scripts/build_release.py
bash scripts/verify_install.sh
```

See [shared contract](docs/CONTRACT.md) and [implementation plan](docs/IMPLEMENTATION.md).
Uninstall preserves configuration, issues, pages, and evidence. Disable the consumer workflow
before removing the runtime. No Forge app or additional board is required.
