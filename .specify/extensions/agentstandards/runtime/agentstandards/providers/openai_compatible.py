from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel, ValidationError

from ..models import Usage, VisibleExchange
from .base import ProviderAdapter, ProviderError, ProviderResult, normalized_schema, parse_output


class OpenAICompatibleProvider(ProviderAdapter):
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
        del project_root
        api_key = self.config.require_api_key()
        base_url = (self.config.base_url or "").rstrip("/")
        if not base_url:
            raise ProviderError(f"participant {self.config.id!r} must set base_url")
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.config.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_model.__name__,
                    "strict": True,
                    "schema": normalized_schema(output_model),
                },
            },
        }
        data, response = await self._post(base_url, api_key, payload)
        visible = self._content(data)
        exchanges = [self._exchange("generate", user_prompt, visible, data, response)]
        try:
            parsed = parse_output(visible, output_model)
        except ValidationError:
            repair_prompt = (
                "Repair the following output so it matches the required JSON schema. "
                "Do not add new substantive claims.\n\n" + visible
            )
            repair_payload = {
                **payload,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": repair_prompt},
                ],
            }
            if reserve_call is not None:
                try:
                    await reserve_call()
                except Exception as exc:
                    raise ProviderError(
                        "repair call was not attempted because the run budget was exhausted",
                        visible_output=visible,
                        exchanges=tuple(exchanges),
                    ) from exc
            data, response = await self._post(base_url, api_key, repair_payload)
            visible = self._content(data)
            exchanges.append(self._exchange("repair", repair_prompt, visible, data, response))
            try:
                parsed = parse_output(visible, output_model)
            except ValidationError as exc:
                raise ProviderError(
                    f"{self.config.id} returned invalid structured output after repair: {exc}",
                    visible_output=visible,
                    exchanges=tuple(exchanges),
                ) from exc
        usage = Usage(
            input_tokens=sum(item.usage.input_tokens for item in exchanges),
            output_tokens=sum(item.usage.output_tokens for item in exchanges),
        )
        resolved_model = str(data.get("model") or self.config.model)
        return ProviderResult(
            parsed=parsed,
            visible_output=visible or json.dumps(data, ensure_ascii=False),
            resolved_model=resolved_model,
            request_id=response.headers.get("x-request-id") or data.get("id"),
            usage=usage,
            exchanges=tuple(exchanges),
        )

    def _exchange(
        self,
        kind: str,
        user_prompt: str,
        visible_output: str,
        data: dict,
        response: httpx.Response,
    ) -> VisibleExchange:
        raw_usage = data.get("usage") or {}
        return VisibleExchange(
            kind=kind,
            visible_user_prompt=user_prompt,
            visible_output=visible_output,
            request_id=response.headers.get("x-request-id") or data.get("id"),
            resolved_model=str(data.get("model") or self.config.model),
            usage=Usage(
                input_tokens=int(raw_usage.get("prompt_tokens", 0) or 0),
                output_tokens=int(raw_usage.get("completion_tokens", 0) or 0),
            ),
        )

    async def _post(
        self, base_url: str, api_key: str, payload: dict
    ) -> tuple[dict, httpx.Response]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "authorization": f"Bearer {api_key}",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.config.id} request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.config.id} transport error: {exc}", retryable=True) from exc
        if response.status_code >= 400:
            retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
            raise ProviderError(
                f"{self.config.id} returned HTTP {response.status_code}: {response.text[:2000]}",
                retryable=retryable,
                visible_output=response.text,
            )
        try:
            return response.json(), response
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"{self.config.id} returned a non-JSON response",
                retryable=True,
                visible_output=response.text,
            ) from exc

    @staticmethod
    def _content(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("OpenAI-compatible provider returned no choices")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        raise ProviderError("OpenAI-compatible provider returned no text content")
