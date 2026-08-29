#!/usr/bin/env python3
"""Verify demo case artifacts and optionally run live UI pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.incident_service import loadArtifactDiagnosis

DEMO_CASES = ("case_01", "case_11", "case_14", "case_15")
ARTIFACTS_DIR = ROOT / "reports" / "artifacts"


def verifyArtifacts() -> int:
    failures = 0
    for caseId in DEMO_CASES:
        path = ARTIFACTS_DIR / f"{caseId}_post_mortem.json"
        if not path.exists():
            print(f"FAIL {caseId}: missing artifact {path}")
            failures += 1
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        diagnosis = loadArtifactDiagnosis(caseId, ARTIFACTS_DIR)
        stored = payload["diagnosis"]
        checks = [
            ("divergence_step", diagnosis.divergence_step, stored["divergence_step"]),
            ("root_cause_category", diagnosis.root_cause_category.value, stored["root_cause_category"]),
            ("culprit_log_ids", diagnosis.culprit_log_ids, stored["culprit_log_ids"]),
        ]
        caseOk = True
        for label, actual, expected in checks:
            if actual != expected:
                print(f"FAIL {caseId}: {label} mismatch — {actual!r} != {expected!r}")
                caseOk = False
                failures += 1
        if caseOk:
            print(
                f"OK   {caseId}: {diagnosis.divergence_step} / "
                f"{diagnosis.root_cause_category.value} / culprits={diagnosis.culprit_log_ids}"
            )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify demo post-mortem artifacts")
    parser.parse_args()
    failures = verifyArtifacts()
    if failures:
        sys.exit(1)
    print(f"\nAll {len(DEMO_CASES)} demo artifacts verified.")


if __name__ == "__main__":
    main()
