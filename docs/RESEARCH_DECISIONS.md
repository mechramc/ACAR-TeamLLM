# Research Decisions

This document records major architectural decisions, alternatives considered,
approaches that did not work, and open questions. It is intended as a curated
narrative for reviewers evaluating the project's research maturity.

---

## Major Architectural Decisions

### Decision 1: Self-Consistency as Difficulty Signal

**Choice:** Use self-consistency variance (σ) computed from N=3 probe samples
to estimate task difficulty.

**Rationale:**
- Self-consistency is model-agnostic (works with any probe model)
- Requires no training data or learned parameters
- Produces interpretable routing decisions
- Fails predictably (agreement-but-wrong is detectable post-hoc)

**Alternatives considered:**
- **Learned difficulty classifier.** Trained on labeled difficulty data.
  Rejected because it requires task-specific training data and introduces
  distribution shift risk.
- **Confidence calibration.** Use model's reported confidence. Rejected
  because LLM confidence is poorly calibrated and varies across providers.
- **Task embedding similarity.** Route based on similarity to known hard/easy
  tasks. Rejected because it requires a labeled reference corpus.

**Outcome:** Self-consistency works well for tasks where model disagreement
correlates with difficulty. It fails on tasks where models confidently agree
on wrong answers.

---

### Decision 2: Three-Model Fixed Ensemble

**Choice:** Fix ensemble size at three models (Claude Sonnet 4, GPT-4o,
Gemini 2.0 Flash).

**Rationale:**
- Three is the minimum for meaningful majority voting
- Leave-one-out attribution is tractable with N=3
- Cost is bounded at 3× single-model
- Diverse provider coverage (Anthropic, OpenAI, Google)

**Alternatives considered:**
- **Two-model ensemble.** Simpler but no majority vote possible; ties require
  tiebreaker logic.
- **Five-model ensemble.** Better coverage but 5× cost and attribution
  becomes expensive (5 counterfactual runs per task).
- **Dynamic ensemble size.** Vary N based on difficulty. Rejected because
  it complicates cost estimation and attribution.

**Outcome:** Three models provide a good balance of diversity, cost, and
tractability. The fixed size simplifies analysis.

---

### Decision 3: Forward-Only State Machine

**Choice:** Run status progresses monotonically through defined states with
no rollback.

**Rationale:**
- Simplifies debugging (current state fully determines history)
- Prevents "retry from middle" bugs that corrupt partial results
- Makes audit trail linear and verifiable

**Alternatives considered:**
- **Checkpoint-and-resume.** Allow runs to pause and resume from intermediate
  states. Rejected because it introduces state management complexity and
  potential for inconsistency.
- **Idempotent operations.** Make all operations safe to re-run. Rejected
  because LLM calls are not idempotent (responses vary).

**Outcome:** Forward-only simplifies reasoning about system state. The cost
is that failed runs must be restarted from scratch.

---

### Decision 4: Append-Only Artifacts

**Choice:** Artifacts are immutable after creation. Modifications create new
versioned records.

**Rationale:**
- Enables independent verification (artifacts cannot be tampered with)
- Simplifies debugging (what you see is what was produced)
- Supports reproducibility claims

**Alternatives considered:**
- **Mutable artifacts with audit log.** Allow modifications but log all
  changes. Rejected because audit logs can also be modified; true
  immutability requires append-only storage.
- **No persistence.** Keep artifacts in memory only. Rejected because it
  prevents post-hoc analysis and reproducibility.

**Outcome:** Append-only storage has worked well. The minor inconvenience
of creating new versions is outweighed by the auditability benefits.

---

### Decision 5: Separation of Routing and Execution

**Choice:** ACAR (routing) and TeamLLM (execution) are separate components
with a narrow interface.

**Rationale:**
- Routing logic can be swapped without changing execution infrastructure
- Execution infrastructure can be tested independently
- Failure isolation (routing bugs don't corrupt artifacts)

**Alternatives considered:**
- **Integrated system.** Single codebase with routing embedded in execution
  loop. Rejected because it couples concerns that should evolve independently.
- **Microservices.** Separate routing and execution into networked services.
  Rejected as overengineering for a research system.

**Outcome:** Separation has enabled clean experimentation with different
routing approaches while keeping the execution substrate stable.

---

## What Was Tried and Did Not Work

### Attempt 1: Attribution-Based Routing

**Hypothesis:** Route tasks based on predicted model contribution. If Model A
is predicted to contribute most, route only to Model A.

**Approach:** Compute Shapley values or difference rewards from historical
data. Use these to predict which models will contribute to future tasks.

**Result:** Failed. Attribution signals from historical data did not
generalize to unseen tasks. The correlation between predicted and actual
contribution was weak (r < 0.3).

**Lesson:** Attribution is task-specific. A model that contributed heavily
on past tasks may not contribute on future tasks. Attribution-based routing
requires per-task prediction, not historical aggregation.

**Impact on design:** We abandoned attribution-based routing and adopted
difficulty-based routing instead. Attribution is now computed for analysis,
not for routing decisions.

---

### Attempt 2: Retrieval Augmentation with Loose Similarity Threshold

**Hypothesis:** Injecting similar past experiences into prompts will improve
model performance by providing relevant context.

**Approach:** Retrieve experiences with any positive similarity (threshold = 0).
Inject top-k retrieved experiences into the prompt.

**Result:** Failed. Accuracy decreased by 3.4 percentage points versus no
retrieval. Median similarity of retrieved experiences was 0.167, meaning
most injected context was barely relevant.

**Lesson:** Retrieval is not automatically beneficial. Low-quality retrieval
introduces noise. "More context" is not the same as "better context."

**Impact on design:** We now require similarity thresholds > 0.7 for retrieval
to be enabled. We also report retrieval as a negative result in the paper.

---

### Attempt 3: Proxy-Based Attribution

**Hypothesis:** Model contribution can be estimated from observable signals
without expensive counterfactual runs.

**Approach:** Use response similarity to final answer, output entropy, and
agreement patterns as proxies for leave-one-out contribution.

**Result:** Failed. Proxies showed weak correlation with ground-truth
leave-one-out values (r < 0.25 for all proxies tested).

**Lesson:** Attribution is fundamentally counterfactual. Observable signals
after the fact do not capture what would have happened under different
conditions.

**Impact on design:** We compute leave-one-out attribution when feasible
but do not claim proxy-based attribution is reliable. The paper explicitly
documents this negative result.

---

### Attempt 4: Continuous Difficulty Signal

**Hypothesis:** A continuous difficulty estimate (rather than discrete σ)
would enable finer-grained routing.

**Approach:** Use entropy of probe sample distribution as a continuous
difficulty signal. Route to more models as entropy increases.

**Result:** Inconclusive. Continuous signals required threshold tuning,
and optimal thresholds varied across benchmarks. The complexity did not
yield clear accuracy gains.

**Lesson:** Discrete signals are more robust to distribution shift. Continuous
signals require hyperparameter tuning that can overfit to specific benchmarks.

**Impact on design:** We retained discrete σ ∈ {0.0, 0.5, 1.0} for its
simplicity and robustness.

---

## How Negative Results Informed the Design

The failures above shaped the final system in specific ways:

| Failure | Design Response |
|---------|-----------------|
| Attribution-based routing failed | Route on difficulty, not predicted contribution |
| Loose retrieval hurt accuracy | Require high similarity thresholds; report as negative result |
| Proxy attribution failed | Use counterfactual LOO; acknowledge limitation in paper |
| Continuous signals overfit | Use discrete σ; accept coarser granularity |

Each negative result removed a degree of freedom from the design space and
clarified what the system should *not* attempt.

---

## Open Research Questions

### Question 1: Can agreement-but-wrong be detected before routing?

Self-consistency routing fails when models agree on wrong answers. Is there
a signal—other than agreement—that distinguishes confident-correct from
confident-wrong?

**Current status:** Unknown. We have not found such a signal. Possibilities
include calibrated uncertainty estimates, task embedding features, or
meta-cognitive probing.

**Why it matters:** Solving this would close the 8pp gap between ACAR and
full ensembling.

---

### Question 2: What makes a retrieval store "aligned"?

We know that low-similarity retrieval hurts. We do not know what properties
a store must have to help. Is it coverage? Diversity? Recency? Task-type
matching?

**Current status:** Unexplored. Our experience store was built opportunistically,
not designed for alignment.

**Why it matters:** Retrieval augmentation is a promising direction, but only
if stores can be constructed or filtered appropriately.

---

### Question 3: How should attribution be communicated to users?

Leave-one-out attribution is expensive but accurate. Proxy attribution is
cheap but unreliable. Is there a middle ground? How should systems communicate
attribution uncertainty to users?

**Current status:** Unexplored. We report LOO attribution in research contexts
but have not designed user-facing attribution interfaces.

**Why it matters:** Multi-model systems need to explain their decisions.
Attribution is part of that explanation.

---

### Question 4: Does σ calibration transfer across domains?

Self-consistency variance is calibrated on our benchmark distribution. Does
this calibration transfer to other domains (e.g., medical QA, legal reasoning)?

**Current status:** Unknown. We have not tested cross-domain transfer.

**Why it matters:** Practical deployment requires knowing when recalibration
is necessary.

---

### Question 5: What is the right cost-quality tradeoff for production?

Our experiments prioritize measurement validity over cost efficiency. In
production, the tradeoff may differ. How should routing thresholds adapt
to different cost tolerances?

**Current status:** Not addressed. We treat cost as a measurement, not an
optimization target.

**Why it matters:** Production systems must balance cost and quality
explicitly. Research systems can defer this question.

---

## Summary

This project proceeded through cycles of hypothesis, experiment, and revision.
Several promising directions (attribution-based routing, loose retrieval,
proxy attribution) failed and were abandoned. These failures were not wasted
effort—they clarified what the system should and should not attempt.

The final design reflects what survived this process: difficulty-based routing,
high-threshold retrieval (or none), counterfactual attribution (when feasible),
and explicit acknowledgment of unsolved problems.

We consider intellectual honesty about negative results to be as important
as positive findings. A system that only reports successes is not credible.
