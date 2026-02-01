# TeamLLM Artifacts System Design

**Version:** 1.0  
**Last Updated:** 2026-01-13  
**Scope:** Artifact definition, ownership, and lifecycle (Arena Mode MVP)  
**Status:** Design approved  

---

## 1. Purpose & Principles

### Purpose
`artifacts.md` defines **what artifacts exist in TeamLLM**, how they are **owned, stored, versioned, exported, and audited**, and which artifacts are **immutable versus derived**.

Artifacts are the **memory and proof layer** of TeamLLM. They enable:
- Reproducibility
- Auditability
- Research analysis
- Enterprise compliance
- User trust without leaking internals

---

### Core Principles

1. **Artifacts are immutable once written**
2. **Artifacts are captured by default**
3. **Ownership is explicit**
4. **Visibility is policy-controlled**
5. **Every decision is traceable**

---

## 2. Artifact Taxonomy

TeamLLM artifacts are grouped into four categories.

### 2.1 Input Artifacts
Describe *what was asked*.

- Task prompt
- Task constraints
- Expected output schema
- Evaluation policy
- Selected models

**Immutability:** Immutable  
**Owner:** System (user-submitted inputs retained as records)

---

### 2.2 Execution Artifacts
Describe *what happened during execution*.

- Run state transitions
- Provider call metadata (latency, tokens, cost)
- Failure events
- Retry attempts
- Truncation flags

**Immutability:** Immutable  
**Owner:** System  

---

### 2.3 Evaluation Artifacts
Describe *how decisions were made*.

- Verifier verdicts
- Ranker orderings
- Tiebreaker outputs
- Scoring components
- Final winner metadata

**Immutability:** Immutable  
**Owner:** System  

---

### 2.4 Output Artifacts
Describe *what was produced*.

- Final winning response
- Optional ranked alternatives (policy-gated)
- Summary explanations (if enabled)

**Immutability:** Winner immutable; derived summaries may evolve  
**Owner:** Shared (system-generated, user-consumable)

---

## 3. Ownership Model (Recommended)

### 3.1 Default Ownership

| Artifact Type | Owner | Rationale |
|--------------|-------|-----------|
| Input | System | Required for replay |
| Execution | System | Internal observability |
| Evaluation | System | Prevent gaming |
| Output | Shared | User value |

> **Design choice:**  
> Artifacts are **system-owned by default**, with **explicit user export rights**.

This mirrors enterprise AI platforms and MAANG internal systems.

---

### 3.2 User Rights

Users may:
- Export output artifacts
- Export selected evaluation summaries (if enabled)
- Delete user-facing outputs (where permitted)

Users may **not**:
- Modify artifacts
- Delete system audit records
- Access hidden evaluation internals by default

---

## 4. Artifact Immutability & Lineage

### 4.1 Immutability Rules

Once written:
- Artifacts cannot be edited
- Corrections require new artifacts
- Superseded artifacts are linked, not replaced

### 4.2 Lineage Graph

Every artifact links to:
- `task_id`
- `run_id`
- Parent artifacts
- Version hashes

This forms a **directed acyclic graph (DAG)** of provenance.

---

## 5. Versioning & Hashing

### 5.1 Versioned Components

The following must be versioned and hashed:
- Prompt templates
- Rubrics
- Evaluation policies
- Scoring constants
- Judge configurations

### 5.2 Hash Strategy

- SHA-256 for content hashing
- Hashes stored alongside artifacts
- Any replay must match hashes exactly

---

## 6. Storage & Retention

### 6.1 Storage Tiers

| Tier | Contents | Purpose |
|----|---------|--------|
| Hot | Recent runs | Fast access |
| Warm | Historical runs | Analysis |
| Cold | Archived runs | Compliance |

### 6.2 Retention Policy (MVP Defaults)

- System artifacts: retained indefinitely
- User outputs: retained per account policy
- Deleted outputs remain referenced (tombstoned) for audit

---

## 7. Export Model

### 7.1 Exportable Artifacts

Users may export:
- Final winner output
- Ranked list (if enabled)
- Summary explanation
- Metadata (timestamps, model IDs)

### 7.2 Export Formats

- JSON (canonical)
- Markdown
- PDF (derived)

Exports are **snapshots**, not live views.

---

## 8. Artifact Visibility & Access Control

Artifact access is governed by **policy + role**.

| Role | Access |
|-----|-------|
| User | Output artifacts only (default) |
| Advanced User | Summary eval artifacts (opt-in) |
| Admin | Full artifacts |
| System | Full |

All access is logged.

---

## 9. Audit & Compliance

TeamLLM can answer:
- What was generated?
- Which models participated?
- Why a winner was chosen?
- What policy was applied?
- Whether the run is reproducible

Artifacts provide:
- SOX-style audit trails
- Research reproducibility
- Incident forensics

---

## 10. Anti-Patterns (Explicitly Disallowed)

- Editing artifacts in place
- Deleting audit records
- Returning raw judge prompts by default
- Allowing user-written artifacts

---

## 11. Future Extensions (Non-MVP)

- Human annotation artifacts
- Dataset labeling exports
- Cross-run artifact analytics
- Artifact diffing and regression views

---

## Document History

| Version | Date | Notes |
|-------|------|------|
| 1.0 | 2026-01-13 | Initial artifacts system design |
