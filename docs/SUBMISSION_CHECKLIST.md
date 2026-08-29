# Hackathon Submission Checklist

Maps **micro1 Agentic Workflows Hackathon** deliverables to repository evidence.

**Repository:** https://github.com/sachin-fitway/micro1-hackathon-bp-investigator  
**Last verified:** 2026-08-29 · **155/155 tests passing**

---

## Official deliverables

| # | Requirement | Evidence | Path / artifact | Status |
|---|-------------|----------|-----------------|--------|
| 1 | **Complete solution code** | Full Python + UI source | Repo root (`agents/`, `shared/`, `workflows/`, `ui/`, …) | ✅ Ready |
| 1b | **Improvement changelog** | Evolution + experiments | `docs/SUBMISSION_CHANGELOG.md`, `README.md` § Improvement Changelog | ✅ Ready |
| 2 | **Reproduction guide** | Setup, eval, UI, tests | `README.md` § Setup, Demo, Reproduction & Inspection | ⚠️ Gaps (see below) |
| 3 | **Solution video** | 3–4 min walkthrough | `docs/SUBMISSION_VIDEO_SCRIPT.md` | ❌ **Not recorded yet** |
| 4 | **Representative agent trajectories** | Sanitized JSON per agent | `docs/trajectories/`, `docs/TRAJECTORY_GUIDE.md` | ✅ Ready |

---

## Evaluation & honesty

| Item | Evidence | Path | Status |
|------|----------|------|--------|
| Dev benchmark (15 cases) | S0 89.06%, S3 89.73%, +0.67 pp | `results/eval_submission.json` | ✅ Committed |
| Holdout (8 cases) | S0 78.56%, S3 74.81%, −3.75 pp | `results/eval_holdout.json` | ✅ Committed |
| Holdout not used for tuning | Documented | `docs/SUBMISSION_CHANGELOG.md` §7, README | ✅ |
| UI shows dev + holdout | Evaluation tab | `/investigate?view=evaluation` | ✅ |
| Non-canonical experiments marked | ARCHIVED docstrings | `run_step_attribution_experiment.py`, `run_constrained_upstream_experiment.py` | ✅ |
| Forensic analyses | Holdout + attribution write-ups | `results/holdout_forensic_analysis.md`, `results/step_attribution_analysis.md` | ✅ Committed |

---

## Code quality & safety

| Item | Evidence | Path | Status |
|------|----------|------|--------|
| Automated tests | 155 passing | `tests/`, `pytest tests/ -q` | ✅ |
| Secrets excluded | `.env` gitignored | `.gitignore` | ✅ |
| Example env (no secrets) | Empty key placeholder | `.env.example` | ✅ |
| Runtime trajectories excluded | Full JSONL not in repo | `trajectories/` gitignored | ✅ |
| Dependencies | Pinned list | `requirements.txt` | ✅ |
| LLM provider documented | OpenRouter only | `README.md` § LLM Provider | ✅ |

---

## Product demo assets

| Item | Evidence | Path | Status |
|------|----------|------|--------|
| Web UI | Landing + investigate + evaluation | `run_ui.py`, `ui/static/` | ✅ |
| 15 benchmark cases | Selectable grid | `data/cases/case_01.json` … `case_15.json` | ✅ |
| Demo post-mortems | Pre-generated reports | `reports/case_{01,11,14,15}_post_mortem.md` | ✅ |
| JSON artifacts | PostMortemArtifact samples | `reports/artifacts/case_*_post_mortem.json` | ✅ |
| Live demo requires API key | Documented | README § LLM Provider | ✅ |

---

## Licenses & credentials

| Item | Status | Notes |
|------|--------|-------|
| Open-source license file | ❌ **Missing** | No `LICENSE` in repo — add MIT/Apache if hackathon requires |
| Third-party licenses | ⚠️ Partial | Python deps via `requirements.txt`; no aggregated NOTICE file |
| Judge credentials | N/A | Judges supply own `OPENROUTER_API_KEY` |
| `.env` in repo | ✅ Excluded | Never commit |

---

## Reproduction guide — remaining gaps

Review of `README.md` vs hackathon “clean environment reproduction” requirement:

| Gap | Severity | Recommendation |
|-----|----------|----------------|
| **No pinned Python version** | P1 | Add “Python 3.11+” (or exact version used) to README Setup |
| **No approximate API cost estimate** | P1 | Add note: ~15 LLM calls/case Stage 3 + post-mortem; full eval ~47 calls × 15 cases; est. $0.50–2 on Gemini Flash via OpenRouter (varies) |
| **Fresh eval may differ from 89.73%** | P0 (documentation) | Already stated — judges should use committed `eval_submission.json` |
| **No Docker / one-command repro** | P2 | Optional `Makefile` or script — not required if README steps suffice |
| **Video URL placeholder** | P0 (deliverable) | Record and add link to submission form + this checklist |
| **Solution video not uploaded** | P0 (deliverable) | Follow `docs/SUBMISSION_VIDEO_SCRIPT.md` |
| **LICENSE file absent** | P1 | Add if organizers require explicit license |

---

## Pre-submit actions (human)

1. [ ] Record/upload **3–4 min solution video** (script in `docs/SUBMISSION_VIDEO_SCRIPT.md`)
2. [ ] Add **video URL** to hackathon submission portal
3. [ ] Confirm **ngrok/live demo URL** works for judges (optional)
4. [ ] Add **LICENSE** if required by hackathon rules
5. [ ] `git add docs/` + commit + push submission docs
6. [ ] Do **not** commit `.env`, `trajectories/`, or local experiment JSON

---

## Quick verification commands

```bash
pytest tests/ -q
python -c "import json; d=json.load(open('results/eval_submission.json')); print(d['stage_means_iqs'])"
python run_ui.py   # requires OPENROUTER_API_KEY in .env
```

Expected: `{0: 89.06…, 3: 89.73…}` and 155 passed tests.
