---
name: speckit-delivery-verify
description: Verify complete coverage, integrity, freshness, and GitHub baseline approval
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: bbjwz
  source: delivery:commands/speckit.delivery.verify.md
---

# Verify complete coverage, integrity, freshness, and GitHub baseline approval

Consider user arguments: `$ARGUMENTS`.
Use the active feature's spec.md, plan.md and tasks.md. Resolve the actual feature and PR numbers;
never guess a reviewer, fabricate evidence, approve as a human, or mark missing checks successful.
Read the installed extension README for command examples and prerequisites.

Invoke the deterministic Python runner from the project root:
`uv run --script .specify/extensions/delivery/scripts/python/delivery.py --feature specs/<feature> verify`
Append the required command arguments. `plan` requires `--mapping <file>`; all other commands require
`--baseline-pr <number>`. `verify`, `status`, and the acceptance gate also use `--pr <number>`.
The gate defaults to acceptance; use `--phase baseline` only before implementation.