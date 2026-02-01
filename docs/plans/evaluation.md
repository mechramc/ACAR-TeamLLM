# TeamLLM Evaluation System Design

**Version:** 1.0  
**Last Updated:** 2026-01-13  
**Scope:** Arena Mode evaluation (Milestone A / MVP)  
**Status:** Design approved  

---

## 1. Purpose & Non-Goals

### Purpose
`evaluation.md` defines **how TeamLLM determines quality, correctness, and superiority** among competing model responses.

It specifies:
- Judge authority and roles
- Evaluation policies and constraints
- Bias mitigation and blindness guarantees
- Disagreement resolution
- Artifact visibility and auditability

The evaluation system is designed to be:
- Deterministic by default
- Auditable and replayable
- Resistant to bias and gaming
- Extensible to future modes (research, consensus, human calibration)

### Non-Goals (MVP)
The following are explicitly out of scope for Arena Mode MVP:
- Autonomous judge learning or self-modification
- User-defined judge prompts without schema enforcement
- Removal or bypassing of verifier gates
- Multiple winners or abstention outcomes
- Unbounded human-in-the-loop evaluation

---

## 2. Judge Authority Model

### 2.1 Default Authority Model (Hierarchical)

TeamLLM uses a **Hierarchical Evaluation Model** by default:

```
Verifier Judge → Ranker Judge → Scoring Engine
```

| Stage | Responsibility | Authority |
|------|----------------|-----------|
| Verifier | Admissibility / quality gate | Absolute |
| Ranker | Relative ordering of valid candidates | Authoritative |
| Scoring | Final numeric score computation | Deterministic |

**Invariants**
- Earlier stages constrain later ones
- Disqualified responses cannot re-enter
- Exactly one winner must be produced (or the run fails)

This model prioritizes clarity, auditability, and enterprise suitability.

---

### 2.2 User-Selectable Evaluation Policy (Constrained)

Users may customize evaluation **policy**, but not **authority**.

```yaml
evaluation_policy:
  type: hierarchical
  version: v1
  overrides:
    ranking_strategy: listwise
    tiebreaker: consensus
    gate_thresholds:
      correctness: 7
      constraint_adherence: 8
```

### 2.3 Non-Negotiable System Invariants
The following cannot be overridden:
- A verifier gate must exist
- Minimum quality thresholds must be enforced
- Exactly one winner must be produced
- All judgments must be logged and replayable

> **Design principle:** Users may customize *policy*, not *authority*.

---

## 3. Judge Roles & Types

Arena Mode supports three judge types in MVP:
- LLM Judges
- Rule-Based Judges
- Hybrid Judges (LLM + Rules)

Human judges are excluded from MVP to preserve determinism.

---

### 3.1 LLM Judges

LLM Judges evaluate subjective qualities using structured prompts and schemas.

**Roles**
- Verifier
- Ranker
- Tiebreaker

**Constraints**
- Temperature = 0 (or provider minimum)
- Fixed prompt + rubric version
- Structured JSON output
- Blind to model identity

**Strengths**
- Expressive
- Research-aligned (LLM-as-a-Judge)
- Domain-flexible

---

### 3.2 Rule-Based Judges

Rule-based judges enforce deterministic constraints.

**Typical checks**
- JSON schema validity
- Required fields
- Length limits
- Safety and policy filters

**Properties**
- Zero variance
- Fully deterministic
- Ideal for hard constraints

---

### 3.3 Hybrid Judges

Hybrid judges apply rules first, then LLM judgment.

**Example (Verifier)**
1. Rule checks: format, schema, safety
2. LLM checks: correctness, completeness

> **Design principle:** Rules decide what is admissible. Models decide what is good.

---

### 3.4 Exclusion of Human Judges (MVP)

Human judges are excluded due to:
- Non-determinism
- Limited replayability
- Operational overhead

Future use cases include calibration, gold dataset creation, and dispute resolution.

---

## 4. Bias Controls & Blindness Guarantees

TeamLLM uses **Adaptive Blindness**.

| Role | Visibility |
|-----|------------|
| Verifier | Fully blind |
| Ranker | Partially blind |
| Scoring | Fully informed |

---

### 4.1 Verifier Judge (Full Blindness)

Verifier sees:
- Task
- Single response

Verifier does not see:
- Model identity
- Cost, tokens, latency

Purpose: determine admissibility only.

---

### 4.2 Ranker Judge (Partial Blindness)

Ranker sees:
- Task
- All qualified responses
- Optional neutral metadata (length bucket)

Ranker does not see:
- Model identity
- Cost or pricing

Purpose: relative quality ordering.

---

### 4.3 Scoring Engine (Fully Informed)

Scoring engine sees:
- Rank position
- Quality scores
- Cost and token metrics
- System constants

Purpose: deterministic final score computation.

---

### 4.4 Bias Mitigation Techniques
- Blind shuffling
- Fixed rubrics
- Versioned prompts
- Judge disagreement tracking

---

## 5. Disagreement, Ties & Uncertainty

Arena Mode enforces a **Force-Winner Policy**.

> If evaluation completes, exactly one winner must be selected.

### 5.1 Tie Resolution Order
1. Ranker ordering
2. Tiebreaker judge (if configured)
3. Deterministic fallback rules (cost, tokens, stable ID)

### 5.2 Uncertainty Metadata
Uncertainty is recorded but does not block outcome.

```json
{
  "winner": "resp_123",
  "margin": 1.7,
  "tie_resolved_by": "TIEBREAKER"
}
```

Abstention is not allowed in Arena Mode.

---

## 6. Evaluation Artifacts & Auditability

### 6.1 Artifact Capture (Mandatory)
Captured for every run:
- Judge verdicts and rankings
- Scoring components
- Prompt and rubric versions
- Seeds and shuffle order
- Judge model IDs

---

### 6.2 Default Visibility Policy

Evaluation artifacts are **internal by default**.

Users receive:
- Final winner
- Primary output only

This prevents:
- Evaluation gaming
- Prompt leakage
- Contract ambiguity

---

### 6.3 Explicit Opt-In Visibility

```yaml
evaluation_policy:
  artifact_visibility:
    enabled: true
    level: summary  # none | summary | full
```

| Level | Description |
|------|-------------|
| none | Default |
| summary | Winner explanation + margin |
| full | Complete judge artifacts (restricted) |

---

### 6.4 Safety & Access Controls
- Role-based access
- Sensitive field redaction
- Explicit user acknowledgment

---

### 6.5 Audit & Replay Guarantees
- All artifacts retained internally
- All decisions replayable
- All evaluations attributable to versions and models

> **Design principle:** Transparency must be intentional, not accidental.

---

## 7. Evaluation-Aware Runs (Phase 7.2 Clarification)

All competitive evaluation in TeamLLM uses **Evaluation-Aware Runs**, where models are explicitly informed of constraints that can disqualify or penalize them.

### 7.1 Evaluation Contract

Every model call in an Evaluation-Aware run receives the following contract appended to its system prompt:

```
=== EVALUATION CONSTRAINTS ===
- You must complete your entire response within {{expected_output_tokens}} output tokens.
- Responses that are truncated or incomplete will be excluded from evaluation.
- Do not exceed the requested scope or length.
- Conciseness is preferred; excessive verbosity may be penalized.
===
```

### 7.2 Fairness Rationale

| Principle | Implementation |
|-----------|----------------|
| No surprise disqualification | Truncation consequence disclosed |
| Equal information | Identical contract to all models |
| Transparent penalties | Verbosity warning stated |
| Neutral language | Provider-agnostic wording |

### 7.3 Truncation Semantics

1. Model is informed of token limit (`expected_output_tokens`)
2. Model is informed of truncation consequence (exclusion)
3. API-level hard limit (`max_tokens`) enforces cutoff
4. Truncation detected via `finish_reason` and content analysis
5. Truncated responses marked `DISQUALIFIED` with reason `RESPONSE_TRUNCATED`
6. Content preserved for forensic inspection

---

## 8. Blind Runs (Planned — Post-MVP)

Blind Runs are a research mode where models are **NOT** informed of evaluation constraints.

### 8.1 Purpose

- Observe natural model behavior without constraint awareness
- Study verbosity tendencies, truncation patterns, self-regulation
- Gather behavioral data for research analysis

### 8.2 What Blind Runs Measure vs. Don't Measure

| Measures | Does NOT Measure |
|----------|------------------|
| Natural output length distribution | Fair competitive ranking |
| Truncation without warning | Constraint-aware performance |
| Model-specific verbosity bias | Publishable winner selection |

### 8.3 Explicit Statement

> **Blind runs are never ranked.**
>
> Results from Blind runs cannot be used for:
> - Winner selection
> - Model comparisons
> - Quality claims
> - Fairness assessments

### 8.4 Implementation Status

Blind Runs are **not implemented** in MVP. No UI, API flags, or execution logic exists.

---

## 9. Experimental Regimes Separation

TeamLLM enforces strict separation between experimental regimes.

### 9.1 Core Rule

> **Evaluation-Aware and Blind runs are never mixed in any analysis.**

### 9.2 Regime Properties

| Property | Evaluation-Aware | Blind (Post-MVP) |
|----------|------------------|------------------|
| Contract injection | Yes | No |
| Ranking | Yes | Never |
| Scoring | Yes | Never |
| Winner selection | Yes | Never |
| Research validity | Publishable | Observational only |

### 9.3 Why This Matters

Mixing regimes would:
- Introduce confounding variables (informed vs. uninformed)
- Create unfair comparisons
- Undermine research credibility
- Violate the fairness principle

---

## Document History

| Version | Date | Notes |
|-------|------|------|
| 1.0 | 2026-01-13 | Initial Arena Mode evaluation design |
| 1.1 | 2026-01-16 | Added Evaluation-Aware Runs, Blind Runs, Experimental Regimes Separation (Phase 7.2) |
