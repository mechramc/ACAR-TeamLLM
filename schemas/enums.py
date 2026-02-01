# This file defines data contracts only.
# It does not implement execution logic and is not sufficient to run the system.

"""Enum types defining state machines and domain contracts.

These enums demonstrate forward-only state machine design patterns
used in auditable multi-model orchestration systems.
"""

import enum


class TaskStatus(str, enum.Enum):
    """Task lifecycle states."""

    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class RunStatus(str, enum.Enum):
    """Run execution states (granular).

    Demonstrates forward-only state machine with explicit terminal states.
    """

    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COLLECTING = "COLLECTING"
    VERIFYING = "VERIFYING"
    RANKING = "RANKING"
    SCORING = "SCORING"
    COMPLETED = "COMPLETED"
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    FAILED_INSUFFICIENT_CANDIDATES = "FAILED_INSUFFICIENT_CANDIDATES"
    FAILED_ALL_DISQUALIFIED = "FAILED_ALL_DISQUALIFIED"
    FAILED_BUDGET_EXCEEDED = "FAILED_BUDGET_EXCEEDED"
    CANCELLED = "CANCELLED"

    @classmethod
    def is_running(cls, status: "RunStatus") -> bool:
        """Check if status is in the 'running' family (derived coarse status)."""
        return status in (
            cls.EXECUTING,
            cls.COLLECTING,
            cls.VERIFYING,
            cls.RANKING,
        )

    @classmethod
    def is_terminal(cls, status: "RunStatus") -> bool:
        """Check if status is terminal (no further transitions)."""
        return status in (
            cls.COMPLETED,
            cls.FAILED_TIMEOUT,
            cls.FAILED_INSUFFICIENT_CANDIDATES,
            cls.FAILED_ALL_DISQUALIFIED,
            cls.FAILED_BUDGET_EXCEEDED,
            cls.CANCELLED,
        )


class ResponseStatus(str, enum.Enum):
    """Response lifecycle states."""

    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    DISQUALIFIED = "DISQUALIFIED"
    EVALUATED = "EVALUATED"
    WINNER = "WINNER"


class EvaluationStatus(str, enum.Enum):
    """Evaluation lifecycle states."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    INVALIDATED = "INVALIDATED"


class ArtifactStatus(str, enum.Enum):
    """Artifact storage states.

    Demonstrates immutability pattern: content fields are
    immutable after status == VERIFIED.
    """

    CREATED = "CREATED"
    STORING = "STORING"
    STORED = "STORED"
    VERIFIED = "VERIFIED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class ExperimentStatus(str, enum.Enum):
    """Experiment lifecycle states."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    CANCELLED = "CANCELLED"


class EventType(str, enum.Enum):
    """Canonical event types for audit log.

    Demonstrates comprehensive audit event taxonomy for
    multi-model orchestration systems.
    """

    # Run lifecycle events
    RUN_CREATED = "RUN_CREATED"
    STATE_TRANSITION = "STATE_TRANSITION"

    # Model call events
    MODEL_CALL_STARTED = "MODEL_CALL_STARTED"
    MODEL_CALL_COMPLETED = "MODEL_CALL_COMPLETED"
    MODEL_FAILURE = "MODEL_FAILURE"

    # Response events
    RESPONSE_VALIDATED = "RESPONSE_VALIDATED"
    RESPONSE_REJECTED = "RESPONSE_REJECTED"

    # Evaluation events
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    DISQUALIFICATION = "DISQUALIFICATION"
    RANKING_COMPLETED = "RANKING_COMPLETED"
    SCORING_COMPLETED = "SCORING_COMPLETED"
    WINNER_SELECTED = "WINNER_SELECTED"

    # Judge events
    JUDGE_SELECTED = "JUDGE_SELECTED"
    AUDIT_EVALUATION_TRIGGERED = "AUDIT_EVALUATION_TRIGGERED"
    AUDIT_DISAGREEMENT_DETECTED = "AUDIT_DISAGREEMENT_DETECTED"

    # Security events
    INJECTION_PATTERN_DETECTED = "INJECTION_PATTERN_DETECTED"

    # Budget events
    BUDGET_WARNING = "BUDGET_WARNING"

    # Routing events
    ROUTING_DECISION = "ROUTING_DECISION"

    # Decision trace events
    DECISION_TRACE_CREATED = "DECISION_TRACE_CREATED"


class FailureType(str, enum.Enum):
    """Model call failure types."""

    TIMEOUT = "TIMEOUT"
    SERVER_ERROR = "SERVER_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"


class BudgetStatus(str, enum.Enum):
    """Budget status after run completion."""

    WITHIN_BUDGET = "WITHIN_BUDGET"
    OVER_BUDGET = "OVER_BUDGET"
    SEVERE_OVERAGE = "SEVERE_OVERAGE"


class ArtifactOwnerType(str, enum.Enum):
    """Artifact owner types for polymorphic relationship."""

    TASK = "TASK"
    RUN = "RUN"
    RESPONSE = "RESPONSE"
    EVALUATION = "EVALUATION"
    EXPERIMENT = "EXPERIMENT"


class JudgeType(str, enum.Enum):
    """Judge types for evaluation."""

    MODEL = "MODEL"
    HUMAN = "HUMAN"
    RULE = "RULE"
    HYBRID = "HYBRID"


class TaxonomyClass(str, enum.Enum):
    """Task taxonomy classes for categorization."""

    FACTUAL_QA = "factual_qa"
    EXPLANATION = "explanation"
    COMPARISON = "comparison"
    PLANNING = "planning"
    CODE_GENERATION = "code_generation"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    REASONING = "reasoning"


class ExecutionMode(str, enum.Enum):
    """Adaptive execution modes.

    Demonstrates complexity-based routing:
    - SINGLE_AGENT: Low complexity, one model sufficient
    - ARENA_LITE: Medium complexity, two models
    - FULL_ARENA: High complexity, full ensemble
    """

    SINGLE_AGENT = "single_agent"
    ARENA_LITE = "arena_lite"
    FULL_ARENA = "full_arena"
