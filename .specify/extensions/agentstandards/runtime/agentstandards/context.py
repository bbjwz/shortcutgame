from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .security import assert_architecture_path, assert_no_secrets, ensure_real_path_inside


@dataclass(frozen=True)
class ContextBundle:
    project_root: Path
    feature_dir: Path
    feature: str
    files: tuple[Path, ...]
    content: str
    content_hash: str


def resolve_project_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".specify").is_dir():
            ensure_real_path_inside(candidate, candidate / ".specify")
            return candidate
    raise ValueError(f"no Spec Kit project found from {start}; expected a .specify directory")


def resolve_feature_dir(project_root: Path) -> Path:
    override = os.environ.get("SPECIFY_FEATURE_DIRECTORY", "").strip()
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = project_root / candidate
    else:
        pointer = project_root / ".specify" / "feature.json"
        ensure_real_path_inside(project_root, pointer)
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"invalid Spec Kit feature pointer: {pointer}") from exc
        value = data.get("feature_directory") if isinstance(data, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"feature_directory is missing from {pointer}")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = project_root / candidate

    feature_dir = ensure_real_path_inside(project_root, candidate)
    if feature_dir.name in {"", ".", "..", "architecture"}:
        raise ValueError(f"unsafe feature directory: {feature_dir}")
    return feature_dir


def _candidate_files(project_root: Path, feature_dir: Path) -> list[Path]:
    files = [
        project_root / ".specify" / "memory" / "constitution.md",
        feature_dir / "spec.md",
        feature_dir / "plan.md",
        feature_dir / "research.md",
        feature_dir / "data-model.md",
        feature_dir / "quickstart.md",
    ]
    contracts = feature_dir / "contracts"
    if contracts.is_dir() and not contracts.is_symlink():
        files.extend(
            path
            for path in sorted(contracts.rglob("*"))
            if path.is_file() and not path.is_symlink()
        )
    return files


def build_context(
    project_root: Path, feature_dir: Path, *, scan_secrets: bool = True
) -> ContextBundle:
    selected: list[Path] = []
    parts: list[str] = []
    for path in _candidate_files(project_root, feature_dir):
        if not path.exists():
            continue
        safe_path = assert_architecture_path(project_root, feature_dir, path)
        try:
            text = safe_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"architecture context must be UTF-8 text: {safe_path}") from exc
        if scan_secrets:
            assert_no_secrets(text, label=str(safe_path.relative_to(project_root)))
        selected.append(safe_path)
        relative = safe_path.relative_to(project_root).as_posix()
        parts.append(
            f"\n===== BEGIN ARCHITECTURE ARTIFACT: {relative} =====\n"
            f"{text}\n===== END ARCHITECTURE ARTIFACT: {relative} =====\n"
        )

    required = {feature_dir / "spec.md", feature_dir / "plan.md"}
    selected_resolved = {item.resolve() for item in selected}
    missing = [path for path in required if path.resolve() not in selected_resolved]
    if missing:
        raise ValueError(
            "Agentstandards requires Spec Kit specification and plan artifacts: "
            + ", ".join(str(path) for path in missing)
        )
    content = "".join(parts)
    digest = hashlib.sha256(content.encode()).hexdigest()
    return ContextBundle(
        project_root=project_root,
        feature_dir=feature_dir,
        feature=feature_dir.name,
        files=tuple(selected),
        content=content,
        content_hash=digest,
    )
