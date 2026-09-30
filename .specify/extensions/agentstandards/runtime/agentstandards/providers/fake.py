from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from ..models import MasterPlanPayload, PersonaPayload, Usage
from .base import ProviderAdapter, ProviderResult


class FakeProvider(ProviderAdapter):
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[BaseModel],
        project_root: str,
        reserve_call: Callable[[], Awaitable[None]] | None = None,
    ) -> ProviderResult:
        self.require_isolated_invocation()
        del system_prompt, project_root, reserve_call
        marker = self.config.id
        if issubclass(output_model, PersonaPayload):
            value = PersonaPayload(
                summary=f"Deterministic {marker} assessment",
                requirement_ids=["REQ-001"],
                recommendations=[f"Retain evidence from {marker}"],
                confidence=80,
                verdict=("READY" if "architecture-validator" in user_prompt else "NOT_APPLICABLE"),
            )
        elif issubclass(output_model, MasterPlanPayload):
            value = MasterPlanPayload(summary="Deterministic compiled master plan")
        else:
            value = output_model.model_validate({})
        visible = value.model_dump_json(indent=2)
        return ProviderResult(
            parsed=value,
            visible_output=visible,
            resolved_model=self.config.model,
            request_id=f"fake-{marker}",
            usage=Usage(input_tokens=10, output_tokens=10),
        )
