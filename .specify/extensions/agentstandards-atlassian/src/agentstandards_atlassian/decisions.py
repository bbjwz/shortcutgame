from __future__ import annotations

import json
from datetime import datetime

import yaml
from agentstandards.models import DecisionManifest

from .common.jira import Jira
from .common.models import Conflict, Settings
from .council import CouncilSnapshot


def plain_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("type") == "doc":

        def visit(node):
            text = node.get("text", "")
            return text + "".join(visit(child) for child in node.get("content", []))

        return visit(value)
    raise Conflict("decision field must contain JSON text")


def approved_manifest(snap: CouncilSnapshot, cfg: Settings, jira: Jira, key: str) -> dict:
    if not snap.context_current or snap.phase not in ("awaiting_human", "blocked"):
        raise Conflict("decisions may only target a current awaiting-human or blocked run")
    required = {"decision_payload", "decision_digest"}
    if not required.issubset(cfg.fields) or not cfg.approver_account_ids:
        raise Conflict("configure decision fields and authorized Jira account IDs first")
    before = jira.get(key)
    meta = jira.metadata(key)
    if (
        meta.get("run_id") != snap.run_id
        or meta.get("decision_digest") != snap.decision_digest
        or meta.get("owner") != "agentstandards-atlassian"
    ):
        raise Conflict("decision request is stale or belongs to another run")
    fields = before["fields"]
    if fields["status"]["name"] != cfg.decision_status:
        raise Conflict("Jira decision request is not approved")
    if fields.get(cfg.fields["decision_digest"]) != snap.decision_digest:
        raise Conflict("approval input digest does not match the current architecture")
    history = jira.changelog(key)
    approvals = [
        entry
        for entry in history
        if any(
            item.get("field") == "status" and item.get("toString") == cfg.decision_status
            for item in entry["items"]
        )
    ]
    if not approvals:
        raise Conflict("no auditable Jira approval transition")
    approvals.sort(key=lambda entry: (datetime.fromisoformat(entry["created"]), int(entry["id"])))
    approval = approvals[-1]
    actor = approval["author"]["accountId"]
    if actor not in cfg.approver_account_ids:
        raise Conflict("Jira approver is not authorized")
    approval_order = (datetime.fromisoformat(approval["created"]), int(approval["id"]))
    controlled = {cfg.fields[name] for name in required}
    for entry in history:
        order = (datetime.fromisoformat(entry["created"]), int(entry["id"]))
        if order > approval_order and any(
            item.get("fieldId") in controlled or item.get("field") == "status"
            for item in entry["items"]
        ):
            raise Conflict("decision or approval state changed after approval; approve again")
    payload = json.loads(plain_text(fields.get(cfg.fields["decision_payload"])))
    if not isinstance(payload, dict) or set(payload) - {"selections", "exceptions"}:
        raise Conflict("decision payload permits only selections and exceptions")
    manifest = dict(snap.manifest)
    manifest.update(
        selections=payload.get("selections", []),
        decided_by=actor,
        decided_at=approval["created"],
        status="approved",
        exceptions=[],
    )
    if payload.get("exceptions"):
        if snap.phase != "blocked" or not snap.blockers:
            raise Conflict("exceptions apply only to a blocked validated run")
        exceptions = []
        for exception in payload["exceptions"]:
            if set(exception) != {"validator_artifact_ids", "reason"}:
                raise Conflict("exception requires validator_artifact_ids and reason")
            exceptions.append(
                {**exception, "approved_by": actor, "approved_at": approval["created"]}
            )
        covered = {item for e in exceptions for item in e["validator_artifact_ids"]}
        if covered != set(snap.blockers):
            raise Conflict("exception must reference exactly every blocking required validator")
        manifest.update(status="exception", exceptions=exceptions)
    elif snap.phase == "blocked":
        raise Conflict("blocked run requires remediation or an explicit exception")
    validated = DecisionManifest.model_validate(manifest).model_dump(mode="json")
    after = jira.get(key)
    if after["fields"]["updated"] != before["fields"]["updated"]:
        raise Conflict("decision changed while being read; retry reconciliation")
    return {
        "manifest": validated,
        "audit": {
            "schema_version": "1.0",
            "jira_key": key,
            "approval_event_id": approval["id"],
            "account_id": actor,
            "approved_at": approval["created"],
            "run_id": snap.run_id,
            "decision_digest": snap.decision_digest,
        },
    }


def changes_for_decision(feature_path: str, approved: dict) -> dict[str, str]:
    run_id = approved["manifest"]["run_id"]
    prefix = feature_path + "/architecture/"
    manifest_text = yaml.safe_dump(approved["manifest"], sort_keys=False)
    # Core reads the run-scoped manifest; the feature-level copy stays consistent for human review.
    return {
        prefix + f"runs/{run_id}/decision-manifest.yaml": manifest_text,
        prefix + "decision-manifest.yaml": manifest_text,
        f".specify/integrations/atlassian/decisions/{run_id}.json": json.dumps(
            approved["audit"], indent=2
        )
        + "\n",
    }
