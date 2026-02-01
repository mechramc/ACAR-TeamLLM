# TeamLLM Runtime Design (Arena Mode)

**Version:** 1.5
**Last Updated:** 2026-01-16
**Scope:** Arena Mode execution engine (Milestone A / MVP)
**Status:** Design approved

---

## 1. Purpose & Scope

**runtime.md** defines how TeamLLM executes Arena Mode runs - from task submission through winner selection.

### What this document covers:
- **Execution lifecycle**: Task → Run → Responses → Evaluation → Winner
- **Parallelism**: How model calls fan out and complete
- **Failure handling**: Timeouts, retries, minimum candidate thresholds
- **Budget enforcement**: When and how cost limits are checked
- **Determinism**: Seeds, shuffling, reproducibility guarantees

### Scope boundaries:
- This document covers **Arena Mode only** (Milestone A / MVP)
- Team Mode (decomposition, routing, integration) deferred to `runtime-team.md`
- Provider-specific details (auth, endpoints, rate limits) live in provider configs
- Evaluation prompts and rubrics live in `packages/eval/`

### Relationship to other docs:
| Document | Role |
|----------|------|
| PRD.md | Source of truth for *what* the system does |
| contracts.md | Domain objects and lifecycles |
| runtime.md (this) | *How* the execution engine orchestrates work |

---

## 2. Arena Execution Lifecycle

An Arena run progresses through these states:

```
PENDING → EXECUTING → COLLECTING → VERIFYING → RANKING → SCORING → COMPLETED
              ↓           ↓            ↓           ↓
          FAILED_*    FAILED_*   FAILED_ALL   FAILED_*
                               _DISQUALIFIED
```

### State definitions:

| State | What happens | Exit condition |
|-------|--------------|----------------|
| `PENDING` | Run created, budget pre-check | Budget approved → EXECUTING |
| `EXECUTING` | Model calls fan out (staggered) | All calls complete or timeout → COLLECTING |
| `COLLECTING` | Responses gathered, truncation detected | ≥2 candidates received → VERIFYING |
| `VERIFYING` | Verifier judge gates each response | ≥1 passes gate → RANKING |
| `RANKING` | Ranker judge compares qualified candidates | Rankings produced → SCORING |
| `SCORING` | Token-aware scoring formula applied | Winner determined → COMPLETED |
| `COMPLETED` | Winner stored, audit trail finalized | Terminal |

### Failure transitions:
- `EXECUTING` → `FAILED_TIMEOUT` if <2 candidates within timeout window
- `COLLECTING` → `FAILED_INSUFFICIENT_CANDIDATES` if <2 valid responses
- `VERIFYING` → `FAILED_ALL_DISQUALIFIED` if 0 pass the gate
- `PENDING` → `FAILED_BUDGET_EXCEEDED` if pre-check rejects (estimate exceeds limit)

> [!NOTE]
> Post-check does **not** fail the run. Budget overages after completion are flagged as warnings only (see §5).

### Invariants:
- State transitions are forward-only (no rollback)
- Every transition logged to `events` table with timestamp
- Run must have exactly one winner when `COMPLETED`

---

## 2.5 ACAR Complexity Assessment

Before execution, ACAR computes complexity score σ to determine resource allocation.

### Complexity Score Computation

σ : Task → [0, 1] is a deterministic weighted sum:

| Feature | Weight | Description |
|---------|--------|-------------|
| Constraint complexity | 0.2 | min(1.0, \|constraints\| / 5) |
| Token complexity | 0.2 | min(1.0, expected_tokens / 2000) |
| Grounding complexity | 0.2 | GROUNDING_MAP[mode] |
| Taxonomy complexity | 0.2 | TAXONOMY[class].complexity_weight |
| Historical failure rate | 0.2 | failure_rate(taxonomy_class) |

### Execution Mode Routing (π_ACAR)

| σ Range | Mode | Models | Cost Multiplier |
|---------|------|--------|-----------------|
| σ < 0.3 | SINGLE_AGENT | 1 | 0.3× |
| 0.3 ≤ σ < 0.7 | ARENA_LITE | 2 | 0.6× |
| σ ≥ 0.7 | FULL_ARENA | N | 1.0× |

### Phase 17-18 Behavior (Static Baseline)

- σ computed and logged for all tasks
- Mode forced to FULL_ARENA (establishes quality ceiling)
- Dᵢ computed but not used for routing

### Phase 19+ Behavior (Adaptive - Planned)

- σ determines execution mode
- Routing decisions logged in decision trace
- Cost savings measured against baseline

---

## 3. Parallel Execution (Staggered Fan-Out)

Model calls are dispatched with small delays to respect rate limits and improve stability.

### Fan-out algorithm:

```python
for i, model in enumerate(selected_models):
    delay_ms = i * STAGGER_DELAY_MS
    schedule_call(model, delay=delay_ms)

await all_calls_with_timeout(per_provider_timeouts)
```

### Configuration defaults:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `STAGGER_DELAY_MS` | 100ms | Delay between successive model calls |
| `DEFAULT_MODELS_PER_ARENA` | 3 | Number of models in standard arena |
| `MAX_MODELS_PER_ARENA` | 5 | Hard cap to control costs |

### Per-provider timeouts:

| Provider | Timeout | Rationale |
|----------|---------|-----------|
| OpenAI | 60s | Generally fast, well-provisioned |
| Anthropic | 90s | Slightly slower on long outputs |
| Google (Gemini) | 45s | Fast but variable |
| Default/Other | 120s | Conservative fallback |

### Completion behavior:
- Wait for all calls to complete OR timeout
- Do NOT fail-fast on first failure - let others finish
- Collect all responses (success or failure) before proceeding

### Response collection:

```python
responses = []
for result in call_results:
    if result.success:
        responses.append(result.response)
    else:
        log_failure(result.model_id, result.error)

if len(responses) < MIN_CANDIDATES:
    transition_to(FAILED_INSUFFICIENT_CANDIDATES)
```

---

## 3.5 Asynchronous Look-Ahead Retrieval

Experience retrieval operates asynchronously to minimize latency impact.

### Execution Model

```
Task Received
    │
    ├─────────────────────────────┐
    │                             │
    ▼                             ▼
σ Computation (sync)      Experience Retrieval (async)
    │                             │
    ▼                             │
Mode Selection                    │
    │                             │
    ▼                             ▼
Model Dispatch ◄──────── JIT Injection (when ready)
    │
    ▼
Response Collection
```

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| RETRIEVAL_TIMEOUT | 500ms | Max wait for embedding search |
| JIT_INJECTION_DEADLINE | 200ms | Max delay before model dispatch |
| ENABLE_ASYNC_RETRIEVAL | ON | Feature flag |

### Trade-offs

| Approach | Latency Impact | Context Quality |
|----------|----------------|-----------------|
| Blocking retrieval | +500ms | Full |
| Async (JIT) | +0-200ms | Usually full |
| No retrieval | +0ms | None |

### Graceful Degradation

If retrieval exceeds deadline:
- Model dispatch proceeds without experiences
- Timeout logged in decision trace
- No failure state (non-blocking by design)

---

## 4. Failure Handling

Individual model failures do not abort the run. The system continues with remaining candidates.

### Failure types and handling:

All failures log as `event_type: MODEL_FAILURE` with a `failure_type` sub-field:

| Failure | Handling | `failure_type` |
|---------|----------|----------------|
| Timeout | Mark model as timed out, continue | `TIMEOUT` |
| HTTP 5xx | No retry (MVP), continue | `SERVER_ERROR` |
| Rate limit (429) | No retry (MVP), continue | `RATE_LIMITED` |
| Invalid response | Mark as malformed, continue | `INVALID_RESPONSE` |
| Context overflow | Mark as failed, continue | `CONTEXT_OVERFLOW` |

### Minimum candidate threshold:

```python
MIN_CANDIDATES = 2
```

- If fewer than 2 responses succeed → `FAILED_INSUFFICIENT_CANDIDATES`
- Rationale: Peer review and ranking require comparison between candidates
- A single response cannot be meaningfully evaluated in Arena Mode

### Response Validation

A valid response must satisfy:

| Requirement | Description |
|-------------|-------------|
| Non-empty | Response body must contain at least 1 character |
| UTF-8 | Must be valid UTF-8 encoded text |
| No error payload | Provider did not return an error object |
| Format | Plain text **or** valid JSON (if task specifies JSON output) |

**Rejected as `INVALID_RESPONSE`:**
- Empty string responses
- Malformed JSON when JSON output expected
- Provider error payloads (e.g., content filter blocks)

> [!NOTE]
> Tool call responses are **not supported in MVP**. Responses containing tool_use blocks are treated as plain text.

### Truncation detection:

A response is marked `was_truncated = true` if:
- `finish_reason == 'length'` (hit max_tokens)
- Response ends mid-structure (unclosed JSON, unfinished list)
- Contains explicit truncation markers ("...", "[truncated]")

### Truncation handling (MVP):
- Truncated responses are still included as candidates
- Verifier may disqualify them for incompleteness
- No automatic retry or budget extension in MVP (deferred to later phase)

### Failure logging:

Every failure writes to `events` table:

```json
{
  "event_type": "MODEL_FAILURE",
  "run_id": "uuid",
  "model_id": "openai:gpt-4o",
  "failure_type": "TIMEOUT",
  "latency_ms": 60000,
  "error_message": "Request exceeded 60s timeout"
}
```

### Event Taxonomy

Canonical `event_type` values (enums):

| Event Type | Trigger | Payload Fields |
|------------|---------|----------------|
| `RUN_CREATED` | Run initialized | `task_id`, `selected_models` |
| `STATE_TRANSITION` | Any state change | `from_state`, `to_state` |
| `MODEL_CALL_STARTED` | Provider request dispatched | `model_id`, `attempt` |
| `MODEL_CALL_COMPLETED` | Provider response received | `model_id`, `latency_ms`, `tokens_in`, `tokens_out` |
| `MODEL_FAILURE` | Provider call failed | `model_id`, `failure_type`, `error_message` |
| `RESPONSE_VALIDATED` | Response passed validation | `response_id`, `was_truncated` |
| `RESPONSE_REJECTED` | Response failed validation | `response_id`, `rejection_reason` |
| `VERIFICATION_COMPLETED` | Verifier judge finished | `response_id`, `verdict`, `scores` |
| `DISQUALIFICATION` | Response failed gate | `response_id`, `reason` |
| `RANKING_COMPLETED` | Ranker judge finished | `ranking_order`, `justification_hash` |
| `SCORING_COMPLETED` | Final scores computed | `response_scores` |
| `WINNER_SELECTED` | Run completed | `winner_response_id`, `margin` |
| `BUDGET_WARNING` | Post-check overage detected | `estimated_usd`, `actual_usd`, `overage_pct` |

---

## 5. Budget Enforcement

Cost limits are enforced at two checkpoints: before execution and after completion.

### Pre-check (before EXECUTING):

```python
estimated_cost = sum(
    estimate_cost(model, expected_input_tokens, expected_output_tokens)
    for model in selected_models
)

if task.max_total_cost_usd and estimated_cost > task.max_total_cost_usd:
    reject_run(reason="ESTIMATED_COST_EXCEEDS_BUDGET")
```

Estimation uses:
- `expected_output_tokens` from task definition
- Per-model pricing from `models` table
- 1.2x safety multiplier for variance

### Post-check (after COMPLETED):

```python
actual_cost = sum(response.estimated_cost_usd for response in responses)
actual_cost += sum(evaluation.judge_cost_usd for evaluation in evaluations)

run.actual_cost_usd = actual_cost

# Determine budget status
if task.max_total_cost_usd:
    if actual_cost > task.max_total_cost_usd * 1.5:
        run.budget_status = "SEVERE_OVERAGE"
        flag_run(warning="BUDGET_EXCEEDED_BY_50_PERCENT")
    elif actual_cost > task.max_total_cost_usd:
        run.budget_status = "OVER_BUDGET"
    else:
        run.budget_status = "WITHIN_BUDGET"
```

- Post-check does NOT fail the run (work already done)
- `OVER_BUDGET`: actual > max (logged for monitoring)
- `SEVERE_OVERAGE`: actual > 1.5× max (triggers alert)

### Budget tracking fields on Run:

| Field | Description |
|-------|-------------|
| `estimated_cost_usd` | Pre-check estimate |
| `actual_cost_usd` | Sum of all response + judge costs |
| `budget_status` | `WITHIN_BUDGET`, `OVER_BUDGET`, `SEVERE_OVERAGE` |

---

## 6. Evaluation Flow

After collecting responses, evaluation proceeds in strict order: Verify → Rank → Score.

### Step 1: Verification (Gate)

Each response is evaluated independently by the Verifier judge:

```python
for response in responses:
    verdict = verifier_judge.evaluate(
        task=task,
        response=response,
        rubric_version=run.rubric_version
    )

    if verdict.correctness < 7.0 or verdict.constraint_adherence < 8.0:
        response.status = DISQUALIFIED
        response.disqualification_reason = verdict.reason
    else:
        response.status = VALIDATED
        qualified_responses.append(response)
```

**Rules:**
- Verifier sees responses in shuffled order (blind)
- Model identities hidden from judge prompt
- If 0 qualified → `FAILED_ALL_DISQUALIFIED`

### Step 2: Ranking (Listwise Comparison)

Qualified candidates are ranked in a single-pass listwise evaluation:

```python
shuffle(qualified_responses, seed=run.seed)

rankings = ranker_judge.rank(
    task=task,
    candidates=qualified_responses,
    rubric_version=run.rubric_version
)
# Returns: ordered list from best (index 0) to worst, with per-candidate justifications
```

**Rules:**
- Ranker sees all qualified responses in a single prompt (listwise, not pairwise)
- Returns full ordered ranking (1st, 2nd, 3rd...) with per-candidate justification
- Tie-break: if score difference < 5 points between top two, trigger head-to-head Judge tiebreaker

> [!NOTE]
> **Why listwise over pairwise?** For MVP with ≤5 candidates, listwise is simpler and cheaper (1 call vs. O(n²) pairwise). Pairwise with Elo/Bradley-Terry is a future enhancement for high-stakes or large-field arenas.

### Step 3: Scoring (Token-Aware)

Final scores computed per the PRD formula:

```python
for response in qualified_responses:
    quality_score = weighted_sum(evaluation.scores, QUALITY_WEIGHTS)
    cost_penalty = LAMBDA * normalize(response.estimated_cost_usd)
    verbosity_penalty = MU * max(0, (tokens_out - expected) / expected)
    efficiency_bonus = 0
    if quality_score >= QUALITY_THRESHOLD and tokens_out < expected:
        efficiency_bonus = NU * (1 - tokens_out / expected)

    response.final_score = quality_score - cost_penalty - verbosity_penalty + efficiency_bonus
```

### Quality score weights:

| Category | Weight |
|----------|--------|
| Correctness | 0.30 |
| Constraint Adherence | 0.25 |
| Completeness | 0.20 |
| Clarity | 0.15 |
| Actionability | 0.10 |

### Scoring constants (server-side, not exposed to models):

| Constant | Value | Purpose |
|----------|-------|---------|
| `LAMBDA` | 6 | Cost penalty weight |
| `MU` | 10 | Verbosity penalty weight |
| `NU` | 5 | Efficiency bonus weight |
| `QUALITY_THRESHOLD` | 85 | Min quality for efficiency bonus |

---

## 7. Determinism & Reproducibility

Every run must be reproducible from stored artifacts.

### Per-run seed:

```python
run.seed = generate_seed()  # Random int, stored on run creation
```

The seed controls:
- Shuffle order for blind review
- Presentation order to judges
- Any randomized tie-breaking

### Shuffle protocol:

```python
def blind_shuffle(responses: list, seed: int) -> list:
    rng = Random(seed)
    shuffled = responses.copy()
    rng.shuffle(shuffled)

    # Record presentation order
    for i, resp in enumerate(shuffled):
        resp.presentation_index = i

    return shuffled
```

### Required reproducibility metadata (stored on Run):

| Field | Example | Purpose |
|-------|---------|---------|
| `seed` | 42 | Shuffle determinism |
| `prompt_template_version` | "v1.2" | Prompt reproducibility |
| `prompt_template_hash` | "sha256:abc123..." | Exact prompt content |
| `rubric_version` | "v1.0" | Evaluation criteria |
| `judge_model_id` | "openai:gpt-4o" | Judge identity |
| `environment_fingerprint` | "git:abc123+py3.11" | Code version |

### Replay guarantee:

Given the same:
- Task (prompt, constraints, expected_tokens)
- Model list
- Seed
- Prompt/rubric versions
- Judge model

The system MUST produce identical:
- Shuffle order
- Presentation order
- Scoring calculations

> [!IMPORTANT]
> Model outputs may vary due to provider non-determinism at temp>0.

### Judge Model Determinism

Judge calls (Verifier, Ranker, Tiebreaker) use settings to maximize reproducibility:

| Setting | Value | Rationale |
|---------|-------|-----------|
| `temperature` | 0 (or provider minimum) | Minimize output variance |
| `top_p` | 1.0 | Disable nucleus sampling |
| `seed` | `run.seed` | Provider-side determinism (where supported) |

**Judge prompt requirements:**
- Must include `rubric_version` in prompt header
- Must specify strict output schema (JSON with required fields)
- Schema version embedded in `prompt_template_hash`

```python
judge_config = {
    "temperature": 0,
    "top_p": 1.0,
    "seed": run.seed,  # OpenAI, Gemini support this
    "response_format": {"type": "json_object"}  # Enforce structured output
}
```

> [!NOTE]
> Even with temp=0, providers may exhibit minor variance. The stored `judge_model_id` and response hash enable audit of any discrepancies.

---

## 8. Configuration Summary

All runtime parameters in one place.

### Execution:

| Parameter | Default | Configurable |
|-----------|---------|--------------|
| `STAGGER_DELAY_MS` | 100 | Yes (env) |
| `DEFAULT_MODELS_PER_ARENA` | 3 | Yes (per-task) |
| `MAX_MODELS_PER_ARENA` | 5 | Yes (env) |
| `MIN_CANDIDATES` | 2 | No (hardcoded) |

### Timeouts:

| Provider | Timeout | Configurable |
|----------|---------|--------------|
| OpenAI | 60s | Yes (config) |
| Anthropic | 90s | Yes (config) |
| Google | 45s | Yes (config) |
| Default | 120s | Yes (config) |

### Scoring:

| Constant | Value | Configurable |
|----------|-------|--------------|
| `LAMBDA` (cost) | 6 | No (server-side) |
| `MU` (verbosity) | 10 | No (server-side) |
| `NU` (efficiency) | 5 | No (server-side) |
| `QUALITY_THRESHOLD` | 85 | No (server-side) |

### Quality gates:

| Gate | Threshold | Configurable |
|------|-----------|--------------|
| Correctness | ≥ 7/10 | No (per PRD) |
| Constraint adherence | ≥ 8/10 | No (per PRD) |

---

## 9. Sequence Diagram (Complete Flow)

```
┌──────────┐     ┌───────────┐     ┌──────────┐     ┌─────────┐     ┌────────┐
│  Client  │     │    API    │     │ Executor │     │ Verifier│     │ Ranker │
└────┬─────┘     └─────┬─────┘     └────┬─────┘     └────┬────┘     └───┬────┘
     │                 │                │                │              │
     │ POST /tasks     │                │                │              │
     │────────────────>│                │                │              │
     │                 │ Create Task    │                │              │
     │                 │ Create Run     │                │              │
     │                 │ Budget pre-check               │              │
     │                 │───────────────>│                │              │
     │                 │                │                │              │
     │                 │                │ Fan-out calls (staggered)    │
     │                 │                │──────────────────────────────>│
     │                 │                │        (to N providers)      │
     │                 │                │                │              │
     │                 │                │<─ ─ ─ responses ─ ─ ─ ─ ─ ─ ─│
     │                 │                │                │              │
     │                 │                │ Verify each    │              │
     │                 │                │───────────────>│              │
     │                 │                │                │ Gate pass/fail
     │                 │                │<───────────────│              │
     │                 │                │                │              │
     │                 │                │ Rank qualified │              │
     │                 │                │─────────────────────────────>│
     │                 │                │                │              │
     │                 │                │<─────────────────────────────│
     │                 │                │                │              │
     │                 │                │ Score + Select Winner        │
     │                 │<───────────────│                │              │
     │                 │                │                │              │
     │  200 OK + winner│                │                │              │
     │<────────────────│                │                │              │
     │                 │                │                │              │
```

---

## 10. Implementation Checklist

Phase 3 (Arena Executor) must implement:

- [ ] Staggered fan-out with configurable delay
- [ ] Per-provider timeout handling
- [ ] Response collection with failure logging
- [ ] Minimum candidate threshold check
- [ ] Truncation detection

Phase 4 (Evaluation Layer) must implement:

- [ ] Blind shuffle with stored seed
- [ ] Verifier judge integration
- [ ] Quality gate enforcement
- [ ] Ranker judge integration
- [ ] Disqualification logging

Phase 5 (Scoring) must implement:

- [ ] Quality score calculation
- [ ] Cost penalty calculation
- [ ] Verbosity penalty calculation
- [ ] Efficiency bonus calculation
- [ ] Winner selection and storage

---

## 11. Phase 7 Auditability Surface

The Run Forensics UI exposes the following raw facts for observability and trust:

### What is displayed (read-only):

| Category | Fields | Source |
|----------|--------|--------|
| **Cost Breakdown** | tokens_in, tokens_out, estimated_cost_usd, max_cost_in_run, expected_token_budget_out, latency_ms | Response model |
| **Scoring** | quality_score, cost_penalty, verbosity_penalty, efficiency_bonus, final_score | Evaluation model |
| **Disqualification** | disqualification_reason, verifier_failure, was_truncated | Response/Evaluation |
| **Partial Output** | content_text (exact text received, even if incomplete) | Response model |
| **Determinism** | run seed | Run model |

### What is explicitly NOT inferred:

- No client-side cost recalculation (values come from backend)
- No summarization or rewriting of partial outputs
- No scoring of disqualified candidates
- No hidden penalty adjustments

### On truncation/disqualification:

1. Candidate marked as `DISQUALIFIED` with `disqualification_reason`
2. `was_truncated` flag set if detected
3. `content_text` preserved for forensic inspection
4. UI displays warning: "Response truncated — excluded from scoring"
5. If content unavailable: "Partial output not recorded in this run payload."

### Scoring formula transparency:

The UI displays the formula:
```
Final = Quality − Cost Penalty − Verbosity Penalty + Efficiency Bonus
```

With explanations:
- Cost Penalty: `LAMBDA × (cost / max_cost) × 10` where LAMBDA = 6
- Verbosity Penalty: `MU × ((tokens_out - expected) / expected)` where MU = 10
- Efficiency Bonus: `NU × (1 - tokens_out / expected)` where NU = 5, if quality ≥ 85

---

## 12. Phase 7.1 Forensics Payload Requirements

The Run Events API (`/runs/{runId}/events`) must return all data necessary for research-grade forensics:

### Required Top-Level Fields

| Field | Type | Source |
|-------|------|--------|
| `run_id` | UUID | Run.run_id |
| `run_status` | string | Run.status |
| `task_id` | UUID | Run.task_id |
| `task_prompt` | string | Task.description (joined) |

### Required Candidate Fields

| Field | Type | Source | Fallback |
|-------|------|--------|----------|
| `response_id` | UUID | Response | Required |
| `model_id` | string | Response | Required |
| `content_text` | string | Response.content_text | "Not recorded" |
| `tokens_in` | int | Response.tokens_in | "Not recorded" |
| `tokens_out` | int | Response.tokens_out | "Not recorded" |
| `estimated_cost_usd` | float | Response.estimated_cost_usd | "Not recorded" |
| `expected_token_budget_out` | int | Response | null |
| `latency_ms` | int | Response.latency_ms | "Not recorded" |
| `was_truncated` | bool | Response.was_truncated | false |
| `max_cost_in_run` | float | Computed | null |
| `disqualification_reason` | string | Response | null |

### UI Display Rules

1. **Task prompt:** Always shown if available, collapsible for long prompts
2. **Winner output:** Displayed inline in winner card
3. **Candidate outputs:** Expandable in candidate detail cards
4. **Truncated outputs:** Shown with warning banner "Response truncated — excluded from scoring"
5. **Missing data:** Display "Not recorded" rather than undefined, blank, or computed fallback

---

---

## 13. Phase 7.2 Evaluation Contract Injection

All Evaluation-Aware runs inject a canonical **Evaluation Contract** into every model call, ensuring models are informed of constraints that can disqualify them.

### 13.1 Evaluation Contract Text

```
=== EVALUATION CONSTRAINTS ===
- You must complete your entire response within {{expected_output_tokens}} output tokens.
- Responses that are truncated or incomplete will be excluded from evaluation.
- Do not exceed the requested scope or length.
- Conciseness is preferred; excessive verbosity may be penalized.
===
```

### 13.2 Injection Point

The contract is appended to the `system_prompt` in `ArenaExecutor._call_model()` before calling any provider.

**Location:** `backend/app/services/arena_executor.py`

### 13.3 Provider Consistency

| Provider | API Parameter | Contract Delivery |
|----------|---------------|-------------------|
| OpenAI | `max_tokens` | In `messages[0].content` (system role) |
| Anthropic | `max_tokens` | In `system` parameter |
| Google | `max_output_tokens` | In combined prompt |

All providers receive **identical contract text**.

### 13.4 What Is Disclosed vs. Not Disclosed

| Disclosed | Not Disclosed |
|-----------|---------------|
| Token limit (expected_output_tokens) | Scoring weights (λ, μ, ν) |
| Truncation consequence | Tie-break rules |
| Verbosity preference | Quality thresholds |

### 13.5 Core Principle

> **Any rule that can disqualify or penalize a model must be disclosed to that model in advance.**

This ensures fair, auditable evaluation where models compete with full knowledge of the constraints.

---

## 14. Experimental Regimes and Fairness

TeamLLM distinguishes between two experimental regimes that must **never be mixed**.

### 14.1 Evaluation-Aware Runs

- Models receive the Evaluation Contract
- Results are ranked, scored, and used for winner selection
- All competitive comparisons use this mode
- This is the default and only ranked mode in MVP

### 14.2 Blind Runs (Post-MVP)

- Models do NOT receive the Evaluation Contract
- Used for behavioral observation only
- Results are **never ranked or scored**
- Never compared against Evaluation-Aware runs
- Implementation deferred to Post-MVP

### 14.3 Regime Separation

| Requirement | Enforcement |
|-------------|-------------|
| Blind and Aware runs never mixed in analysis | By design |
| Rankings only from Evaluation-Aware runs | Enforced in scoring layer |
| Blind run data never used for fairness claims | Policy |

### 14.4 Research Credibility Rationale

Explicit constraint disclosure:
- Eliminates "surprise disqualification" as a confounding variable
- Makes evaluation results more defensible for publication
- Allows models to self-regulate within known bounds

Blind runs (when implemented):
- Provide valuable behavioral data
- Show natural model tendencies
- Are explicitly unranked to prevent apples-to-oranges comparisons

---

## 15. Model-Aware Constraints (Phase 7.3)

Models have different hard output token limits. TeamLLM enforces these limits to prevent provider 400 errors.

### 15.1 Model Capabilities Registry

A static registry (`backend/app/services/model_capabilities.py`) defines max_output_tokens for each supported model:

| Model | Provider | Max Output Tokens |
|-------|----------|-------------------|
| claude-3-haiku | Anthropic | 4,096 |
| claude-3-opus | Anthropic | 4,096 |
| claude-3-5-sonnet | Anthropic | 8,192 |
| gpt-4o | OpenAI | 16,384 |
| gpt-4-turbo | OpenAI | 4,096 |
| gemini-1.5-flash | Google | 8,192 |
| gemini-2.0-flash | Google | 8,192 |

### 15.2 Token Clamping

When a user requests more tokens than a model supports:

```python
effective_max_tokens = min(requested_max_tokens, model_cap)
was_clamped = requested_max_tokens > model_cap
```

Clamping occurs in `ArenaExecutor._call_model()` before any provider call.

### 15.3 Evaluation Contract Uses Effective Value

The Evaluation Contract is built with the **effective** token limit, not the user's requested value:

```
=== EVALUATION CONSTRAINTS ===
- You must complete your entire response within {effective_max_tokens} output tokens.
...
===
```

This ensures models are never told a limit they cannot satisfy.

### 15.4 Error Handling

| Scenario | Behavior |
|----------|----------|
| requested > model_cap | Clamp to model_cap, log warning, continue |
| requested <= 0 | Reject with ValueError (HTTP 422) |
| Unknown model | Use default cap (4,096), log warning |
| Provider 400 despite clamping | Return HTTP 422 with details |

### 15.5 Forensics Visibility

The Forensics UI shows:
- Requested max tokens (user's original value)
- Model cap (model's hard limit)
- Effective max tokens (actual limit used)
- Was clamped (boolean indicator)

---

## 16. Cost Penalty Transparency (Phase 7.4)

The cost penalty system uses a **two-regime model** to ensure quality always dominates evaluation while still penalizing genuinely expensive responses.

### 16.1 Problem Statement

Previous cost penalty formula (`LAMBDA × (cost / max_cost) × 10`) applied a −60 cliff penalty to the most expensive response regardless of absolute cost differences. This could unfairly penalize a $0.02 response competing against a $0.01 response.

### 16.2 Two-Regime Model

| Regime | Trigger | Penalty | Purpose |
|--------|---------|---------|---------|
| **Hard** | Cost > HARD_COST_CEILING_USD ($0.10) OR budget_exceeded flag | −60 | Absolute non-viability |
| **Soft** | Within budget, cost > min_cost | max −10 | Proportional, bounded |

### 16.3 Constants

```python
HARD_COST_PENALTY = 60.0          # Maximum penalty for non-viable costs
HARD_COST_CEILING_USD = 0.10      # Absolute ceiling triggering hard penalty
SOFT_COST_CAP = 10.0              # Maximum soft penalty (bounded)
```

### 16.4 Soft Penalty Formula

```
soft_penalty = SOFT_COST_CAP × ((cost - min_cost) / (max_cost - min_cost))
```

- Lowest-cost candidate receives no soft penalty
- Maximum soft penalty is capped at SOFT_COST_CAP (10)
- Cost differences within budget never dominate quality scores

### 16.5 Reason Codes

| Reason Code | Meaning |
|-------------|---------|
| `HARD_COST_CEILING_EXCEEDED` | Cost exceeds $0.10 hard ceiling |
| `BUDGET_EXCEEDED` | Response exceeded run's budget |
| `SOFT_RELATIVE_COST` | Within budget, soft penalty applied |
| `NO_PENALTY` | Lowest or equal cost in run |

### 16.6 Forensics Payload

The SCORING_COMPLETED event includes:

```json
{
  "scores": [
    {
      "response_id": "...",
      "cost_penalty": 5.2,
      "cost_penalty_reason": "SOFT_RELATIVE_COST",
      "cost_penalty_details": {
        "estimated_cost_usd": 0.042,
        "min_cost_usd": 0.018,
        "max_cost_usd": 0.065,
        "median_cost_usd": 0.035,
        "hard_cost_ceiling_usd": 0.10,
        "soft_cost_cap": 10.0,
        "reason": "SOFT_RELATIVE_COST"
      }
    }
  ]
}
```

### 16.7 Invariants

- Quality always dominates: A +1 quality difference exceeds any soft penalty
- Hard penalty is decisive: Responses exceeding ceiling are effectively disqualified from winning
- Transparency: All penalty decisions include full context in events

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-13 | Initial Arena Mode runtime design |
| 1.1 | 2026-01-16 | Added Phase 7 Auditability Surface section |
| 1.2 | 2026-01-16 | Added Phase 7.1 Forensics Payload Requirements |
| 1.3 | 2026-01-16 | Added Phase 7.2 Evaluation Contract Injection, Experimental Regimes |
| 1.4 | 2026-01-16 | Added Phase 7.3 Model-Aware Constraints |
| 1.5 | 2026-01-16 | Added Phase 7.4 Cost Penalty Transparency |
