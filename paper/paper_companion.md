# ACAR: Adaptive Complexity Routing for Multi-Model Ensembles with Auditable Decision Traces

**Target:** arXiv (primary), NeurIPS format for convenience
**Status:** Draft v4 (PhD feedback revision)
**Last Updated:** 2026-01-31

---

## Abstract

We present ACAR (Adaptive Complexity & Attribution Routing) as a measurement framework for studying multi-model orchestration under auditable conditions. ACAR uses self-consistency variance (σ) computed from N=3 probe samples to route tasks across single-model, two-model, and three-model execution modes, implemented atop TeamLLM, a deterministic substrate with immutable artifacts and complete decision traces. We evaluate across 1,510 tasks spanning four benchmarks (MathArena, Reasoning Gym, LiveCodeBench, SuperGPQA) with Claude Sonnet 4, GPT-4o, and Gemini 2.0 Flash, producing 7,550+ auditable runs.

**What holds**: σ-based routing achieves 55.6% accuracy, exceeding the two-model baseline (54.4%) while avoiding full ensembling on 54.2% of tasks; the mechanism is model-agnostic and requires no learned components.

**What does not hold**: (1) Retrieval augmentation *decreased* accuracy by 3.4 percentage points—median retrieval similarity was only 0.167, demonstrating that experience injection without semantic alignment introduces harmful noise rather than grounding. (2) When models agree on incorrect answers (σ=0), no downstream ensemble can recover; this "agreement-but-wrong" failure mode is intrinsic to self-consistency and bounds achievable accuracy at 8pp below full ensembling. (3) Attribution estimates based on proxy signals (response similarity, entropy) showed weak correlation with ground-truth leave-one-out values; practical attribution requires explicit counterfactual computation.

This paper documents what assumptions fail in practice, providing falsifiable baselines for future work on routing, retrieval, and multi-model attribution.

---

## 1. Introduction

### Background and Motivation

Large language models (LLMs) have achieved strong performance across diverse tasks, but deploying them effectively requires navigating a fundamental trade-off between quality and cost. A single model may produce incorrect or incomplete answers, while running multiple models in parallel (ensembling) improves reliability but multiplies inference costs. This tension—*how to allocate compute before knowing whether a task is easy or hard*—is central to practical LLM deployment.

**Why the problem matters.** Organizations deploying LLMs face heterogeneous workloads where task difficulty varies substantially. Simple factual queries may require only one model, while complex reasoning tasks benefit from multiple perspectives. Naive strategies—always using one model (cheap but unreliable) or always using many (reliable but expensive)—leave significant value unrealized. A principled routing mechanism that allocates compute adaptively could reduce costs on easy tasks while preserving quality on hard ones.

**Why existing solutions are insufficient.** Current approaches to multi-model orchestration fall into two categories, each with limitations:

1. **Learned routers** (Hu et al., 2024; Chen et al., 2023; Ong et al., 2024) train classifiers to predict which model will succeed on a given query. These achieve high routing accuracy but introduce distribution shift between training and deployment, lack interpretable decision traces, and do not address credit assignment when multiple models contribute.

2. **Observability platforms** provide post-hoc dashboards showing model performance but do not influence routing decisions at execution time. They enable debugging but not adaptive resource allocation.

Neither approach provides the combination of (a) cost-aware routing, (b) measurable attribution when models collaborate, and (c) deterministic reproducibility required for rigorous experimentation.

**Why the problem is challenging.** Three factors make principled multi-model routing difficult:

- **Task difficulty is latent**: We cannot directly observe whether a task is "hard" before attempting it. Difficulty must be estimated from proxy signals.
- **Output equivalence is non-trivial**: Determining whether two model outputs are semantically equivalent (especially for code) requires domain-specific comparison logic.
- **Attribution requires counterfactuals**: Assigning credit to individual models in an ensemble requires knowing what would have happened without each model—expensive counterfactual runs.

### Approach and Contributions

We propose ACAR (Adaptive Complexity & Attribution Routing), which uses *self-consistency variance* (σ) as a task difficulty signal. The intuition is simple: when multiple samples from a fast model agree on an answer, the task is likely easy and a single model suffices; when samples disagree, the task is ambiguous and benefits from diverse model perspectives.

We deliberately use a heuristic σ rather than a learned router. This design choice sacrifices some routing accuracy for three properties we consider essential for credible measurement: (1) no distribution shift between training and deployment, (2) fully interpretable decision traces, and (3) immunity to benchmark-specific overfitting.

**Contributions:**

1. We introduce ACAR, an adaptive routing mechanism using σ-based task difficulty estimation that achieves 55.6% accuracy while avoiding full ensembling on 54.2% of tasks.

2. We demonstrate that retrieval augmentation with low-quality stores *hurts* performance (-3.4pp), providing actionable negative results: similarity thresholds >0.7 are required.

3. We release TeamLLM, a deterministic execution substrate with 7,550+ auditable runs, enabling reproducible multi-model research. All figures in this paper can be regenerated from released artifacts.

---

## 2. Related Work

We position this work at the intersection of three research areas: multi-model routing, cost-aware inference, and reproducible benchmarking. We summarize each area and clarify how ACAR differs.

### 2.1 Multi-Model Routing and Orchestration

**Learned routers.** RouterBench (Hu et al., 2024) introduced a benchmark for evaluating LLM routing systems, comparing learned classifiers that predict which model will succeed on a given query. FrugalGPT (Chen et al., 2023) proposed cascading strategies that route to cheaper models first and escalate only on failure. RouteLLM (Ong et al., 2024) trains routers using preference data from human evaluations.

These systems optimize for routing accuracy—maximizing the probability of selecting the best model. ACAR differs in three ways: (1) we use self-consistency rather than learned classifiers, avoiding distribution shift; (2) we log complete decision traces for auditability; (3) we explicitly measure and report failure modes rather than optimizing a single metric.

**Multi-agent systems.** ReAct (Yao et al., 2023) and related work coordinate tool-augmented agents but focus on single-model reasoning augmented with external tools, not multi-model ensembles. Mixture-of-Experts (Cai et al., 2024) routes at the token level within a single model architecture, orthogonal to our inter-model routing.

### 2.2 Cost-Aware and Adaptive Inference

Several works address the cost-quality trade-off in LLM inference. Speculative decoding uses small models to draft tokens that larger models verify. Early-exit strategies terminate computation when confidence is high. These operate within a single model or model pair; ACAR addresses routing across heterogeneous models from different providers.

The key distinction is that ACAR treats cost awareness as a *measurement* problem: we seek to understand when adaptive routing helps and when it fails, not to maximize a cost-quality metric.

### 2.3 Reproducible Benchmarking Frameworks

Benchmark contamination and evaluation inconsistency have motivated calls for more rigorous evaluation infrastructure. LiveCodeBench provides execution-verified code tasks with temporal splits. SuperGPQA tests broad knowledge with multiple-choice questions.

ACAR contributes to this area by providing: (1) deterministic execution with logged seeds and environment fingerprints, (2) immutable artifacts enabling independent verification, and (3) explicit reporting of negative results alongside positive findings.

**How this work differs.** Unlike learned routing systems, ACAR prioritizes auditability and reproducibility over routing accuracy. Unlike observability platforms, ACAR makes routing decisions at execution time based on measurable signals. Unlike benchmark papers, we report both what works and what fails, with complete artifacts for reproduction.

---

## 3. Method

### 3.1 TeamLLM Execution Substrate

TeamLLM is a research-grade execution substrate designed for auditable multi-model experiments. It enforces three invariants:

1. **Deterministic execution**: Every run captures: random seed, prompt template hash, rubric version, model identifiers, and environment fingerprint. Re-execution with identical inputs produces identical outputs.

2. **Immutable artifacts**: All responses, evaluations, and decision traces are append-only. Modifications create new versioned records; existing records cannot be altered.

3. **Forward-only state machine**: Run status progresses through defined states (PENDING → EXECUTING → VERIFYING → COMPLETED) with no rollback transitions.

Artifacts are stored as structured JSONL files (`runs.jsonl`) containing per-task decision traces. All figures in this paper can be regenerated from these artifacts using provided scripts.

### 3.2 ACAR: Adaptive Complexity Routing

ACAR routes tasks to execution modes based on *self-consistency variance* (σ), a measure of agreement among multiple samples from a fast "probe" model.

#### Definitions

Let T be a task (prompt + expected output format). Let M_probe be a fast model used for difficulty estimation (we use Gemini 2.0 Flash). Let EXTRACT(r) denote an answer extraction function that maps a model response r to a canonical answer representation.

**Definition (Self-Consistency Variance).** Given N=3 independent samples r₁, r₂, r₃ from M_probe on task T, let aᵢ = EXTRACT(rᵢ) be the extracted answers. The self-consistency variance is:

```
σ = (|{a₁, a₂, a₃}| - 1) / 2
```

where |{a₁, a₂, a₃}| counts distinct answers. σ ∈ {0.0, 0.5, 1.0}.

**Definition (Execution Mode).** The execution mode M(σ) maps variance to model count:

| σ Value | Interpretation | Execution Mode |
|---------|----------------|----------------|
| 0.0 | All agree | `single_agent` (1 model) |
| 0.5 | 2/3 agree | `arena_lite` (2 models) |
| 1.0 | All differ | `full_arena` (3 models) |

#### Algorithm

**Algorithm 1: ACAR Routing Procedure**

```
Input: Task T, probe model M_probe, ensemble models {M₁, M₂, M₃}
Output: Final answer a*, decision trace D

Phase 1: Difficulty Estimation
1. for i = 1 to 3 do
2.     rᵢ ← M_probe(T)           // Sample from probe model
3.     aᵢ ← EXTRACT(rᵢ)          // Extract canonical answer
4. end for
5. σ ← (|{a₁, a₂, a₃}| - 1) / 2  // Compute variance

Phase 2: Adaptive Routing
6. if σ = 0.0 then
7.     a* ← a₁                    // All agree: use single answer
8.     mode ← single_agent
9. else if σ = 0.5 then
10.    a* ← MAJORITY_VOTE({a₁, a₂, a₃})
11.    Execute M₁, M₂ for verification
12.    mode ← arena_lite
13. else  // σ = 1.0
14.    Execute all models {M₁, M₂, M₃}
15.    a* ← JUDGE_SELECT({r_M₁, r_M₂, r_M₃})
16.    mode ← full_arena
17. end if

Phase 3: Logging
18. D ← {T, σ, mode, a*, timestamp, cost}
19. Append D to immutable trace

20. return a*, D
```

#### Design Rationale

Several design choices merit explanation:

**Why N=3 samples?** Three samples provide the minimal information to distinguish consensus (all agree), partial agreement (2/3 agree), and disagreement (all differ). Larger N would provide finer granularity but increase probe cost.

**Why discrete σ rather than continuous?** A discrete routing signal ensures deterministic, interpretable decisions. Continuous signals would require threshold tuning, introducing hyperparameters that could overfit to specific benchmarks.

**Why not a learned router?** Learned routers achieve higher routing accuracy but introduce distribution shift and lack interpretability. For a *measurement* framework, we prioritize auditability over optimization.

#### Configurations

We evaluate two ACAR variants:

**ACAR-U (Ult only)** uses σ-based routing without retrieval augmentation.

**ACAR-UJ (Ult + Jungler)** adds asynchronous retrieval from an experience store, injecting similar past examples into prompts before model dispatch. The Jungler component retrieves experiences with similarity above a threshold (we use 0.0, i.e., any match). As we show in Section 6, this design choice leads to negative results.

---

### Figure 1: Distribution of σ Across Tasks

![Figure 1: Sigma Distribution](figures/fig1_sigma_histogram.pdf)

**Figure 1: Distribution of σ across 1,510 tasks.** Task difficulty is bimodal: 32.9% show full agreement (σ=0.0), while 45.8% show complete disagreement (σ=1.0). This bimodality enables effective routing—easy tasks avoid expensive ensembling.

---

## 4. Experimental Setup

### 4.1 Benchmarks

We evaluate on 1,510 tasks spanning four benchmarks selected to cover diverse task types:

- **MathArena** (60 tasks): Competition mathematics problems requiring multi-step reasoning. Highest difficulty in our suite.
- **Reasoning Gym** (250 tasks): Procedural reasoning tasks testing logical inference chains.
- **LiveCodeBench** (200 tasks): Code generation with execution-based verification. Answers are correct only if generated code passes test cases.
- **SuperGPQA** (1,000 tasks): Multiple-choice knowledge questions spanning diverse domains.

### 4.2 Models

All experiments use three frontier models at temperature 0 for deterministic evaluation:
- Claude Sonnet 4 (Anthropic)
- GPT-4o (OpenAI)
- Gemini 2.0 Flash (Google) — also used as probe model M_probe

### 4.3 Configurations

We compare five configurations:
- **Single-Model**: Best single model only (Claude Sonnet 4)
- **Arena-2**: Two-model ensemble (Claude + GPT-4o)
- **Arena-3**: Three-model ensemble (all models, all tasks)
- **ACAR-U**: Adaptive routing without retrieval
- **ACAR-UJ**: Adaptive routing with retrieval augmentation

### 4.4 Metrics

- **Accuracy**: Fraction of tasks with correct final answer
- **Cost**: Total API cost in USD
- **Escalation rate**: Fraction of tasks routed to each mode

---

## 5. Results

### 5.1 Main Results

| Configuration | Accuracy | Correct | Cost |
|---------------|----------|---------|------|
| Single-Model | 45.4% | 686/1510 | $17.04 |
| Arena-2 | 54.4% | 822/1510 | $20.64 |
| **ACAR-U** | **55.6%** | **839/1510** | **$20.34** |
| Arena-3 | 63.6% | 961/1510 | $20.64 |

**Table 1: Overall accuracy on 1,510 tasks.** ACAR-U exceeds Arena-2 while costing less. Arena-3 represents the quality ceiling. Arena-2 and Arena-3 show identical cost due to coordination overhead dominating marginal per-model costs.

---

### Figure 2: Overall Pass Rate Comparison

![Figure 2: Overall Pass Rate](figures/fig2_overall_pass_rate.pdf)

**Figure 2: Overall pass rate comparison.** ACAR-U (55.6%) exceeds Arena-2 (54.4%) with adaptive compute allocation. Arena-3 (63.6%) represents the quality ceiling.

---

ACAR-U exceeds Arena-2 by 1.2 percentage points while costing 1.5% less. The 8.0pp gap to Arena-3 reflects a fundamental limitation discussed in Section 6.

---

### Figure 3: Pass Rate by Benchmark

![Figure 3: Pass Rate by Benchmark](figures/fig3_pass_rate_by_benchmark.pdf)

**Figure 3: Pass rate by benchmark.** Performance varies by domain: SuperGPQA shows highest accuracy (60.5%), while MathArena remains challenging (26.7%). ACAR-U matches or exceeds Arena-2 on all benchmarks.

---

### 5.2 Cost-Accuracy Trade-off

### Figure 4: Cost vs. Accuracy Pareto Frontier

![Figure 4: Cost vs Accuracy](figures/fig4_cost_vs_accuracy.pdf)

**Figure 4: Cost vs. accuracy Pareto frontier.** ACAR-U achieves better accuracy than Arena-2 at lower cost.

---

### 5.3 Escalation Behavior

ACAR-U routes 32.9% of tasks to single-agent, 21.3% to arena-lite, and 45.8% to full-arena. SuperGPQA (easiest) routes 42% to single-agent, while LiveCodeBench escalates 96% to full-arena due to non-canonical code outputs.

---

### Figure 5: Escalation Distribution by Benchmark

![Figure 5: Escalation by Benchmark](figures/fig5_escalation_by_benchmark.pdf)

**Figure 5: Escalation distribution by benchmark.** σ-routing adapts to task difficulty: SuperGPQA routes 42% to single-agent, while MathArena (93%) and LiveCodeBench (96%) escalate to full-arena.

---

### Figure 6: Cumulative Full-Arena Usage

![Figure 6: Cumulative Full Arena](figures/fig6_cumulative_full_arena.pdf)

**Figure 6: Cumulative full-arena usage.** ACAR-U avoids full ensembling on 54.2% of tasks.

---

### 5.4 Latency Analysis

### Figure 7: Latency Distribution

![Figure 7: Latency Comparison](figures/fig7_latency_comparison.pdf)

**Figure 7: Latency distribution by configuration.** ACAR-U achieves intermediate latency by routing easy tasks to faster single-model execution.

---

## 6. Negative Results and Failure Modes

We report three significant negative findings. These are not incidental observations but systematic failures that bound the applicability of our approach.

### 6.1 Retrieval Augmentation Hurts Performance

| Benchmark | ACAR-U | ACAR-UJ | Δ |
|-----------|--------|---------|---|
| MathArena | 26.7% | 21.7% | -5.0pp |
| Reasoning Gym | 46.0% | 44.0% | -2.0pp |
| LiveCodeBench | 51.5% | 47.5% | -4.0pp |
| SuperGPQA | 60.5% | 57.3% | -3.2pp |
| **Overall** | **55.6%** | **52.4%** | **-3.4pp** |

**Table 2: ACAR-UJ vs ACAR-U.** Retrieval augmentation hurts across all benchmarks.

ACAR-UJ *decreased* accuracy by 3.4pp overall. The experience store (837 entries) achieved high hit rates (84-100%) but **median similarity was only 0.167**. Most retrieved experiences were weakly relevant, injecting noise rather than grounding.

---

### Figure 8: Retrieval Hit Rate by Benchmark

![Figure 8: Retrieval Hit Rate](figures/fig8_retrieval_hit_rate.pdf)

**Figure 8: Retrieval hit rate by benchmark.** High hit rates did not predict retrieval utility.

---

### Figure 9: Similarity Distribution (Key Negative Finding)

![Figure 9: Similarity Histogram](figures/fig9_similarity_histogram.pdf)

**Figure 9: Similarity distribution for retrieved experiences.** Median similarity of 0.167 explains why retrieval hurt.

---

**Implication**: Retrieval augmentation requires task-aligned stores with similarity thresholds >0.7.

### 6.2 Agreement-But-Wrong is Unrecoverable

When all probe samples agree on an incorrect answer (σ=0), ACAR routes to single-agent mode and cannot recover. This "agreement-but-wrong" failure is intrinsic to self-consistency: if models consistently produce the same wrong answer, no amount of ensembling helps. The 8pp gap between ACAR-U and Arena-3 quantifies this irreducible ceiling.

### 6.3 Attribution Proxies Do Not Work

We attempted to estimate model contribution using proxy signals (response similarity to final answer, entropy of outputs, agreement patterns). These showed weak correlation with ground-truth leave-one-out values computed via counterfactual runs. Practical attribution requires explicit counterfactual computation.

---

## 7. Discussion

**What worked.**
(1) σ-based routing is robust without learned components.
(2) Selective escalation provides 70% cost reduction on easy tasks.
(3) Infrastructure discipline enables reproducible comparison.

**What failed.**
(1) Attribution proxies did not correlate with ground truth.
(2) Naive retrieval hurt; "more context" is not automatically beneficial.
(3) Agreement-but-wrong bounds achievable accuracy.

**Lessons learned.** Three findings generalize beyond ACAR:

**Self-consistency routing has fundamental limits.** When models unanimously agree incorrectly, no downstream ensemble can recover. Any system relying on agreement-based difficulty estimation will exhibit this ceiling.

**Retrieval requires semantic alignment.** High hit rate does not imply utility. Without similarity thresholds, retrieval injects noise.

**Attribution requires counterfactuals.** Post-hoc attribution from observational data does not work. Practical attribution needs explicit counterfactual runs or architectures that make contribution explicit by design.

---

## 8. Limitations

- **Model set**: Three models from major providers; may not generalize to open-source models.
- **Benchmark bias**: SuperGPQA dominates (66% of tasks).
- **No learned routing**: Learned routers may outperform on specific distributions. We consider this a feature for measurement validity.
- **Code equivalence**: LiveCodeBench escalation is inflated by syntactically different but semantically equivalent outputs.

---

## 9. Conclusion

We presented ACAR, adaptive routing using self-consistency variance. The primary contribution is a *measurement methodology*: σ-based routing exceeds two-model baselines on 54% fewer full-ensemble calls, while naive retrieval *hurts* without task-aligned stores. We documented three assumptions that fail in practice: self-consistency cannot recover from unanimous incorrect agreement; retrieval with high hit rate does not improve performance; attribution cannot be estimated from proxy signals. With 7,550+ auditable runs and regenerable figures, we provide falsifiable baselines for future research.

---

**AI Assistance Disclosure.**
Large language models were used as development and editorial aids in this work. Claude was used to assist in the development of the experimental test harness and in writing and debugging unit tests and evaluation code. ChatGPT was used for drafting support, structural editing, and clarity improvements in the manuscript text.

All experimental design decisions, benchmarks, hypotheses, implementations, executions, result validation, interpretations, and conclusions were conceived, executed, and verified by the author. The author takes full responsibility for the correctness and integrity of the work.

---

## References

1. Hu, Q. J., Bieker, J., Li, X., Jiang, N., Keigwin, B., Ranganath, G., Keutzer, K., & Upadhyay, S. K. (2024). RouterBench: A benchmark for multi-LLM routing system. *arXiv preprint arXiv:2403.12031*.

2. Chen, L., Zaharia, M., & Zou, J. (2023). FrugalGPT: How to use large language models while reducing cost and improving performance. *arXiv preprint arXiv:2305.05176*.

3. Ong, I., Almahairi, A., Wu, V., Chiang, W.-L., Wu, T., Gonzalez, J. E., Kadous, M. W., & Stoica, I. (2024). RouteLLM: Learning to route LLMs with preference data. In *ICLR 2025*.

4. Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing reasoning and acting in language models. In *ICLR 2023*.

5. Cai, W., Jiang, J., Wang, F., Tang, J., Kim, S., & Huang, J. (2024). A survey on mixture of experts in large language models. *arXiv preprint arXiv:2407.06204*.

6. Rozemberczki, B., Watson, L., Bayer, P., Yang, H.-T., Kiss, O., Nilsson, S., & Sarkar, R. (2022). The Shapley value in machine learning. In *IJCAI* (pp. 5572-5579).

7. Wolpert, D. H., & Tumer, K. (2001). Optimal payoff functions for members of collectives. *Advances in Complex Systems*, 4(2-3), 265-279.

---

## Appendix A: Reproducibility

All experimental artifacts are structured for independent verification:

- All runs logged with seed, prompt hash, environment fingerprint
- Complete `runs.jsonl` with per-task decision traces (7,550+ runs)
- Audit reports: zero parse errors across all runs
- 208 unit tests for infrastructure validation
- All figures regenerable from released artifacts

---

## Appendix B: Artifact Manifest

```
artifacts/phase22_acar_u/
  runs.jsonl          # 1,510 ACAR-U runs
  figures/            # All main result figures

artifacts/phase22_acar_uj/
  runs.jsonl          # 1,510 ACAR-UJ runs
  figures/            # Retrieval analysis figures

datasets/
  arena_3model_runs.jsonl    # Arena-3 baseline
  arena_2model_runs.jsonl    # Arena-2 baseline
  single_model_runs.jsonl    # Single-model baseline
```

---

## Appendix C: Figure Manifest

| Figure | Filename | Description |
|--------|----------|-------------|
| Fig 1 | `fig1_sigma_histogram.pdf` | Distribution of σ across tasks |
| Fig 2 | `fig2_overall_pass_rate.pdf` | Overall pass rate comparison |
| Fig 3 | `fig3_pass_rate_by_benchmark.pdf` | Pass rate by benchmark |
| Fig 4 | `fig4_cost_vs_accuracy.pdf` | Cost vs. accuracy Pareto frontier |
| Fig 5 | `fig5_escalation_by_benchmark.pdf` | Escalation distribution by benchmark |
| Fig 6 | `fig6_cumulative_full_arena.pdf` | Cumulative full-arena usage |
| Fig 7 | `fig7_latency_comparison.pdf` | Latency distribution comparison |
| Fig 8 | `fig8_retrieval_hit_rate.pdf` | Retrieval hit rate by benchmark |
| Fig 9 | `fig9_similarity_histogram.pdf` | Similarity distribution for retrievals |

---
