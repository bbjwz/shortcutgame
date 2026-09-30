from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from ..config import ParticipantConfig
from ..models import IsolationEvidence, Usage, VisibleExchange


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        visible_output: str = "",
        exchanges: tuple[VisibleExchange, ...] = (),
        usage: Usage | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.visible_output = visible_output
        self.exchanges = exchanges
        self.usage = usage or Usage()


@dataclass(frozen=True)
class ProviderResult:
    parsed: BaseModel
    visible_output: str
    resolved_model: str
    request_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    exchanges: tuple[VisibleExchange, ...] = ()


class ProviderAdapter(ABC):
    def __init__(self, config: ParticipantConfig, *, timeout_seconds: int):
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.adapter_instance_id = f"adapter-{uuid4().hex}"
        self._invocation_claimed = False
        self._generation_started = False

    def begin_isolated_invocation(self, invocation_id: str) -> IsolationEvidence:
        """Bind this adapter object to exactly one fresh-context inference attempt."""
        if self._invocation_claimed:
            raise ProviderError(
                "provider adapter instance cannot be reused across inference attempts"
            )
        self._invocation_claimed = True
        return IsolationEvidence(
            invocation_id=invocation_id,
            adapter_instance_id=self.adapter_instance_id,
        )

    def require_isolated_invocation(self) -> None:
        """Refuse unclaimed or repeated generation on this adapter instance."""
        if not self._invocation_claimed:
            raise ProviderError("provider generation requires a claimed fresh-context invocation")
        if self._generation_started:
            raise ProviderError(
                "provider adapter instance cannot generate more than once"
            )
        self._generation_started = True

    @abstractmethod
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[BaseModel],
        project_root: str,
        reserve_call: Callable[[], Awaitable[None]] | None = None,
    ) -> ProviderResult:
        raise NotImplementedError


def normalized_schema(output_model: type[BaseModel]) -> dict[str, Any]:
    schema = output_model.model_json_schema(mode="validation")
    return _clean_schema(schema)


def _clean_schema(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"default", "examples"}:
                continue
            result[key] = _clean_schema(item)
        if result.get("type") == "object":
            result["additionalProperties"] = False
        return result
    if isinstance(value, list):
        return [_clean_schema(item) for item in value]
    return value


def parse_output(text: str, output_model: type[BaseModel]) -> BaseModel:
    candidate = text.strip()
    if candidate.startswith("```json"):
        candidate = candidate[7:]
    elif candidate.startswith("```"):
        candidate = candidate[3:]
    if candidate.endswith("```"):
        candidate = candidate[:-3]
    return output_model.model_validate_json(candidate.strip())
