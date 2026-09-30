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

config = load_yaml(".specify/integrations/atlassian/config.yml")
assert config["site"] == "https://barthisagent.atlassian.net"
assert config["jira_project"] == "SCRUM"
assert config["confluence_space_id"] == "65822"
assert config["email_env"] == "ATLASSIAN_EMAIL"
assert config["token_env"] == "ATLASSIAN_API_TOKEN"
assert set(config["enabled_integrations"]) == {
    "spec-kit-atlassian",
    "agentstandards-atlassian",
}

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

for workflow in (
    "atlassian-sync.yml",
    "delivery-evidence.yml",
    "delivery-acceptance.yml",
    "delivery-review-signal.yml",
):
    document = load_yaml(f".github/workflows/{workflow}")
    assert document["name"]
    assert "jobs" in document

assert not sources["trust_candidates"]["speckit-delivery-public-runner"]["enabled"]
print("Tooling manifests, pins, skills, and workflows are consistent.")
