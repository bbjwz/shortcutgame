from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from pathlib import Path
from uuid import uuid4

import yaml
from pydantic import ValidationError

from .config import CouncilConfig, ParticipantConfig
from .context import ContextBundle
from .models import (
    AdrLog,
    ArchitectureDecisionRecord,
    ArtifactEnvelope,
    CallAttemptTranscript,
    DecisionConflict,
    DecisionManifest,
    DecisionOption,
    GateIsolationRecord,
    GateReport,
    IsolationEvidence,
    MasterPlan,
    MasterPlanPayload,
    PersonaDefinition,
    PersonaPayload,
    RunState,
    Transcript,
    Usage,
    Verdict,
    VisibleExchange,
    utc_now,
)
from .personas import load_personas
from .prompts import SYSTEM_PROMPT, compile_prompt, disclosed_prompt, independent_prompt
from .providers import ProviderError, build_provider
from .security import SecurityViolation, assert_no_secrets
from .storage import (
    RunPaths,
    current_run_paths,
    load_state,
    new_run_paths,
    publish_feature_outputs,
    read_yaml,
    save_state,
    sha256_text,
    stable_json,
    write_json,
    write_yaml,
)


class CouncilError(RuntimeError):
    """A council run cannot safely continue."""


class CouncilRunner:
    def __init__(
        self,
        *,
        context: ContextBundle,
        config: CouncilConfig,
        config_path: Path,
    ) -> None:
        self.context = context
        self.config = config
        self.config_path = config_path
        self.registry = load_personas()
        self._semaphore = asyncio.Semaphore(config.limits.max_concurrency)
        self._state_lock = asyncio.Lock()
        self.paths: RunPaths | None = None
        self.state: RunState | None = None

    async def architect(self, *, new_run: bool = False) -> RunPaths:
        self.paths, self.state = self._open_or_create_run(new_run=new_run)
        if self.state.phase in {"awaiting_human", "compiling", "validating", "ready", "blocked"}:
            return self.paths

        try:
            self.state.phase = "planning"
            save_state(self.paths, self.state)
            planning = await self._two_pass_stage(
                stage="planning",
                personas=self.registry.planners,
                context_text=self.context.content,
            )

            self.state.phase = "critiquing"
            save_state(self.paths, self.state)
            critiques = await self._two_pass_stage(
                stage="critiquing",
                personas=self.registry.critics,
                context_text=self.context.content,
                upstream=planning,
            )

            self.state.phase = "synthesizing"
            save_state(self.paths, self.state)
            syntheses = await self._two_pass_stage(
                stage="synthesizing",
                personas=[self.registry.get("consensus-synthesizer")],
                context_text=self.context.content,
                upstream=[*planning, *critiques],
            )
            self._create_decision_manifest(syntheses)
            self.state.phase = "awaiting_human"
            self._write_gate_report(status="AWAITING_HUMAN")
            save_state(self.paths, self.state)
            publish_feature_outputs(self.paths)
            return self.paths
        except Exception as exc:
            self.state.phase = "failed"
            self.state.errors.append(self._safe_error_text(exc))
            save_state(self.paths, self.state)
            raise

    async def resume(self) -> RunPaths:
        self.paths = current_run_paths(self.context.project_root, self.context.feature_dir)
        self.state = load_state(self.paths)
        self._assert_run_matches_inputs()
        manifest = self._load_completed_manifest()

        try:
            master_plan = await self._compile_master_plan(manifest)
            validation_context = self._validation_context(master_plan, manifest)
            self.state.phase = "validating"
            save_state(self.paths, self.state)
            validators = await self._two_pass_stage(
                stage="validating",
                personas=[self.registry.get("architecture-validator")],
                context_text=validation_context,
            )
            self._aggregate_gate(validators, manifest)
            save_state(self.paths, self.state)
            publish_feature_outputs(self.paths)
            return self.paths
        except Exception as exc:
            self.state.phase = "failed"
            self.state.errors.append(self._safe_error_text(exc))
            save_state(self.paths, self.state)
            raise

    def _open_or_create_run(self, *, new_run: bool) -> tuple[RunPaths, RunState]:
        config_hash = self.config.stable_hash()
        if not new_run:
            try:
                existing = current_run_paths(self.context.project_root, self.context.feature_dir)
                state = load_state(existing)
                inputs_match = state.context_hash == self.context.content_hash
                config_matches = state.config_hash == config_hash
                if inputs_match and config_matches:
                    return existing, state
            except (FileNotFoundError, ValueError, ValidationError):
                pass

        paths = new_run_paths(self.context.feature_dir, self.context.content_hash, config_hash)
        state = RunState(
            run_id=paths.run_id,
            feature=self.context.feature,
            context_hash=self.context.content_hash,
            config_hash=config_hash,
        )
        write_yaml(paths.run_dir / "config-snapshot.yaml", self.config)
        write_json(
            paths.run_dir / "context-manifest.json",
            {
                "context_hash": self.context.content_hash,
                "files": [
                    {
                        "path": path.relative_to(self.context.project_root).as_posix(),
                        "sha256": sha256_text(path.read_text(encoding="utf-8")),
                    }
                    for path in self.context.files
                ],
            },
        )
        save_state(paths, state)
        return paths, state

    def _assert_run_matches_inputs(self) -> None:
        assert self.state
        if self.state.context_hash != self.context.content_hash:
            raise CouncilError(
                "architecture inputs changed after the council run; start a new architect run"
            )
        if self.state.config_hash != self.config.stable_hash():
            raise CouncilError(
                "participant configuration changed after the council run; start a new architect run"
            )

    async def _two_pass_stage(
        self,
        *,
        stage: str,
        personas: Sequence[PersonaDefinition],
        context_text: str,
        upstream: Sequence[ArtifactEnvelope] = (),
    ) -> list[ArtifactEnvelope]:
        independent = await self._run_batch(
            stage=stage,
            pass_kind="independent",
            personas=personas,
            context_text=context_text,
            upstream=upstream,
        )
        disclosed = await self._run_batch(
            stage=stage,
            pass_kind="disclosed",
            personas=personas,
            context_text=context_text,
            upstream=upstream,
            independent=independent,
        )
        return disclosed

    async def _run_batch(
        self,
        *,
        stage: str,
        pass_kind: str,
        personas: Sequence[PersonaDefinition],
        context_text: str,
        upstream: Sequence[ArtifactEnvelope],
        independent: Sequence[ArtifactEnvelope] = (),
    ) -> list[ArtifactEnvelope]:
        jobs = []
        for persona in personas:
            same_persona = [item for item in independent if item.persona == persona.id]
            for participant in self.config.enabled_participants:
                jobs.append(
                    self._persona_job(
                        stage=stage,
                        pass_kind=pass_kind,
                        persona=persona,
                        participant=participant,
                        context_text=context_text,
                        upstream=upstream,
                        independent=same_persona,
                    )
                )
        results = await asyncio.gather(*jobs, return_exceptions=True)
        artifacts: list[ArtifactEnvelope] = []
        required_failures: list[str] = []
        for result in results:
            if isinstance(result, _OptionalFailure):
                self._add_warning(result.message)
            elif isinstance(result, BaseException):
                required_failures.append(str(result))
            else:
                artifacts.append(result)
        if required_failures:
            raise CouncilError(
                f"required provider failure during {stage}/{pass_kind}: "
                + " | ".join(required_failures)
            )
        return sorted(artifacts, key=lambda item: (item.persona, item.participant_id))

    async def _persona_job(
        self,
        *,
        stage: str,
        pass_kind: str,
        persona: PersonaDefinition,
        participant: ParticipantConfig,
        context_text: str,
        upstream: Sequence[ArtifactEnvelope],
        independent: Sequence[ArtifactEnvelope],
    ) -> ArtifactEnvelope | _OptionalFailure:
        try:
            if pass_kind == "independent":
                prompt = independent_prompt(
                    persona,
                    stage,
                    context_text,
                    planning_artifacts=upstream,
                )
            else:
                prompt = disclosed_prompt(
                    persona,
                    stage,
                    context_text,
                    independent,
                    upstream_artifacts=upstream,
                )
            return await self._call_persona(
                stage=stage,
                pass_kind=pass_kind,
                persona=persona,
                participant=participant,
                user_prompt=prompt,
            )
        except Exception as exc:
            message = (
                f"{participant.id}/{persona.id}/{stage}/{pass_kind}: {type(exc).__name__}: {exc}"
            )
            if participant.required:
                raise CouncilError(message) from exc
            return _OptionalFailure(message)

    async def _call_persona(
        self,
        *,
        stage: str,
        pass_kind: str,
        persona: PersonaDefinition,
        participant: ParticipantConfig,
        user_prompt: str,
    ) -> ArtifactEnvelope:
        assert self.paths and self.state
        input_hash = self._input_hash(participant, SYSTEM_PROMPT, user_prompt, PersonaPayload)
        artifact_path = self.paths.artifact_path(stage, pass_kind, persona.id, participant.id)
        if artifact_path.exists():
            artifact = ArtifactEnvelope.model_validate(read_yaml(artifact_path))
            if artifact.input_hash != input_hash:
                raise CouncilError(
                    f"idempotency conflict for existing artifact {artifact.artifact_id}"
                )
            return artifact

        result, started_at, completed_at, exchanges, isolation = await self._generate_with_retry(
            participant=participant,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=PersonaPayload,
            stage=stage,
            pass_kind=pass_kind,
            persona=persona.id,
            input_hash=input_hash,
        )
        if not isinstance(result.parsed, PersonaPayload):
            raise CouncilError(f"{participant.id} returned the wrong payload type")
        self._scan_visible_io(user_prompt, result.visible_output)
        usage = self._priced_usage(participant, result.usage)
        artifact_id = f"{self.paths.run_id}:{stage}:{pass_kind}:{persona.id}:{participant.id}"
        transcript_path = self.paths.transcript_path(stage, pass_kind, persona.id, participant.id)
        transcript = Transcript(
            transcript_id=f"transcript:{artifact_id}",
            run_id=self.paths.run_id,
            stage=stage,
            pass_kind=pass_kind,
            persona=persona.id,
            participant_id=participant.id,
            transport=participant.transport,
            underlying_vendor=participant.underlying_vendor,
            requested_model=participant.model,
            resolved_model=result.resolved_model,
            request_id=result.request_id,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
            visible_system_prompt=SYSTEM_PROMPT,
            visible_user_prompt=user_prompt,
            visible_output=result.visible_output,
            input_hash=input_hash,
            output_hash=sha256_text(result.visible_output),
            isolation=isolation,
            usage=usage,
            exchanges=exchanges,
        )
        artifact = ArtifactEnvelope(
            artifact_id=artifact_id,
            run_id=self.paths.run_id,
            stage=stage,
            pass_kind=pass_kind,
            persona=persona.id,
            participant_id=participant.id,
            transport=participant.transport,
            underlying_vendor=participant.underlying_vendor,
            requested_model=participant.model,
            resolved_model=result.resolved_model,
            input_hash=input_hash,
            isolation=isolation,
            transcript_path=transcript_path.relative_to(self.context.project_root).as_posix(),
            payload=result.parsed,
        )
        if self.config.transcripts.commit_visible_io:
            write_json(transcript_path, transcript)
        write_yaml(artifact_path, artifact)
        await self._record_artifact(artifact_id, usage)
        return artifact

    async def _generate_with_retry(
        self,
        *,
        participant: ParticipantConfig,
        system_prompt: str,
        user_prompt: str,
        output_model: type[PersonaPayload] | type[MasterPlanPayload],
        stage: str,
        pass_kind: str,
        persona: str,
        input_hash: str,
    ):
        last_error: Exception | None = None
        first_attempt_number = self._next_attempt_number(stage, pass_kind, persona, participant.id)
        for attempt in range(self.config.limits.max_retries + 1):
            attempt_number = first_attempt_number + attempt
            await self._reserve_call()
            provider = build_provider(
                participant, timeout_seconds=self.config.limits.request_timeout_seconds
            )
            isolation = provider.begin_isolated_invocation(
                self._invocation_id(stage, pass_kind, persona, participant.id, attempt_number)
            )
            started_at = utc_now()
            try:
                async with self._semaphore:
                    result = await provider.generate(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        output_model=output_model,
                        project_root=str(self.context.project_root),
                        reserve_call=self._reserve_call,
                    )
                completed_at = utc_now()
                exchanges = self._result_exchanges(participant, user_prompt, result)
                self._write_call_attempt(
                    participant=participant,
                    stage=stage,
                    pass_kind=pass_kind,
                    persona=persona,
                    attempt_number=attempt_number,
                    started_at=started_at,
                    completed_at=completed_at,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    input_hash=input_hash,
                    isolation=isolation,
                    outcome="success",
                    retryable=False,
                    error=None,
                    exchanges=exchanges,
                )
                return result, started_at, completed_at, exchanges, isolation
            except ProviderError as exc:
                completed_at = utc_now()
                exchanges = self._error_exchanges(participant, user_prompt, exc)
                self._write_call_attempt(
                    participant=participant,
                    stage=stage,
                    pass_kind=pass_kind,
                    persona=persona,
                    attempt_number=attempt_number,
                    started_at=started_at,
                    completed_at=completed_at,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    input_hash=input_hash,
                    isolation=isolation,
                    outcome="error",
                    retryable=exc.retryable,
                    error=self._safe_error_text(exc),
                    exchanges=exchanges,
                )
                await self._record_failed_usage(exchanges)
                last_error = exc
                if not exc.retryable or attempt >= self.config.limits.max_retries:
                    raise
                await asyncio.sleep(min(2**attempt, 8))
        raise CouncilError(str(last_error or "provider call failed"))

    def _invocation_id(
        self,
        stage: str,
        pass_kind: str,
        persona: str,
        participant_id: str,
        attempt_number: int,
    ) -> str:
        assert self.paths
        return (
            f"invocation:{self.paths.run_id}:{stage}:{pass_kind}:{persona}:"
            f"{participant_id}:{attempt_number}:{uuid4().hex}"
        )

    def _next_attempt_number(
        self, stage: str, pass_kind: str, persona: str, participant_id: str
    ) -> int:
        assert self.paths
        parent = self.paths.transcripts / stage / pass_kind / persona
        return len(list(parent.glob(f"{participant_id}.attempt-*.json"))) + 1

    def _result_exchanges(
        self, participant: ParticipantConfig, user_prompt: str, result
    ) -> list[VisibleExchange]:
        exchanges = list(result.exchanges) or [
            VisibleExchange(
                kind="generate",
                visible_user_prompt=user_prompt,
                visible_output=result.visible_output,
                request_id=result.request_id,
                resolved_model=result.resolved_model,
                usage=result.usage,
            )
        ]
        return [
            exchange.model_copy(update={"usage": self._priced_usage(participant, exchange.usage)})
            for exchange in exchanges
        ]

    def _error_exchanges(
        self, participant: ParticipantConfig, user_prompt: str, error: ProviderError
    ) -> list[VisibleExchange]:
        exchanges = list(error.exchanges)
        if not exchanges:
            exchanges = [
                VisibleExchange(
                    kind="generate",
                    visible_user_prompt=user_prompt,
                    visible_output=error.visible_output or self._safe_error_text(error),
                    resolved_model=participant.model,
                    usage=error.usage,
                )
            ]
        return [
            exchange.model_copy(update={"usage": self._priced_usage(participant, exchange.usage)})
            for exchange in exchanges
        ]

    async def _record_failed_usage(self, exchanges: list[VisibleExchange]) -> None:
        assert self.paths and self.state
        usage = Usage(
            input_tokens=sum(exchange.usage.input_tokens for exchange in exchanges),
            output_tokens=sum(exchange.usage.output_tokens for exchange in exchanges),
            estimated_cost_usd=sum(exchange.usage.estimated_cost_usd for exchange in exchanges),
        )
        if not usage.input_tokens and not usage.output_tokens and not usage.estimated_cost_usd:
            return
        async with self._state_lock:
            self.state.usage.input_tokens += usage.input_tokens
            self.state.usage.output_tokens += usage.output_tokens
            self.state.usage.estimated_cost_usd += usage.estimated_cost_usd
            save_state(self.paths, self.state)
            budget_error = self._budget_error()
            if budget_error:
                raise CouncilError(budget_error)

    def _write_call_attempt(
        self,
        *,
        participant: ParticipantConfig,
        stage: str,
        pass_kind: str,
        persona: str,
        attempt_number: int,
        started_at,
        completed_at,
        system_prompt: str,
        user_prompt: str,
        input_hash: str,
        isolation: IsolationEvidence,
        outcome: str,
        retryable: bool,
        error: str | None,
        exchanges: list[VisibleExchange],
    ) -> None:
        assert self.paths
        for exchange in exchanges:
            self._scan_visible_io(exchange.visible_user_prompt, exchange.visible_output)
        attempt = CallAttemptTranscript(
            attempt_id=(
                f"attempt:{self.paths.run_id}:{stage}:{pass_kind}:{persona}:"
                f"{participant.id}:{attempt_number}"
            ),
            run_id=self.paths.run_id,
            stage=stage,
            pass_kind=pass_kind,
            persona=persona,
            participant_id=participant.id,
            transport=participant.transport,
            underlying_vendor=participant.underlying_vendor,
            requested_model=participant.model,
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
            outcome=outcome,
            retryable=retryable,
            error=error,
            visible_system_prompt=system_prompt,
            visible_user_prompt=user_prompt,
            input_hash=input_hash,
            isolation=isolation,
            exchanges=exchanges,
        )
        write_json(
            self.paths.attempt_path(stage, pass_kind, persona, participant.id, attempt_number),
            attempt,
        )

    async def _reserve_call(self) -> None:
        assert self.paths and self.state
        async with self._state_lock:
            budget_error = self._budget_error()
            if budget_error:
                raise CouncilError(budget_error)
            if self.state.call_count >= self.config.limits.max_calls_per_run:
                raise CouncilError("maximum provider calls for this run has been reached")
            self.state.call_count += 1
            save_state(self.paths, self.state)

    async def _record_artifact(self, artifact_id: str, usage: Usage) -> None:
        assert self.paths and self.state
        async with self._state_lock:
            self.state.usage.input_tokens += usage.input_tokens
            self.state.usage.output_tokens += usage.output_tokens
            self.state.usage.estimated_cost_usd += usage.estimated_cost_usd
            if artifact_id not in self.state.completed_artifact_ids:
                self.state.completed_artifact_ids.append(artifact_id)
            save_state(self.paths, self.state)
            budget_error = self._budget_error()
            if budget_error:
                raise CouncilError(budget_error)

    def _budget_error(self) -> str | None:
        assert self.state
        limits = self.config.limits
        if self.state.usage.input_tokens > limits.max_total_input_tokens:
            return "maximum input-token budget exceeded"
        if self.state.usage.output_tokens > limits.max_total_output_tokens:
            return "maximum output-token budget exceeded"
        if self.state.usage.estimated_cost_usd > limits.max_cost_usd:
            return "maximum estimated cost budget exceeded"
        return None

    def _priced_usage(self, participant: ParticipantConfig, usage: Usage) -> Usage:
        cost = (
            usage.input_tokens * participant.pricing.input_per_million_usd
            + usage.output_tokens * participant.pricing.output_per_million_usd
        ) / 1_000_000
        return usage.model_copy(update={"estimated_cost_usd": cost})

    def _input_hash(
        self,
        participant: ParticipantConfig,
        system_prompt: str,
        user_prompt: str,
        output_model: type[PersonaPayload] | type[MasterPlanPayload],
    ) -> str:
        return sha256_text(
            stable_json(
                {
                    "participant": participant.model_dump(mode="json", exclude={"pricing"}),
                    "system": system_prompt,
                    "user": user_prompt,
                    "schema": output_model.model_json_schema(mode="validation"),
                }
            )
        )

    def _scan_visible_io(self, user_prompt: str, output: str) -> None:
        if self.config.transcripts.secret_scan:
            assert_no_secrets(user_prompt, label="outgoing architecture prompt")
            assert_no_secrets(output, label="provider visible output")

    def _add_warning(self, warning: str) -> None:
        assert self.paths and self.state
        try:
            assert_no_secrets(warning, label="provider warning")
        except SecurityViolation as exc:
            raise CouncilError(
                "provider failure text contained a suspected secret and was not persisted"
            ) from exc
        if warning not in self.state.optional_warnings:
            self.state.optional_warnings.append(warning)
            save_state(self.paths, self.state)

    @staticmethod
    def _safe_error_text(error: Exception) -> str:
        message = str(error)
        try:
            assert_no_secrets(message, label="provider error")
        except SecurityViolation:
            return "provider error contained a suspected secret; content was not persisted"
        return message

    def _create_decision_manifest(self, syntheses: Sequence[ArtifactEnvelope]) -> DecisionManifest:
        assert self.paths
        if self.paths.decision_manifest.exists():
            return DecisionManifest.model_validate(read_yaml(self.paths.decision_manifest))
        options: list[DecisionOption] = []
        seen: set[str] = set()
        for artifact in syntheses:
            option_count_before = len(options)
            for proposal in artifact.payload.decisions:
                option_id = f"{artifact.artifact_id}::{proposal.proposal_id}"
                if option_id in seen:
                    continue
                seen.add(option_id)
                options.append(
                    DecisionOption(
                        proposal_id=option_id,
                        statement=proposal.statement,
                        rationale=proposal.rationale,
                        source_artifact_ids=[
                            artifact.artifact_id,
                            *proposal.source_artifact_ids,
                        ],
                    )
                )
            if len(options) == option_count_before:
                option_id = f"{artifact.artifact_id}::synthesis-position"
                disposition = (
                    f"Accepted: {artifact.payload.accepted_proposal_ids or ['none stated']}; "
                    f"Rejected: {artifact.payload.rejected_proposal_ids or ['none stated']}; "
                    f"Unresolved: {artifact.payload.unresolved_decisions or ['none stated']}."
                )
                options.append(
                    DecisionOption(
                        proposal_id=option_id,
                        statement=artifact.payload.summary,
                        rationale=disposition,
                        source_artifact_ids=[artifact.artifact_id],
                    )
                )
        conflicts = (
            [
                DecisionConflict(
                    conflict_id="architecture-decisions",
                    question=(
                        "Which synthesis proposals should become authoritative? "
                        "Select one or more proposal IDs."
                    ),
                    options=options,
                )
            ]
            if options
            else []
        )
        manifest = DecisionManifest(
            run_id=self.paths.run_id,
            instructions=[
                "Review every option and the cited run artifacts.",
                "For each conflict, add one selection with selected_proposal_ids and rationale.",
                "Set status to approved, decided_by, and decided_at; do not change run_id.",
                "Use status exception only after validator disagreement and record the "
                "blocking validator artifact IDs, reason, approver, and timestamp.",
            ],
            conflicts=conflicts,
        )
        write_yaml(self.paths.decision_manifest, manifest)
        return manifest

    def _load_completed_manifest(self) -> DecisionManifest:
        assert self.paths
        try:
            manifest = DecisionManifest.model_validate(read_yaml(self.paths.decision_manifest))
        except FileNotFoundError as exc:
            raise CouncilError("human decision manifest is missing; run architect first") from exc
        if manifest.run_id != self.paths.run_id:
            raise CouncilError("decision manifest run_id does not match the active run")
        if manifest.status == "pending":
            raise CouncilError(
                f"human decision required in {self.paths.decision_manifest} before resume"
            )
        return manifest

    async def _compile_master_plan(self, manifest: DecisionManifest) -> MasterPlan:
        assert self.paths and self.state
        normalized_manifest = manifest.model_dump(mode="json", exclude={"exceptions", "status"})
        normalized_manifest["status"] = "approved"
        syntheses = self._load_artifacts("synthesizing", "disclosed")
        prompt = compile_prompt(
            self.context.content,
            syntheses,
            yaml.safe_dump(normalized_manifest, sort_keys=False),
        )
        codex = next(p for p in self.config.required_participants if p.id == "codex")
        input_hash = self._input_hash(codex, SYSTEM_PROMPT, prompt, MasterPlanPayload)
        if self.paths.master_plan.exists():
            master = MasterPlan.model_validate(read_yaml(self.paths.master_plan))
            if master.input_hash != input_hash:
                raise CouncilError(
                    "human architecture selections changed after compilation; "
                    "start a new council run"
                )
            self._write_adr_log(master)
            return master

        self.state.phase = "compiling"
        save_state(self.paths, self.state)
        result, started_at, completed_at, exchanges, isolation = await self._generate_with_retry(
            participant=codex,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            output_model=MasterPlanPayload,
            stage="compiling",
            pass_kind="compile",
            persona="consensus-compiler",
            input_hash=input_hash,
        )
        if not isinstance(result.parsed, MasterPlanPayload):
            raise CouncilError("Codex returned the wrong master-plan payload type")
        self._scan_visible_io(prompt, result.visible_output)
        usage = self._priced_usage(codex, result.usage)
        transcript_path = self.paths.transcript_path("compiling", "compile", "master-plan", "codex")
        transcript = Transcript(
            transcript_id=f"transcript:{self.paths.run_id}:master-plan:codex",
            run_id=self.paths.run_id,
            stage="compiling",
            pass_kind="compile",
            persona="consensus-compiler",
            participant_id="codex",
            transport=codex.transport,
            underlying_vendor=codex.underlying_vendor,
            requested_model=codex.model,
            resolved_model=result.resolved_model,
            request_id=result.request_id,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
            visible_system_prompt=SYSTEM_PROMPT,
            visible_user_prompt=prompt,
            visible_output=result.visible_output,
            input_hash=input_hash,
            output_hash=sha256_text(result.visible_output),
            isolation=isolation,
            usage=usage,
            exchanges=exchanges,
        )
        master = MasterPlan(
            master_plan_id=f"{self.paths.run_id}:master-plan",
            run_id=self.paths.run_id,
            decision_manifest_path=self.paths.decision_manifest.relative_to(
                self.context.project_root
            ).as_posix(),
            input_hash=input_hash,
            payload=result.parsed,
        )
        if self.config.transcripts.commit_visible_io:
            write_json(transcript_path, transcript)
        write_yaml(self.paths.master_plan, master)
        self._write_adr_log(master)
        await self._record_artifact(master.master_plan_id, usage)
        return master

    def _write_adr_log(self, master: MasterPlan) -> None:
        assert self.paths
        records: list[ArchitectureDecisionRecord] = []
        for status, decisions in (
            ("accepted", master.payload.accepted_decisions),
            ("rejected", master.payload.rejected_decisions),
        ):
            for index, decision in enumerate(decisions, start=1):
                records.append(
                    ArchitectureDecisionRecord(
                        adr_id=f"ADR-{status.upper()}-{index:03d}",
                        status=status,
                        statement=decision.statement,
                        rationale=decision.rationale,
                        requirement_ids=decision.requirement_ids,
                        source_artifact_ids=decision.source_artifact_ids,
                        tradeoffs=decision.tradeoffs,
                    )
                )
        write_yaml(
            self.paths.adr_log,
            AdrLog(run_id=self.paths.run_id, records=records),
        )

    def _load_artifacts(self, stage: str, pass_kind: str) -> list[ArtifactEnvelope]:
        assert self.paths
        root = self.paths.artifacts / stage / pass_kind
        if not root.exists():
            return []
        return sorted(
            (ArtifactEnvelope.model_validate(read_yaml(path)) for path in root.rglob("*.yaml")),
            key=lambda item: (item.persona, item.participant_id),
        )

    def _validation_context(self, master_plan: MasterPlan, manifest: DecisionManifest) -> str:
        review_manifest = manifest.model_dump(mode="json", exclude={"exceptions", "status"})
        review_manifest["status"] = "approved"
        content = (
            self.context.content
            + "\n===== BEGIN AUTHORITATIVE MASTER PLAN =====\n"
            + yaml.safe_dump(master_plan.model_dump(mode="json"), sort_keys=False)
            + "===== END AUTHORITATIVE MASTER PLAN =====\n"
            + "\n===== BEGIN HUMAN DECISION MANIFEST =====\n"
            + yaml.safe_dump(review_manifest, sort_keys=False)
            + "===== END HUMAN DECISION MANIFEST =====\n"
        )
        if self.config.transcripts.secret_scan:
            assert_no_secrets(content, label="validator architecture context")
        return content

    def _aggregate_gate(
        self,
        validators: Sequence[ArtifactEnvelope],
        manifest: DecisionManifest,
    ) -> GateReport:
        assert self.paths and self.state
        final_by_participant = {item.participant_id: item for item in validators}
        missing = [
            participant.id
            for participant in self.config.required_participants
            if participant.id not in final_by_participant
        ]
        if missing:
            raise CouncilError("required validator output missing: " + ", ".join(sorted(missing)))
        ready = sorted(
            participant_id
            for participant_id, artifact in final_by_participant.items()
            if artifact.payload.verdict == Verdict.READY
        )
        blocked = sorted(
            participant.id
            for participant in self.config.required_participants
            if final_by_participant[participant.id].payload.verdict != Verdict.READY
        )
        blocking_artifact_ids = [
            final_by_participant[participant_id].artifact_id for participant_id in blocked
        ]
        required_ids = {participant.id for participant in self.config.required_participants}
        for participant_id, artifact in final_by_participant.items():
            if participant_id not in required_ids and artifact.payload.verdict != Verdict.READY:
                self._add_warning(
                    f"optional validator {participant_id} returned "
                    f"{artifact.payload.verdict.value} in {artifact.artifact_id}"
                )
        exception_ids = {
            artifact_id
            for exception in manifest.exceptions
            for artifact_id in exception.validator_artifact_ids
        }
        exception_applied = (
            bool(blocked)
            and manifest.status == "exception"
            and set(blocking_artifact_ids).issubset(exception_ids)
        )
        if manifest.status == "exception" and blocked and not exception_applied:
            raise CouncilError(
                "human exception does not reference every blocking required-validator artifact"
            )
        status = "READY" if not blocked or exception_applied else "BLOCKED"
        independent_by_participant = {
            artifact.participant_id: artifact
            for artifact in self._load_artifacts("validating", "independent")
        }
        missing_isolation = sorted(required_ids - set(independent_by_participant))
        if missing_isolation:
            raise CouncilError(
                "required independent validator isolation evidence missing: "
                + ", ".join(missing_isolation)
            )
        validator_isolation = [
            GateIsolationRecord(
                participant_id=participant_id,
                independent_invocation_id=independent_by_participant[
                    participant_id
                ].isolation.invocation_id,
                disclosed_invocation_id=artifact.isolation.invocation_id,
            )
            for participant_id, artifact in sorted(final_by_participant.items())
            if participant_id in independent_by_participant
        ]
        report = self._write_gate_report(
            status=status,
            ready=ready,
            blocked=blocked,
            validator_ids=[artifact.artifact_id for artifact in validators],
            validator_isolation=validator_isolation,
            exception_applied=exception_applied,
        )
        self.state.phase = "ready" if status == "READY" else "blocked"
        return report

    def _write_gate_report(
        self,
        *,
        status: str,
        ready: Iterable[str] = (),
        blocked: Iterable[str] = (),
        validator_ids: Iterable[str] = (),
        validator_isolation: Iterable[GateIsolationRecord] = (),
        exception_applied: bool = False,
    ) -> GateReport:
        assert self.paths and self.state
        report = GateReport(
            run_id=self.paths.run_id,
            feature=self.context.feature,
            status=status,
            required_participants=[p.id for p in self.config.required_participants],
            ready_participants=list(ready),
            blocked_participants=list(blocked),
            optional_warnings=self.state.optional_warnings,
            validator_artifact_ids=list(validator_ids),
            validator_isolation=list(validator_isolation),
            exception_applied=exception_applied,
            decision_manifest_path=self.paths.decision_manifest.relative_to(
                self.context.project_root
            ).as_posix(),
            master_plan_path=(
                self.paths.master_plan.relative_to(self.context.project_root).as_posix()
                if self.paths.master_plan.exists()
                else None
            ),
        )
        write_yaml(self.paths.gate_report, report)
        return report


class _OptionalFailure:
    def __init__(self, message: str) -> None:
        self.message = message


def gate_status(project_root: Path, feature_dir: Path) -> GateReport:
    paths = current_run_paths(project_root, feature_dir)
    try:
        return GateReport.model_validate(read_yaml(paths.gate_report))
    except FileNotFoundError as exc:
        raise CouncilError("architecture gate report does not exist") from exc


def verify_ready_gate(
    project_root: Path,
    feature_dir: Path,
    config: CouncilConfig,
    context_hash: str,
) -> GateReport:
    paths = current_run_paths(project_root, feature_dir)
    state = load_state(paths)
    if state.context_hash != context_hash:
        raise CouncilError("architecture gate is stale because Spec Kit inputs changed")
    if state.config_hash != config.stable_hash():
        raise CouncilError("architecture gate is stale because council configuration changed")
    errors = validate_run_offline(project_root, feature_dir)
    if errors:
        raise CouncilError("invalid architecture evidence: " + " | ".join(errors))
    report = gate_status(project_root, feature_dir)
    required_ids = {participant.id for participant in config.required_participants}
    if set(report.required_participants) != required_ids:
        raise CouncilError("gate report required-participant set does not match configuration")
    manifest = DecisionManifest.model_validate(read_yaml(paths.decision_manifest))
    validators = {
        artifact.participant_id: artifact
        for artifact in _read_artifact_tree(paths.artifacts / "validating" / "disclosed")
    }
    missing = sorted(required_ids - set(validators))
    if missing:
        raise CouncilError("required validator evidence is missing: " + ", ".join(missing))
    blocking = [
        validators[participant_id].artifact_id
        for participant_id in required_ids
        if validators[participant_id].payload.verdict != Verdict.READY
    ]
    exception_ids = {
        artifact_id
        for exception in manifest.exceptions
        for artifact_id in exception.validator_artifact_ids
    }
    exception_valid = (
        bool(blocking) and manifest.status == "exception" and set(blocking).issubset(exception_ids)
    )
    if blocking and not exception_valid:
        raise CouncilError("required validator disagreement has no complete human exception")
    if report.status != "READY":
        raise CouncilError(f"architecture gate is {report.status}")
    if report.exception_applied != exception_valid:
        raise CouncilError("gate report exception state does not match the decision manifest")
    return report


def _read_artifact_tree(root: Path) -> list[ArtifactEnvelope]:
    if not root.exists():
        return []
    return [
        ArtifactEnvelope.model_validate(read_yaml(path)) for path in sorted(root.rglob("*.yaml"))
    ]


def validate_run_offline(project_root: Path, feature_dir: Path) -> list[str]:
    paths = current_run_paths(project_root, feature_dir)
    state = load_state(paths)
    errors: list[str] = []
    snapshot = CouncilConfig.model_validate(read_yaml(paths.run_dir / "config-snapshot.yaml"))
    manifest: DecisionManifest | None = None
    try:
        manifest = DecisionManifest.model_validate(read_yaml(paths.decision_manifest))
        if manifest.run_id != state.run_id:
            errors.append("decision manifest run_id does not match state")
    except (FileNotFoundError, ValidationError, ValueError) as exc:
        errors.append(f"invalid decision manifest: {exc}")
    artifacts: list[ArtifactEnvelope] = []
    artifact_invocation_ids: set[str] = set()
    for path in paths.artifacts.rglob("*.yaml") if paths.artifacts.exists() else ():
        try:
            artifact = ArtifactEnvelope.model_validate(read_yaml(path))
            artifacts.append(artifact)
            if artifact.run_id != state.run_id:
                errors.append(f"artifact has wrong run_id: {path}")
            invocation_id = artifact.isolation.invocation_id
            if invocation_id in artifact_invocation_ids:
                errors.append(f"artifact reuses an inference invocation: {path}")
            artifact_invocation_ids.add(invocation_id)
            transcript = project_root / artifact.transcript_path
            if not transcript.exists():
                errors.append(f"artifact transcript is missing: {artifact.transcript_path}")
            else:
                transcript_data = Transcript.model_validate_json(
                    transcript.read_text(encoding="utf-8")
                )
                if transcript_data.input_hash != artifact.input_hash:
                    errors.append(f"artifact/transcript input hash mismatch: {path}")
                if transcript_data.isolation != artifact.isolation:
                    errors.append(f"artifact/transcript isolation mismatch: {path}")
        except (ValidationError, ValueError) as exc:
            errors.append(f"invalid artifact {path}: {exc}")

    required_ids = {participant.id for participant in snapshot.required_participants}
    validator_artifacts = {
        (artifact.pass_kind, artifact.participant_id): artifact
        for artifact in artifacts
        if artifact.stage == "validating" and artifact.persona == "architecture-validator"
    }
    if state.phase in {"ready", "blocked"}:
        for participant_id in sorted(required_ids):
            independent = validator_artifacts.get(("independent", participant_id))
            disclosed = validator_artifacts.get(("disclosed", participant_id))
            if independent is None or disclosed is None:
                errors.append(
                    f"required validator fresh-context evidence is incomplete: {participant_id}"
                )
            elif independent.isolation.invocation_id == disclosed.isolation.invocation_id:
                errors.append(
                    f"validator passes reuse an inference invocation: {participant_id}"
                )

    attempt_invocation_ids: set[str] = set()
    adapter_instance_ids: set[str] = set()
    successful_invocation_ids: set[str] = set()
    final_transcripts: list[tuple[Path, Transcript]] = []
    for path in paths.transcripts.rglob("*.json") if paths.transcripts.exists() else ():
        try:
            if ".attempt-" in path.name:
                attempt = CallAttemptTranscript.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if attempt.run_id != state.run_id:
                    errors.append(f"attempt transcript has wrong run_id: {path}")
                invocation_id = attempt.isolation.invocation_id
                adapter_instance_id = attempt.isolation.adapter_instance_id
                if invocation_id in attempt_invocation_ids:
                    errors.append(f"attempt reuses an inference invocation: {path}")
                attempt_invocation_ids.add(invocation_id)
                if adapter_instance_id in adapter_instance_ids:
                    errors.append(f"attempt reuses a provider adapter instance: {path}")
                adapter_instance_ids.add(adapter_instance_id)
                if attempt.outcome == "success":
                    successful_invocation_ids.add(invocation_id)
                for exchange in attempt.exchanges:
                    if exchange.input_hash != sha256_text(exchange.visible_user_prompt):
                        errors.append(f"attempt exchange input hash mismatch: {path}")
                    if exchange.output_hash != sha256_text(exchange.visible_output):
                        errors.append(f"attempt exchange output hash mismatch: {path}")
                assert_no_secrets(path.read_text(encoding="utf-8"), label=str(path))
                continue
            transcript = Transcript.model_validate_json(path.read_text(encoding="utf-8"))
            final_transcripts.append((path, transcript))
            if transcript.run_id != state.run_id:
                errors.append(f"transcript has wrong run_id: {path}")
            if transcript.input_hash != sha256_text(
                stable_json(
                    {
                        "participant": next(
                            (
                                p.model_dump(mode="json", exclude={"pricing"})
                                for p in snapshot.enabled_participants
                                if p.id == transcript.participant_id
                            ),
                            {},
                        ),
                        "system": transcript.visible_system_prompt,
                        "user": transcript.visible_user_prompt,
                        "schema": (
                            MasterPlanPayload.model_json_schema(mode="validation")
                            if transcript.pass_kind == "compile"
                            else PersonaPayload.model_json_schema(mode="validation")
                        ),
                    }
                )
            ):
                errors.append(f"transcript input hash mismatch: {path}")
            if transcript.output_hash != sha256_text(transcript.visible_output):
                errors.append(f"transcript output hash mismatch: {path}")
            for exchange in transcript.exchanges:
                if exchange.input_hash != sha256_text(exchange.visible_user_prompt):
                    errors.append(f"transcript exchange input hash mismatch: {path}")
                if exchange.output_hash != sha256_text(exchange.visible_output):
                    errors.append(f"transcript exchange output hash mismatch: {path}")
            assert_no_secrets(path.read_text(encoding="utf-8"), label=str(path))
        except (ValidationError, ValueError) as exc:
            errors.append(f"invalid transcript {path}: {exc}")
    final_invocation_ids: set[str] = set()
    for path, transcript in final_transcripts:
        invocation_id = transcript.isolation.invocation_id
        if invocation_id in final_invocation_ids:
            errors.append(f"final transcript reuses an inference invocation: {path}")
        final_invocation_ids.add(invocation_id)
        if invocation_id not in successful_invocation_ids:
            errors.append(f"final transcript lacks a successful isolated attempt: {path}")
    if paths.master_plan.exists():
        try:
            master = MasterPlan.model_validate(read_yaml(paths.master_plan))
            if master.run_id != state.run_id:
                errors.append("master plan run_id does not match state")
        except (ValidationError, ValueError) as exc:
            errors.append(f"invalid master plan: {exc}")
    if paths.adr_log.exists():
        try:
            adr_log = AdrLog.model_validate(read_yaml(paths.adr_log))
            if adr_log.run_id != state.run_id:
                errors.append("ADR log run_id does not match state")
        except (ValidationError, ValueError) as exc:
            errors.append(f"invalid ADR log: {exc}")
    if paths.gate_report.exists():
        try:
            report = GateReport.model_validate(read_yaml(paths.gate_report))
            if report.run_id != state.run_id:
                errors.append("gate report run_id does not match state")
            if report.status == "READY" and (
                not paths.master_plan.exists() or not paths.adr_log.exists()
            ):
                errors.append("READY gate requires a master plan and ADR log")
            expected_isolation = {
                participant_id: (
                    validator_artifacts[("independent", participant_id)].isolation.invocation_id,
                    validator_artifacts[("disclosed", participant_id)].isolation.invocation_id,
                )
                for participant_id in required_ids
                if ("independent", participant_id) in validator_artifacts
                and ("disclosed", participant_id) in validator_artifacts
            }
            reported_isolation = {
                record.participant_id: (
                    record.independent_invocation_id,
                    record.disclosed_invocation_id,
                )
                for record in report.validator_isolation
                if record.participant_id in required_ids
            }
            if report.status in {"READY", "BLOCKED"} and reported_isolation != expected_isolation:
                errors.append("gate report validator isolation evidence does not match artifacts")
        except (ValidationError, ValueError) as exc:
            errors.append(f"invalid gate report: {exc}")
    return errors
