"""Recovery Engine — Automated extraction failure detection and recovery.

7 modular components:
1. QualityAssessment — Evaluate extraction quality (10 checks)
2. FailureClassifier — Classify failure types (14 categories)
3. RecoveryPlanner — Plan recovery actions
4. TargetedExtractor — Re-extract failed fields with LLM
5. RecoveryMerger — Merge recovered data with original
6. RecoveryValidator — Validate merged results (7 checks)
7. RecoveryAuditLogger — Log full audit trail
"""

from .quality_assessment import QualityAssessment, QualityReport
from .failure_classifier import FailureClassifier, ClassifiedFailures, FailureType
from .recovery_planner import RecoveryPlanner, RecoveryPlan, RecoveryAction
from .targeted_extractor import TargetedExtractor, ExtractedField
from .recovery_merger import RecoveryMerger, MergedResults
from .recovery_validator import RecoveryValidator, ValidationReport
from .audit_logger import RecoveryAuditLogger, RecoverySession

__version__ = "1.0.0"
__all__ = [
    "QualityAssessment",
    "QualityReport",
    "FailureClassifier",
    "ClassifiedFailures",
    "FailureType",
    "RecoveryPlanner",
    "RecoveryPlan",
    "RecoveryAction",
    "TargetedExtractor",
    "ExtractedField",
    "RecoveryMerger",
    "MergedResults",
    "RecoveryValidator",
    "ValidationReport",
    "RecoveryAuditLogger",
    "RecoverySession",
]
