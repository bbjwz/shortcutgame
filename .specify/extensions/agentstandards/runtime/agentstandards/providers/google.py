from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel, ValidationError

from ..models import Usage
from .base import ProviderAdapter, ProviderError, ProviderResult, normalized_schema, parse_output


class GoogleProvider(ProviderAdapter):
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
        base_url = (
            self.config.base_url or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")
        model = self.config.model.removeprefix("models/")
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self.config.max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": normalized_schema(output_model),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{base_url}/models/{model}:generateContent",
                    headers={"x-goog-api-key": api_key, "content-type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("Google request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Google transport error: {exc}", retryable=True) from exc
        if response.status_code >= 400:
            retryable = response.status_code in {408, 429} or response.status_code >= 500
            raise ProviderError(
                f"Google returned HTTP {response.status_code}: {response.text[:2000]}",
                retryable=retryable,
                visible_output=response.text,
            )
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Google returned a non-JSON response",
                retryable=True,
                visible_output=response.text,
            ) from exc
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("Google returned no candidates")
        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        visible = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        raw_usage = data.get("usageMetadata") or {}
        usage = Usage(
            input_tokens=int(raw_usage.get("promptTokenCount", 0) or 0),
            output_tokens=int(raw_usage.get("candidatesTokenCount", 0) or 0),
        )
        finish_reason = candidate.get("finishReason")
        if finish_reason not in {None, "STOP"}:
            raise ProviderError(
                f"Google stopped with {finish_reason}",
                visible_output=visible,
                usage=usage,
            )
        try:
            parsed = parse_output(visible, output_model)
        except ValidationError as exc:
            raise ProviderError(
                f"Google returned invalid structured output: {exc}",
                retryable=True,
                visible_output=visible,
                usage=usage,
            ) from exc
        return ProviderResult(
            parsed=parsed,
            visible_output=visible or json.dumps(data, ensure_ascii=False),
            resolved_model=self.config.model,
            request_id=response.headers.get("x-request-id"),
            usage=usage,
        )
