# Solution Video Script (3–4 minutes)

**Hackathon requirement:** Problem → baseline → realistic execution → architecture → results → failed experiment → holdout honesty.

**Existing asset:** ~1:28 clean product demo footage (Landing → Case 01 → investigation → post-mortem). **Embed this clip** at **0:50–2:20** below; record voiceover separately if needed.

---

## 0:00–0:30 — Problem + user + bottleneck

**Visual:** Landing page hero or analyst-style log collage.

**Voiceover:**

> RevOps and business operations analysts investigate silent workflow failures — orders stuck, provisioning incomplete — across four to six systems. Logs look healthy: HTTP 200, no obvious ERROR. The bottleneck is not missing data; it is **attributing the earliest process divergence** and **proving it with the right evidence**, without conflating downstream symptoms with root cause.

---

## 0:30–0:50 — Simple baseline + initial result

**Visual:** Architecture diagram (single prompt) or terminal running Stage 0.

**Voiceover:**

> We started with a single-prompt baseline. After forensic prompt hardening, the frozen Stage 0 checkpoint reached **89.06%** mean Investigation Quality Score on our fixed fifteen-case development benchmark. That is strong — but a single prompt still risks plausible wrong stories on decoy-heavy silent failures, and it cannot enforce no-fabrication structurally.

**On-screen text:** Stage 0: **89.06%** IQS (15-case dev benchmark)

---

## 0:50–2:20 — Realistic product execution

**Visual:** **[INSERT EXISTING ~1:28 DEMO FOOTAGE]**

Script beats to match footage:

1. Landing → **Try Now**
2. Case **01** selected → **Investigate Incident**
3. Loader (processing phases)
4. **What failed?** — divergence + root cause + explanation
5. **How it unfolded** — root cause → downstream consequence
6. **Why we believe this** — evidence cards
7. **Explore Evidence** — raw log JSON
8. **View Post-Mortem** → **Export Markdown / JSON**

**Voiceover (during clip):**

> This is the shipped investigator: immutable Stage 3 diagnosis, causal chain, grounded evidence, and an export-ready post-mortem — about twenty to thirty seconds per case with a live API key.

---

## 2:20–2:50 — Architecture

**Visual:** README mermaid diagram or simplified slide.

**Voiceover:**

> Stage 3 runs: deterministic timeline, baseline diagnosis, rule-checker challenger, adjudication verifier, then **deterministic safety gates** — including same-step causal role and no-fabrication checks. The diagnosis is frozen. Evidence is pre-hydrated in Python; the post-mortem reporter explains but cannot rewrite divergence or culprit logs.

**On-screen text:**

```text
Baseline → Challenger → Adjudicator → Gates → Hydrate → Reporter → UI
```

---

## 2:50–3:20 — Final comparison (dev benchmark)

**Visual:** Evaluation tab in UI (dev + holdout sections).

**Voiceover:**

> On the fixed development benchmark: Stage 0 **89.06%**, Stage 3 **89.73%** — a **+0.67 percentage point** gain. Modest on mean IQS because the forensic baseline is already high; Stage 3 adds **100% divergence accuracy**, **97.78% evidence recall**, and **100% no-fabrication** on this set. These are evaluation metrics — not universal product accuracy.

**On-screen text:**

| | IQS |
|--|-----|
| Stage 0 | 89.06% |
| Stage 3 | 89.73% |
| Delta | +0.67 pp |

---

## 3:20–3:45 — One removed experiment

**Visual:** `docs/SUBMISSION_CHANGELOG.md` section or simple slide: "Step attribution prompt → 82.3%"

**Voiceover:**

> We tried explicit step-attribution hints in the baseline prompt to improve holdout generalization. Development IQS **dropped to 82.3%** with broad regressions. We reverted it. Lesson: holdout-diagnosed problems need structural classification, not prompt stuffing on the dev set.

---

## 3:45–4:00 — Holdout + honest limitation + close

**Visual:** Evaluation tab holdout block (red section).

**Voiceover:**

> We report an independent eight-case holdout never used for tuning: Stage 0 **78.56%**, Stage 3 **74.81%**. The gap is step attribution under distribution shift — not hidden overfitting. The product value is the verified investigation pipeline; the research frontier is attributing sparse evidence to the correct process step. Repository and reproduction steps are in the README.

**On-screen text:** Holdout: 78.56% → 74.81% (−3.75 pp) · not used for tuning

---

## Production checklist

- [ ] Record or reuse 1:28 demo segment (1080p, show URL bar if using ngrok)
- [ ] Record voiceover or live narration
- [ ] Blur/obscure API keys in `.env` if terminal shown
- [ ] Upload unlisted/public video; link in hackathon submission form
- [ ] Add video URL to `docs/SUBMISSION_CHECKLIST.md` when available
