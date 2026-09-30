from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import yaml
from agentstandards.config import CouncilConfig, load_config
from agentstandards.context import build_context
from agentstandards.models import ArtifactEnvelope, DecisionManifest, GateReport, RunState
from agentstandards.orchestrator import verify_ready_gate
from agentstandards.personas import load_personas
from pydantic import Field

from .common.confluence import Section
from .common.models import Binding, Conflict, Model, Settings, digest, inside, read_yaml


class ReviewCell(Model):
    persona: str
    participant: str
    pass_kind: Literal["independent", "disclosed"]
    state: Literal["complete", "not_observed"]
    artifact_id: str | None = None
    artifact_path: str | None = None
    payload: dict = Field(default_factory=dict)


class CouncilSnapshot(Model):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    feature_identity: str
    source_revision: str
    phase: str
    outcome: str
    verified_ready: bool
    updated_at: str
    participants: list[dict]
    reviewers: list[dict]
    cells: list[ReviewCell]
    manifest: dict
    decision_digest: str
    usage: dict
    warnings: list[str]
    errors: list[str]
    master_plan: dict | None = None
    adr_log: dict | None = None
    blockers: list[str] = Field(default_factory=list)
    core_verification: str
    context_current: bool


def snapshot(root: Path, binding: Binding, sha: str) -> CouncilSnapshot:
    prefix = binding.feature_path + "/architecture"
    pointer = json.loads(inside(root, prefix + "/current-run.json").read_text())
    run_id = pointer["run_id"]
    if not isinstance(run_id, str) or "/" in run_id or "\\" in run_id or run_id in (".", ".."):
        raise Conflict("unsafe council run ID")
    run_prefix = prefix + "/runs/" + run_id
    state = RunState.model_validate(
        json.loads(inside(root, run_prefix + "/state.json").read_text())
    )
    if state.run_id != run_id:
        raise Conflict("council pointer and state disagree")
    cfg = CouncilConfig.model_validate(
        read_yaml(inside(root, run_prefix + "/config-snapshot.yaml"))
    )
    registry = load_personas()
    reviewers = [
        {"id": item.id, "focus": item.focus, "stage": stage}
        for stage, entries in (
            ("planning", registry.planners),
            ("critiquing", registry.critics),
            ("synthesizing", [registry.get("consensus-synthesizer")]),
            ("validating", [registry.get("architecture-validator")]),
        )
        for item in entries
    ]
    artifacts = {}
    artifact_digests = {}
    for path in sorted(inside(root, run_prefix + "/artifacts").rglob("*.yaml")):
        relative = path.relative_to(root).as_posix()
        item = ArtifactEnvelope.model_validate(read_yaml(inside(root, relative)))
        if item.run_id != run_id:
            raise Conflict("artifact belongs to a different council run")
        key = (item.persona, item.participant_id, item.pass_kind)
        if key in artifacts:
            raise Conflict("duplicate reviewer/pass artifact")
        artifacts[key] = (item, relative)
        artifact_digests[item.artifact_id] = digest(item.model_dump(mode="json"))
    cells = []
    for reviewer in reviewers:
        for participant in cfg.enabled_participants:
            for pass_kind in ("independent", "disclosed"):
                found = artifacts.get((reviewer["id"], participant.id, pass_kind))
                values = {
                    "persona": reviewer["id"],
                    "participant": participant.id,
                    "pass_kind": pass_kind,
                    "state": "complete" if found else "not_observed",
                }
                if found:
                    item, relative = found
                    values.update(
                        artifact_id=item.artifact_id,
                        artifact_path=relative,
                        payload=item.payload.model_dump(mode="json"),
                    )
                cells.append(ReviewCell.model_validate(values))
    manifest_path = inside(root, run_prefix + "/decision-manifest.yaml")
    manifest = (
        DecisionManifest.model_validate(read_yaml(manifest_path)).model_dump(mode="json")
        if manifest_path.exists()
        else {"run_id": run_id, "status": "pending", "conflicts": []}
    )
    if manifest["run_id"] != run_id:
        raise Conflict("decision manifest belongs to another council run")
    report_path = inside(root, run_prefix + "/gate-report.yaml")
    report = GateReport.model_validate(read_yaml(report_path)) if report_path.exists() else None
    if report and report.run_id != run_id:
        raise Conflict("gate report belongs to another council run")
    ready, current, verification = False, False, "not ready; no readiness claim"
    outcome = report.status if report else state.phase.upper()
    try:
        current_cfg = load_config(
            inside(root, ".specify/extensions/agentstandards/agentstandards-config.yml")
        )
        context = build_context(root, inside(root, binding.feature_path))
        current = (
            state.context_hash == context.content_hash
            and state.config_hash == current_cfg.stable_hash()
        )
        if not current:
            outcome, verification = (
                "STALE",
                "architecture inputs or participant configuration changed",
            )
        elif report and report.status == "READY":
            verified = verify_ready_gate(
                root, inside(root, binding.feature_path), current_cfg, context.content_hash
            )
            ready = True
            outcome = "READY_WITH_EXCEPTION" if verified.exception_applied else "READY"
            verification = "Agentstandards offline gate verified"
    except (ValueError, OSError, RuntimeError):
        outcome, verification = "UNVERIFIED", "Agentstandards offline verification did not pass"
    blockers = [
        cell.artifact_id
        for cell in cells
        if cell.pass_kind == "disclosed"
        and cell.persona == "architecture-validator"
        and cell.payload.get("verdict") != "READY"
        and cell.participant in {p.id for p in cfg.required_participants}
        and cell.artifact_id
    ]

    def optional(name: str) -> dict | None:
        path = inside(root, run_prefix + "/" + name)
        return read_yaml(path) if path.exists() else None

    return CouncilSnapshot(
        run_id=run_id,
        feature_identity=binding.identity,
        source_revision=sha,
        phase=state.phase,
        outcome=outcome,
        verified_ready=ready,
        updated_at=state.updated_at.isoformat(),
        participants=[
            {"id": p.id, "required": p.required, "vendor": p.underlying_vendor, "model": p.model}
            for p in cfg.enabled_participants
        ],
        reviewers=reviewers,
        cells=cells,
        manifest=manifest,
        decision_digest=digest(
            {
                "run_id": run_id,
                "context": state.context_hash,
                "config": state.config_hash,
                "conflicts": manifest["conflicts"],
                "artifacts": artifact_digests,
            }
        ),
        usage=state.usage.model_dump(mode="json"),
        warnings=state.optional_warnings,
        errors=state.errors,
        master_plan=optional("master-plan.yaml"),
        adr_log=optional("adr-log.yaml"),
        blockers=blockers,
        core_verification=verification,
        context_current=current,
    )


def sections(snap: CouncilSnapshot, cfg: Settings, decision_key: str | None) -> list[Section]:
    decision = (
        f'<p><a href="{cfg.site}/browse/{decision_key}">Human input required</a></p>'
        if decision_key and snap.phase in ("awaiting_human", "blocked")
        else ""
    )
    summary = (
        f"<p>Outcome: <strong>{escape(snap.outcome)}</strong> · "
        f"Phase: {escape(snap.phase)}</p>{decision}"
        f"<p>Last recorded update: {escape(snap.updated_at)}</p>"
        f"<p>{escape(snap.core_verification)}. Source: <code>{snap.source_revision}</code></p>"
        "<p>Per-call running state is not exposed by this core version. "
        "Not observed does not mean currently running.</p>"
    )
    pipeline = (
        "<p>Architects → Critics → Synthesis → <strong>Human decision</strong> → "
        "Compile → Validators → Outcome</p>"
    )
    result = [Section("architecture-summary", "Architecture review", summary + pipeline, True)]
    for stage, title in (
        ("planning", "Architects: proposals and review passes"),
        ("critiquing", "Critics: findings and disagreements"),
        ("synthesizing", "Synthesis and decision options"),
        ("validating", "Validation evidence"),
    ):
        body = ""
        for reviewer in [r for r in snap.reviewers if r["stage"] == stage]:
            body += f"<h3>{escape(reviewer['id'])}</h3><p>{escape(reviewer['focus'])}</p>"
            body += (
                "<table><tbody><tr><th>Provider</th><th>Pass</th>"
                "<th>State</th><th>Evidence</th></tr>"
            )
            matching = [c for c in snap.cells if c.persona == reviewer["id"]]
            for cell in matching:
                link = "—"
                if cell.artifact_path:
                    url = (
                        f"https://github.com/{cfg.github_repository}/blob/{snap.source_revision}/"
                        + quote(cell.artifact_path, safe="/")
                    )
                    link = f'<a href="{url}">{escape(cell.artifact_id or "Artifact")}</a>'
                body += (
                    f"<tr><td>{escape(cell.participant)}</td><td>{cell.pass_kind}</td>"
                    f"<td>{cell.state}</td><td>{link}</td></tr>"
                )
            body += "</tbody></table>"
            for cell in matching:
                if cell.state == "complete":
                    body += (
                        f"<h4>{escape(cell.participant)} · {cell.pass_kind}</h4>"
                        f"<pre>{escape(yaml.safe_dump(cell.payload, sort_keys=False))}</pre>"
                    )
        result.append(Section(stage, title, body))
    result.append(
        Section(
            "decisions",
            "Human decisions and rationale",
            "<pre>" + escape(yaml.safe_dump(snap.manifest, sort_keys=False)) + "</pre>",
        )
    )
    result.append(
        Section(
            "master-plan",
            "Master plan and architecture decisions",
            "<pre>"
            + escape(
                yaml.safe_dump(
                    {"master_plan": snap.master_plan, "adr_log": snap.adr_log}, sort_keys=False
                )
            )
            + "</pre>",
        )
    )
    result.append(
        Section(
            "health",
            "Warnings, errors, and usage",
            "<pre>"
            + escape(
                yaml.safe_dump(
                    {
                        "warnings": snap.warnings,
                        "errors": snap.errors,
                        "usage": snap.usage,
                        "participants": snap.participants,
                    },
                    sort_keys=False,
                )
            )
            + "</pre>",
        )
    )
    return result
