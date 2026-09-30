from __future__ import annotations

import re
from pathlib import Path


class SecurityViolation(ValueError):
    """Raised when data cannot safely leave the local project."""


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("bearer token", re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+")),
    (
        "assigned credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"
        ),
    ),
)


def find_secrets(text: str) -> list[str]:
    return [name for name, pattern in _SECRET_PATTERNS if pattern.search(text)]


def assert_no_secrets(text: str, *, label: str) -> None:
    matches = find_secrets(text)
    if matches:
        raise SecurityViolation(
            f"refusing to send or persist {label}: possible secrets detected ({', '.join(matches)})"
        )


def ensure_real_path_inside(root: Path, target: Path, *, must_exist: bool = True) -> Path:
    root = root.resolve()
    if must_exist and not target.exists():
        raise SecurityViolation(f"required path does not exist: {target}")

    current = target if target.exists() else target.parent
    while current != root and current != current.parent:
        if current.is_symlink():
            raise SecurityViolation(f"symlinked paths are not allowed: {current}")
        current = current.parent

    resolved = target.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SecurityViolation(f"path escapes project root: {target}") from exc
    return resolved


def assert_architecture_path(project_root: Path, feature_dir: Path, path: Path) -> Path:
    resolved = ensure_real_path_inside(project_root, path)
    allowed_exact = {
        (project_root / ".specify" / "memory" / "constitution.md").resolve(),
        *(
            feature_dir / name
            for name in (
                "spec.md",
                "plan.md",
                "research.md",
                "data-model.md",
                "quickstart.md",
            )
        ),
    }
    allowed_exact = {item.resolve() for item in allowed_exact}
    contracts = (feature_dir / "contracts").resolve()
    architecture = (feature_dir / "architecture").resolve()

    if resolved in allowed_exact:
        return resolved
    for allowed_dir in (contracts, architecture):
        try:
            resolved.relative_to(allowed_dir)
            return resolved
        except ValueError:
            pass
    raise SecurityViolation(
        f"external reviewers may only receive constitution, feature architecture artifacts, "
        f"or contracts; rejected: {path}"
    )
