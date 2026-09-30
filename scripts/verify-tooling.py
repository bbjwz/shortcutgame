from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(relative: str):
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


sources = load_yaml(".specify/sources.yml")
assert sources["components"]["spec-kit"]["version"] == "1.0.12"

init_options = json.loads((ROOT / ".specify/init-options.json").read_text())
assert init_options["speckit_version"] == "1.0.12"
assert init_options["integration"] == "codex"

expected_extensions = {
    "agentstandards": "0.1.1",
    "atlassian": "0.1.0",
    "agentstandards-atlassian": "0.1.0",
    "delivery": "0.1.0",
}
for extension_id, version in expected_extensions.items():
    manifest = load_yaml(f".specify/extensions/{extension_id}/extension.yml")
    assert manifest["extension"]["version"] == version, extension_id

extensions = load_yaml(".specify/extensions.yml")
assert set(extensions["installed"]) == set(expected_extensions)

required_skills = {
    "speckit-specify",
    "speckit-plan",
    "speckit-agentstandards-architect",
    "speckit-atlassian-sync",
    "speckit-agentstandards-atlassian-sync",
    "speckit-delivery-verify",
}
installed_skills = {path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")}
assert required_skills <= installed_skills

for forbidden_path in (
    ".specify/integrations/atlassian/config.yml",
    ".delivery-policy.yml",
    ".github/workflows/atlassian-sync.yml",
    ".github/workflows/delivery-evidence.yml",
    ".github/workflows/delivery-acceptance.yml",
    ".github/workflows/delivery-review-signal.yml",
):
    assert not (ROOT / forbidden_path).exists(), forbidden_path

assert "trust_candidates" not in sources
print("Pinned guest source installations and the source-only boundary are consistent.")
