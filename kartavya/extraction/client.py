"""Ollama wrapper — JSON mode, schema validation, prompt SHA, single retry on parse failure (§3.6, §10.1)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

import ollama  # type: ignore[import-untyped]
import structlog
from pydantic import BaseModel, ValidationError

from kartavya.errors import ExtractionFailed

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "llama3.1:8b-instruct-q4_K_M"
DEFAULT_NUM_CTX = 16384
DEFAULT_NUM_PREDICT = 8192

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CallMetadata:
    """Provenance for one Ollama call. Used by the validator to build `ExtractionProvenance`."""

    prompt_sha: str
    model_id: str
    temperature: float
    extracted_at: datetime


class OllamaClient:
    """Thin wrapper around the `ollama` package. Stateful only by Ollama-host config (§9)."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str | None = None,
        num_ctx: int = DEFAULT_NUM_CTX,
        num_predict: int = DEFAULT_NUM_PREDICT,
    ) -> None:
        self.model = model
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self._client = ollama.Client(host=host) if host else ollama.Client()

    def generate_json(
        self,
        prompt: str,
        schema: type[T],
        *,
        temperature: float = 0.0,
    ) -> tuple[T, CallMetadata]:
        """Run one JSON-mode generation and validate against `schema`.

        On `ValidationError` retries once at temperature 0; if the retry also
        fails, raises `ExtractionFailed` with the prompt SHA and raw response
        attached for audit/debug. Never returns silently with defaults.
        """
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        last_error: Exception | None = None
        last_raw: str | None = None
        for attempt in (1, 2):
            attempt_temp = temperature if attempt == 1 else 0.0
            try:
                response = self._client.generate(
                    model=self.model,
                    prompt=prompt,
                    format="json",
                    options={
                        "temperature": attempt_temp,
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                    },
                )
                raw_response = response["response"]
                if not isinstance(raw_response, str):
                    raise ExtractionFailed(
                        f"Ollama returned non-string response: {type(raw_response).__name__}"
                    )
                last_raw = raw_response
                parsed = schema.model_validate_json(last_raw)
                return parsed, CallMetadata(
                    prompt_sha=prompt_sha,
                    model_id=self.model,
                    temperature=attempt_temp,
                    extracted_at=datetime.now(timezone.utc),
                )
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                _log.warning(
                    "ollama_parse_failure",
                    attempt=attempt,
                    prompt_sha=prompt_sha,
                    error=str(exc),
                    raw_preview=(last_raw or "")[:500],
                )

        raise ExtractionFailed(
            f"schema validation failed after retry "
            f"(prompt_sha={prompt_sha[:12]}, schema={schema.__name__}): {last_error}"
        )
