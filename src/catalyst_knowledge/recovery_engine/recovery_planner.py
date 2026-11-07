"""RecoveryPlanner — Plan recovery actions for classified failures.

Generates actionable recovery plans with:
- Target field identification
- Recovery strategy selection
- Model configuration
- Context window specification
- Cost estimation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import yaml

from .failure_classifier import ClassifiedFailures, FailureType, Recoverability


class RecoveryStrategy(str, Enum):
    """Recovery strategy types."""
    TARGETED_REEXTRACTION = "TARGETED_REEXTRACTION"
    CONTEXT_REEXTRACTION = "CONTEXT_REEXTRACTION"
    UNIT_NORMALIZATION = "UNIT_NORMALIZATION"
    CROSS_VALIDATION = "CROSS_VALIDATION"
    ANCHOR_INFERENCE = "ANCHOR_INFERENCE"
    FORMAT_CORRECTION = "FORMAT_CORRECTION"
    DEDUPLICATION = "DEDUPLICATION"
    EVIDENCE_RECONCILIATION = "EVIDENCE_RECONCILIATION"
    MODEL_UPGRADE = "MODEL_UPGRADE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    SKIP = "SKIP"


class ModelTier(str, Enum):
    """LLM model tiers for cost optimization."""
    FLASH = "FLASH"  # Fast, cheap, for simple tasks
    PRO = "PRO"  # Balanced cost/performance
    PREMIUM = "PREMIUM"  # Expensive, for complex tasks


@dataclass
class ModelConfig:
    """Model configuration for recovery action."""
    tier: ModelTier
    model_name: str
    temperature: float = 0.1
    max_tokens: int = 1000


@dataclass
class ContextWindow:
    """Document context window for targeted extraction."""
    section: Optional[str] = None
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None
    surrounding_lines: int = 5


@dataclass
class RecoveryAction:
    """Single recovery action specification."""
    action_id: str
    target_field: str
    failure_type: FailureType
    strategy: RecoveryStrategy
    model_config: ModelConfig
    context_window: ContextWindow
    prompt_template: str
    expected_output_schema: dict
    priority: int  # 1 = highest, 5 = lowest
    estimated_tokens: int = 500


@dataclass
class RecoveryPlan:
    """Complete recovery plan with multiple actions."""
    plan_id: str
    document_id: str
    created_at: str
    actions: list[RecoveryAction] = field(default_factory=list)
    total_estimated_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    recoverable_count: int = 0
    manual_review_count: int = 0
    skipped_count: int = 0

    def by_priority(self) -> dict[int, list[RecoveryAction]]:
        """Group actions by priority."""
        result: dict[int, list[RecoveryAction]] = {}
        for action in self.actions:
            if action.priority not in result:
                result[action.priority] = []
            result[action.priority].append(action)
        return result

    def high_priority_actions(self) -> list[RecoveryAction]:
        """Get priority 1-2 actions."""
        return [a for a in self.actions if a.priority <= 2]


class RecoveryPlanner:
    """Generate recovery plans for classified failures."""

    # Default model configurations per failure type
    DEFAULT_MODEL_CONFIGS = {
        FailureType.LLM_FALSE_NEGATIVE: ModelConfig(
            tier=ModelTier.FLASH,
            model_name="deepseek-v3-flash",
            temperature=0.1,
            max_tokens=800,
        ),
        FailureType.LOW_CONFIDENCE: ModelConfig(
            tier=ModelTier.FLASH,
            model_name="deepseek-v3-flash",
            temperature=0.1,
            max_tokens=800,
        ),
        FailureType.LITERATURE_CONTAMINATION: ModelConfig(
            tier=ModelTier.PRO,
            model_name="glm-4-pro",
            temperature=0.05,
            max_tokens=1200,
        ),
        FailureType.VALUE_OUT_OF_RANGE: ModelConfig(
            tier=ModelTier.PRO,
            model_name="glm-4-pro",
            temperature=0.1,
            max_tokens=1000,
        ),
        FailureType.CROSS_FIELD_INCOHERENCE: ModelConfig(
            tier=ModelTier.PRO,
            model_name="glm-4-pro",
            temperature=0.1,
            max_tokens=1000,
        ),
    }

    # Default prompt templates
    PROMPT_TEMPLATES = {
        RecoveryStrategy.TARGETED_REEXTRACTION: "recovery_targeted_extraction",
        RecoveryStrategy.CONTEXT_REEXTRACTION: "recovery_context_extraction",
        RecoveryStrategy.UNIT_NORMALIZATION: "recovery_unit_normalization",
        RecoveryStrategy.CROSS_VALIDATION: "recovery_cross_validation",
        RecoveryStrategy.ANCHOR_INFERENCE: "recovery_anchor_inference",
        RecoveryStrategy.FORMAT_CORRECTION: "recovery_format_correction",
        RecoveryStrategy.DEDUPLICATION: "recovery_deduplication",
        RecoveryStrategy.EVIDENCE_RECONCILIATION: "recovery_evidence_reconciliation",
        RecoveryStrategy.MODEL_UPGRADE: "recovery_targeted_extraction",
        RecoveryStrategy.MANUAL_REVIEW: "recovery_manual_review_flag",
        RecoveryStrategy.SKIP: "recovery_skip",
    }

    # Cost per 1K tokens by model tier (approximate)
    COST_PER_1K_TOKENS = {
        ModelTier.FLASH: 0.001,
        ModelTier.PRO: 0.005,
        ModelTier.PREMIUM: 0.02,
    }

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with optional configuration file."""
        self.config = self._load_config(config_path)
        self._action_counter = 0

    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load configuration from YAML file."""
        if config_path is None:
            return {
                "max_recovery_attempts": 2,
                "cost_budget_tokens": 10000,
                "cost_budget_usd": 1.0,
            }
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def plan(
        self,
        classified_failures: ClassifiedFailures,
        document_ir: Optional[dict] = None,
        document_text: Optional[str] = None,
    ) -> RecoveryPlan:
        """Generate recovery plan for classified failures.

        Args:
            classified_failures: Output from FailureClassifier
            document_ir: Document intermediate representation
            document_text: Full document text for context extraction

        Returns:
            RecoveryPlan with actionable recovery steps
        """
        plan_id = f"PLAN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        document_id = document_ir.get("document_id", "unknown") if document_ir else "unknown"

        actions: list[RecoveryAction] = []
        total_tokens = 0
        recoverable_count = 0
        manual_review_count = 0
        skipped_count = 0

        # Process each failure
        for failure in classified_failures.failures:
            # Determine strategy
            strategy = self._select_strategy(failure)

            # Skip if strategy is SKIP
            if strategy == RecoveryStrategy.SKIP:
                skipped_count += 1
                continue

            # Skip if manual review required
            if failure.recoverability == Recoverability.MANUAL_REVIEW:
                manual_review_count += 1
                # Still create action for tracking
                action = self._create_action(
                    failure=failure,
                    strategy=strategy,
                    document_ir=document_ir,
                    document_text=document_text,
                    priority=4,  # Low priority for manual review
                )
                actions.append(action)
                total_tokens += action.estimated_tokens
                continue

            # Create recovery action
            priority = self._calculate_priority(failure)
            action = self._create_action(
                failure=failure,
                strategy=strategy,
                document_ir=document_ir,
                document_text=document_text,
                priority=priority,
            )
            actions.append(action)
            total_tokens += action.estimated_tokens
            recoverable_count += 1

        # Sort by priority
        actions.sort(key=lambda a: a.priority)

        # Calculate cost
        total_cost = self._calculate_cost(actions)

        return RecoveryPlan(
            plan_id=plan_id,
            document_id=document_id,
            created_at=datetime.now().isoformat(),
            actions=actions,
            total_estimated_tokens=total_tokens,
            total_estimated_cost_usd=total_cost,
            recoverable_count=recoverable_count,
            manual_review_count=manual_review_count,
            skipped_count=skipped_count,
        )

    def _select_strategy(self, failure: ClassifiedFailure) -> RecoveryStrategy:
        """Select recovery strategy for failure."""
        # Use suggested strategy if available
        if failure.suggested_strategy:
            try:
                return RecoveryStrategy(failure.suggested_strategy)
            except ValueError:
                pass

        # Map failure type to strategy
        strategy_mapping = {
            FailureType.LLM_FALSE_NEGATIVE: RecoveryStrategy.TARGETED_REEXTRACTION,
            FailureType.LOW_CONFIDENCE: RecoveryStrategy.TARGETED_REEXTRACTION,
            FailureType.UNIT_INCONSISTENCY: RecoveryStrategy.UNIT_NORMALIZATION,
            FailureType.VALUE_OUT_OF_RANGE: RecoveryStrategy.CONTEXT_REEXTRACTION,
            FailureType.CROSS_FIELD_INCOHERENCE: RecoveryStrategy.CROSS_VALIDATION,
            FailureType.MISSING_SOURCE_ANCHOR: RecoveryStrategy.ANCHOR_INFERENCE,
            FailureType.FORMAT_ERROR: RecoveryStrategy.FORMAT_CORRECTION,
            FailureType.DUPLICATE_ENTRY: RecoveryStrategy.DEDUPLICATION,
            FailureType.EXTRACTION_INCOMPLETE: RecoveryStrategy.TARGETED_REEXTRACTION,
            FailureType.AMBIGUOUS_VALUE: RecoveryStrategy.CONTEXT_REEXTRACTION,
            FailureType.CONTRADICTORY_EVIDENCE: RecoveryStrategy.EVIDENCE_RECONCILIATION,
            FailureType.LITERATURE_CONTAMINATION: RecoveryStrategy.MANUAL_REVIEW,
            FailureType.SCHEMA_VIOLATION: RecoveryStrategy.MANUAL_REVIEW,
            FailureType.DATA_NOT_PRESENT: RecoveryStrategy.SKIP,
        }

        return strategy_mapping.get(failure.failure_type, RecoveryStrategy.MANUAL_REVIEW)

    def _calculate_priority(self, failure: ClassifiedFailure) -> int:
        """Calculate action priority (1=highest, 5=lowest)."""
        # Priority based on severity and recoverability
        severity_priority = {
            "CRITICAL": 1,
            "HIGH": 2,
            "MEDIUM": 3,
            "LOW": 4,
        }
        base_priority = severity_priority.get(failure.severity.value, 3)

        # Adjust for failure type
        if failure.failure_type == FailureType.LLM_FALSE_NEGATIVE:
            return min(base_priority, 2)  # High priority for false negatives
        if failure.failure_type == FailureType.LITERATURE_CONTAMINATION:
            return 1  # Critical priority for contamination

        return base_priority

    def _create_action(
        self,
        failure: ClassifiedFailure,
        strategy: RecoveryStrategy,
        document_ir: Optional[dict],
        document_text: Optional[str],
        priority: int,
    ) -> RecoveryAction:
        """Create a single recovery action."""
        self._action_counter += 1
        action_id = f"ACT_{self._action_counter:03d}"

        # Get model config
        model_config = self._get_model_config(failure.failure_type)

        # Determine context window
        context_window = self._determine_context_window(
            field_path=failure.field_path,
            document_ir=document_ir,
            document_text=document_text,
        )

        # Get prompt template
        prompt_template = self.PROMPT_TEMPLATES.get(strategy, "recovery_targeted_extraction")

        # Estimate tokens
        estimated_tokens = self._estimate_tokens(strategy, context_window)

        # Expected output schema
        expected_schema = self._get_expected_schema(failure.field_path)

        return RecoveryAction(
            action_id=action_id,
            target_field=failure.field_path,
            failure_type=failure.failure_type,
            strategy=strategy,
            model_config=model_config,
            context_window=context_window,
            prompt_template=prompt_template,
            expected_output_schema=expected_schema,
            priority=priority,
            estimated_tokens=estimated_tokens,
        )

    def _get_model_config(self, failure_type: FailureType) -> ModelConfig:
        """Get model configuration for failure type."""
        return self.DEFAULT_MODEL_CONFIGS.get(
            failure_type,
            ModelConfig(
                tier=ModelTier.FLASH,
                model_name="deepseek-v3-flash",
                temperature=0.1,
                max_tokens=800,
            )
        )

    def _determine_context_window(
        self,
        field_path: str,
        document_ir: Optional[dict],
        document_text: Optional[str],
    ) -> ContextWindow:
        """Determine context window for extraction."""
        # Parse field path to infer section
        parts = field_path.split(".")
        dimension = parts[0] if parts else ""

        # Map dimension to likely section
        section_mapping = {
            "catalyst_design": "Catalyst Preparation",
            "characterization": "Characterization",
            "performance": "Catalytic Performance",
            "mechanism": "Mechanism",
            "structure_activity": "Structure-Activity Relationship",
            "reliability": "Stability",
        }

        section = section_mapping.get(dimension, None)

        # Try to find section in document_ir
        if document_ir and section:
            sections = document_ir.get("sections", [])
            for sec in sections:
                if section.lower() in sec.get("title", "").lower():
                    return ContextWindow(
                        section=sec.get("title"),
                        char_offset_start=sec.get("start_offset"),
                        char_offset_end=sec.get("end_offset"),
                        surrounding_lines=5,
                    )

        # Default context window
        return ContextWindow(
            section=section,
            surrounding_lines=10,
        )

    def _estimate_tokens(self, strategy: RecoveryStrategy, context_window: ContextWindow) -> int:
        """Estimate token cost for action."""
        # Base tokens by strategy
        base_tokens = {
            RecoveryStrategy.TARGETED_REEXTRACTION: 500,
            RecoveryStrategy.CONTEXT_REEXTRACTION: 600,
            RecoveryStrategy.UNIT_NORMALIZATION: 200,
            RecoveryStrategy.CROSS_VALIDATION: 400,
            RecoveryStrategy.ANCHOR_INFERENCE: 300,
            RecoveryStrategy.FORMAT_CORRECTION: 250,
            RecoveryStrategy.DEDUPLICATION: 350,
            RecoveryStrategy.EVIDENCE_RECONCILIATION: 500,
            RecoveryStrategy.MODEL_UPGRADE: 600,
            RecoveryStrategy.MANUAL_REVIEW: 100,
            RecoveryStrategy.SKIP: 0,
        }

        base = base_tokens.get(strategy, 400)

        # Add context tokens
        context_lines = context_window.surrounding_lines
        context_tokens = context_lines * 20  # ~20 tokens per line

        return base + context_tokens

    def _get_expected_schema(self, field_path: str) -> dict:
        """Get expected output schema for field."""
        # Infer schema from field path
        parts = field_path.split(".")
        field_name = parts[-1] if parts else ""

        # Common field patterns
        if "temperature" in field_name.lower():
            return {"value_type": "numerical", "unit_type": "temperature"}
        if "pressure" in field_name.lower():
            return {"value_type": "numerical", "unit_type": "pressure"}
        if "conversion" in field_name.lower() or "selectivity" in field_name.lower():
            return {"value_type": "numerical", "unit_type": "percent"}
        if "size" in field_name.lower():
            return {"value_type": "numerical", "unit_type": "length"}
        if "energy" in field_name.lower():
            return {"value_type": "numerical", "unit_type": "energy"}

        # Default schema
        return {"value_type": "text", "validation_rules": []}

    def _calculate_cost(self, actions: list[RecoveryAction]) -> float:
        """Calculate total estimated cost."""
        total_cost = 0.0
        for action in actions:
            tier_cost = self.COST_PER_1K_TOKENS.get(action.model_config.tier, 0.005)
            action_cost = (action.estimated_tokens / 1000) * tier_cost
            total_cost += action_cost
        return total_cost
