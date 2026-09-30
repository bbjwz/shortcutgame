from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel, ValidationError

from ..models import Usage
from .base import ProviderAdapter, ProviderError, ProviderResult, normalized_schema, parse_output


class AnthropicProvider(ProviderAdapter):
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
        del project_root, reserve_call
        api_key = self.config.require_api_key()
        base_url = (self.config.base_url or "https://api.anthropic.com").rstrip("/")
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": normalized_schema(output_model),
                }
            },
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{base_url}/v1/messages", headers=headers, json=payload
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("Anthropic request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic transport error: {exc}", retryable=True) from exc
        if response.status_code >= 400:
            retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
            raise ProviderError(
                f"Anthropic returned HTTP {response.status_code}: {response.text[:2000]}",
                retryable=retryable,
                visible_output=response.text,
            )
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Anthropic returned a non-JSON response",
                retryable=True,
                visible_output=response.text,
            ) from exc
        blocks = data.get("content", [])
        visible = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        raw_usage = data.get("usage") or {}
        usage = Usage(
            input_tokens=int(raw_usage.get("input_tokens", 0) or 0),
            output_tokens=int(raw_usage.get("output_tokens", 0) or 0),
        )
        if data.get("stop_reason") in {"refusal", "max_tokens"}:
            raise ProviderError(
                f"Anthropic stopped with {data.get('stop_reason')}",
                visible_output=visible,
                usage=usage,
            )
        try:
            parsed = parse_output(visible, output_model)
        except ValidationError as exc:
            raise ProviderError(
                f"Anthropic returned invalid structured output: {exc}",
                retryable=True,
                visible_output=visible,
                usage=usage,
            ) from exc
        return ProviderResult(
            parsed=parsed,
            visible_output=visible or json.dumps(data, ensure_ascii=False),
            resolved_model=str(data.get("model") or self.config.model),
            request_id=response.headers.get("request-id") or data.get("id"),
            usage=usage,
        )
