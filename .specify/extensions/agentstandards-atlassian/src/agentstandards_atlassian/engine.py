from __future__ import annotations

import io
import json
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw

from .common.confluence import NS, Confluence, Section, document, section_id, serialized
from .common.git import revision
from .common.http import Cloud
from .common.jira import Jira
from .common.models import Binding, Conflict, Settings
from .common.security import scan
from .council import CouncilSnapshot, sections, snapshot

OWNER = "agentstandards-atlassian"


def pipeline(snap: CouncilSnapshot) -> bytes:
    labels = [
        "planning",
        "critiquing",
        "synthesizing",
        "awaiting_human",
        "compiling",
        "validating",
        "ready",
    ]
    image = Image.new("RGB", (920, 150), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.text((15, 12), "Council pipeline - recorded phase: " + snap.phase, fill="#172b4d")
    for i, name in enumerate(labels):
        x = 12 + i * 130
        color = "#fff0b3" if name == "awaiting_human" else "#eef2f6"
        if name == snap.phase:
            color = "#b3d4ff"
        draw.rounded_rectangle((x, 48, x + 117, 96), radius=7, fill=color, outline="#344563")
        draw.text((x + 5, 66), name.replace("_", " "), fill="#172b4d")
        if i < 6:
            draw.text((x + 119, 65), ">", fill="#172b4d")
    draw.text(
        (15, 116),
        "Outcome: " + snap.outcome + " | Blue: recorded phase | Yellow: human input",
        fill="#172b4d",
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def board_status(snap: CouncilSnapshot, cfg: Settings) -> str:
    if snap.outcome in ("STALE", "UNVERIFIED") or snap.phase in ("blocked", "failed"):
        return cfg.statuses["blocked"]
    if snap.verified_ready:
        return cfg.statuses["done"]
    if snap.phase == "awaiting_human":
        return cfg.statuses["waiting"]
    if snap.phase == "created":
        return cfg.statuses["todo"]
    return cfg.statuses["active"]


def synchronize(root: Path, cfg: Settings, binding: Binding, cloud: Cloud, save_binding) -> dict:
    sha = revision(root, require_clean=True)
    snap = snapshot(root, binding, sha)
    scan(snap.model_dump_json())
    jira, confluence = Jira(cloud, cfg), Confluence(cloud, cfg)
    title = binding.feature_path.rsplit("/", 1)[-1]
    epic, _ = jira.upsert(
        binding.identity + ":feature",
        OWNER,
        "feature",
        title,
        "Architecture feature. Specifications and delivery may be published separately.",
        binding.identity,
        adopt_key=binding.epic_key,
    )
    binding.epic_key = epic
    save_binding(binding)
    binding.page_id = jira.shared_page(epic, binding.identity, binding.page_id)
    page = confluence.ensure_page(binding.identity, title, binding.page_id)
    jira.shared_page(epic, binding.identity, page)
    binding.page_id = page
    save_binding(binding)
    extra = {
        cfg.fields[name]: value
        for name, value in (("council_phase", snap.phase), ("architecture_outcome", snap.outcome))
        if name in cfg.fields
    }
    run_key, action = jira.upsert(
        binding.identity + ":run:" + snap.run_id,
        OWNER,
        "council",
        f"Council: {title} ({snap.run_id})",
        f"Phase: {snap.phase}\nOutcome: {snap.outcome}\n"
        f"Recorded update: {snap.updated_at}\nCompleted reviewer passes: "
        f"{sum(c.state == 'complete' for c in snap.cells)}/{len(snap.cells)}\n"
        f"Evidence: {cfg.site}/wiki/spaces/{cfg.confluence_space_id}/pages/{page}\n"
        f"Verification: {snap.core_verification}",
        binding.identity,
        parent=epic,
        extra=extra,
        metadata={
            "run_id": snap.run_id,
            "decision_digest": snap.decision_digest,
            "outcome": snap.outcome,
        },
    )
    # Earlier runs remain visible and are marked superseded without rewriting their outcomes.
    for old in jira.owned(binding.identity, OWNER):
        meta = jira.metadata(old["key"])
        if meta.get("kind") == "council" and meta.get("run_id") != snap.run_id:
            jira.transition(old["key"], cfg.statuses["done"])
            if "superseded" in cfg.fields and (
                jira.get(old["key"])["fields"].get(cfg.fields["superseded"]) != "true"
            ):
                cloud.request(
                    "jira",
                    "PUT",
                    f"/rest/api/3/issue/{old['key']}",
                    json={"fields": {cfg.fields["superseded"]: "true"}},
                )
    jira.transition(run_key, board_status(snap, cfg))
    decision_key = None
    if snap.phase in ("awaiting_human", "blocked") and snap.context_current:
        if not {"decision_payload", "decision_digest"}.issubset(cfg.fields):
            raise Conflict("configure decision_payload and decision_digest Jira fields")
        decision_key, decision_action = jira.upsert(
            binding.identity + ":decision:" + snap.run_id + ":" + snap.decision_digest,
            OWNER,
            "decision",
            f"Human architecture decision: {title}",
            "Review each conflict and select proposal IDs with rationale. "
            "Enter JSON selections in the decision payload field, "
            "then use the configured approval transition.\n"
            + json.dumps(
                {"conflicts": snap.manifest["conflicts"], "blocking_validators": snap.blockers},
                indent=2,
            ),
            binding.identity,
            parent=epic,
            extra={cfg.fields["decision_digest"]: snap.decision_digest},
            metadata={"run_id": snap.run_id, "decision_digest": snap.decision_digest},
        )
        if decision_action == "created":
            jira.transition(decision_key, cfg.statuses["waiting"])
        jira.link(run_key, decision_key)
    current_sections = sections(snap, cfg, decision_key)
    filename = "agentstandards-pipeline-" + snap.run_id + ".png"
    confluence.attachment(page, filename, pipeline(snap), "image/png")
    current_sections[0] = Section(
        current_sections[0].key,
        current_sections[0].title,
        current_sections[0].body + f"<p>Run: <code>{escape(snap.run_id)}</code></p>"
        f'<ac:image><ri:attachment ri:filename="{escape(filename)}" /></ac:image>',
        True,
    )
    # Archive the previous rendered report on the same page before replacing current sections.
    properties = confluence.properties(page)
    last_key = "atlassian.integration.current-run.v1"
    last_prop = properties.get(last_key)
    old_run = last_prop["value"] if last_prop else None
    if old_run and old_run != snap.run_id:
        body = document(confluence.get(page)["body"]["storage"]["value"])
        history_id = section_id(binding.identity, OWNER, "history-" + old_run)
        archived = body.xpath(
            ".//ac:structured-macro[@ac:macro-id=$id]", namespaces=NS, id=history_id
        )
        if not archived:
            history = ""
            for section in current_sections:
                sid = section_id(binding.identity, OWNER, section.key)
                found = body.xpath(
                    ".//ac:structured-macro[@ac:macro-id=$id]", namespaces=NS, id=sid
                )
                if found:
                    rich = found[0].find("ac:rich-text-body", NS)
                    history += f"<h2>{escape(section.title)}</h2>" + (rich.text or "")
                    history += "".join(serialized(child) for child in rich)
            current_sections.append(
                Section("history-" + old_run, "Previous council run: " + old_run, history)
            )
    page_action = confluence.update(page, binding.identity, OWNER, current_sections)
    confluence.set_property(page, last_key, snap.run_id, last_prop)
    jira.remote_link(
        run_key,
        f"{cfg.site}/wiki/spaces/{cfg.confluence_space_id}/pages/{page}",
        "Council evidence and human decisions",
    )
    return {
        "source_revision": sha,
        "run_id": snap.run_id,
        "run_key": run_key,
        "decision_key": decision_key,
        "outcome": snap.outcome,
        "verified_ready": snap.verified_ready,
        "page": page,
        "page_action": page_action,
        "run_action": action,
    }
