from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .models import RunState
from .security import ensure_real_path_inside


def stable_json(data: Any) -> str:
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def write_json(path: Path, value: Any) -> None:
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_yaml(path: Path, value: Any) -> None:
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RunPaths:
    architecture_dir: Path
    run_dir: Path
    run_id: str

    @property
    def state(self) -> Path:
        return self.run_dir / "state.json"

    @property
    def transcripts(self) -> Path:
        return self.run_dir / "transcripts"

    @property
    def artifacts(self) -> Path:
        return self.run_dir / "artifacts"

    @property
    def decision_manifest(self) -> Path:
        return self.run_dir / "decision-manifest.yaml"

    @property
    def master_plan(self) -> Path:
        return self.run_dir / "master-plan.yaml"

    @property
    def adr_log(self) -> Path:
        return self.run_dir / "adr-log.yaml"

    @property
    def gate_report(self) -> Path:
        return self.run_dir / "gate-report.yaml"

    def artifact_path(self, stage: str, pass_kind: str, persona: str, participant: str) -> Path:
        return self.artifacts / stage / pass_kind / persona / f"{participant}.yaml"

    def transcript_path(self, stage: str, pass_kind: str, persona: str, participant: str) -> Path:
        return self.transcripts / stage / pass_kind / persona / f"{participant}.json"

    def attempt_path(
        self,
        stage: str,
        pass_kind: str,
        persona: str,
        participant: str,
        attempt_number: int,
    ) -> Path:
        return (
            self.transcripts
            / stage
            / pass_kind
            / persona
            / f"{participant}.attempt-{attempt_number:02d}.json"
        )


def new_run_paths(feature_dir: Path, context_hash: str, config_hash: str) -> RunPaths:
    architecture = feature_dir / "architecture"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{sha256_text(context_hash + config_hash)[:8]}"
    run_dir = architecture / "runs" / run_id
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_id = f"{stamp}-{sha256_text(context_hash + config_hash)[:8]}-{suffix}"
        run_dir = architecture / "runs" / run_id
    run_dir.mkdir(parents=True)
    write_json(architecture / "current-run.json", {"run_id": run_id})
    return RunPaths(architecture, run_dir, run_id)


def current_run_paths(project_root: Path, feature_dir: Path) -> RunPaths:
    architecture = feature_dir / "architecture"
    pointer = architecture / "current-run.json"
    ensure_real_path_inside(project_root, pointer)
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid current run pointer: {pointer}") from exc
    run_id = data.get("run_id") if isinstance(data, dict) else None
    if not isinstance(run_id, str) or not run_id or "/" in run_id or ".." in run_id:
        raise ValueError(f"unsafe current run ID in {pointer}")
    run_dir = ensure_real_path_inside(project_root, architecture / "runs" / run_id)
    return RunPaths(architecture, run_dir, run_id)


def load_state(paths: RunPaths) -> RunState:
    return RunState.model_validate(json.loads(paths.state.read_text(encoding="utf-8")))


def save_state(paths: RunPaths, state: RunState) -> None:
    state.touch()
    write_json(paths.state, state)


def publish_feature_outputs(paths: RunPaths) -> None:
    mapping = {
        paths.decision_manifest: paths.architecture_dir / "decision-manifest.yaml",
        paths.master_plan: paths.architecture_dir / "master-plan.yaml",
        paths.adr_log: paths.architecture_dir / "adr-log.yaml",
        paths.gate_report: paths.architecture_dir / "gate-report.yaml",
    }
    for source, target in mapping.items():
        if source.exists():
            _atomic_write(target, source.read_text(encoding="utf-8"))
