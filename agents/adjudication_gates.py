"""Deterministic gates for baseline-vs-challenger adjudication."""

from __future__ import annotations

from shared.schemas import EvalCase, InvestigationResult, RootCauseCategory


def divergenceStepIndex(step: str, expectedSequence: list[str]) -> int | None:
    normalized = step.strip().lower()
    for index, sequenceStep in enumerate(expectedSequence):
        if sequenceStep.strip().lower() == normalized:
            return index
    return None


def isDownstreamDivergence(
    challengerStep: str,
    baselineStep: str,
    expectedSequence: list[str],
) -> bool:
    challengerIndex = divergenceStepIndex(challengerStep, expectedSequence)
    baselineIndex = divergenceStepIndex(baselineStep, expectedSequence)
    if challengerIndex is None or baselineIndex is None:
        return False
    return challengerIndex > baselineIndex


def isSameDivergenceStep(
    baseline: InvestigationResult,
    challenger: InvestigationResult,
    expectedSequence: list[str],
) -> bool:
    baselineIndex = divergenceStepIndex(baseline.divergence_step, expectedSequence)
    challengerIndex = divergenceStepIndex(challenger.divergence_step, expectedSequence)
    return (
        baselineIndex is not None
        and challengerIndex is not None
        and baselineIndex == challengerIndex
    )


def blocksFalseSuccessOverSequenceSkip(
    baseline: InvestigationResult,
    challenger: InvestigationResult,
    expectedSequence: list[str],
) -> bool:
    if baseline.root_cause_category != RootCauseCategory.SEQUENCE_SKIP:
        return False
    if challenger.root_cause_category != RootCauseCategory.FALSE_SUCCESS_SIGNAL:
        return False
    baselineIndex = divergenceStepIndex(baseline.divergence_step, expectedSequence)
    challengerIndex = divergenceStepIndex(challenger.divergence_step, expectedSequence)
    if baselineIndex is None or challengerIndex is None:
        return False
    return challengerIndex <= baselineIndex


def comparisonCitesLogEvidence(comparisonText: str, validLogIds: set[str]) -> bool:
    if not comparisonText.strip():
        return False
    return any(logId in comparisonText for logId in validLogIds)


def buildLogTimestampMap(case: EvalCase) -> dict[str, str]:
    return {log.log_id: log.timestamp for log in case.raw_logs}


def blocksSameStepSupportLogPromotion(
    baseline: InvestigationResult,
    challenger: InvestigationResult,
    expectedSequence: list[str],
    logTimestamps: dict[str, str],
) -> bool:
    """Block same-step overrides that elevate baseline supporting logs to culprit.

    General principle: at the same divergence step, a challenger must not override
    by re-labeling logs the baseline already cited as non-culprit evidence while
    dropping the baseline's culprit anchor, when those promoted logs are not
    chronologically downstream of the baseline's causal anchor.

    Uses evidence dependency roles (culprit vs evidence sets) and temporal
    plausibility — not root-cause enums, log message keywords, or timestamp alone.
    """
    if not isSameDivergenceStep(baseline, challenger, expectedSequence):
        return False

    baselineCulprits = set(baseline.culprit_log_ids)
    baselineEvidence = set(baseline.evidence_log_ids)
    challengerCulprits = set(challenger.culprit_log_ids)
    challengerEvidence = set(challenger.evidence_log_ids)

    if not baselineCulprits or not challengerCulprits:
        return False

    if baselineCulprits & challengerCulprits:
        return False

    baselineSupportOnly = baselineEvidence - baselineCulprits
    if not challengerCulprits.issubset(baselineSupportOnly):
        return False

    if not baselineCulprits.issubset(challengerEvidence):
        return False

    if not challengerCulprits.issubset(baselineEvidence):
        return False

    baselineAnchorTimes = [
        logTimestamps[logId]
        for logId in baselineCulprits
        if logId in logTimestamps
    ]
    if not baselineAnchorTimes:
        return False

    maxBaselineAnchorTime = max(baselineAnchorTimes)
    for logId in challengerCulprits:
        challengerTime = logTimestamps.get(logId)
        if challengerTime is None:
            return False
        if challengerTime > maxBaselineAnchorTime:
            return False

    return True


def evaluateOverrideBlocks(
    baseline: InvestigationResult,
    challenger: InvestigationResult,
    expectedSequence: list[str],
    baselineGateIssues: list[str],
    challengerGateIssues: list[str],
    comparisonText: str,
    validLogIds: set[str],
    logTimestamps: dict[str, str] | None = None,
) -> list[str]:
    blocks: list[str] = []

    if isDownstreamDivergence(
        challenger.divergence_step,
        baseline.divergence_step,
        expectedSequence,
    ):
        blocks.append(
            "DECOY_DEFENSE: Challenger identifies a downstream divergence step; "
            "baseline upstream explanation preserved."
        )

    if blocksFalseSuccessOverSequenceSkip(baseline, challenger, expectedSequence):
        blocks.append(
            "SEQUENCE_SKIP_PRIORITY: Required step was skipped/bypassed (sequence_skip). "
            "false_success_signal is not a sufficient override."
        )

    if logTimestamps and blocksSameStepSupportLogPromotion(
        baseline,
        challenger,
        expectedSequence,
        logTimestamps,
    ):
        blocks.append(
            "SAME_STEP_CAUSAL_ROLE: Challenger promotes baseline supporting logs to "
            "culprit without adopting baseline anchors or new upstream evidence."
        )

    if challengerGateIssues and not baselineGateIssues:
        blocks.append(
            "GATE_DEFENSE: Challenger failed deterministic validation; baseline passed."
        )

    if not comparisonCitesLogEvidence(comparisonText, validLogIds):
        blocks.append(
            "BURDEN_OF_PROOF: Override requires cited log evidence in comparison.why_selected."
        )

    baselineIndex = divergenceStepIndex(baseline.divergence_step, expectedSequence)
    challengerIndex = divergenceStepIndex(challenger.divergence_step, expectedSequence)
    if (
        not baselineGateIssues
        and baselineIndex is not None
        and challengerIndex is not None
        and challengerIndex < baselineIndex
        and blocksFalseSuccessOverSequenceSkip(baseline, challenger, expectedSequence)
    ):
        blocks.append(
            "UPSTREAM_FALSE_SUCCESS: Upstream false_success_signal cannot replace "
            "downstream sequence_skip when workflow continued without required state."
        )

    return list(dict.fromkeys(blocks))
