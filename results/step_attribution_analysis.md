# Process-Step Attribution Failure — Holdout Deep Analysis

**Date:** 2026-08-29  
**Inputs:** `results/holdout_forensic_analysis.md`, `results/eval_holdout.json`, `data/holdout/case_16.json` … `case_23.json`  
**Production system:** UNCHANGED (no prompt, gate, schema, scoring, or benchmark edits)

---

## Executive Summary

| Finding | Result |
|---------|--------|
| **Primary failure mechanism (16, 17, 23)** | **D — evidence-to-step attribution**, compounded by **C — causal reasoning** (conflating enforcement/symptom locus with contract-origin locus) |
| **case_20** | **Not a step-attribution failure** — step correct in S0 and S3; regression is **E + F** (taxonomy + LLM variance) |
| **Common structural difference** | Failed cases split evidence across **origin violation at step S** vs **loud enforcement/decoy at step S+k**; model anchors on S+k |
| **Candidate principle** | **Step-Local Contract Violation vs Downstream Enforcement Discrimination** |
| **Final verdict** | **IMPLEMENT EXPERIMENT** |

---

## Methodology

For each focus case we compare:

1. Ground truth and Stage 0 / Stage 3 predictions from `results/eval_holdout.json`
2. Raw logs and `expected_sequence` from holdout JSON
3. `meta.difficulty_factors` and `decoy_diagnosis` where present
4. Model explanations (especially which logs are labeled “culprit” vs “evidence”)

Constraints honored:

- No “earliest timestamp = root cause”
- No “first anomaly = root cause”
- No “missing log = skipped step”
- No “ERROR log = divergence step”
- No case-specific rules proposed

---

## Failed Cases — Per-Case Attribution Forensics

### case_16 — healthcare_prior_auth (IQS 65.0, step wrong)

| Field | Value |
|-------|-------|
| GT step / category | `coverage_verify` / `entitlement_mismatch` |
| S0/S3 step / category | `prior_auth_submit` / `entitlement_mismatch` |

#### 1. Evidence that correctly identifies the true divergence step

| Log | Role |
|-----|------|
| **c16-02** | At `coverage_verify`: message `"Coverage verified"` but metadata `plan_tier: basic`, `required_tier: specialist` — **step-local contract breach** (false authorization state) |
| **c16-06** | Audit at same step window: `"Member plan tier basic; referral requires specialist"` — confirms verify produced invalid entitlement state |
| **c16-03** | Downstream **enforcement**: auth correctly blocks submission — symptom, not origin |

#### 2. Evidence that caused wrong-step anchoring

| Log | Why it pulled the model |
|-----|-------------------------|
| **c16-03** | Explicit `"Prior auth submission blocked: plan insufficient"` — loudest **failure-shaped** message; reads as “where the process failed” |
| Model narrative | Explanation states `coverage_verify` “**correctly identified** the plan tiers” — metadata interpreted as verify **working**, not **deviating** |

#### 3. Wrong-step classification

**Downstream symptom (enforcement gate).**  
`prior_auth_submit` did not breach its contract; it **correctly rejected** invalid upstream state. This is not a decoy ERROR, temporal trap, or partial execution at the wrong step — it is **legitimate competing hypothesis** unless origin vs enforcement is distinguished.

#### 4. Distinction the model must make

> **Origin violation** at `coverage_verify` (emitting “verified” / proceeding state when tiers do not satisfy referral) vs **correct rejection** at `prior_auth_submit` (blocking submission given bad state).

The model must not treat “first step with block/fail language” as divergence when an earlier step **produced the invalid state** the gate is reacting to.

#### 5. Is `expected_sequence` sufficient?

**Partially.** Sequence order shows verify precedes submit, but runbook alone does not:

- Map `coverage-service` logs to `coverage_verify`
- Classify c16-02 as verify **deviation** vs verify **success**
- Separate gate behavior at submit from state creation at verify

#### 6. Primary failure mechanism

| Code | Weight | Rationale |
|------|--------|-----------|
| **D** evidence-to-step attribution | **Primary** | c16-02/c16-06 mapped to evidence but divergence assigned to submit step |
| **C** causal reasoning | **Strong secondary** | Enforcement log treated as cause origin |
| **E** root-cause taxonomy | No | Category correct (`entitlement_mismatch`) |
| **A** sequence reasoning | Weak | Model knows sequence but mis-orders causality |
| **F** LLM variance | No | S0 ≡ S3 |

---

### case_17 — logistics_cross_dock (IQS 55.0, step wrong)

| Field | Value |
|-------|-------|
| GT step / category | `cross_dock_transfer` / `webhook_missing` |
| S0/S3 step / category | `last_mile_dispatch` / `webhook_missing` |

#### 1. Evidence for true divergence step

| Log | Role |
|-----|------|
| **c17-04** | `"No carrier handoff webhook received"` — **step-local absence artifact** for `cross_dock_transfer` completion contract |
| **c17-03** | Partial execution at same step (“move initiated”) — step ran but **contract incomplete** |
| **c17-07** | Downstream: `"Route not created: missing handoff event"` — **symptom** referencing missing handoff |

#### 2. Evidence causing wrong-step anchoring

| Log | Why it pulled the model |
|-----|-------------------------|
| **c17-05** | `level: ERROR`, `"Dispatch API timeout"` — **downstream decoy** (GT `decoy_diagnosis`) |
| **c17-07** | Failure at `last_mile_dispatch` — model narrates webhook absence **as dispatch’s failure** |
| **c17-04** | Cited as culprit but **attributed narratively to dispatch**, not `cross_dock_transfer` |

#### 3. Wrong-step classification

**Downstream symptom + upstream decoy (ERROR).**  
Category `webhook_missing` is correct; **step ownership** is wrong. `cross_dock_transfer` is **partially executed** (c17-03), not silent — failure is **missing handoff artifact**, not missing step logs.

#### 4. Distinction the model must make

> Webhook absence is a **`cross_dock_transfer` completion defect** (origin), while dispatch timeout/route failure is **consequence** of missing handoff.

Same root-cause category can apply to logs at different steps; **divergence_step** must attach to the step whose **completion contract** was violated, not the step where the missing prerequisite first **blocks** downstream work.

#### 5. Is `expected_sequence` sufficient?

**No.** Sequence lists four steps but does not define that handoff webhooks belong to `cross_dock_transfer` vs `last_mile_dispatch`. Semantic mapping + violation typing required.

#### 6. Primary failure mechanism

| Code | Weight | Rationale |
|------|--------|-----------|
| **D** evidence-to-step attribution | **Primary** | c17-04 cited but step label follows symptom service (`lastmile`) |
| **C** causal reasoning | **Primary** | Symptom cluster (ERROR + route failure) wins over origin cluster |
| **B** temporal reasoning | Minor | c17-07 timestamp before c17-05; not decisive |
| **A** sequence reasoning | Weak | Model does not walk sequence to assign c17-04 to transfer step |

---

### case_20 — telecom_number_port (IQS 100.0 → 70.0, step **correct**)

| Field | Value |
|-------|-------|
| GT step / category | `carrier_validate` / `sequence_skip` |
| S0 step / category | `carrier_validate` / `sequence_skip` ✓ |
| S3 step / category | `carrier_validate` / `config_drift` ✗ |

#### 1. Evidence for true divergence step

| Log | Role |
|-----|------|
| **c20-02** | `"Validation bypassed: expedite flag set"` — explicit **step-local skip** at `carrier_validate` |
| **c20-06** | `"No carrier validation artifact stored"` — absence artifact at same step |
| **c20-03** | Downstream rejection: `"validation token absent"` — enforcement |

#### 2. Evidence causing wrong **category** (not wrong step)

| Log | Role |
|-----|------|
| **c20-04** | ERROR decoy `"Release polling timeout"` — challenger bait; adjudication **kept baseline** |
| **“expedite flag” framing** | S3 baseline re-run labels bypass as **config_drift** instead of **sequence_skip** |

#### 3. Wrong-step classification

**N/A — step attribution succeeded.**  
Decoy at `number_release` (c20-04) was correctly not selected as divergence step.

#### 4. Distinction the model must make (category, not step)

> Bypass of a required step = `sequence_skip` (process contract not enforced) vs misconfiguration = `config_drift` (rules/map wrong but step attempted normally).

Both can cite c20-02; taxonomy requires interpreting **bypass semantics**, not step placement.

#### 5. Is `expected_sequence` sufficient?

**For step: yes.** For category: **no** — bypass vs config drift is semantic on same log.

#### 6. Primary failure mechanism

| Code | Weight | Rationale |
|------|--------|-----------|
| **F** LLM variance | **Primary (S3 regression)** | Same evidence, same step, different category on independent baseline call |
| **E** root-cause taxonomy | **Primary** | `sequence_skip` vs `config_drift` boundary |
| **D–C** step attribution | **Not implicated** | Step stable at `carrier_validate` |

**Note:** case_20 is included in the user’s focus set but is **not evidence of process-step attribution failure**; it isolates **category stability** under Stage 3’s second baseline invocation.

---

### case_23 — energy_grid_dispatch (IQS 32.5, step wrong)

| Field | Value |
|-------|-------|
| GT step / category | `meter_confirm` / `sequence_skip` |
| S0/S3 step / category | `dispatch_execute` / `race_condition` |

#### 1. Evidence for true divergence step

| Log | Role |
|-----|------|
| **c23-07** | `"Confirm step invoked without dispatch completion"` — **step-local contract breach** at `meter_confirm` |
| **c23-04** | `"Meter confirmation missing dispatch token"` — confirm attempted without valid prerequisite |
| **c23-03** | Dispatch command **was** issued — dispatch largely executed |

#### 2. Evidence causing wrong-step anchoring

| Log | Why it pulled the model |
|-----|-------------------------|
| **c23-05** | `"Dispatch ack received before command logged"` + `clock_skew_ms: 1500` — **temporal decoy** (GT `decoy_diagnosis`) |
| **c23-03** | Paired with c23-05 to construct **race_condition** narrative at `dispatch_execute` |

#### 3. Wrong-step classification

**Temporal decoy at upstream-adjacent step.**  
`dispatch_execute` logs contain an **execution-order anomaly** (not necessarily process-contract skip). True divergence is **`meter_confirm` invoked out of contract** (sequence_skip), not dispatch racing itself.

#### 4. Distinction the model must make

> **Execution anomaly within dispatch** (clock skew, ack ordering) vs **confirm step proceeding without satisfied prerequisite** (sequence contract violation at `meter_confirm`).

Temporal inversion is not automatically divergence; ask whether the step **failed its own completion contract** or merely logged out of order while functionally completing.

#### 5. Is `expected_sequence` sufficient?

**Partially.** Sequence shows confirm follows dispatch, but does not disambiguate:

- Whether skewed ack means dispatch incomplete
- Whether confirm’s token check failure is **origin** vs **symptom of skew**

Requires interpreting c23-07 as **authoritative contract audit** at confirm step.

#### 6. Primary failure mechanism

| Code | Weight | Rationale |
|------|--------|-----------|
| **B** temporal reasoning | **Primary** | Decoy cluster wins attribution |
| **C** causal reasoning | **Primary** | Race narrative explains confirm failure indirectly |
| **D** evidence-to-step attribution | **Strong** | c23-07 in evidence but step label stays at dispatch |
| **A** sequence reasoning | Secondary | Confirm-after-dispatch known but not used to locate skip |

---

## Successful Holdout Cases — Comparison Baseline

| Case | GT step | Step correct? | Decisive pattern |
|------|---------|---------------|------------------|
| **18** | `adjuster_assign` | ✓ 96.0 | **Origin at step:** c18-04 duplicate event **on adjuster-queue**; payment_release block (c18-05) reads as downstream consequence |
| **19** | `recipe_load` | ✓ 97.5 | **Origin at step:** c19-02 explicitly at recipe-service with wrong version in message+metadata |
| **21** | `fee_calculate` | ✓ 82.5 | **Origin at step:** c21-02 metadata/message conflict **inside fee-engine log**; payout block is enforcement |
| **22** | `background_check` | ✓ 100.0 | **Origin at step:** c22-02 false success **at background-service**; c22-03 skip is enforcement |

All four successes share: **the primary culprit log cluster is unambiguously owned by the GT step’s service/semantics**, and downstream failures are narrated as **“blocked/skipped/rejected because …”** rather than as the first contract breach.

---

## Common Structural Difference (Failed vs Successful)

```text
SUCCESSFUL ATTRIBUTION                         FAILED ATTRIBUTION
────────────────────────                       ────────────────────────
┌─────────────────────┐                        ┌─────────────────────┐
│ Step S: ORIGIN log  │  ← culprit here       │ Step S: origin log   │  ← in evidence, not step label
│ (breach co-located) │                        │ (subtle / audit)     │
└──────────┬──────────┘                        └──────────┬──────────┘
           │ downstream                                      │
           ▼                                                 ▼
┌─────────────────────┐                        ┌─────────────────────┐
│ Step S+k: symptom   │  ← evidence only      │ Step S+k: LOUD log  │  ← culprit + step label
│ block/reject/skip   │                        │ ERROR / block / skew │
└─────────────────────┘                        └─────────────────────┘
```

### Quantitative meta contrast (median difficulty_factors)

| Factor | Failed 16/17/23 (median) | Success 18/19/21/22 (median) |
|--------|---------------------------|------------------------------|
| `causal_distance` | **2.5** | 1.5 |
| `competing_hypotheses` | **2** | 1.5 |
| `temporal_ambiguity` | **1** (23 drives 3) | 0 |
| `metadata_conflict` | 1.5 | **2.5** (21/22 high yet succeed) |

**Key insight:** High `metadata_conflict` alone does not predict failure (21, 22 succeed). Failure correlates with **high causal_distance + competing step-level clusters** where the **loudest cluster is not the origin cluster**.

### What failed cases share (mechanism, not surface pattern)

1. **Dual-cluster evidence:** an upstream **origin** cluster (false success, missing artifact, audit of contract breach) and a downstream or adjacent **enforcement/decoy** cluster (block, ERROR, temporal inversion).
2. **Mis-ownership:** logs from step S appear in `evidence_log_ids` but `divergence_step` is assigned to S+k where failure **surfaces**.
3. **Narrative inversion:** upstream behavior misread as **correct** (case_16 verify “correctly identified tiers”) or upstream anomaly misread as **root** when it is **instrumentation noise** (case_23 clock skew).

### What successful cases share

1. **Single decisive origin cluster** at GT step in culprit set.
2. Downstream logs explicitly **reference inherited missing/invalid state** without being the first contract breach.
3. Even with decoys (case_18 payment ACH reject), model keeps duplicate at `adjuster_assign`.

---

## Candidate Generalized Reasoning Principle

### Name

**Step-Local Contract Violation vs Downstream Enforcement Discrimination**

### Precise definition

Before finalizing `divergence_step`, walk `expected_sequence` in order and, for each step **S**, map relevant logs to **S** using service/message semantics (not timestamp alone). For each mapped anomaly, classify it as exactly one of:

| Class | Definition | Divergence candidate? |
|-------|------------|----------------------|
| **Origin violation** | Step **S** failed its **own completion contract**: emitted false success, produced invalid state, bypassed/skipped required work, or logged missing required artifact/event **for S’s completion** | **Yes — primary candidate** |
| **Downstream enforcement** | Step **S** correctly **detected, blocked, or rejected** invalid/missing state inherited from earlier steps; log language is gate/skip/reject “because prerequisite X” | **No — symptom only** |
| **Execution anomaly** | Step **S** shows ordering/timing/infra noise (clock skew, timeout, duplicate delivery) **without** evidence that S’s contract output was wrong or bypassed | **Conditional — not automatic divergence** |

**Selection rule:** Choose the **earliest** step with a supported **origin violation**. Do **not** select a step whose logs are only enforcement or decoy execution anomalies unless **no earlier origin violation exists in the evidence**.

This is **not**:

- Earliest timestamp
- First ERROR
- First “failed/blocked” message
- Topological silence

It **is**:

- Earliest **contract-origin** breach with log support
- Explicit separation of **state creation** vs **state rejection**

### Why it should generalize

1. **Matches successful holdout structure:** 18/19/21/22 already follow origin-at-S / symptom-at-S+k; principle codifies what the model does when it succeeds.
2. **Addresses all three step failures without case-specific rules:** 16 (verify origin vs submit enforcement), 17 (transfer webhook origin vs dispatch ERROR), 23 (confirm skip origin vs dispatch temporal decoy).
3. **Aligns with existing prompt intent** but makes the **classification step explicit** — current `BASELINE_INSTRUCTIONS` says “earliest divergence” and “don’t treat loudest ERROR as root” yet holdout shows the model still collapses enforcement into divergence.
4. **Dev benchmark decoy cases** (e.g. payment timeout downstream of coupon) share the same enforcement-vs-origin structure; principle should reinforce rather than contradict frozen 89.1% behavior.

### Examples from holdout (≥2)

**case_16**

- Origin: c16-02/c16-06 at `coverage_verify` — false “verified” / tier mismatch (**origin violation**).
- Enforcement: c16-03 at `prior_auth_submit` — block given bad tier (**downstream enforcement**).
- Principle selects `coverage_verify`.

**case_17**

- Origin: c17-04 at `cross_dock_transfer` — handoff webhook missing (**origin violation**); c17-03 partial execution does not negate this.
- Enforcement/decoy: c17-07 enforcement, c17-05 ERROR decoy at `last_mile_dispatch`.
- Principle selects `cross_dock_transfer`.

**case_23** (third validating example)

- Origin: c23-07/c23-04 at `meter_confirm` — confirm without dispatch completion (**origin / sequence_skip**).
- Execution anomaly: c23-05 at `dispatch_execute` — clock skew ack (**execution anomaly**, not contract origin).
- Principle selects `meter_confirm`.

### Possible false positives

| Scenario | Risk |
|----------|------|
| True divergence genuinely at downstream step S+k (misconfiguration local to that step) | Principle could over-pull upstream if any ambiguous log exists earlier |
| Partial execution logged at S misclassified as “complete enough” | Could miss origin when only enforcement logs exist (not seen in 16/17/23 — origin logs exist) |
| Legitimate `race_condition` at S where contract truly failed due to concurrency | Could demote real race at dispatch if confirm also logged token failure |

### Possible false negatives

| Scenario | Risk |
|----------|------|
| Origin violation **only** inferable from downstream text with no step-local log | Principle requires origin support at S; silent/async cases without audit logs may still fail |
| Origin and enforcement on **same step** (step both breaches and logs ERROR) | Classification collapse — may need tie-break (not case-specific: general “same-step origin wins”) |

### Placement: baseline, Stage 3, or both?

| Layer | Recommendation | Rationale |
|-------|----------------|-----------|
| **Baseline prompt** | **Primary** | Step selection happens here; holdout S0 failures (16, 17, 23) are baseline-equivalent |
| **Stage 3 rule_checker** | **Secondary** | Structured per-step walk already exists; add explicit origin/enforcement/execution tags to hypotheses |
| **Adjudication gates** | **No change in experiment** | Gates only help when baseline is upstream; they cannot fix baseline downstream anchoring (16, 17, 23) |

**case_20 note:** Principle does not address category variance; keep category experiment separate.

### Estimated risk to 89.1% dev checkpoint

| Risk level | Estimate | Basis |
|------------|----------|-------|
| **Overall** | **Low–moderate (−0 to −3 pp plausible, +0 to +2 pp upside)** | Principle reinforces existing decoy-defense intent; dev failures are often downstream anchoring |
| **Regression vector** | Downstream-true-divergence cases rare in dev | Over-upstreaming |
| **Stage 3 interaction** | Neutral for step | case_20 shows category variance independent of step logic |
| **Experiment design** | Single-variable baseline prompt addition; revert if dev IQS &lt; 89.1% or recall floor violated | Matches project experiment protocol |

---

## Hypothesis Verdict

| Question | Answer |
|----------|--------|
| Is process-step attribution the core holdout gap? | **Yes** for 16/17/23 (62.5% S3 divergence accuracy) |
| Is one generalized principle identifiable without case-specific rules? | **Yes** — Step-Local Contract Violation vs Downstream Enforcement Discrimination |
| Is `expected_sequence` alone enough? | **No** — requires log-to-step mapping + violation class typing |
| Should we implement now? | **No** — analysis only per user constraint |

---

## Final Verdict

### **IMPLEMENT EXPERIMENT**

Run a **single-variable baseline prompt experiment** adding the Step-Local Contract Violation vs Downstream Enforcement Discrimination principle (explicit origin / enforcement / execution-anomaly classification before selecting `divergence_step`). Evaluate on frozen 15-case dev checkpoint first; holdout is diagnostic only.

**Not REJECT** — structural difference is stable across failed vs successful holdout cases and matches known dev decoy patterns.

**Not NEEDS MORE EVIDENCE** — raw logs, GT, predictions, and successful-case contrast supply sufficient mechanistic grounding; further evidence would be empirical (A/B), not forensic.

---

## Production Code Status

- No modifications to production code, prompts, gates, schemas, benchmark, or scoring.
- Analysis artifact: `results/step_attribution_analysis.md`
