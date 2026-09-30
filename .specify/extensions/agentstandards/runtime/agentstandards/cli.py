from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from .config import (
    CouncilConfig,
    LimitsConfig,
    ParticipantConfig,
    Pricing,
    TranscriptConfig,
    load_config,
    save_config,
)
from .context import build_context, resolve_feature_dir, resolve_project_root
from .orchestrator import (
    CouncilError,
    CouncilRunner,
    gate_status,
    validate_run_offline,
    verify_ready_gate,
)
from .storage import current_run_paths, load_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentstandards",
        description="Run the Spec Kit multi-vendor architecture council.",
    )
    parser.add_argument("--project-root", type=Path, help="Spec Kit project root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create the project council configuration")
    init.add_argument("--codex-model", required=True)
    init.add_argument("--anthropic-model", required=True)
    init.add_argument("--anthropic-key-env", default="ANTHROPIC_API_KEY")
    init.add_argument("--anthropic-base-url")
    init.add_argument(
        "--provider-json",
        action="append",
        default=[],
        metavar="JSON",
        help="Optional ParticipantConfig JSON; repeat for each optional vendor",
    )
    init.add_argument("--max-concurrency", type=int, default=4)
    init.add_argument("--timeout-seconds", type=int, default=180)
    init.add_argument("--max-retries", type=int, default=2)
    init.add_argument("--max-calls", type=int, default=500)
    init.add_argument("--max-input-tokens", type=int, default=2_000_000)
    init.add_argument("--max-output-tokens", type=int, default=500_000)
    init.add_argument("--max-cost-usd", type=float, default=100)
    init.add_argument("--codex-input-price", type=float, default=0)
    init.add_argument("--codex-output-price", type=float, default=0)
    init.add_argument("--anthropic-input-price", type=float, default=0)
    init.add_argument("--anthropic-output-price", type=float, default=0)

    architect = subparsers.add_parser("architect", help="Run through the human gate")
    architect.add_argument("--new-run", action="store_true")
    architect.add_argument("--json", action="store_true")

    resume = subparsers.add_parser("resume", help="Resume after human decisions")
    resume.add_argument("--json", action="store_true")

    status = subparsers.add_parser("status", help="Show current council progress")
    status.add_argument("--json", action="store_true")

    gate = subparsers.add_parser("gate", help="Require a READY architecture gate")
    gate.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate saved runs without API calls")
    validate.add_argument("--all", action="store_true", help="Validate every feature with a run")
    validate.add_argument("--require-ready", action="store_true")
    return parser


def _project_root(args: argparse.Namespace) -> Path:
    if args.project_root:
        root = args.project_root.resolve()
        if not (root / ".specify").is_dir():
            raise ValueError(f"not a Spec Kit project: {root}")
        return root
    return resolve_project_root(Path.cwd())


def _config_path(project_root: Path) -> Path:
    return project_root / ".specify" / "extensions" / "agentstandards" / "agentstandards-config.yml"


def _init(args: argparse.Namespace, project_root: Path) -> int:
    optional: list[ParticipantConfig] = []
    for raw in args.provider_json:
        value = json.loads(raw)
        value["required"] = False
        value.setdefault("enabled", True)
        optional.append(ParticipantConfig.model_validate(value))
    config = CouncilConfig(
        configured=True,
        participants=[
            ParticipantConfig(
                id="codex",
                required=True,
                transport="codex-cli",
                underlying_vendor="openai",
                model=args.codex_model,
                executable="codex",
                pricing=Pricing(
                    input_per_million_usd=args.codex_input_price,
                    output_per_million_usd=args.codex_output_price,
                ),
            ),
            ParticipantConfig(
                id="anthropic",
                required=True,
                transport="anthropic",
                underlying_vendor="anthropic",
                model=args.anthropic_model,
                api_key_env=args.anthropic_key_env,
                base_url=args.anthropic_base_url,
                pricing=Pricing(
                    input_per_million_usd=args.anthropic_input_price,
                    output_per_million_usd=args.anthropic_output_price,
                ),
            ),
            *optional,
        ],
        limits=LimitsConfig(
            max_concurrency=args.max_concurrency,
            request_timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            max_calls_per_run=args.max_calls,
            max_total_input_tokens=args.max_input_tokens,
            max_total_output_tokens=args.max_output_tokens,
            max_cost_usd=args.max_cost_usd,
        ),
        transcripts=TranscriptConfig(),
    )
    path = _config_path(project_root)
    save_config(path, config)
    print(f"Configured {len(config.enabled_participants)} council participants in {path}")
    for participant in config.enabled_participants:
        requirement = "required" if participant.required else "optional"
        print(
            f"- {participant.id}: {participant.transport} -> "
            f"{participant.underlying_vendor}/{participant.model} ({requirement})"
        )
    return 0


def _runner(project_root: Path) -> CouncilRunner:
    config_path = _config_path(project_root)
    config = load_config(config_path)
    feature_dir = resolve_feature_dir(project_root)
    context = build_context(
        project_root,
        feature_dir,
        scan_secrets=config.transcripts.secret_scan,
    )
    return CouncilRunner(context=context, config=config, config_path=config_path)


async def _architect(args: argparse.Namespace, project_root: Path) -> int:
    runner = _runner(project_root)
    paths = await runner.architect(new_run=args.new_run)
    state = load_state(paths)
    payload = {
        "run_id": paths.run_id,
        "phase": state.phase,
        "decision_manifest": str(paths.decision_manifest),
        "gate_report": str(paths.gate_report),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Council run {paths.run_id} is {state.phase}.")
        if state.phase == "awaiting_human":
            print(f"Complete the human decision manifest: {paths.decision_manifest}")
            print("Then run $speckit-agentstandards-resume.")
    return 0


async def _resume(args: argparse.Namespace, project_root: Path) -> int:
    runner = _runner(project_root)
    paths = await runner.resume()
    state = load_state(paths)
    report = gate_status(project_root, runner.context.feature_dir)
    payload = {
        "run_id": paths.run_id,
        "phase": state.phase,
        "gate": report.status,
        "gate_report": str(paths.gate_report),
        "exception_applied": report.exception_applied,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Architecture gate: {report.status}")
        print(f"Report: {paths.gate_report}")
        if report.status == "BLOCKED":
            print(
                "Codex and Anthropic did not both validate the architecture. "
                "Remediate and start a new run, or record an explicit human exception and resume."
            )
    return 0 if report.status == "READY" else 2


def _status(args: argparse.Namespace, project_root: Path) -> int:
    feature_dir = resolve_feature_dir(project_root)
    paths = current_run_paths(project_root, feature_dir)
    state = load_state(paths)
    config = CouncilConfig.model_validate(
        yaml.safe_load((paths.run_dir / "config-snapshot.yaml").read_text(encoding="utf-8"))
    )
    report = None
    if paths.gate_report.exists():
        report = gate_status(project_root, feature_dir)
    report_status = report.status if report else None
    expected = len(config.enabled_participants) * 26 + 1
    payload = {
        "run_id": state.run_id,
        "feature": state.feature,
        "phase": state.phase,
        "gate": report_status,
        "participants": [
            {
                "id": p.id,
                "required": p.required,
                "transport": p.transport,
                "underlying_vendor": p.underlying_vendor,
                "model": p.model,
            }
            for p in config.enabled_participants
        ],
        "completed_artifacts": len(state.completed_artifact_ids),
        "expected_artifacts_including_compile": expected,
        "provider_calls_including_retries": state.call_count,
        "isolation": config.isolation.model_dump(mode="json"),
        "validator_isolation": (
            [item.model_dump(mode="json") for item in report.validator_isolation]
            if report
            else []
        ),
        "usage": state.usage.model_dump(mode="json"),
        "optional_warnings": state.optional_warnings,
        "errors": state.errors,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Run: {state.run_id} ({state.phase})")
        print(f"Gate: {report_status or 'not created'}")
        print("Isolation: fresh context and a new adapter for every inference attempt")
        print(
            f"Artifacts: {len(state.completed_artifact_ids)}/{expected}; "
            f"calls: {state.call_count}; estimated cost: ${state.usage.estimated_cost_usd:.4f}"
        )
        for participant in payload["participants"]:
            print(
                f"- {participant['id']}: {participant['underlying_vendor']}/"
                f"{participant['model']} ({'required' if participant['required'] else 'optional'})"
            )
        for warning in state.optional_warnings:
            print(f"WARNING: {warning}")
        for error in state.errors:
            print(f"ERROR: {error}")
    return 0


def _gate(args: argparse.Namespace, project_root: Path) -> int:
    feature_dir = resolve_feature_dir(project_root)
    try:
        config = load_config(_config_path(project_root))
        context = build_context(
            project_root,
            feature_dir,
            scan_secrets=config.transcripts.secret_scan,
        )
        report = verify_ready_gate(
            project_root,
            feature_dir,
            config,
            context.content_hash,
        )
    except (CouncilError, FileNotFoundError, ValidationError, ValueError) as exc:
        if args.json:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        else:
            print(f"Task generation blocked: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(report.model_dump_json(indent=2))
    elif report.status == "READY":
        suffix = " (human exception recorded)" if report.exception_applied else ""
        print(f"Architecture gate READY{suffix}.")
    else:
        print(
            f"Task generation blocked: architecture gate is {report.status}. "
            f"See {report.decision_manifest_path}.",
            file=sys.stderr,
        )
    return 0 if report.status == "READY" else 2


def _validate(args: argparse.Namespace, project_root: Path) -> int:
    if args.all:
        features = sorted(
            path.parent.parent
            for path in (project_root / "specs").glob("*/architecture/current-run.json")
        )
    else:
        features = [resolve_feature_dir(project_root)]
    errors: list[str] = []
    for feature in features:
        feature_errors = validate_run_offline(project_root, feature)
        errors.extend(f"{feature.name}: {error}" for error in feature_errors)
        if args.require_ready:
            try:
                config = load_config(_config_path(project_root))
                context = build_context(
                    project_root,
                    feature,
                    scan_secrets=config.transcripts.secret_scan,
                )
                verify_ready_gate(
                    project_root,
                    feature,
                    config,
                    context.content_hash,
                )
            except Exception as exc:
                errors.append(f"{feature.name}: gate validation failed: {exc}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"Validated {len(features)} architecture run(s) without provider calls.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        project_root = _project_root(args)
        if args.command == "init":
            return _init(args, project_root)
        if args.command == "architect":
            return asyncio.run(_architect(args, project_root))
        if args.command == "resume":
            return asyncio.run(_resume(args, project_root))
        if args.command == "status":
            return _status(args, project_root)
        if args.command == "gate":
            return _gate(args, project_root)
        if args.command == "validate":
            return _validate(args, project_root)
    except (CouncilError, ValidationError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agentstandards: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
