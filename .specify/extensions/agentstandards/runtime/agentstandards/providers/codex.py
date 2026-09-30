from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ..models import Usage
from .base import ProviderAdapter, ProviderError, ProviderResult, normalized_schema, parse_output


class CodexCliProvider(ProviderAdapter):
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
        executable = self.config.executable or "codex"
        combined = f"{system_prompt}\n\n{user_prompt}"
        with tempfile.TemporaryDirectory(prefix="agentstandards-codex-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            output_path = Path(temp_dir) / "output.json"
            schema_path.write_text(
                json.dumps(normalized_schema(output_model), ensure_ascii=False), encoding="utf-8"
            )
            args = [
                executable,
                "exec",
                "-",
                "--model",
                self.config.model,
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--cd",
                temp_dir,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--json",
                "--color",
                "never",
            ]
            try:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=temp_dir,
                    env={**os.environ, "NO_COLOR": "1"},
                )
            except FileNotFoundError as exc:
                raise ProviderError(f"Codex executable not found: {executable}") from exc
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(combined.encode("utf-8")),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                process.kill()
                await process.wait()
                raise ProviderError("Codex request timed out", retryable=True) from exc
            if process.returncode != 0:
                error = stderr.decode("utf-8", errors="replace").strip()
                raise ProviderError(
                    f"Codex exited with {process.returncode}: {error[-2000:]}",
                    retryable=process.returncode in {1, 75},
                    visible_output=error,
                )
            if not output_path.exists():
                raise ProviderError("Codex completed without writing its structured output")
            visible = output_path.read_text(encoding="utf-8")
            request_id: str | None = None
            usage = Usage()
            for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                request_id = request_id or event.get("thread_id") or event.get("id")
                event_usage = event.get("usage")
                if isinstance(event_usage, dict):
                    usage = Usage(
                        input_tokens=int(
                            event_usage.get("input_tokens", event_usage.get("inputTokens", 0)) or 0
                        ),
                        output_tokens=int(
                            event_usage.get("output_tokens", event_usage.get("outputTokens", 0))
                            or 0
                        ),
                    )
            try:
                parsed = parse_output(visible, output_model)
            except ValidationError as exc:
                raise ProviderError(
                    f"Codex returned invalid structured output: {exc}",
                    retryable=True,
                    visible_output=visible,
                    usage=usage,
                ) from exc
            return ProviderResult(
                parsed=parsed,
                visible_output=visible,
                resolved_model=self.config.model,
                request_id=request_id,
                usage=usage,
            )
