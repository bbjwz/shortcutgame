from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common.confluence import Confluence, merge_sections
from .common.git import dispatch, draft_change, revision, run
from .common.http import Cloud
from .common.jira import Jira
from .common.models import Conflict, inside
from .common.runtime import (
    adopt,
    cache_path,
    change_branch,
    doctor,
    initialize,
    load,
    require_worker,
    restore_binding,
    save_status,
)
from .council import sections, snapshot
from .decisions import approved_manifest, changes_for_decision
from .engine import OWNER, synchronize


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Agentstandards council → Jira/Confluence Cloud")
    p.add_argument("--project", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    for flag in ("feature", "repository", "site", "jira-project", "space-id"):
        init.add_argument("--" + flag, required=True)
    for name in ("doctor", "preview", "sync", "reconcile-decisions", "status", "adopt"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--binding", required=True)
        if name == "preview":
            cmd.add_argument("--offline", action="store_true")
        if name in ("sync", "reconcile-decisions", "adopt"):
            cmd.add_argument("--apply", action="store_true", help="worker-only remote write")
            cmd.add_argument("--base", default=None, help="feature branch for a draft PR")
        if name == "reconcile-decisions":
            cmd.add_argument("--decision-key", default="")
        if name == "adopt":
            cmd.add_argument("--epic", required=True)
            cmd.add_argument("--page", required=True)
    return p


def execute(args) -> dict:
    root = args.project.resolve()
    if args.command == "init":
        return initialize(
            root, args.feature, args.repository, args.site, args.jira_project, args.space_id, OWNER
        )
    cfg, binding = load(root, args.binding)
    original_binding = binding.model_dump(mode="json")
    binding = restore_binding(binding, OWNER)
    if args.command == "status":
        path = cache_path(binding, OWNER)
        return json.loads(path.read_text()) if path.exists() else {"state": "never synchronized"}
    if args.command == "doctor":
        return doctor(cfg, binding, Cloud(cfg))
    sha = revision(root, require_clean=args.command in ("sync", "reconcile-decisions", "adopt"))
    if args.command in ("sync", "reconcile-decisions") and not args.apply:
        dispatch(
            cfg.github_repository,
            cfg.workflow,
            cfg.runtime_ref,
            args.binding,
            OWNER,
            args.command,
            sha,
            getattr(args, "decision_key", ""),
        )
        return {"state": "dispatched", "source_revision": sha}
    snap = snapshot(root, binding, sha)
    if args.command == "preview" and args.offline:
        return {"offline": True, "remote_conflicts_checked": False, **snap.model_dump(mode="json")}
    cloud = Cloud(cfg)
    jira = Jira(cloud, cfg)
    if args.command == "preview":
        page = binding.page_id
        if page:
            confluence = Confluence(cloud, cfg)
            data, props = confluence.get(page), confluence.properties(page)
            merge_sections(
                data["body"]["storage"]["value"],
                binding.identity,
                OWNER,
                sections(snap, cfg, None),
                props.get(f"atlassian.integration.sections.v1.{OWNER}", {}).get("value", {}),
            )
        return snap.model_dump(mode="json")
    if args.command == "adopt" and not args.apply:
        return {
            "proposed_binding": {"epic": args.epic, "page": args.page},
            "note": "run in serialized worker with --apply to adopt existing containers",
        }
    require_worker()
    try:
        if args.command == "sync":
            result = synchronize(
                root, cfg, binding, cloud, lambda b: save_status(b, OWNER, {"state": "partial"})
            )
            save_status(binding, OWNER, {"state": "synchronized", **result})
            changes = {}
            if binding.model_dump(mode="json") != original_binding:
                changes[args.binding] = json.dumps(binding.model_dump(mode="json"), indent=2) + "\n"
        elif args.command == "adopt":
            result = adopt(cfg, binding, cloud, args.epic, args.page)
            changes = {args.binding: json.dumps(result, indent=2) + "\n"}
        else:
            if not args.decision_key:
                identity = (
                    binding.identity + ":decision:" + snap.run_id + ":" + snap.decision_digest
                )
                request = jira.find(identity)
                if not request or request["fields"]["status"]["name"] != cfg.decision_status:
                    return {"state": "no approved decision to reconcile"}
                args.decision_key = request["key"]
            approved = approved_manifest(snap, cfg, jira, args.decision_key)
            changes = changes_for_decision(binding.feature_path, approved)
            result = {"changed_files": list(changes)}
        changes = {
            path: text
            for path, text in changes.items()
            if not inside(root, path).exists() or inside(root, path).read_text() != text
        }
        if changes:
            base = args.base or run(["git", "branch", "--show-current"], root)
            if not base:
                raise Conflict("--base is required for detached feature checkouts")
            result["pull_request"] = draft_change(
                root,
                cfg.github_repository,
                base,
                change_branch(args.command, binding, changes),
                changes,
                (
                    "Record verified Jira architecture decision"
                    if args.command == "reconcile-decisions"
                    else "Record Atlassian feature bindings"
                ),
                (
                    "Records a verified Jira approval. Paid validation remains a separate action."
                    if args.command == "reconcile-decisions"
                    else "Records shared Jira and Confluence container identities."
                ),
            )
        return result
    except Exception:
        save_status(
            binding,
            OWNER,
            {
                "state": "failed",
                "source_revision": sha,
                "note": "inspect the failed worker; remote writes may be partial",
            },
        )
        raise


def main() -> int:
    args = parser().parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, indent=2, default=str))
        return 1 if result.get("ok") is False else 0
    except (Conflict, ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
