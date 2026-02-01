# ACAR: Adaptive Complexity Routing for Multi-Model Ensembles

This repository contains design documentation, data contracts, and examples
from the ACAR research project on auditable multi-model orchestration.

## Important Notice

**This is NOT a runnable system.**

This repository provides:
- Research paper and methodology documentation
- Design specifications and domain contracts
- Data schema definitions demonstrating state machine patterns
- Example utilities for parsing decision traces

This repository does NOT provide:
- Execution engine or routing logic
- LLM provider integrations
- Experiment configurations or datasets
- Database setup or migrations

The materials here are intended to help others understand the design principles
behind auditable multi-model systems, not to enable reproduction of the full system.

## Contents

```
OpenSource/
├── paper/                    # Research paper (arXiv submission)
│   ├── acar_neurips.tex      # LaTeX source
│   ├── paper_companion.md    # Markdown version
│   └── figures/              # Paper figures
│
├── docs/                     # Design documentation
│   ├── specs/
│   │   ├── schema.md         # Database schema design
│   │   └── contracts.md      # Domain contracts and invariants
│   └── plans/
│       ├── execution_runtime.md  # Execution engine design
│       ├── evaluation.md         # Evaluation system design
│       └── artifacts.md          # Artifact immutability design
│
├── schemas/                  # Data contracts (Python enums)
│   └── enums.py              # State machine definitions
│
└── examples/                 # Usage examples
    ├── trace_format_example.jsonl  # Synthetic decision trace
    └── trace_reader.py             # Standalone trace parser
```

## Key Concepts

### Self-Consistency Variance (σ)

ACAR uses self-consistency variance computed from N=3 probe samples to estimate
task difficulty:

- σ = 0.0: All samples agree → route to single model
- σ = 0.5: 2/3 samples agree → route to two models
- σ = 1.0: All samples differ → route to full ensemble

### Decision Traces

Every execution produces an immutable decision trace containing:
- Task identifier and timestamp
- Computed σ value and routing decision
- Models invoked and winner selection
- Cost and latency measurements

See `examples/trace_format_example.jsonl` for the trace format.

### State Machine Design

The system uses forward-only state machines with explicit terminal states.
See `schemas/enums.py` for the state definitions:

- `RunStatus`: PENDING → EXECUTING → VERIFYING → COMPLETED (or FAILED_*)
- `ArtifactStatus`: CREATED → STORING → STORED → VERIFIED

## Running the Examples

The trace reader requires only Python 3.10+ with no external dependencies:

```bash
cd examples
python trace_reader.py trace_format_example.jsonl
python trace_reader.py --stats trace_format_example.jsonl
```

## Citation

If you use these materials in your research, please cite:

```bibtex
@article{acar2025,
  title={ACAR: Adaptive Complexity Routing for Multi-Model Ensembles
         with Auditable Decision Traces},
  author={Anonymous},
  journal={arXiv preprint},
  year={2025}
}
```

## License

See LICENSE file for terms.
