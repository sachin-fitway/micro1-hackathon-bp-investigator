# Holdout Forensic Analysis — Topological Absence Blindness Hypothesis

**Date:** 2026-08-29  
**Artifacts:** `data/holdout/case_16.json` … `case_23.json`, `results/eval_holdout.json`  
**Production system:** UNCHANGED (prompts, Stage 3, gates, scoring frozen)

---

## Executive Summary

| Verdict | Result |
|---------|--------|
| **Topological Absence Blindness hypothesis** | **PARTIALLY SUPPORTED** (weak) |
| **Stronger claim** (zero logs = sufficient divergence) | **UNSAFE** |
| **Recommendation** | **B — Modify topological-diff idea with additional constraints** |

The holdout failures on cases **16, 17, and 23** are **not primarily caused by completely absent process-step logs**. In all three cases, every expected step has at least one observable log. Failures are dominated by **wrong divergence-step anchoring** (downstream symptoms, decoys, temporal noise) and **category labeling variance** (case_20), not by the model being unable to see that a step left no trace.

---

## Methodology

For each holdout case we:

1. Read ground truth from holdout JSON (never exposed to LLM).
2. Read Stage 0 / Stage 3 predictions from `results/eval_holdout.json`.
3. Manually map each non-noise log (`cNN-n*` excluded) to the best-matching `expected_sequence` step by service/message semantics.
4. Classify the **first** step in sequence order that exhibits: no log / contradictory metadata / explicit failure / apparent success.
5. Determine whether GT divergence requires **log absence** vs **semantic interpretation** of existing logs.

Noise logs (`metadata.irrelevant: true`) are excluded from step coverage.

---

## Focus Cases — Shared Comparison

| Case | GT step | GT cause | S0 step | S3 step | All steps have logs? | Primary failure mode |
|------|---------|----------|---------|---------|----------------------|----------------------|
| **16** | `coverage_verify` | entitlement_mismatch | `prior_auth_submit` | `prior_auth_submit` | **Yes** | Downstream symptom anchoring + metadata at verify ignored for step ID |
| **17** | `cross_dock_transfer` | webhook_missing | `last_mile_dispatch` | `last_mile_dispatch` | **Yes** | Downstream decoy (ERROR timeout) + wrong step despite explicit absence log |
| **20** | `carrier_validate` | sequence_skip | `carrier_validate` ✓ | `carrier_validate` ✓ | **Yes** | Category drift (S3 baseline re-run), not absence |
| **23** | `meter_confirm` | sequence_skip | `dispatch_execute` | `dispatch_execute` | **Yes** | Temporal decoy (race at dispatch vs skip at confirm) |

**Do 16, 17, 23 share the SAME mechanism?**  
**No.** They share a *superficial pattern* (wrong `divergence_step`, holdout IQS ≤65%) but differ mechanistically:

- **16:** Semantic/metadata conflict at **`coverage_verify`** (`c16-02` says "verified" but metadata shows tier mismatch). Model anchors on explicit **block** at `prior_auth_submit` (`c16-03`).
- **17:** **Explicit absence artifact** at `cross_dock_transfer` (`c17-04` "No carrier handoff webhook received") plus normal transfer log (`c17-03`). Model anchors on loudest downstream **ERROR** (`c17-05`) and `last_mile_dispatch`.
- **23:** All steps present including **`dispatch_execute`** (`c23-03`). Temporal decoy (`c23-05` ack before command) pulls model to **`dispatch_execute`/race_condition** instead of **`meter_confirm`/sequence_skip** (`c23-04`, `c23-07`).

---

## Per-Case Forensic Records

### case_16 — healthcare_prior_auth (IQS: 65.0 / 65.0)

#### Ground truth
| Field | Value |
|-------|-------|
| divergence_step | `coverage_verify` |
| root_cause_category | `entitlement_mismatch` |
| culprit_log_ids | `c16-02`, `c16-06` |
| required_evidence_ids | `c16-02`, `c16-06`, `c16-03` |

#### Predictions
| Stage | step | category | culprits | evidence |
|-------|------|----------|----------|----------|
| S0 | `prior_auth_submit` | entitlement_mismatch | `c16-03` | `c16-02`, `c16-03`, `c16-06` |
| S3 | `prior_auth_submit` | entitlement_mismatch | `c16-03` | `c16-02`, `c16-03`, `c16-06` |

#### expected_sequence
`referral_intake` → `coverage_verify` → `prior_auth_submit` → `care_schedule`

#### Log → step mapping

| Log ID | Step | Observation |
|--------|------|-------------|
| c16-01 | referral_intake | Successful: "Referral accepted" |
| c16-02 | coverage_verify | **Contradictory:** message "Coverage verified" but `plan_tier: basic`, `required_tier: specialist` |
| c16-06 | coverage_verify | Audit confirms tier mismatch (DEBUG) |
| c16-07 | coverage_verify (context) | Stale cache — supporting, not step completion |
| c16-03 | prior_auth_submit | **Explicit failure:** "Prior auth submission blocked" |
| c16-04 | care_schedule | Process continued incorrectly |
| c16-05 | (downstream) | Support symptom |

#### Step coverage
| Step | Observable log? |
|------|-----------------|
| referral_intake | Yes (c16-01) |
| coverage_verify | Yes (c16-02, c16-06, c16-07) |
| prior_auth_submit | Yes (c16-03) |
| care_schedule | Yes (c16-04) |

**Every expected step has an observable log.**

#### First step in sequence with anomaly
**`coverage_verify`** — contradictory metadata / false-success message (`c16-02`), confirmed by `c16-06`.

#### Inferability
**Requires semantic interpretation** of existing logs at `coverage_verify`. Not inferable from log absence alone — the step *did* emit logs; the failure is entitlement state vs message text.

#### Topological absence?
**No.** `coverage_verify` is present and logged.

---

### case_17 — logistics_cross_dock (IQS: 55.0 / 55.0)

#### Ground truth
| Field | Value |
|-------|-------|
| divergence_step | `cross_dock_transfer` |
| root_cause_category | `webhook_missing` |
| culprit_log_ids | `c17-04` |
| required_evidence_ids | `c17-04`, `c17-07`, `c17-03` |

#### Predictions
| Stage | step | category | culprits | evidence |
|-------|------|----------|----------|----------|
| S0/S3 | `last_mile_dispatch` | webhook_missing | `c17-04`, `c17-07` | `c17-04`, `c17-07`, `c17-05`, `c17-08` |

#### expected_sequence
`inbound_scan` → `customs_clear` → `cross_dock_transfer` → `last_mile_dispatch`

#### Log → step mapping

| Log ID | Step | Observation |
|--------|------|-------------|
| c17-01 | inbound_scan | Successful |
| c17-02 | customs_clear | Successful |
| c17-03 | cross_dock_transfer | "Cross-dock move initiated" — step ran |
| c17-04 | cross_dock_transfer | **Absence artifact:** "No carrier handoff webhook received" (DEBUG) |
| c17-07 | last_mile_dispatch | Failure: "Route not created: missing handoff event" |
| c17-05 | last_mile_dispatch | **ERROR decoy:** "Dispatch API timeout" |
| c17-08 | (infra) | Health-check-only webhook endpoint |

#### Step coverage
**All four steps have observable logs.** `cross_dock_transfer` has both execution (`c17-03`) and absence-of-webhook (`c17-04`).

#### First anomaly in sequence order
**`cross_dock_transfer`** — required webhook/event absent (`c17-04`), while physical move started (`c17-03`).

#### Inferability
**Semantic interpretation + explicit absence statement** in `c17-04`. Not pure topological silence — the audit log names the missing webhook. Zero logs at `cross_dock_transfer` would be **insufficient** here because `c17-03` proves the step partially executed.

#### Topological absence?
**Partial.** Missing *webhook*, not missing *step*. Step has logs; contract violation is logged explicitly.

---

### case_18 — insurance_claim_payment (IQS: 96.0 / 96.0)

#### Ground truth
step=`adjuster_assign`, cause=`duplicate_processing`, culprits=`c18-04`,`c18-07`, evidence=`c18-04`,`c18-07`,`c18-05`

#### Predictions (S0/S3 identical)
Correct step and category. Duplicate event `c18-04` at `adjuster_assign` is **explicitly logged** — not absence.

#### Step coverage: all steps logged. **Generalizes well.**

---

### case_19 — manufacturing_batch_qc (IQS: 97.5 / 97.5)

#### Ground truth
step=`recipe_load`, cause=`config_drift`

#### Predictions (S0/S3 identical)
Correct. Wrong recipe version **explicitly logged** at `recipe_load` (`c19-02`). **Generalizes well.**

---

### case_20 — telecom_number_port (IQS: 100.0 → 70.0) ⚠️

#### Ground truth
| Field | Value |
|-------|-------|
| divergence_step | `carrier_validate` |
| root_cause_category | `sequence_skip` |
| culprit_log_ids | `c20-02`, `c20-06` |
| required_evidence_ids | `c20-02`, `c20-06`, `c20-03` |

#### Predictions
| Stage | step | category | culprits | evidence |
|-------|------|----------|----------|----------|
| **S0** | `carrier_validate` | **sequence_skip** | `c20-02` | `c20-02`, `c20-06`, `c20-03` |
| **S3** | `carrier_validate` | **config_drift** | `c20-02` | `c20-02`, `c20-06`, `c20-03` |

#### expected_sequence
`port_request` → `carrier_validate` → `number_release` → `account_link`

#### Log → step mapping

| Log ID | Step | Observation |
|--------|------|-------------|
| c20-01 | port_request | Successful |
| c20-02 | carrier_validate | **Bypass/skip:** "Validation bypassed: expedite flag set" |
| c20-06 | carrier_validate | **Absence artifact:** "No carrier validation artifact stored" |
| c20-03 | number_release | Rejected: validation token absent |
| c20-04 | number_release | **ERROR decoy:** "Release polling timeout" |
| c20-07 | account_link | Deferred |

#### Step coverage
**All steps have logs.** `carrier_validate` is **not topologically absent** — it logged bypass (`c20-02`) and missing artifact (`c20-06`).

#### First anomaly
**`carrier_validate`** — explicit bypass + missing validation artifact (sequence_skip semantics).

#### Why Stage 3 dropped from 100% → 70%

Stage 3 does **not** change the divergence step. Regression is **100% root-cause scoring** (1.0 → 0.0):

1. **Separate baseline LLM call inside Stage 3** (trajectory `case_20_stage3.jsonl`) produced `config_drift` instead of Stage 0's `sequence_skip`, despite identical evidence IDs and correct step.
2. **Challenger** proposed downstream `number_release` / `config_drift` (decoy aligned with `c20-04` timeout).
3. **Adjudication:** `keep_baseline` with `DECOY_DEFENSE` — correctly rejected downstream challenger.
4. **Final output:** kept Stage 3 **baseline** = `carrier_validate` / **`config_drift`** (70% IQS).

**Root cause:** Non-deterministic **category labeling** on the same logs (`expedite flag` → config_drift vs sequence_skip), not agentic override or topological blindness. Gates worked; baseline variance hurt.

#### Topological absence?
**No.** Bypass is explicitly logged.

---

### case_21 — marketplace_seller_payout (IQS: 82.5 / 82.5)

#### Ground truth
step=`fee_calculate`, cause=`metadata_message_conflict`

#### Predictions
step=`fee_calculate`, cause=`false_success_signal` (partial credit 0.5)

Metadata conflict at `c21-02` (`fee_state: waived` vs `seller_fee_due: 42.5`). Step fully logged. **Not absence.**

---

### case_22 — hr_onboarding (IQS: 100.0 / 100.0)

#### Ground truth
step=`background_check`, cause=`false_success_signal`

#### Predictions (S0/S3 identical)
Correct. False success **explicitly logged** at `background_check` (`c22-02` vs metadata). **Generalizes well.**

---

### case_23 — energy_grid_dispatch (IQS: 32.5 / 32.5)

#### Ground truth
| Field | Value |
|-------|-------|
| divergence_step | `meter_confirm` |
| root_cause_category | `sequence_skip` |
| culprit_log_ids | `c23-04`, `c23-07` |
| required_evidence_ids | `c23-03`, `c23-04`, `c23-07` |

#### Predictions (S0/S3 identical)
step=`dispatch_execute`, cause=`race_condition`, culprits=`c23-05`,`c23-03`

#### expected_sequence
`demand_forecast` → `unit_commit` → `dispatch_execute` → `meter_confirm`

#### Log → step mapping

| Log ID | Step | Observation |
|--------|------|-------------|
| c23-01 | demand_forecast | Successful |
| c23-02 | unit_commit | Successful |
| c23-08 | (context) | Weather feed |
| c23-03 | dispatch_execute | "Dispatch command issued" @ 16:00:03 |
| c23-05 | dispatch_execute | **Temporal decoy:** "Dispatch ack received before command logged" @ 16:00:02 (`clock_skew_ms: 1500`) |
| c23-04 | meter_confirm | **Failure:** "Meter confirmation missing dispatch token" @ 16:00:04 |
| c23-07 | meter_confirm | Audit: "Confirm step invoked without dispatch completion" |
| c23-06 | (downstream) | Grid imbalance alert |

#### Step coverage
**All four expected steps have observable logs**, including `meter_confirm` (`c23-04`, `c23-07`).

#### First anomaly in strict sequence order
- `dispatch_execute`: temporal inconsistency (`c23-05` before `c23-03`) — **decoy**, not GT divergence.
- **`meter_confirm`:** confirm invoked without valid dispatch completion (`c23-04`, `c23-07`) — **GT divergence**.

#### Inferability
**Semantic interpretation** — must read `c23-07` and relate confirm failure to incomplete dispatch contract. Not pure log absence: dispatch *was* logged; confirm *was* logged but invalid.

#### Topological absence?
**No.** This is **temporal decoy + downstream-vs-upstream anchoring**, same family as dev case_03/case_08, not absence blindness.

---

## Hypothesis Tests

### H1: Topological Absence Blindness

> "Cases 16, 17, and 23 expose a general Topological Absence Blindness failure: the model detects anomalies in logs but fails when a required process step is completely absent from the observed timeline."

| Case | Step completely absent from logs? | Model detected anomaly in logs? | Failure matches absence hypothesis? |
|------|----------------------------------|------------------------------|-------------------------------------|
| 16 | **No** — all steps logged | Yes (blocked auth, tier mismatch cited) | **No** — wrong step (symptom vs verify) |
| 17 | **No** — all steps logged | Yes (webhook missing cited) | **Partial** — wrong step despite naming absence |
| 23 | **No** — all steps logged | Yes (race/temporal cited) | **No** — decoy step, not absence |

**Verdict: PARTIALLY SUPPORTED (weak)**

- **Supported fragment:** In case_17, the model correctly identifies *webhook* absence (`webhook_missing`) but anchors divergence at the **wrong step** (`last_mile_dispatch` vs `cross_dock_transfer`). Absence is **named in logs**, not inferred from silence.
- **Rejected fragment:** Cases 16 and 23 have **no topologically absent steps**. Failures are metadata conflict and temporal decoy respectively.
- Holdout cases with **explicit bypass/skip logs** (20, 22) **generalize well** when the skip is verbalized — contradicting pure absence blindness.

---

### H2: Stronger Claim — Zero Logs = Sufficient Divergence

> "If an expected process step has zero observable logs before a later expected step occurs, that alone is sufficient evidence to declare that step the divergence."

#### Counterexamples in holdout data

| Case | Why UNSAFE |
|------|------------|
| **17** | `cross_dock_transfer` has `c17-03` (move initiated) **before** `last_mile_dispatch` logs. Zero-log rule would mis-handle partial/async execution. |
| **16** | `coverage_verify` has logs; absence rule irrelevant — GT is metadata mismatch at logged step. |
| **20** | `carrier_validate` logs bypass (`c20-02`) — step is represented by **anti-pattern log**, not silence. |
| **22** | `background_check` logs false success — silent batch/async vendor work is **`c22-06`**, not missing step. |
| **23** | `dispatch_execute` and `meter_confirm` both logged; later step failure ≠ earlier step had zero logs. |

#### Async / silent / batched patterns observed
- **c16-07:** Cached coverage snapshot (stale read, not missing step)
- **c17-03 + c17-04:** Step executed + webhook absent (partial contract)
- **c20-02:** Bypass log substitutes for normal validate completion
- **c22-06:** Vendor queue DEBUG — async completion not yet arrived
- **c23-05:** Clock-skew ack — out-of-order, not absent dispatch

**Verdict: UNSAFE**

Zero observable logs at a step is **neither necessary nor sufficient** for divergence in this holdout set. Required additional conditions:

1. Distinguish **no log** vs **bypass/skip log** vs **false-success log**
2. Require **later step attempted without required artifact/state** from earlier step
3. Treat **explicit absence artifacts** (`c17-04`, `c20-06`) as first-class, not inferred silence
4. Do not override when **partial execution logs** exist for the same step

---

## Holdout vs Development Benchmark

| Metric | Dev (15-case) | Holdout (8-case) | Notes |
|--------|---------------|------------------|-------|
| Stage 0 IQS | 89.06% | 78.56% | −10.5 pp |
| Stage 3 IQS | 89.73% | 74.81% | −14.9 pp |
| Divergence accuracy (S3) | 100% | 62.5% | Wrong step on 16, 17, 23 |
| Root cause (S3) | 73.3% | 68.8% | case_20 category drift |

Failures that **generalize poorly** align with **decoy/symptom anchoring**, not absence-only patterns.

---

## Recommendation

### **B — Modify topological-diff idea with additional constraints**

Do **not** implement raw "count logs per expected step → earliest gap = divergence" yet.

**Proposed constraints before any prompt experiment:**

1. **Three-valued step status:** `completed` | `explicitly_bypassed_or_skipped` | `no_observable_evidence` — bypass logs (`c20-02`, `c16-03` block) are not equivalent to silence.
2. **Absence artifacts:** Treat audit/DEBUG lines that state missing artifacts/events (`c17-04`, `c20-06`, `c23-07`) as primary evidence, not inferred gaps.
3. **Partial execution guard:** If any log maps to step *S*, do not classify *S* as topologically absent (case_17).
4. **Decoy defense preserved:** Loudest ERROR or temporal inversion alone cannot override explicit bypass/absence at earlier step (existing gate philosophy).
5. **Category stability:** Topological diff addresses **step** only; case_20 shows **category** needs separate guardrails (sequence_skip vs config_drift on bypass logs).

**Why not A (implement now):** Holdout evidence does not show absence-only failures; raw topological diff would not fix cases 16 or 23 and risks false positives on partial/async steps (17).

**Why not C (reject entirely):** Case_17 shows explicit absence artifacts exist and are **mis-located** to wrong steps — a constrained topological+artifact walk could help **if** paired with decoy defense.

---

## Production Code Status

- No changes to `BASELINE_INSTRUCTIONS`, Stage 3, gates, schemas, scoring, or benchmark.
- Analysis only; artifacts in `results/holdout_forensic_analysis.md`.
