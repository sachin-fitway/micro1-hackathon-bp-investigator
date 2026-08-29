# Agent Trajectory Guide (Submission Package)

This folder contains **sanitized, representative trajectories** for hackathon review. They are derived from real runtime logs under `trajectories/` (gitignored) produced by `shared/trajectories.py` during live Stage 3 + post-mortem runs.

## Sanitization policy

Each file removes:

- `prompt_built` events and full `instructions` fields
- System prompts and chain-of-thought
- API keys and secrets
- Full raw log payloads (except cited log IDs)

Each file preserves:

- Agent name, event type, step order
- Observable outputs (diagnosis fields, gate blocks, adjudication decisions)
- Retry counts and verifier feedback strings
- Evidence hydration summaries (log IDs only)

## Recommended reading order

1. `case_01_stage3_investigation_chain.json` — end-to-end Stage 3 flow (happy path)
2. Per-agent slices below
3. `case_03_stage3_decoy_chain.json` — decoy/symptom case (optional contrast)

---

## File index

| File | Agent / role | Why representative |
|------|----------------|-------------------|
| `01_preprocess_timeline.json` | **preprocess** | Deterministic timeline construction before any LLM call |
| `02_baseline_diagnosis.json` | **baseline** | Single forensic prompt → structured `InvestigationResult` (Case 01: `inventory_reserve` / `sequence_skip`) |
| `03_rule_checker_challenger.json` | **rule_checker** | Challenger hypothesis board output competing with baseline |
| `04_orchestrator_adjudication_flow.json` | **orchestrator** | Hypothesis pairing and keep/override routing |
| `05_adjudication_verifier.json` | **adjudication verifier** | LLM adjudication decision + deterministic gate blocks |
| `06_post_mortem_reporter.json` | **post_mortem_reporter** | Pre-hydrated evidence lookup + report generation (diagnosis unchanged) |
| `case_01_stage3_investigation_chain.json` | **full chain** | All agents in order for Case 01 (canonical demo case) |
| `case_03_stage3_decoy_chain.json` | **full chain** | Case 03 decoy pattern — shows challenger/adjudication under symptom noise |

## Agent responsibilities (mapped to architecture)

```text
preprocess          → timeline_built
baseline            → llm_response (diagnosis)
rule_checker        → hypothesis_board / hypothesis_selected
orchestrator        → hypotheses_prepared / adjudication_keep_baseline | override
verifier            → adjudication_started / adjudication_complete (+ gate blocks)
post_mortem_reporter → logs_retrieved (LogLookupTool) / report_generated
```

## Evidence / log lookup

There is no runtime tool-calling loop. **Evidence hydration** is implemented in Python (`agents/log_lookup.py`, invoked from `post_mortem_reporter`) and logged as `logs_retrieved` events in `06_post_mortem_reporter.json`.

## Reproducing fresh trajectories (judges)

```bash
cp .env.example .env   # set OPENROUTER_API_KEY
python incident_investigation.py --cases case_01 --stage 3
# writes trajectories/case_01_stage3.jsonl and trajectories/case_01_stagepost_mortem.jsonl
```

Do **not** commit the full `trajectories/` directory — it accumulates multiple runs. Use this `docs/trajectories/` package for submission.

## UI parity

The product UI trace (`Show investigation process`) applies the same sanitization rules as `ui/trace_parser.py`: skips `prompt_built`, shows observable phases only.
