# TeamLLM Contracts (contracts.md)
**Version:** 0.2
**Last Updated:** 2026-01-18
**Purpose:** Canonical domain contracts for TeamLLM Research MVP + ACAR Integration (FastAPI + Postgres + Alembic).
**Scope:** Entities, identifiers, lifecycles, immutability rules, and cross-entity invariants. This document is intentionally implementation-oriented and must be treated as a *build contract*.

---

## 0) Design Principles

1. **Research-grade auditability where it matters** (Runs, Experiments, Responses, Evaluations, Artifacts are append-only).
2. **Authoring flexibility where safe** (Tasks may be edited **only** while `Task.status = DRAFT` and before any Run exists).
3. **No silent mutation**: if an object is immutable, changes are new rows with new IDs (or explicit `INVALIDATED` marker when applicable).
4. **Reproducibility first**: every Run captures enough metadata to be replayed (seed, model ids/versions, prompt template hash, rubric version, environment fingerprint).

---

## 1) Canonical Identifiers

All primary identifiers are **UUID v4** unless otherwise noted.

- `task_id: UUID`
- `run_id: UUID`
- `response_id: UUID`
- `evaluation_id: UUID`
- `experiment_id: UUID`
- `artifact_id: UUID`
- `experience_id: UUID` *(v0.2: ACAR)*
- `trace_id: UUID` *(v0.2: Decision Trace)*
- `round_id: UUID` *(v0.2: Deliberation Round)*
- `model_id: string` (provider-stable id, e.g. `openai:gpt-4o-2025-xx`, `anthropic:claude-sonnet-4.5`, `google:gemini-2.0-flash`)
- `judge_id: string` (may be a model_id or `human:<name|team>`)

**Correlation / trace ids (recommended):**
- `request_id: string` (UUID or ULID), generated per inbound API request
- `idempotency_key: string` (client-provided)

---

## 2) Lifecycles (Enums)

### 2.1 TaskStatus
- `DRAFT`
- `READY`
- `ARCHIVED`

### 2.2 RunStatus (Arena Mode)

**Execution States (per runtime.md §2):**
- `PENDING` — Run created, awaiting execution
- `EXECUTING` — Model calls in progress
- `COLLECTING` — Gathering and validating responses
- `VERIFYING` — Running Verifier judge gate
- `RANKING` — Running Ranker judge (+ deliberation if enabled)
- `SCORING` — Calculating final scores
- `COMPLETED` — Winner selected, run finalized

**Failure States:**
- `FAILED_TIMEOUT` — Insufficient candidates within timeout
- `FAILED_INSUFFICIENT_CANDIDATES` — <2 valid responses collected
- `FAILED_ALL_DISQUALIFIED` — All candidates failed verification
- `FAILED_BUDGET_EXCEEDED` — Pre-check rejected due to budget
- `FAILED_TERMINAL` — Unrecoverable error
- `CANCELLED` — User or system cancellation

### 2.3 ExperimentStatus
- `CREATED`
- `RUNNING`
- `PAUSED`
- `COMPLETED`
- `FAILED_TERMINAL`
- `CANCELLED`

### 2.4 ResponseStatus
- `PENDING`
- `RECEIVED`
- `VALIDATED`
- `DISQUALIFIED`
- `EVALUATED`
- `WINNER`

### 2.5 EvaluationStatus
- `PENDING`
- `COMPLETED`
- `INVALIDATED`

### 2.6 ArtifactStatus
- `CREATED`
- `STORING`
- `STORED`
- `VERIFIED`
- `FAILED_RETRYABLE`
- `FAILED_TERMINAL`

---

## 3) Relationship Model (Canonical)

### 3.1 Experiment ↔ Task ↔ Run
- **Experiment** owns many **Tasks** *(when present)*.
- **Tasks may exist standalone** (no experiment).
- Each **Task** owns many **Runs**.
- Each **Run** belongs to exactly one **Task**.

**Cardinality**
- `Experiment (0..1) -> (0..N) Task`
- `Task (1) -> (0..N) Run`
- `Run (1) -> (1) Task`

### 3.2 Run ↔ Response ↔ Evaluation
- Each **Run** expects one or more **Responses** (one per role×model call in the run plan).
- Each **Response** may have one or more **Evaluations** over time (e.g., re-evaluated under new rubric).  
  - Only **one** Evaluation should be marked as the **active** evaluation used for winner selection within a given Run scoring pass.

**Cardinality**
- `Run (1) -> (0..N) Response`
- `Response (1) -> (0..N) Evaluation`

### 3.3 Artifacts
- Artifacts are attachable to **Task**, **Run**, **Response**, **Evaluation**, or **Experiment** via `(artifact.owner_type, artifact.owner_id)`.

---

## 4) Immutability Rules (Hybrid Model)

### 4.1 Task (conditionally mutable)
- Mutable **only** when:
  - `Task.status == DRAFT`, **and**
  - `Task.run_count == 0` (no Runs exist for the task)
- Once any Run exists for a Task, the Task becomes effectively immutable.
- If a Task must change after execution has begun, create a **new Task** (new `task_id`) and optionally link via `Task.supersedes_task_id`.

### 4.2 Run (immutable, append-only)
- Runs are immutable once created **except**:
  - status transitions
  - timestamps
  - retry counters / last_error metadata
- The set of reproducibility metadata for a Run must never be overwritten; if something was wrong, create a new Run.

### 4.3 Response (immutable)
- Response text and token metrics are immutable once `RECEIVED`.
- Disqualification does not delete the response; it updates `Response.status` to `DISQUALIFIED` and records a reason.

### 4.4 Evaluation (immutable; invalidation allowed)
- Evaluations are immutable once `COMPLETED`.
- If an evaluation is discovered to be erroneous (buggy rubric version, judge failure), mark it `INVALIDATED` with a required `invalidation_reason`.

### 4.5 Artifact (immutable after VERIFIED)
- Artifact content is immutable after `VERIFIED`.
- Replacing an artifact requires a new artifact id.

---

## 5) Retry Policy (Recoverability Contract)

Locked policy:
- `Task: NO` (tasks are not auto-retried; fix inputs / create new task version)
- `Run: YES`
- `Experiment: YES`
- `Response: YES` *(as a new attempt / new Response record; never overwrite)*
- `Evaluation: YES` *(append-only; re-eval produces a new Evaluation record)*
- `Artifact: YES` *(retry store/verify; never accept silently corrupted artifacts)*

---

## 6) Core Domain Objects (Schemas)

The following are **contract schemas** (language-agnostic). Types are indicative.

### 6.1 Task
**Represents:** A user request + constraints + task_type used for decomposition and evaluation.

Required:
- `task_id: UUID`
- `title: string` (short)
- `description: string` (full user ask)
- `task_type: string` *(must be in your TaskType enum defined elsewhere)*
- `taxonomy_class: string` *(v0.2: locked taxonomy per PRD v1.6 §10.10)*
- `constraints: list[string]` (may be empty)
- `status: TaskStatus`
- `created_at, updated_at: timestamp`
- `experiment_id: UUID | null` *(standalone allowed)*

**Taxonomy Classes (v0.2 - Locked):**
- `factual_qa`, `explanation`, `comparison`, `planning`
- `code_generation`, `analysis`, `synthesis`, `reasoning`

Recommended:
- `tags: list[string]`
- `supersedes_task_id: UUID | null`
- `ground_truth_ref: string | null` (for benchmarked tasks)

**Invariants**
- If `status == READY` then `title` and `description` must be non-empty.
- If `run_count > 0`, Task must not be edited (enforced at service layer).

---

### 6.2 Budget
**Represents:** Budgeting policy and per-role allocations for a Task/Run.

Required:
- `budget_id: UUID`
- `budget_mode: string` (e.g., fast_cheap/standard/high_accuracy)
- `total_budget_tokens: int`
- `role_budgets: list[RoleBudget]`
- `created_at: timestamp`

RoleBudget (required):
- `role: string` (planner/specialist/integrator/verifier/etc.)
- `max_input_tokens: int`
- `max_output_tokens: int`
- `expected_output_tokens: int` *(used for verbosity penalty)*

**Invariants**
- Sum of role expected outputs should be <= total budget (soft invariant; allow over if intentionally conservative).
- `max_output_tokens >= expected_output_tokens`.

---

### 6.3 Run
**Represents:** One execution attempt of a Task under a specific config (reproducible unit).

Required:
- `run_id: UUID`
- `task_id: UUID`
- `status: RunStatus`
- `created_at, started_at, completed_at: timestamp | null`
- `budget_id: UUID` *(or embed budget snapshot)*

Reproducibility (required on every Run; never overwritten):
- `seed: int`
- `prompt_template_version: string` *(semantic version, e.g. v1.3)*
- `prompt_template_hash: string` *(sha256 of concatenated prompts/templates)*
- `rubric_version: string`
- `judge_policy_version: string` *(tie-break, gates, etc.)*
- `environment_fingerprint: string` *(e.g., git_sha + python + deps hash)*

Execution tracking (recommended):
- `retry_count: int`
- `max_retries: int`
- `last_error_code: string | null`
- `last_error_message: string | null`
- `request_id: string | null`

**Invariants**
- A Run’s `task_id` never changes.
- If `status == COMPLETED`, then there must exist exactly one winner Response for this run.

---

### 6.4 Model
**Represents:** A callable LLM with pricing and metadata.

Required:
- `model_id: string` *(provider-stable)*
- `provider: string` (openai/anthropic/google/other)
- `model_name: string` (human readable)
- `is_latest: bool`
- `cost_per_1k_input_usd: decimal | null`
- `cost_per_1k_output_usd: decimal | null`
- `created_at, updated_at: timestamp`

Recommended:
- `capabilities: json` (context window, tools, modalities)
- `deprecation_date: date | null`

**Invariants**
- `model_id` is unique.
- `is_latest` can be true for multiple models if “latest” is per-provider or per-family; define policy elsewhere.

---

### 6.5 Judge
**Represents:** The evaluator identity (model or human).

Required:
- `judge_id: string` *(model_id or human:team)*
- `judge_type: string` (`model` | `human`)
- `rubric_version: string`
- `created_at: timestamp`

Recommended:
- `model_id: string | null`
- `notes: string | null`

---

### 6.6 Response
**Represents:** A model’s output for a specific Run and role.

Required:
- `response_id: UUID`
- `run_id: UUID`
- `task_id: UUID` *(denormalized; must match run.task_id)*
- `model_id: string`
- `role: string`
- `status: ResponseStatus`
- `created_at: timestamp`

Content & metrics (required when status >= RECEIVED):
- `content_text: string`
- `tokens_in: int`
- `tokens_out: int`
- `total_tokens: int` *(may be computed)*
- `estimated_cost_usd: decimal | null`
- `latency_ms: int | null`

Budget context (recommended):
- `expected_token_budget_out: int`
- `actual_vs_budget_ratio: decimal`

Disqualification (required when status == DISQUALIFIED):
- `disqualification_reason: string`
- `failed_quality_gate: bool`
- `primary_failure_mode: string | null` *(v0.2: per PRD v1.6 §8.8)*

**Failure Modes (v0.2 - Locked):**
- `missed_constraint`, `hallucination`, `verbosity_violation`, `logical_gap`
- `format_error`, `incomplete`, `unjustified_refusal`, `off_topic`, `overconfidence`

**Invariants**
- `Response.status` progression must be monotonic (no going backwards).
- If `status == WINNER`, run must be in `SCORING` or `COMPLETED`.
- If `status == DISQUALIFIED`, `primary_failure_mode` must be set (v0.2).

---

### 6.7 Evaluation
**Represents:** Scoring and review of a Response (machine or human).

Required:
- `evaluation_id: UUID`
- `response_id: UUID`
- `run_id: UUID`
- `judge_id: string`
- `status: EvaluationStatus`
- `created_at: timestamp`

Scores (required when status == COMPLETED):
- `correctness: float (0-10)`
- `constraint_adherence: float (0-10)`
- `completeness: float (0-10)`
- `clarity: float (0-10)`
- `actionability: float (0-10)`
- `token_efficiency: float (0-10)`

Computed (required when status == COMPLETED):
- `quality_score: float (0-100)`
- `cost_penalty: float`
- `verbosity_penalty: float`
- `efficiency_bonus: float`
- `final_score: float`

Reviewer feedback (required when status == COMPLETED):
- `redundant_sections: json` *(array of {location, reason})*
- `reviewer_notes: string | null`

Invalidation (required when status == INVALIDATED):
- `invalidation_reason: string`
- `invalidated_at: timestamp`

---

### 6.8 Experiment
**Represents:** A controlled study config + a set of Tasks.

Required:
- `experiment_id: UUID`
- `name: string`
- `status: ExperimentStatus`
- `created_at, updated_at: timestamp`

Config (required):
- `ablation_matrix: json` *(list of toggles and levels)*
- `default_budget_mode: string`
- `reproducibility_policy_version: string`
- `dataset_ref: string | null`

Progress (recommended):
- `total_tasks: int`
- `total_runs_planned: int`
- `runs_completed: int`
- `runs_failed_terminal: int`

---

### 6.9 RoutingDecision
**Represents:** A recorded decision on model selection for a role.

Required:
- `routing_decision_id: UUID`
- `run_id: UUID`
- `task_id: UUID`
- `role: string`
- `selected_model_id: string`
- `route_score: float`
- `decided_at: timestamp`

Recommended:
- `alternatives: json` *(top-k alternatives with scores)*
- `features_used: json` *(cost/latency/risk inputs)*

---

### 6.10 Artifact
**Represents:** Stored run bundles, reports, logs, datasets, or exports.

Required:
- `artifact_id: UUID`
- `owner_type: string` (`task|run|response|evaluation|experiment`)
- `owner_id: UUID|string`
- `artifact_type: string`
- `status: ArtifactStatus`
- `created_at: timestamp`

Storage (required when status >= STORED):
- `storage_provider: string` (supabase_storage/s3/local)
- `storage_uri: string`
- `content_sha256: string`
- `content_bytes: int`

Verification (required when status == VERIFIED):
- `verified_at: timestamp`
- `verifier: string` (system/human)

Failure (required when FAILED_*):
- `failure_reason: string`
- `last_attempt_at: timestamp`
- `attempt_count: int`

---

### 6.11 Experience (v0.2 — ACAR)
**Represents:** A learned contrastive or direct experience from past runs.

Required:
- `experience_id: UUID`
- `task_taxonomy: string` *(from locked taxonomy)*
- `key_differentiator: string` *(what made the winner better)*
- `strategy_description: string`
- `experience_type: string` (`contrastive` | `direct`)
- `source_run_id: UUID`
- `quality_score: decimal`
- `credit_score: decimal` *(default: 0.6)*
- `created_at: timestamp`

Optional:
- `failure_mode_avoided: string | null` *(from failure mode taxonomy)*
- `actionable_tip: string | null`

Tracking (updated over time):
- `retrieval_count: int` *(default: 0)*
- `success_count: int` *(default: 0)*
- `success_rate: decimal` *(computed: success_count / retrieval_count)*
- `last_used: timestamp | null`

Embedding (required for semantic retrieval):
- `task_embedding: vector(1536)` *(text-embedding-3-small)*

**Invariants**
- `experience_type` must be `contrastive` or `direct`.
- `credit_score` must be in range [0, 1].
- `task_taxonomy` must be from locked taxonomy.
- Evolution is append-only via learning rate updates (α=0.1).

---

### 6.12 DecisionTrace (v0.2 — ACAR)
**Represents:** A complete decision audit trail for a single run.

Required:
- `trace_id: UUID`
- `run_id: UUID`
- `trace_json: json` *(full Decision Trace per PRD v1.6 §8.9)*
- `created_at: timestamp`

**Decision Trace JSON Structure:**
```json
{
  "run_id": "uuid",
  "task": { "task_id", "taxonomy", "constraints", "grounding" },
  "candidates": [{ "model_id", "response_id" }],
  "judge_panel": { "judges", "selection_mode", "notes" },
  "deliberation": { "depth_used", "entropy", "early_stop", "rounds" },
  "winner": { "response_id", "model_id", "consensus" },
  "credit": { "hybrid": {...}, "shapley": {...} },
  "evaluation": { "quality_score", "failure_mode" },
  "experience": { "retrieved_ids", "contrastive_experience_id" },
  "cost": { "usd", "tokens_in", "tokens_out", "latency_ms" },
  "repro": { "seed", "git_sha", "task_suite_hash" }
}
```

**Invariants**
- Exactly one DecisionTrace per `COMPLETED` run.
- `trace_json` is immutable once written.
- All required fields must be present in `trace_json`.

---

### 6.13 DeliberationRound (v0.2 — ACAR)
**Represents:** A single round of judge deliberation during ranking.

Required:
- `round_id: UUID`
- `run_id: UUID`
- `round_number: int` *(1-indexed)*
- `opinions: json` *(array of AgentOpinion)*
- `entropy: decimal` *(normalized entropy of opinions)*
- `created_at: timestamp`

**AgentOpinion Structure:**
```json
{
  "judge_model_id": "string",
  "preferred_response_id": "uuid",
  "confidence": 0.85,
  "reasoning": "string"
}
```

**Invariants**
- `round_number` must be sequential starting from 1.
- `entropy` must be in range [0, 1].
- Once a round is created, it is immutable.

---

## 7) Cross-Object Invariants (Non-Negotiable)

1. `Response.task_id == Run.task_id`.
2. Exactly one winner Response per `COMPLETED` Run.
3. Retries never overwrite:
   - Response retry => new `response_id`
   - Evaluation retry => new `evaluation_id`
4. Reproducibility metadata always present on Run and never overwritten.
5. Status monotonicity (forward-only transitions).
6. Publication-grade artifacts must be `VERIFIED` with sha256 + size.

**ACAR Invariants (v0.2):**
7. Decision Trace emitted for every `COMPLETED` run (when `ENABLE_DECISION_TRACE` is ON).
8. Experiences evolve via append-only updates (never overwrite base record).
9. Deliberation rounds are immutable once created.
10. `primary_failure_mode` must be set for every `DISQUALIFIED` response.

---

## 8) Minimal "Done" Definition

This contract is implemented when:
- DB schema has tables for all objects above
- enums are enforced (DB constraints or app validation)
- service layer enforces immutability + invariants
- tests cover:
  - Task edit blocked after first Run
  - Winner uniqueness
  - Evaluation invalidation without deletion
  - Artifact verification required for bundles

---

## 9) Evaluation Contract (Phase 7.2)

All Evaluation-Aware runs inject a canonical Evaluation Contract into every model call.

### 9.1 Contract Text

```
=== EVALUATION CONSTRAINTS ===
- You must complete your entire response within {{expected_output_tokens}} output tokens.
- Responses that are truncated or incomplete will be excluded from evaluation.
- Do not exceed the requested scope or length.
- Conciseness is preferred; excessive verbosity may be penalized.
===
```

### 9.2 Injection Rules

| Rule | Description |
|------|-------------|
| Injection point | Appended to `system_prompt` before provider call |
| Timing | Before every LLM call in Evaluation-Aware runs |
| Consistency | Identical text for all providers |
| Template variable | `{{expected_output_tokens}}` replaced with actual value |

### 9.3 Contract Invariants

- **Disclosure before execution**: Contract is injected before any LLM call
- **Identical across providers**: No provider-specific variations
- **No hidden penalties**: Any rule that can disqualify must be disclosed
- **Neutral language**: No provider branding or bias

### 9.4 Relationship to Truncation Handling

| Stage | Action |
|-------|--------|
| Pre-call | Evaluation Contract injected (disclosure) |
| API call | `max_tokens` enforced by provider (hard limit) |
| Post-call | Truncation detected via `finish_reason` + content analysis |
| Verification | `was_truncated=true` → `DISQUALIFIED` with `RESPONSE_TRUNCATED` |

---

## 10) Experimental Regimes Contract (Phase 7.2)

### 10.1 Regime Definitions

| Regime | Contract Injected | Ranked | Scored | Status |
|--------|-------------------|--------|--------|--------|
| **Evaluation-Aware** | Yes | Yes | Yes | Implemented (MVP) |
| **Blind** | No | Never | Never | Post-MVP |

### 10.2 Non-Mixing Invariant

> **Evaluation-Aware and Blind runs MUST never be mixed in any analysis, comparison, or ranking.**

This is a **non-negotiable system invariant** per CLAUDE.md.

### 10.3 Blind Runs (Post-MVP Only)

Blind Runs are:
- **Exploratory**: Observe natural model behavior
- **Unranked**: Never used for winner selection
- **Unscored**: Never used for quality comparison
- **Not implemented**: No code paths in MVP

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-01-12 | Initial contracts document (Interview-locked) |
| 0.2 | 2026-01-18 | **ACAR Integration:** Added Experience, DecisionTrace, DeliberationRound schemas; Updated RunStatus enum to match runtime.md; Added taxonomy_class to Task; Added primary_failure_mode to Response; Added ACAR invariants (§7); Added experience_id, trace_id, round_id identifiers |
