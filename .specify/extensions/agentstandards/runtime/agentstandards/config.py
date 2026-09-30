from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Pricing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_per_million_usd: float = Field(default=0, ge=0)
    output_per_million_usd: float = Field(default=0, ge=0)


class ParticipantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    required: bool = False
    enabled: bool = True
    transport: Literal["codex-cli", "anthropic", "google", "openai-compatible", "fake"]
    underlying_vendor: str = Field(pattern=r"^[a-z0-9-]+$")
    model: str
    executable: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    max_output_tokens: int = Field(default=12000, ge=256, le=100000)
    pricing: Pricing = Field(default_factory=Pricing)

    @model_validator(mode="after")
    def validate_transport(self) -> ParticipantConfig:
        if self.enabled and not self.model.strip():
            raise ValueError(f"participant {self.id!r} must pin an explicit model")
        if self.model != self.model.strip() or re.search(r"\s", self.model):
            raise ValueError(f"participant {self.id!r} model must be one exact whitespace-free ID")
        lowered = self.model.strip().lower()
        if lowered in {"route-llm", "auto", "automatic", "default", "unknown"}:
            raise ValueError(
                f"participant {self.id!r} uses auto-routing model {self.model!r}; "
                "pin an explicit model so vendor diversity is auditable"
            )
        if self.transport == "codex-cli":
            if self.underlying_vendor != "openai":
                raise ValueError("codex-cli participant must declare underlying_vendor: openai")
            if not self.executable:
                self.executable = "codex"
        elif self.transport != "fake":
            if not self.api_key_env:
                raise ValueError(f"participant {self.id!r} must set api_key_env")
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.api_key_env):
                raise ValueError(f"participant {self.id!r} has unsafe api_key_env")
        if self.transport == "anthropic" and self.underlying_vendor != "anthropic":
            raise ValueError("native Anthropic transport must declare anthropic as its vendor")
        if self.transport == "google" and self.underlying_vendor != "google":
            raise ValueError("native Google transport must declare google as its vendor")
        if self.transport == "openai-compatible":
            if not self.base_url:
                raise ValueError(f"OpenAI-compatible participant {self.id!r} must set base_url")
            gateway_identities = {
                "abacus",
                "auto",
                "gateway",
                "openrouter",
                "router",
                "unknown",
            }
            if self.underlying_vendor in gateway_identities:
                raise ValueError(
                    f"participant {self.id!r} must identify the model's underlying vendor, "
                    "not its gateway transport"
                )
        return self

    def require_api_key(self) -> str:
        if self.transport in {"codex-cli", "fake"}:
            return ""
        assert self.api_key_env
        value = os.environ.get(self.api_key_env, "")
        if not value:
            raise ValueError(
                f"participant {self.id!r} requires environment variable {self.api_key_env}"
            )
        return value


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_concurrency: int = Field(default=4, ge=1, le=32)
    request_timeout_seconds: int = Field(default=180, ge=10, le=3600)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_calls_per_run: int = Field(default=500, ge=1, le=1000)
    max_total_input_tokens: int = Field(default=2_000_000, ge=1)
    max_total_output_tokens: int = Field(default=500_000, ge=1)
    max_cost_usd: float = Field(default=100, ge=0)


class TranscriptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commit_visible_io: Literal[True] = True
    include_response_envelope: Literal[False] = False
    secret_scan: Literal[True] = True
    redaction_policy: Literal["abort"] = "abort"


class IsolationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context_mode: Literal["fresh-context-per-invocation"] = "fresh-context-per-invocation"
    reuse_provider_sessions: Literal[False] = False
    reuse_adapter_instances: Literal[False] = False


class CouncilConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    configured: bool = False
    participants: list[ParticipantConfig]
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    transcripts: TranscriptConfig = Field(default_factory=TranscriptConfig)
    isolation: IsolationConfig = Field(default_factory=IsolationConfig)

    @model_validator(mode="after")
    def validate_council(self) -> CouncilConfig:
        enabled = [p for p in self.participants if p.enabled]
        ids = [p.id for p in enabled]
        if len(ids) != len(set(ids)):
            raise ValueError("enabled participant IDs must be unique")
        vendors = [p.underlying_vendor for p in enabled]
        if len(vendors) != len(set(vendors)):
            raise ValueError(
                "enabled participants must use distinct underlying vendors; "
                "transport diversity alone does not count"
            )
        by_id = {p.id: p for p in enabled}
        codex = by_id.get("codex")
        anthropic = by_id.get("anthropic")
        if not codex or not codex.required or codex.transport != "codex-cli":
            raise ValueError("required codex participant using codex-cli is missing")
        if (
            not anthropic
            or not anthropic.required
            or anthropic.transport != "anthropic"
            or anthropic.underlying_vendor != "anthropic"
        ):
            raise ValueError("required anthropic participant is missing")
        return self

    @property
    def enabled_participants(self) -> list[ParticipantConfig]:
        return [participant for participant in self.participants if participant.enabled]

    @property
    def required_participants(self) -> list[ParticipantConfig]:
        return [participant for participant in self.enabled_participants if participant.required]

    def stable_hash(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def load_config(path: Path, *, require_configured: bool = True) -> CouncilConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"configuration not found: {path}") from exc
    config = CouncilConfig.model_validate(raw)
    if require_configured and not config.configured:
        raise ValueError(f"configuration is not complete: {path}; run speckit.agentstandards.init")
    return config


def save_config(path: Path, config: CouncilConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json", exclude_none=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
