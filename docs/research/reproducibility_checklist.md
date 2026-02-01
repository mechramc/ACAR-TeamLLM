# Reproducibility Checklist

## Overview

This checklist ensures all TeamLLM experiments are fully reproducible. Every item must be verified before publishing results.

## 1. Prompts & Templates

### System Prompts
- [ ] All system prompts stored in version control
- [ ] Prompt template version recorded in run metadata (`prompt_template_version`)
- [ ] SHA-256 hash of prompt content stored (`prompt_template_hash`)
- [ ] Evaluation Contract text included verbatim

### User Prompts
- [ ] Task descriptions stored in task suite manifest
- [ ] No dynamic prompt generation without seed control
- [ ] Constraint lists fully specified

## 2. Seeds & Randomness

### Fixed Seeds
- [ ] Global seed specified for each run (`run.seed`)
- [ ] Per-task seeds in task suite manifest (`TaskSuiteEntry.seed`)
- [ ] Presentation order shuffle uses run seed
- [ ] Judge rotation uses run seed

### Seed Documentation
- [ ] Seed values recorded in all events
- [ ] Seed-dependent operations identified in code
- [ ] No unseeded random operations in evaluation path

## 3. Model Versions

### Model Identification
- [ ] Full model identifiers used (e.g., `openai:gpt-4-0613`)
- [ ] Model versions pinned (not aliases like "gpt-4")
- [ ] Provider API versions documented

### Model Configuration
- [ ] Temperature recorded (default: 0.0)
- [ ] Max tokens recorded (`effective_max_tokens`)
- [ ] Any model-specific parameters logged

## 4. Judge Configuration

### Judge Prompts
- [ ] Judge prompt templates in version control
- [ ] Judge prompt version recorded (`judge_policy_version`)
- [ ] Scoring rubric version recorded (`rubric_version`, `rubric_hash`)

### Judge Selection
- [ ] Judge model ID recorded (`judge_model_id`)
- [ ] Judge pool configuration logged
- [ ] Audit rate specified and logged

### Audit Trail
- [ ] JUDGE_SELECTED events for all stages
- [ ] AUDIT_EVALUATION_TRIGGERED events when audited
- [ ] AUDIT_DISAGREEMENT_DETECTED events when disagreement occurs

## 5. Evaluation Policy

### Policy Documentation
- [ ] Evaluation policy named and versioned (`evaluation_policy`)
- [ ] Policy hash computed if custom (`evaluation_policy_hash`)
- [ ] Scoring constants documented:
  - LAMBDA (latency factor)
  - MU (verbosity penalty)
  - NU (efficiency bonus)
  - QUALITY_THRESHOLD
  - HARD_COST_CEILING_USD
  - SOFT_COST_CAP

### Verification Rules
- [ ] Verifier rules documented
- [ ] Disqualification criteria specified
- [ ] Quality gate thresholds recorded

## 6. Event & Artifact Persistence

### Event Log Completeness
- [ ] RUN_CREATED events with full config
- [ ] STATE_TRANSITION events for all state changes
- [ ] MODEL_CALL_STARTED/COMPLETED events
- [ ] VERIFICATION_COMPLETED events
- [ ] RANKING_COMPLETED events
- [ ] SCORING_COMPLETED events with full breakdown
- [ ] WINNER_SELECTED events with margin
- [ ] BIAS_REPORT_COMPUTED events
- [ ] CONFIDENCE_SCORE_COMPUTED events

### Artifact Storage
- [ ] Response content preserved (`content_text`)
- [ ] Token counts recorded (`tokens_in`, `tokens_out`)
- [ ] Cost estimates stored (`estimated_cost_usd`)
- [ ] Truncation status recorded (`was_truncated`)

## 7. Budget & Routing Configuration

### Budget Settings
- [ ] Max total cost recorded (`max_total_cost_usd`)
- [ ] Budget warnings logged (`BUDGET_WARNING`)
- [ ] Cost estimation method documented

### Routing Configuration
- [ ] For baseline: routing table version stored
- [ ] For Arena: model selection recorded (`selected_models`)
- [ ] Pinch-hit triggers logged if applicable

## 8. Environment Fingerprint

### Compute Environment
- [ ] Environment fingerprint computed and stored
- [ ] Components of fingerprint:
  - Python version
  - Key dependency versions
  - OS information
  - Timestamp

### API Configuration
- [ ] Provider endpoints documented
- [ ] API timeout values recorded
- [ ] Rate limit handling documented

## 9. Task Suite Integrity

### Suite Verification
- [ ] Suite version recorded (`suite_version`)
- [ ] Suite content hash verified (`content_hash`)
- [ ] Task count matches expected

### Task-Level
- [ ] All task IDs unique within suite
- [ ] Ground truth references where applicable
- [ ] Constraint lists non-empty where required

## 10. Statistical Analysis

### Data Preparation
- [ ] Outlier handling documented
- [ ] Missing data handling documented
- [ ] Normalization methods specified

### Tests & Thresholds
- [ ] Statistical tests named
- [ ] Significance threshold (alpha) specified
- [ ] Effect size measures included
- [ ] Multiple comparison corrections if applicable

## Verification Commands

```bash
# Verify task suite integrity
python -c "
from app.schemas.task_suite import TaskSuiteManifest
import json
with open('backend/app/data/task_suites/benchmark_v1.json') as f:
    manifest = TaskSuiteManifest.from_dict(json.load(f))
print(f'Suite: {manifest.suite_name} v{manifest.suite_version}')
print(f'Tasks: {manifest.task_count}')
print(f'Hash: {manifest.content_hash}')
"

# Verify all events captured for a run
# SELECT event_type, COUNT(*) FROM events WHERE run_id = ? GROUP BY event_type;

# Verify reproducibility metadata present
# SELECT seed, prompt_template_version, prompt_template_hash, rubric_version
# FROM runs WHERE run_id = ?;
```

## Sign-off

| Checkpoint | Reviewer | Date | Notes |
|------------|----------|------|-------|
| Prompts & Seeds | | | |
| Model Versions | | | |
| Judge Config | | | |
| Event Completeness | | | |
| Environment | | | |
| Task Suite | | | |
| **Final Approval** | | | |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Phase 10 | Initial checklist |
