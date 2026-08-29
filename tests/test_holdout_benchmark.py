"""Holdout benchmark integrity tests — separate from development set."""

from __future__ import annotations

from generate_holdout_data import HOLDOUT_CASE_IDS, buildHoldoutCases, writeHoldoutCases
from shared.case_loader import assertLlmPayloadIsClean, serializeForLlm
from shared.holdout_loader import HOLDOUT_DIR, loadAllHoldoutCases
from shared.schemas import EvalCase


def testHoldoutCasesIndependentFromDevelopment():
    devIds = {f"case_{index:02d}" for index in range(1, 16)}
    holdoutIds = set(HOLDOUT_CASE_IDS)
    assert holdoutIds.isdisjoint(devIds)
    assert len(holdoutIds) >= 5


def testHoldoutCasesValidateAndStripCleanly():
    writeHoldoutCases(HOLDOUT_DIR)
    for case in loadAllHoldoutCases():
        assert isinstance(case, EvalCase)
        payload = serializeForLlm(case)
        assertLlmPayloadIsClean(payload)
        assert "ground_truth" not in payload
        assert case.ground_truth.divergence_step in case.process_context.expected_sequence


def testHoldoutDoesNotReuseDevelopmentCaseIds():
    devCases = {case.case_id for case in __import__("generate_data", fromlist=["buildCases"]).buildCases()}
    holdoutCases = buildHoldoutCases()
    assert {case.case_id for case in holdoutCases}.isdisjoint(devCases)
