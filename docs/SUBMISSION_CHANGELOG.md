# Improvement Changelog — Incident Investigator

This document records the **actual evolution** of the project for hackathon submission review. Metrics are taken from frozen evaluation artifacts in `results/` unless noted as non-canonical experiment logs.

**Canonical submission metrics (development benchmark, 15 cases):**

| Checkpoint | Mean IQS |
|------------|----------|
| Stage 0 (frozen) | **89.06%** |
| Stage 3 (shipped) | **89.73%** |
| Delta | **+0.67 pp** |

Artifact: `results/eval_submission.json`

---

## 1. Initial baseline (~80.9% era)

**Approach:** Single-prompt diagnostic on raw logs — identify divergence step, root-cause category, culprit/evidence log IDs, and a short explanation.

**Result:** Approximately **~80.9%** mean IQS on early development runs with the first hardened benchmark (documented in intermediate frozen checkpoints such as `results/eval_stage0_frozen.json` context and same-step-gate ablation notes). An earlier preserved multi-stage ablation artifact (`eval_stage0_frozen.json`) shows **72.9%** Stage 0 before later prompt hardening — illustrating how sensitive early scores were to prompt quality.

**Decision:** KEEP as starting point, but insufficient for silent-failure / decoy-heavy cases (wrong step, symptom chasing, category drift).

**Lesson:** A plausible narrative is not the same as a verified process divergence.

---

## 2. Forensic baseline improvement → 89.06% (KEEP)

**Hypothesis:** Generalize the baseline prompt with forensic discipline instead of case-specific hacks.

**Changes (frozen in `shared/prompts.py` → `BASELINE_INSTRUCTIONS`):**

- Structured step reasoning against `expected_sequence`
- Taxonomy clarification (enum-aligned root-cause categories)
- Evidence discipline (cite log IDs; do not treat loudest ERROR as root)
- Earliest **process-contract** divergence vs downstream symptoms
- Tolerant root-cause scoring documented in `shared/root_cause_taxonomy.py` (Track B)

**Result:** **89.06%** mean IQS — frozen as Stage 0 in `results/eval_submission.json` (sourced from `eval_stage0_experiment.json` metadata).

**Decision:** **KEEP** — this is the frozen Stage 0 checkpoint for all fair comparisons.

**Evidence:** `results/eval_submission.json` → `stage_means_iqs["0"]`

---

## 3. Multi-hypothesis / adversarial architecture (REVISED)

**Hypothesis:** Replace single challenger with a hypothesis board (baseline + rule-checker candidates + planted decoy) and an adversarial verifier that must reject weak leading hypotheses.

**What changed:**

- Multi-hypothesis rule checker (2–3 competing hypotheses)
- Hypothesis board assembly (orchestrator-side decoy injection from ground truth — evaluation only)
- Adversarial verifier with burden-of-proof language

**Result:** Stage 3 mean IQS **~77.7–78.0%** vs frozen Stage 0 **~80.9%** at that checkpoint (**regression**). Verifier rejected leading hypotheses aggressively; some correct baselines were preserved, but harmful overrides and instability remained (e.g. case_02, case_05 regressions in experiment logs).

**Decision:** **REVISED** — architecture replaced with baseline + single rule-checker challenger + dedicated adjudication verifier + deterministic gates (Phase 2).

**Evidence:** `results/eval_track_a.log`, `results/eval_burden_of_proof.log` (non-canonical)

**Lesson:** More agents ≠ better if the verifier cannot reliably distinguish upstream cause from downstream symptom; ground-truth decoys in the board also risk evaluation leakage patterns.

---

## 4. SAME_STEP_CAUSAL_ROLE safety gate (RETAINED)

**Hypothesis:** Block challenger overrides that merely re-label baseline **supporting** logs as **culprit** at the same divergence step without new upstream evidence.

**Why introduced:** Case 15–style failures where challenger promotes baseline evidence logs to culprit while demoting the true causal anchor — a general evidence-role confusion, not a one-off string match.

**Implementation:** `agents/adjudication_gates.py` → `blocksSameStepSupportLogPromotion()`; surfaces as deterministic block `SAME_STEP_CAUSAL_ROLE`.

**Result (intermediate checkpoint):** Stage 3 **82.5%** vs Stage 0 **80.9%** (+1.6 pp) with **0 harmful overrides** and **0 regressions** vs that frozen S0 in the same-step gate ablation run (`results/eval_same_step_gate.log`). Trade-off: fewer successful overrides (more conservative).

**Decision:** **RETAINED** in shipped Stage 3 — combined with later prompt/orchestration improvements that raised the final canonical score.

**Lesson:** Deterministic gates belong where LLM adjudication is structurally blind (evidence roles), not only where it is wrong on semantics.

---

## 5. Failed experiments (reverted or not shipped)

### 5a. Upstream-laundering adjudicator prompt

| | |
|--|--|
| **Hypothesis** | Strengthen adjudicator to reject “earlier timestamp = root cause” overrides |
| **Change** | Added general rule: earlier **event** ≠ earlier **causal divergence** |
| **Result** | Mean S3 dropped to **~74.0%** with **3 harmful overrides** (cases 09, 11, 12) vs prior **82.5%** run |
| **Decision** | **REVERTED** prompt change |
| **Lesson** | Prompt-only causal rules can over-correct; deterministic gates + narrower adjudication scope worked better |

### 5b. Process-contract audit (prompt-level)

| | |
|--|--|
| **Hypothesis** | Explicit process-contract auditing in baseline/adjudicator reduces sequence-skip misses |
| **Change** | Stronger contract language in prompts (evolved into forensic baseline, not a separate shipped mode) |
| **Result** | Absorbed into forensic baseline (89.06%); standalone “audit-only” experiments did not beat frozen S0 alone |
| **Decision** | **Merged** into baseline prompt; not a separate stage |
| **Lesson** | Contract language helps when paired with evidence IDs, not as prose alone |

### 5c. Evidence pruner (Stage 4)

| | |
|--|--|
| **Hypothesis** | Post-baseline evidence pruning improves precision without hurting recall |
| **Change** | Stage 4: baseline + evidence pruner (`results/eval_stage4_pruner.log`) |
| **Result** | **~89.7%** mean IQS in one run — near frozen S0, not clearly better than shipped Stage 3 (**89.73%**) with full workflow |
| **Decision** | **NOT SHIPPED** |
| **Lesson** | Pruning is redundant once gates + hydration enforce evidence discipline |

### 5d. Minimal sufficient evidence (baseline prompt experiment)

| | |
|--|--|
| **Hypothesis** | Force minimal evidence sets to improve precision |
| **Change** | Baseline prompt variant emphasizing minimal sufficient evidence |
| **Result** | **78.8%** Stage 0 (`results/eval_stage0_minimal_evidence.log`) |
| **Decision** | **REVERTED** |
| **Lesson** | Over-minimizing evidence hurt recall on sparse-log silent failures |

### 5e. Step-attribution prompt experiment

| | |
|--|--|
| **Hypothesis** | Explicit step-local origin vs enforcement classification improves holdout attribution |
| **Change** | Upstream step hints / attribution principle in baseline (`run_step_attribution_experiment.py`) |
| **Result** | Dev IQS **82.28%** (down from **89.06%** frozen S0); widespread regressions on cases 02–07, 09 |
| **Decision** | **REVERTED** — script marked **ARCHIVED / NON-CANONICAL** |
| **Evidence:** | `results/eval_step_attribution_experiment.log` |

### 5f. Constrained upstream challenger

| | |
|--|--|
| **Hypothesis** | Allow structured upstream challenger proposals with tighter gate constraints |
| **Change** | Stage 3 gate experiment (`run_constrained_upstream_experiment.py`) |
| **Result** | Harmful overrides on **case_03**, **case_11**; not promoted over stable architecture |
| **Decision** | **REVERTED** — script marked **ARCHIVED / NON-CANONICAL** |
| **Evidence:** | `results/eval_constrained_upstream_experiment.json` (local, gitignored) |

---

## 6. Final shipped architecture

**Pipeline (Stage 3):**

1. Deterministic timeline preprocess
2. Baseline LLM diagnosis (frozen forensic prompt)
3. Rule-checker challenger hypothesis
4. Adjudication verifier LLM
5. **Deterministic safety gates** (downstream divergence block, false-success over sequence-skip, same-step causal role, burden-of-proof evidence citation)
6. Immutable `InvestigationResult`
7. Deterministic evidence hydration (`LogLookupTool`)
8. Post-mortem reporter LLM (explain-only; cannot mutate diagnosis)
9. Product UI: diagnosis → causal chain → evidence → post-mortem export

**Canonical results (15-case dev benchmark):**

| Metric | Value |
|--------|-------|
| Stage 0 | **89.06%** |
| Stage 3 | **89.73%** |
| Delta | **+0.67 pp** |
| Divergence accuracy (S3 mean) | **100%** |
| Evidence recall (S3 mean) | **97.78%** |
| No-fabrication (S3 mean) | **100%** |

**Note:** +0.67 pp on mean IQS is modest because the forensic baseline already achieves ~89%; Stage 3 primarily secures **integrity** (gates, challenger/adjudication) and fixes long-tail failures rather than transforming an weak baseline.

---

## 7. Independent holdout (not used for tuning)

| Metric | Value |
|--------|-------|
| Cases | **8** unseen (`case_16`–`case_23`, `data/holdout/`) |
| Stage 0 IQS | **78.56%** |
| Stage 3 IQS | **74.81%** |
| Delta | **−3.75 pp** |

**Artifact:** `results/eval_holdout.json`

**Explicit statement:** Holdout cases were **never** used for prompt tuning, gate design iteration, or benchmark cherry-picking. They were evaluated post-hoc for generalization.

**Discovered limitation:** Failures on holdout cases 16, 17, 23 are dominated by **wrong divergence-step anchoring** (downstream symptoms, decoys, temporal noise) — not missing logs. See `results/holdout_forensic_analysis.md` and `results/step_attribution_analysis.md`.

---

## Closing summary

### Main failure mode discovered

**Evidence-to-process-step attribution under distribution shift** — especially distinguishing step-local contract violation (origin) from downstream enforcement symptoms when logs are sparse or decoy-heavy.

### Main engineering insight (hot take)

Structured workflow value is **not** raw mean-IQS lift alone (+0.67 pp on an already-strong 89% baseline). It is **immutable diagnosis**, **deterministic no-fabrication gates**, **challenge/adjudicate without rewriting ground truth in the reporter**, and **honest holdout reporting**. The product is an investigation pipeline, not a single prompt score.

### What would be researched next

1. Step-local **origin vs enforcement vs execution-anomaly** classification **before** divergence selection (holdout-diagnostic; dev-safe evaluation protocol)
2. Richer challenger recall without re-introducing multi-hypothesis board instability
3. Holdout-targeted attribution features that do **not** leak holdout labels into prompt tuning
