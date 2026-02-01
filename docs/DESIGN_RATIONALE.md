# Design Rationale

This document explains the reasoning behind key architectural decisions in ACAR
and the TeamLLM substrate. It is intended for readers evaluating the design
maturity of the system, not as implementation guidance.

---

## Problem Framing

### Why Multi-Model Orchestration Is Hard

The naive framing of multi-model orchestration—"run multiple models and pick the
best output"—obscures several fundamental difficulties:

1. **Task difficulty is latent.** We cannot observe whether a task is "hard"
   before attempting it. Any routing decision must be made with incomplete
   information about the task's true complexity.

2. **Output equivalence is non-trivial.** Determining whether two model outputs
   are semantically equivalent requires domain-specific logic. Code that produces
   identical behavior may differ syntactically. Natural language answers may be
   paraphrased. This makes majority voting and consensus detection harder than
   they appear.

3. **Cost scales multiplicatively.** Running N models costs N times as much.
   Without selective routing, ensembling is economically impractical for
   production workloads.

4. **Attribution is counterfactual.** Assigning credit to individual models
   requires knowing what would have happened without each model—expensive
   counterfactual computation that doesn't scale.

5. **Evaluation is not neutral.** Any judge (human or model) introduces bias.
   Model-as-judge approaches inherit the biases of the judge model. Human
   evaluation is expensive and inconsistent.

These difficulties compound. A system that solves routing but ignores attribution
is incomplete. A system that solves attribution but ignores cost is impractical.

---

## Why Naive Ensemble Routing Is Insufficient

The simplest ensemble approach—run all models on all tasks, then vote or
judge—fails for several reasons:

- **Cost ceiling.** At $0.01-0.03 per model call, running three models on
  thousands of tasks becomes prohibitively expensive. Cost must inform routing.

- **Latency ceiling.** Sequential model calls add latency. Parallel calls
  reduce latency but increase cost. Neither is acceptable at scale without
  selective invocation.

- **No learning signal.** Running all models on all tasks produces no signal
  about which tasks benefit from ensembling. Easy tasks waste compute; hard
  tasks may need more than three models.

- **Attribution blindness.** Voting produces a winner but no understanding of
  why that model won or what each model contributed. This limits debugging
  and improvement.

The core insight motivating ACAR is that **task difficulty can be estimated
cheaply** using self-consistency among samples from a fast probe model. When
samples agree, the task is likely easy. When they disagree, the task benefits
from diverse perspectives.

---

## Why Cost-Awareness Must Be First-Class

Cost-awareness was a design requirement, not an afterthought, for several reasons:

- **Research budgets are finite.** Running 7,550 experimental runs at frontier
  model prices requires disciplined cost tracking. Without budget enforcement,
  a single experiment can exhaust monthly allocation.

- **Production economics.** Any system intended for production use must
  demonstrate cost efficiency. Academic systems that ignore cost are not
  credible for real deployment.

- **Cost is a research signal.** The cost-accuracy Pareto frontier is itself
  interesting. Understanding where adaptive routing beats fixed ensembling
  requires measuring both dimensions.

TeamLLM tracks cost at multiple granularities:
- Per-model-call (input/output tokens × pricing)
- Per-run (sum of all model calls)
- Per-experiment (sum of all runs)

Budget guards can halt execution before overage. This is not optimization—it
is research infrastructure hygiene.

---

## Why Immutability and Auditability Were Design Requirements

Several failure modes motivated immutability:

- **Silent mutation.** If run results can be modified after completion,
  debugging becomes impossible. "The results looked different yesterday"
  is not an acceptable failure mode.

- **Reproducibility collapse.** If artifacts can be overwritten, independent
  verification becomes impossible. A claimed result that cannot be reproduced
  from artifacts is not a result.

- **Audit trail gaps.** If decisions are not logged, understanding why a
  model was selected or why a task was routed to full ensemble requires
  re-running the experiment.

TeamLLM enforces:
- **Append-only artifacts.** Once written, artifacts cannot be modified. New
  versions create new records.
- **Forward-only state machines.** Run status progresses monotonically. There
  is no "retry from middle" or "rollback to previous state."
- **Complete decision traces.** Every routing decision, model call, and
  evaluation is logged with timestamps and inputs.

This is not paranoia. It is the minimum standard for credible experimental
infrastructure.

---

## Why ACAR Was Layered Atop TeamLLM

ACAR (the routing mechanism) and TeamLLM (the execution substrate) could have
been built as a single integrated system. We chose separation for several reasons:

- **Separation of concerns.** TeamLLM handles execution, logging, and state
  management. ACAR handles routing decisions. Neither needs to know the
  implementation details of the other.

- **Substrate reuse.** TeamLLM can support routing mechanisms other than ACAR.
  Future work on learned routers, human-in-the-loop routing, or hybrid
  approaches can reuse the same substrate.

- **Testing isolation.** TeamLLM's invariants (immutability, forward-only
  state, complete logging) can be tested independently of routing logic.
  Routing logic can be tested with mock substrates.

- **Failure isolation.** A bug in ACAR's routing logic should not corrupt
  TeamLLM's artifact storage. A bug in TeamLLM's state machine should not
  silently change routing behavior.

The interface between ACAR and TeamLLM is intentionally narrow: ACAR provides
a routing decision (which models to invoke); TeamLLM executes that decision
and returns results.

---

## Key Tradeoffs Consciously Accepted

### Discrete σ vs. Continuous Difficulty Estimation

We discretize self-consistency variance into three buckets (σ ∈ {0.0, 0.5, 1.0})
rather than using continuous values. This sacrifices granularity for:
- Deterministic, interpretable routing decisions
- No threshold hyperparameters to tune
- Immunity to benchmark-specific overfitting

A continuous difficulty signal would require learning thresholds, introducing
distribution shift risk.

### Heuristic Routing vs. Learned Routing

We use self-consistency (a heuristic) rather than a learned classifier to
route tasks. This sacrifices potential routing accuracy for:
- No training data required
- No distribution shift between training and deployment
- Full auditability of routing decisions
- Model-agnostic applicability

Learned routers achieve higher accuracy on in-distribution tasks but introduce
opacity and generalization risk.

### Three Models vs. N Models

We fix the ensemble size at three models rather than supporting arbitrary N.
This sacrifices flexibility for:
- Bounded cost (at most 3× single-model cost)
- Tractable attribution (leave-one-out is feasible with N=3)
- Simpler routing logic (three execution modes, not a continuum)

Larger ensembles might improve quality but make attribution and cost analysis
intractable.

### No Retry Logic

TeamLLM does not automatically retry failed model calls. A failure is a failure.
This sacrifices convenience for:
- Predictable cost (no runaway retries)
- Clean audit trails (no hidden retry loops)
- Explicit failure handling (caller decides whether to retry)

Automatic retries obscure failure patterns and can mask systemic issues.

---

## Summary

The system's design reflects a specific stance: **measurement infrastructure
must be trustworthy before measurements can be trusted.** Immutability,
auditability, and cost-awareness are not features—they are prerequisites.

ACAR's routing mechanism is intentionally simple because the goal is not
optimal routing but credible measurement of routing behavior. A more
sophisticated router would be harder to audit and easier to overfit.

The tradeoffs above are not compromises. They are deliberate choices that
prioritize interpretability and reproducibility over raw performance.
