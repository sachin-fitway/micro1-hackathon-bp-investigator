"""Root-cause taxonomy: documented semantic equivalence for tolerant scoring (Track B).

Exact enum match scores 1.0. Categories in the same equivalence group score
ROOT_CAUSE_PARTIAL_CREDIT (0.5). Case-specific ``acceptable_root_causes`` on
ground truth also score 1.0 when matched.

Groups are intentionally narrow — decoy categories at the wrong divergence step
still fail on the failure-point dimension (35%).
"""

from __future__ import annotations

from shared.schemas import GroundTruth, RootCauseCategory

ROOT_CAUSE_PARTIAL_CREDIT = 0.5

# Each frozenset is an undirected equivalence class with documented overlap.
ROOT_CAUSE_EQUIVALENCE_GROUPS: tuple[frozenset[RootCauseCategory], ...] = (
    frozenset(
        {
            RootCauseCategory.SEQUENCE_SKIP,
            RootCauseCategory.FALSE_SUCCESS_SIGNAL,
        }
    ),  # Skipped step + continued pipeline vs misleading success log
    frozenset(
        {
            RootCauseCategory.CONFIG_DRIFT,
            RootCauseCategory.FALSE_SUCCESS_SIGNAL,
        }
    ),  # Silent rejection / ignored campaign config vs false continuation
    frozenset(
        {
            RootCauseCategory.RACE_CONDITION,
            RootCauseCategory.DUPLICATE_PROCESSING,
        }
    ),  # Concurrent duplicate events vs race-induced duplication
    frozenset(
        {
            RootCauseCategory.ENTITLEMENT_MISMATCH,
            RootCauseCategory.WEBHOOK_MISSING,
        }
    ),  # Missing contract/event sync vs stale entitlement state
    frozenset(
        {
            RootCauseCategory.METADATA_MESSAGE_CONFLICT,
            RootCauseCategory.FALSE_SUCCESS_SIGNAL,
        }
    ),  # Message says success, metadata/body contradicts
)

GROUP_RATIONALE: dict[frozenset[RootCauseCategory], str] = {
    ROOT_CAUSE_EQUIVALENCE_GROUPS[0]: (
        "A required step was skipped or not enforced while the pipeline continued; "
        "a nearby success log can be read either way."
    ),
    ROOT_CAUSE_EQUIVALENCE_GROUPS[1]: (
        "Configuration or campaign rules caused silent rejection that looks like "
        "the process succeeded and moved on."
    ),
    ROOT_CAUSE_EQUIVALENCE_GROUPS[2]: (
        "Duplicate consumption of the same event is often the observable symptom "
        "of a race at an upstream step."
    ),
    ROOT_CAUSE_EQUIVALENCE_GROUPS[3]: (
        "Downstream entitlement state is wrong because an upstream event was never "
        "observed — webhook missing and hash mismatch are two views of the same gap."
    ),
    ROOT_CAUSE_EQUIVALENCE_GROUPS[4]: (
        "Log message implies success while metadata or downstream behavior shows "
        "the step did not actually complete correctly."
    ),
}


def buildEquivalenceLookup() -> dict[RootCauseCategory, frozenset[RootCauseCategory]]:
    """Categories that share at least one equivalence group with the key."""
    lookup: dict[RootCauseCategory, set[RootCauseCategory]] = {}
    for group in ROOT_CAUSE_EQUIVALENCE_GROUPS:
        for category in group:
            lookup.setdefault(category, set()).update(group)
    return {category: frozenset(matches) for category, matches in lookup.items()}


EQUIVALENCE_LOOKUP = buildEquivalenceLookup()


def areEquivalentCategories(
    predicted: RootCauseCategory,
    canonical: RootCauseCategory,
) -> bool:
    if predicted == canonical:
        return True
    return any(
        predicted in group and canonical in group
        for group in ROOT_CAUSE_EQUIVALENCE_GROUPS
    )


def scoreRootCauseMatch(
    predicted: RootCauseCategory,
    groundTruth: GroundTruth,
) -> float:
    canonical = groundTruth.root_cause_category
    if predicted == canonical:
        return 1.0
    acceptable = set(groundTruth.acceptable_root_causes)
    if predicted in acceptable:
        return 1.0
    if areEquivalentCategories(predicted, canonical):
        return ROOT_CAUSE_PARTIAL_CREDIT
    return 0.0


def rootCauseMatchLabel(
    predicted: RootCauseCategory,
    groundTruth: GroundTruth,
) -> str:
    score = scoreRootCauseMatch(predicted, groundTruth)
    if score >= 1.0:
        return "exact" if predicted == groundTruth.root_cause_category else "acceptable"
    if score >= ROOT_CAUSE_PARTIAL_CREDIT:
        return "equivalent"
    return "wrong"
