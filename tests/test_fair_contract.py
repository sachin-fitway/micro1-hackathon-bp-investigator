"""Tests for fair LLM comparison contract."""

from __future__ import annotations

import json

import pytest

from generate_data import buildCases
from shared.case_loader import assertLlmPayloadIsClean, serializeForLlm, stripForLlm
from shared.llm import (
    GeminiClient,
    LlmAuditLog,
    LlmCallRecord,
    LlmConfig,
    assertFairComparisonParity,
    buildGenerationConfig,
    estimateTokens,
    loadLlmConfig,
    parseStructuredResponse,
)
from shared.schemas import InvestigationResult, RootCauseCategory


def testLoadLlmConfigDefaults(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    config = loadLlmConfig()
    assert config.provider == "gemini"
    assert config.model == "gemini-flash-latest"
    assert config.max_output_tokens == 2048


def testLoadLlmConfigOpenRouter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    config = loadLlmConfig()
    assert config.provider == "openrouter"
    assert config.model == "google/gemini-2.5-flash"


def testGenerationConfigUsesZeroTemperature():
    config = LlmConfig(provider="gemini", api_key="test", model="gemini-flash-latest", max_output_tokens=1024)
    generationConfig = buildGenerationConfig(config)
    assert generationConfig["temperature"] == 0
    assert generationConfig["max_output_tokens"] == 1024
    assert generationConfig["response_mime_type"] == "application/json"


def testParseStructuredResponse():
    payload = json.dumps(
        {
            "divergence_step": "inventory_reserve",
            "root_cause_category": "sequence_skip",
            "culprit_log_ids": ["log-1"],
            "evidence_log_ids": ["log-1", "log-2"],
            "explanation": "Skipped reservation.",
        }
    )
    result = parseStructuredResponse(payload, InvestigationResult)
    assert result.root_cause_category == RootCauseCategory.SEQUENCE_SKIP
    assert result.culprit_log_ids == ["log-1"]


def testParseStructuredResponseUnwrapsNestedPayload():
    payload = json.dumps(
        {
            "case_id": "case_01",
            "investigation": {
                "divergence_step": "inventory_reserve",
                "root_cause_category": "sequence_skip",
                "culprit_log_ids": ["log-1"],
                "evidence_log_ids": ["log-1", "log-2"],
                "explanation": "Skipped reservation.",
            },
        }
    )
    result = parseStructuredResponse(payload, InvestigationResult)
    assert result.root_cause_category == RootCauseCategory.SEQUENCE_SKIP
    assert result.culprit_log_ids == ["log-1"]


def testFairComparisonParityDetectsModelMismatch():
    logA = LlmAuditLog(
        calls=[
            LlmCallRecord(
                provider="gemini",
                model="gemini-flash-latest",
                max_output_tokens=2048,
                input_token_estimate=100,
                stage="baseline",
            )
        ]
    )
    logB = LlmAuditLog(
        calls=[
            LlmCallRecord(
                provider="gemini",
                model="gemini-2.5-pro",
                max_output_tokens=2048,
                input_token_estimate=100,
                stage="agent",
            )
        ]
    )
    with pytest.raises(ValueError, match="Model mismatch"):
        assertFairComparisonParity(logA, logB)


def testFairComparisonParityDetectsTokenMismatch():
    logA = LlmAuditLog(
        calls=[
            LlmCallRecord(
                provider="gemini",
                model="gemini-flash-latest",
                max_output_tokens=2048,
                input_token_estimate=100,
                stage="baseline",
            )
        ]
    )
    logB = LlmAuditLog(
        calls=[
            LlmCallRecord(
                provider="gemini",
                model="gemini-flash-latest",
                max_output_tokens=4096,
                input_token_estimate=100,
                stage="agent",
            )
        ]
    )
    with pytest.raises(ValueError, match="Token budget mismatch"):
        assertFairComparisonParity(logA, logB)


def testFairComparisonParityPassesWhenMatched():
    record = LlmCallRecord(
        provider="openrouter",
        model="gemini-flash-latest",
        max_output_tokens=2048,
        input_token_estimate=100,
        stage="baseline",
    )
    logA = LlmAuditLog(calls=[record])
    logB = LlmAuditLog(
        calls=[
            LlmCallRecord(
                provider="openrouter",
                model="gemini-flash-latest",
                max_output_tokens=2048,
                input_token_estimate=120,
                stage="agent",
            )
        ]
    )
    assertFairComparisonParity(logA, logB)


def testLlmPayloadStripsForbiddenKeysForAllCases():
    for case in buildCases():
        payload = serializeForLlm(case)
        assertLlmPayloadIsClean(payload)
        dumped = json.loads(payload)
        assert set(dumped.keys()) == {"case_id", "process_context", "raw_logs"}
        for logEntry in dumped["raw_logs"]:
            assert "baseline_hypothesis" not in logEntry
            assert "difficulty_factors" not in str(logEntry)


def testGeminiClientRecordsAuditLog():
    client = GeminiClient(
        config=LlmConfig(
            provider="gemini",
            api_key="test",
            model="gemini-flash-latest",
            max_output_tokens=512,
        ),
        auditLog=LlmAuditLog(),
    )
    assert client.config.max_output_tokens == 512
    assert client.auditLog.calls == []


def testEstimateTokensMinimumOne():
    assert estimateTokens("") == 1
    assert estimateTokens("hello world") >= 1
