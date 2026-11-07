"""FailureClassifier — Classify extraction failures into 14 types.

Failure types:
Recoverable (11):
- LLM_FALSE_NEGATIVE — LLM claims no data when data exists
- LOW_CONFIDENCE — Extraction confidence below threshold
- UNIT_INCONSISTENCY — Unit format issues
- VALUE_OUT_OF_RANGE — Values outside plausible ranges
- CROSS_FIELD_INCOHERENCE — Related fields inconsistent
- MISSING_SOURCE_ANCHOR — No document location
- FORMAT_ERROR — Value format incorrect
- DUPLICATE_ENTRY — Same data extracted multiple times
- EXTRACTION_INCOMPLETE — Partial extraction
- AMBIGUOUS_VALUE — Multiple interpretations possible
- CONTRADICTORY_EVIDENCE — Conflicting data points

Manual Review (2):
- LITERATURE_CONTAMINATION — Literature data mixed with original
- SCHEMA_VIOLATION — Structural schema issues

Not Recoverable (1):
- DATA_NOT_PRESENT — Data genuinely not in document
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import yaml

from .quality_assessment import QualityReport, Severity


class FailureType(str, Enum):
    """Classification of failure types."""
    # Recoverable failures
    LLM_FALSE_NEGATIVE = "LLM_FALSE_NEGATIVE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UNIT_INCONSISTENCY = "UNIT_INCONSISTENCY"
    VALUE_OUT_OF_RANGE = "VALUE_OUT_OF_RANGE"
    CROSS_FIELD_INCOHERENCE = "CROSS_FIELD_INCOHERENCE"
    MISSING_SOURCE_ANCHOR = "MISSING_SOURCE_ANCHOR"
    FORMAT_ERROR = "FORMAT_ERROR"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    EXTRACTION_INCOMPLETE = "EXTRACTION_INCOMPLETE"
    AMBIGUOUS_VALUE = "AMBIGUOUS_VALUE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"

    # Manual review required
    LITERATURE_CONTAMINATION = "LITERATURE_CONTAMINATION"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"

    # Not recoverable
    DATA_NOT_PRESENT = "DATA_NOT_PRESENT"


class Recoverability(str, Enum):
    """Recovery feasibility classification."""
    RECOVERABLE = "RECOVERABLE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NOT_RECOVERABLE = "NOT_RECOVERABLE"


@dataclass
class ClassifiedFailure:
    """A single classified failure."""
    field_path: str
    failure_type: FailureType
    severity: Severity
    recoverability: Recoverability
    message: str
    evidence: Optional[dict] = None
    suggested_strategy: Optional[str] = None


@dataclass
class ClassifiedFailures:
    """Collection of classified failures."""
    failures: list[ClassifiedFailure] = field(default_factory=list)
    total_failures: int = 0
    recoverable_count: int = 0
    manual_review_count: int = 0
    not_recoverable_count: int = 0

    def by_type(self) -> dict[FailureType, list[ClassifiedFailure]]:
        """Group failures by type."""
        result: dict[FailureType, list[ClassifiedFailure]] = {}
        for failure in self.failures:
            if failure.failure_type not in result:
                result[failure.failure_type] = []
            result[failure.failure_type].append(failure)
        return result

    def by_severity(self) -> dict[Severity, list[ClassifiedFailure]]:
        """Group failures by severity."""
        result: dict[Severity, list[ClassifiedFailure]] = {}
        for failure in self.failures:
            if failure.severity not in result:
                result[failure.severity] = []
            result[failure.severity].append(failure)
        return result

    def recoverable_failures(self) -> list[ClassifiedFailure]:
        """Get all recoverable failures."""
        return [f for f in self.failures if f.recoverability == Recoverability.RECOVERABLE]


class FailureClassifier:
    """Classify extraction failures into 14 types."""

    # Mapping from quality check failure modes to failure types
    FAILURE_MODE_MAPPING = {
        "LLM_FALSE_NEGATIVE": (FailureType.LLM_FALSE_NEGATIVE, Recoverability.RECOVERABLE),
        "LOW_CONFIDENCE": (FailureType.LOW_CONFIDENCE, Recoverability.RECOVERABLE),
        "UNIT_INCONSISTENCY": (FailureType.UNIT_INCONSISTENCY, Recoverability.RECOVERABLE),
        "VALUE_OUT_OF_RANGE": (FailureType.VALUE_OUT_OF_RANGE, Recoverability.RECOVERABLE),
        "CROSS_FIELD_INCOHERENCE": (FailureType.CROSS_FIELD_INCOHERENCE, Recoverability.RECOVERABLE),
        "MISSING_SOURCE_ANCHOR": (FailureType.MISSING_SOURCE_ANCHOR, Recoverability.RECOVERABLE),
        "FORMAT_ERROR": (FailureType.FORMAT_ERROR, Recoverability.RECOVERABLE),
        "DUPLICATE_ENTRY": (FailureType.DUPLICATE_ENTRY, Recoverability.RECOVERABLE),
        "EXTRACTION_INCOMPLETE": (FailureType.EXTRACTION_INCOMPLETE, Recoverability.RECOVERABLE),
        "AMBIGUOUS_VALUE": (FailureType.AMBIGUOUS_VALUE, Recoverability.RECOVERABLE),
        "CONTRADICTORY_EVIDENCE": (FailureType.CONTRADICTORY_EVIDENCE, Recoverability.RECOVERABLE),
        "LITERATURE_CONTAMINATION": (FailureType.LITERATURE_CONTAMINATION, Recoverability.MANUAL_REVIEW),
        "SCHEMA_VIOLATION": (FailureType.SCHEMA_VIOLATION, Recoverability.MANUAL_REVIEW),
        "MISSING_VALUE": (FailureType.EXTRACTION_INCOMPLETE, Recoverability.RECOVERABLE),
        "INVALID_SOURCE_TYPE": (FailureType.FORMAT_ERROR, Recoverability.RECOVERABLE),
    }

    # Default recovery strategies for each failure type
    DEFAULT_STRATEGIES = {
        FailureType.LLM_FALSE_NEGATIVE: "TARGETED_REEXTRACTION",
        FailureType.LOW_CONFIDENCE: "TARGETED_REEXTRACTION",
        FailureType.UNIT_INCONSISTENCY: "UNIT_NORMALIZATION",
        FailureType.VALUE_OUT_OF_RANGE: "CONTEXT_REEXTRACTION",
        FailureType.CROSS_FIELD_INCOHERENCE: "CROSS_VALIDATION",
        FailureType.MISSING_SOURCE_ANCHOR: "ANCHOR_INFERENCE",
        FailureType.FORMAT_ERROR: "FORMAT_CORRECTION",
        FailureType.DUPLICATE_ENTRY: "DEDUPLICATION",
        FailureType.EXTRACTION_INCOMPLETE: "TARGETED_REEXTRACTION",
        FailureType.AMBIGUOUS_VALUE: "CONTEXT_REEXTRACTION",
        FailureType.CONTRADICTORY_EVIDENCE: "EVIDENCE_RECONCILIATION",
        FailureType.LITERATURE_CONTAMINATION: "MANUAL_REVIEW",
        FailureType.SCHEMA_VIOLATION: "MANUAL_REVIEW",
        FailureType.DATA_NOT_PRESENT: "SKIP",
    }

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with optional configuration file."""
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load configuration from YAML file."""
        if config_path is None:
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def classify(self, quality_report: QualityReport) -> ClassifiedFailures:
        """Classify all failures from quality report.

        Args:
            quality_report: Output from QualityAssessment

        Returns:
            ClassifiedFailures with all failures categorized
        """
        failures: list[ClassifiedFailure] = []

        # Process failed fields from quality report
        for failed_field in quality_report.failed_fields:
            failure_mode = failed_field.get("failure_mode", "UNKNOWN")
            field_path = failed_field.get("field_path", "unknown")
            severity_str = failed_field.get("severity", "MEDIUM")
            message = failed_field.get("message", "")

            # Map failure mode to type and recoverability
            if failure_mode in self.FAILURE_MODE_MAPPING:
                failure_type, recoverability = self.FAILURE_MODE_MAPPING[failure_mode]
            else:
                failure_type = FailureType.EXTRACTION_INCOMPLETE
                recoverability = Recoverability.RECOVERABLE

            # Get severity
            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.MEDIUM

            # Get suggested strategy
            suggested_strategy = self.DEFAULT_STRATEGIES.get(failure_type, "MANUAL_REVIEW")

            failures.append(ClassifiedFailure(
                field_path=field_path,
                failure_type=failure_type,
                severity=severity,
                recoverability=recoverability,
                message=message,
                evidence=failed_field.get("evidence"),
                suggested_strategy=suggested_strategy,
            ))

        # Process check results for additional failures
        for check_result in quality_report.check_results:
            if check_result.status.value in ["FAIL", "WARNING"]:
                for field_path in check_result.affected_fields:
                    # Avoid duplicates
                    if any(f.field_path == field_path for f in failures):
                        continue

                    # Infer failure type from check name
                    failure_type = self._infer_failure_type(check_result.check_name)
                    recoverability = self._get_recoverability(failure_type)
                    suggested_strategy = self.DEFAULT_STRATEGIES.get(failure_type, "MANUAL_REVIEW")

                    failures.append(ClassifiedFailure(
                        field_path=field_path,
                        failure_type=failure_type,
                        severity=check_result.severity,
                        recoverability=recoverability,
                        message=check_result.message,
                        evidence=check_result.evidence,
                        suggested_strategy=suggested_strategy,
                    ))

        # Calculate counts
        recoverable_count = sum(1 for f in failures if f.recoverability == Recoverability.RECOVERABLE)
        manual_review_count = sum(1 for f in failures if f.recoverability == Recoverability.MANUAL_REVIEW)
        not_recoverable_count = sum(1 for f in failures if f.recoverability == Recoverability.NOT_RECOVERABLE)

        return ClassifiedFailures(
            failures=failures,
            total_failures=len(failures),
            recoverable_count=recoverable_count,
            manual_review_count=manual_review_count,
            not_recoverable_count=not_recoverable_count,
        )

    def _infer_failure_type(self, check_name: str) -> FailureType:
        """Infer failure type from check name."""
        type_mapping = {
            "missing_value_detection": FailureType.EXTRACTION_INCOMPLETE,
            "confidence_threshold": FailureType.LOW_CONFIDENCE,
            "source_type_validation": FailureType.FORMAT_ERROR,
            "unit_consistency": FailureType.UNIT_INCONSISTENCY,
            "range_plausibility": FailureType.VALUE_OUT_OF_RANGE,
            "cross_field_coherence": FailureType.CROSS_FIELD_INCOHERENCE,
            "literature_contamination": FailureType.LITERATURE_CONTAMINATION,
            "false_negative_detection": FailureType.LLM_FALSE_NEGATIVE,
            "extraction_completeness": FailureType.EXTRACTION_INCOMPLETE,
            "schema_compliance": FailureType.SCHEMA_VIOLATION,
            "duplicate_detection": FailureType.DUPLICATE_ENTRY,
        }
        return type_mapping.get(check_name, FailureType.EXTRACTION_INCOMPLETE)

    def _get_recoverability(self, failure_type: FailureType) -> Recoverability:
        """Get recoverability for failure type."""
        if failure_type in [FailureType.LITERATURE_CONTAMINATION, FailureType.SCHEMA_VIOLATION]:
            return Recoverability.MANUAL_REVIEW
        if failure_type == FailureType.DATA_NOT_PRESENT:
            return Recoverability.NOT_RECOVERABLE
        return Recoverability.RECOVERABLE
