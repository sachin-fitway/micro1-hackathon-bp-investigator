"""LLM client with fair-comparison contract (Google Gemini or OpenRouter)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

T = TypeVar("T", bound=BaseModel)

MAX_PARSE_RETRIES = 2
MAX_TRANSIENT_RETRIES = 5
TRANSIENT_BACKOFF_SECONDS = 2.0
OPENROUTER_PAYMENT_RETRY_SECONDS = 120.0
DEFAULT_MODEL = "gemini-flash-latest"
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

OPENROUTER_MODEL_MAP = {
    "gemini-flash-latest": DEFAULT_OPENROUTER_MODEL,
    "gemini-2.5-flash": "google/gemini-2.5-flash",
    "gemini-2.0-flash": "google/gemini-2.0-flash-001",
}


@dataclass
class LlmConfig:
    provider: Literal["gemini", "openrouter"]
    api_key: str
    model: str
    max_output_tokens: int


@dataclass
class LlmCallRecord:
    provider: str
    model: str
    max_output_tokens: int
    input_token_estimate: int
    stage: str


@dataclass
class LlmCallResult:
    parsed: BaseModel
    raw_response: str
    retry_count: int


@dataclass
class LlmAuditLog:
    calls: list[LlmCallRecord] = field(default_factory=list)

    def record(self, record: LlmCallRecord) -> None:
        self.calls.append(record)


def getOpenRouterKey() -> str:
    return (
        os.getenv("OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPEN_ROUTER_API_KEY", "").strip()
    )


def resolveProvider(explicitProvider: str) -> Literal["gemini", "openrouter"]:
    normalized = explicitProvider.strip().lower()
    openrouterKey = getOpenRouterKey()
    geminiKey = os.getenv("GEMINI_API_KEY", "").strip()

    if normalized == "openrouter":
        return "openrouter"
    if normalized == "gemini":
        return "gemini"
    if openrouterKey:
        return "openrouter"
    if geminiKey:
        return "gemini"
    return "gemini"


def resolveOpenRouterModel(model: str) -> str:
    explicit = os.getenv("OPENROUTER_MODEL", "").strip()
    if explicit:
        return explicit
    if model.startswith("google/"):
        return model
    return OPENROUTER_MODEL_MAP.get(model, f"google/{model}")


def loadLlmConfig() -> LlmConfig:
    provider = resolveProvider(os.getenv("LLM_PROVIDER", ""))
    maxOutputTokens = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))

    if provider == "openrouter":
        apiKey = getOpenRouterKey()
        geminiModel = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        model = resolveOpenRouterModel(geminiModel)
        if not apiKey:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        return LlmConfig(
            provider="openrouter",
            api_key=apiKey,
            model=model,
            max_output_tokens=maxOutputTokens,
        )

    apiKey = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    if not apiKey:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return LlmConfig(
        provider="gemini",
        api_key=apiKey,
        model=model,
        max_output_tokens=maxOutputTokens,
    )


def estimateTokens(text: str) -> int:
    return max(1, len(text) // 4)


def buildGenerationConfig(config: LlmConfig) -> dict[str, Any]:
    """Return generation settings (used in tests and client config)."""
    return {
        "temperature": 0,
        "max_output_tokens": config.max_output_tokens,
        "response_mime_type": "application/json",
    }


def parseStructuredResponse(responseText: str, modelClass: type[T]) -> T:
    cleaned = responseText.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    payload = json.loads(cleaned)
    if isinstance(payload, dict):
        payload = _unwrapModelPayload(payload, modelClass)
    return modelClass.model_validate(payload)


def _unwrapModelPayload(payload: dict[str, Any], modelClass: type[BaseModel]) -> dict[str, Any]:
    requiredFields = set(modelClass.model_fields.keys())
    if requiredFields.issubset(payload.keys()):
        return payload

    nestedKeys = (
        "investigation_result",
        "investigation",
        "result",
        "diagnosis",
        "output",
        "analysis",
    )
    for key in nestedKeys:
        nested = payload.get(key)
        if isinstance(nested, dict):
            unwrapped = _unwrapModelPayload(nested, modelClass)
            if requiredFields.issubset(unwrapped.keys()):
                return unwrapped

    for value in payload.values():
        if isinstance(value, dict):
            unwrapped = _unwrapModelPayload(value, modelClass)
            if requiredFields.issubset(unwrapped.keys()):
                return unwrapped

    return payload


JSON_OBJECT_OPENROUTER_MODELS = frozenset(
    {"HypothesisBoard", "AdversarialVerificationOutcome", "VerifierAdjudicationOutcome"}
)


def _buildOpenRouterResponseFormat(modelClass: type[BaseModel]) -> dict[str, Any]:
    if modelClass.__name__ in JSON_OBJECT_OPENROUTER_MODELS:
        return {"type": "json_object"}
    schema = modelClass.model_json_schema()
    schema["additionalProperties"] = False
    return {
        "type": "json_schema",
        "json_schema": {
            "name": modelClass.__name__,
            "strict": True,
            "schema": schema,
        },
    }


def assertFairComparisonParity(logA: LlmAuditLog, logB: LlmAuditLog) -> None:
    if not logA.calls or not logB.calls:
        return
    modelsA = {call.model for call in logA.calls}
    modelsB = {call.model for call in logB.calls}
    tokensA = {call.max_output_tokens for call in logA.calls}
    tokensB = {call.max_output_tokens for call in logB.calls}
    if modelsA != modelsB:
        raise ValueError(f"Model mismatch across workflows: {modelsA} vs {modelsB}")
    if tokensA != tokensB:
        raise ValueError(f"Token budget mismatch across workflows: {tokensA} vs {tokensB}")


def _isTransientError(statusCode: int) -> bool:
    return statusCode in {402, 429, 500, 502, 503, 504}


def _retryDelaySeconds(statusCode: int, attempt: int, retryAfterHeader: str | None = None) -> float:
    if retryAfterHeader:
        try:
            return max(float(retryAfterHeader), TRANSIENT_BACKOFF_SECONDS)
        except ValueError:
            pass
    if statusCode == 402:
        return OPENROUTER_PAYMENT_RETRY_SECONDS
    if statusCode == 429:
        return max(60.0, TRANSIENT_BACKOFF_SECONDS * (2**attempt))
    return TRANSIENT_BACKOFF_SECONDS * (2**attempt)


def _extractStatusCode(error: Exception) -> int:
    statusCode = getattr(error, "status_code", None) or getattr(error, "code", 0)
    try:
        return int(statusCode)
    except (TypeError, ValueError):
        return 0


def _geminiGenerate(config: LlmConfig, prompt: str, modelClass: type[BaseModel]) -> str:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError, ClientError, ServerError

    client = genai.Client(api_key=config.api_key)
    generationConfig = types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=config.max_output_tokens,
        response_mime_type="application/json",
        response_schema=modelClass,
    )
    lastError: Exception | None = None
    for attempt in range(MAX_TRANSIENT_RETRIES):
        try:
            response = client.models.generate_content(
                model=config.model,
                contents=prompt,
                config=generationConfig,
            )
            return response.text or ""
        except (APIError, ClientError, ServerError) as error:
            lastError = error
            statusCode = _extractStatusCode(error)
            if _isTransientError(statusCode) and attempt < MAX_TRANSIENT_RETRIES - 1:
                time.sleep(_retryDelaySeconds(statusCode, attempt))
                continue
            raise
    raise RuntimeError(f"Gemini request failed after retries: {lastError}")


def _openrouterGenerate(config: LlmConfig, prompt: str, modelClass: type[BaseModel]) -> str:
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": config.max_output_tokens,
        "response_format": _buildOpenRouterResponseFormat(modelClass),
        "provider": {"require_parameters": True},
        "plugins": [{"id": "response-healing"}],
    }
    requestData = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_API_URL,
        data=requestData,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/micro1-hackathon-bp-investigator",
            "X-Title": "BP Failure Investigator",
        },
        method="POST",
    )
    lastError: Exception | None = None
    for attempt in range(MAX_TRANSIENT_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
            choices = body.get("choices") or []
            if not choices:
                raise RuntimeError(f"OpenRouter returned no choices: {body}")
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            if not content:
                raise RuntimeError(f"OpenRouter returned empty content: {body}")
            return content
        except urllib.error.HTTPError as error:
            lastError = error
            retryAfter = error.headers.get("Retry-After") if error.headers else None
            if _isTransientError(error.code) and attempt < MAX_TRANSIENT_RETRIES - 1:
                delay = _retryDelaySeconds(error.code, attempt, retryAfter)
                time.sleep(delay)
                continue
            errorBody = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {error.code}: {errorBody}") from error
        except urllib.error.URLError as error:
            lastError = error
            if attempt < MAX_TRANSIENT_RETRIES - 1:
                time.sleep(TRANSIENT_BACKOFF_SECONDS * (2**attempt))
                continue
            raise RuntimeError(f"OpenRouter network error: {error}") from error
    raise RuntimeError(f"OpenRouter request failed after retries: {lastError}")


def _generateRaw(config: LlmConfig, prompt: str, modelClass: type[BaseModel]) -> str:
    if config.provider == "openrouter":
        return _openrouterGenerate(config, prompt, modelClass)
    return _geminiGenerate(config, prompt, modelClass)


class GeminiClient:
    """Shared LLM client for baseline and agent workflows."""

    def __init__(self, config: LlmConfig | None = None, auditLog: LlmAuditLog | None = None):
        self.config = config or loadLlmConfig()
        self.auditLog = auditLog or LlmAuditLog()

    def completeJson(
        self,
        prompt: str,
        modelClass: type[T],
        stage: str = "unknown",
    ) -> LlmCallResult:
        lastError: Exception | None = None
        rawResponse = ""
        currentPrompt = prompt
        for attempt in range(MAX_PARSE_RETRIES + 1):
            self.auditLog.record(
                LlmCallRecord(
                    provider=self.config.provider,
                    model=self.config.model,
                    max_output_tokens=self.config.max_output_tokens,
                    input_token_estimate=estimateTokens(currentPrompt),
                    stage=stage,
                )
            )
            rawResponse = _generateRaw(self.config, currentPrompt, modelClass)
            try:
                parsed = parseStructuredResponse(rawResponse, modelClass)
                return LlmCallResult(parsed=parsed, raw_response=rawResponse, retry_count=attempt)
            except (ValidationError, json.JSONDecodeError) as error:
                lastError = error
                currentPrompt = (
                    f"{prompt}\n\nPrevious response was invalid JSON/schema. "
                    f"Return valid JSON only. Error: {error}"
                )
        raise RuntimeError(f"Failed to parse LLM response after retries: {lastError}")


def serializePromptPayload(payload: BaseModel) -> str:
    return json.dumps(payload.model_dump(mode="json"), indent=2)
