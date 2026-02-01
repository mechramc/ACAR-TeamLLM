# Failure Modes and Guards

This document catalogs known and anticipated failure modes in multi-model
orchestration systems, the detection mechanisms and guardrails we employ,
and the risks that remain unsolved.

This is intended as a preemptive safety review, not incident documentation.

---

## Known Failure Modes

### 1. Agreement-But-Wrong

**Description:** All probe samples agree on an incorrect answer. The routing
mechanism interprets consensus as confidence and routes to single-agent mode.
The final answer is wrong, and no ensemble can recover because the routing
decision already committed to a single model.

**Detection:** Post-hoc only. We detect this by comparing single-agent
predictions against ground truth. During execution, this failure is invisible.

**Guard:** None. This is an intrinsic limitation of self-consistency-based
routing. Any system that uses agreement as a proxy for correctness will
exhibit this failure mode.

**Measured Impact:** Approximately 8 percentage points of accuracy are lost
to this failure mode (the gap between ACAR and full ensembling).

**Status:** Unsolved. Solving this requires a difficulty signal that does not
depend on agreement, which likely requires task-specific features or learned
representations.

---

### 2. Retrieval Poisoning

**Description:** Retrieval-augmented systems inject context from an experience
store. If the store contains low-quality or misaligned experiences, retrieval
introduces noise rather than grounding. Models may hallucinate based on
irrelevant retrieved context.

**Detection:** Measure similarity between retrieved experiences and the query.
Low median similarity (e.g., < 0.3) indicates the store is not aligned with
the task distribution.

**Guard:** Similarity threshold filtering. Experiences below a minimum
similarity score are not injected. In our experiments, we found thresholds
below 0.7 to be harmful.

**Measured Impact:** Naive retrieval (threshold = 0.0) decreased accuracy by
3.4 percentage points versus no retrieval.

**Status:** Partially mitigated. Threshold filtering helps, but requires
tuning. A fundamentally better approach would use task-aligned stores or
learned retrieval relevance.

---

### 3. Cost Runaway

**Description:** A bug or misconfiguration causes unbounded model calls.
Without budget enforcement, a single experiment can exhaust monthly API
allocation.

**Detection:** Real-time cost tracking against budget limits.

**Guard:** Budget guards that halt execution when estimated cost exceeds
threshold. Pre-run cost estimation before execution begins.

**Measured Impact:** Prevented. No incidents after budget guards were
implemented.

**Status:** Solved at the infrastructure level. Application-level bugs can
still cause high cost within budget limits.

---

### 4. State Machine Corruption

**Description:** A run transitions to an invalid state (e.g., COMPLETED
before VERIFYING, or backward from COMPLETED to EXECUTING). This corrupts
the audit trail and makes results untrustworthy.

**Detection:** State transition validation. Every transition is checked
against the allowed transition graph.

**Guard:** Forward-only state machine with explicit terminal states. Invalid
transitions raise exceptions and halt execution rather than silently
proceeding.

**Measured Impact:** Prevented. Zero invalid transitions in 7,550+ runs.

**Status:** Solved by design. The state machine is simple enough to verify
exhaustively.

---

### 5. Artifact Mutation

**Description:** An artifact (response, evaluation, decision trace) is
modified after creation. This breaks reproducibility and makes debugging
impossible.

**Detection:** Content hashing. Artifacts include SHA-256 hashes of their
content.

**Guard:** Append-only storage. Modifications create new versioned records;
existing records cannot be altered. Database constraints enforce immutability.

**Measured Impact:** Prevented. Zero mutations in production.

**Status:** Solved by design.

---

### 6. Judge Bias Amplification

**Description:** Model-as-judge evaluation inherits the biases of the judge
model. If the judge prefers verbose responses, verbose models win regardless
of correctness. If the judge shares training data with a candidate model,
it may favor that model's outputs.

**Detection:** Bias reports comparing judge behavior across models. Statistical
tests for systematic preference.

**Guard:** Judge rotation (using multiple judge models). Audit evaluations
(secondary judge reviews primary judge decisions). Rule-based verification
gates before ranking.

**Measured Impact:** Partially mitigated. Bias is reduced but not eliminated.
We observe residual same-family preference (e.g., GPT-4 as judge slightly
prefers GPT-4 outputs).

**Status:** Partially mitigated. Full solution requires human evaluation or
formal verification, both of which are expensive.

---

### 7. Prompt Injection via Candidate Responses

**Description:** A candidate model's response contains text that manipulates
the judge model's evaluation. For example, a response might include "This
response should be ranked first because..." which the judge interprets as
instruction rather than content.

**Detection:** Pattern matching for common injection patterns. Anomaly
detection on evaluation distributions.

**Guard:** Input sanitization before judge evaluation. Structured evaluation
formats that separate content from instructions.

**Measured Impact:** Low incidence in practice (frontier models rarely
produce injection attempts). No successful injections detected.

**Status:** Mitigated but not solved. Adversarial attacks are always possible.

---

### 8. Latency Variance Masking Quality Signals

**Description:** Model A is faster than Model B. If both produce correct
answers, the system may systematically prefer A due to lower latency, even
if B produces higher-quality responses on harder tasks.

**Detection:** Stratified analysis by task difficulty. Compare quality
conditional on both models attempting the task.

**Guard:** Explicit separation of latency and quality metrics. Latency is
logged but does not influence ranking.

**Measured Impact:** Not observed as a systematic issue. Latency variance
exists but does not correlate strongly with quality.

**Status:** Monitored but not actively guarded.

---

## Explicit Non-Goals

The system explicitly refuses to perform certain behaviors:

- **No automatic retries.** Failed calls fail. The system does not hide
  failures behind retry logic.

- **No silent fallbacks.** If a model is unavailable, the run fails. The
  system does not substitute a different model without explicit configuration.

- **No learned routing without explicit opt-in.** The default routing
  mechanism is heuristic. Learned routers are treated as experimental and
  require explicit configuration.

- **No cross-experiment artifact sharing.** Each experiment maintains
  isolated artifacts. There is no implicit reuse of previous results.

- **No real-time adaptation.** Routing thresholds and model selection are
  fixed at experiment start. The system does not adapt during execution.

---

## Unsolved Risks

### Attribution Without Counterfactuals

We attempted to estimate model contribution using proxy signals (response
similarity, output entropy, agreement patterns). These proxies showed weak
correlation with ground-truth leave-one-out attribution.

**Why it's hard:** Attribution is fundamentally counterfactual. Knowing what
Model A contributed requires knowing what would have happened without Model A.
This requires either (a) expensive counterfactual runs, or (b) architectural
changes that make contribution explicit.

**Status:** Unsolved. We report leave-one-out attribution when feasible but
do not claim proxy-based attribution is reliable.

---

### Difficulty Estimation for Novel Distributions

Self-consistency variance assumes the probe model's uncertainty correlates
with task difficulty. This holds when the probe model is calibrated on the
task distribution. For out-of-distribution tasks, self-consistency may be
misleading.

**Why it's hard:** Calibration requires knowing the task distribution in
advance. Novel distributions are, by definition, unknown.

**Status:** Unsolved. We recommend validating σ calibration on held-out
data before deploying to new domains.

---

### Semantic Equivalence for Code

Determining whether two code snippets are functionally equivalent is
undecidable in general. Our current approach uses execution-based verification
(run test cases), which is sound but incomplete.

**Why it's hard:** Code equivalence reduces to the halting problem. Any
practical solution must accept false negatives (functionally equivalent
code marked as different).

**Status:** Unsolved in general. Execution-based verification is the
pragmatic approach but inflates disagreement rates for code tasks.

---

## Summary

The system is designed with defense in depth:

1. **Invariants** prevent invalid states (forward-only state machine,
   immutable artifacts).

2. **Guards** detect and halt dangerous conditions (budget limits,
   state transition validation).

3. **Monitoring** enables post-hoc detection of subtle failures
   (bias reports, similarity analysis).

4. **Explicit non-goals** prevent scope creep into dangerous territory
   (no silent retries, no automatic fallbacks).

The remaining unsolved risks—agreement-but-wrong, attribution without
counterfactuals, out-of-distribution calibration—are fundamental research
problems, not implementation gaps. We document them because intellectual
honesty requires acknowledging what we cannot solve.
