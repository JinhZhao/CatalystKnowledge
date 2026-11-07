"""RecoveryAuditLogger — Log full audit trail for recovery sessions.

Logs:
- Session metadata (ID, document, timestamps, versions)
- Component execution trace
- Input/output quality scores
- Recovery metrics (success rate, cost, LLM usage)
- Field-level audit trail
- Validation report
- Recovery plan
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .failure_classifier import ClassifiedFailures
from .quality_assessment import QualityReport
from .recovery_merger import MergedResults
from .recovery_planner import RecoveryPlan
from .recovery_validator import ValidationReport
from .targeted_extractor import ExtractedField

logger = logging.getLogger(__name__)


@dataclass
class RecoveryMetrics:
    """Recovery session metrics."""
    total_fields_attempted: int = 0
    fields_recovered: int = 0
    fields_preserved: int = 0
    fields_flagged: int = 0
    fields_skipped: int = 0
    recovery_success_rate: float = 0.0
    false_recovery_rate: float = 0.0
    llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class RecoverySession:
    """Complete recovery session record."""
    session_id: str
    document_id: str
    pipeline_version: str
    recovery_engine_version: str
    timestamp_start: str
    timestamp_end: Optional[str] = None
    components_executed: list[str] = field(default_factory=list)
    input_quality_score: float = 0.0
    output_quality_score: float = 0.0
    recovery_metrics: RecoveryMetrics = field(default_factory=RecoveryMetrics)
    quality_report: Optional[dict] = None
    classified_failures: Optional[dict] = None
    recovery_plan: Optional[dict] = None
    extracted_fields: list[dict] = field(default_factory=list)
    merged_results: Optional[dict] = None
    validation_report: Optional[dict] = None
    audit_trail: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class RecoveryAuditLogger:
    """Log full audit trail for recovery sessions."""

    def __init__(self, config: Optional[dict] = None):
        """Initialize with optional configuration."""
        self.config = config or {}
        self.log_dir = Path(self.config.get("log_dir", "runs/recovery_logs"))
        self.log_level = self.config.get("log_level", "INFO")
        self.include_field_level = self.config.get("include_field_level_audit", True)
        self.include_plan = self.config.get("include_recovery_plan", True)
        self.output_format = self.config.get("output_format", "JSON")
        self.retention_days = self.config.get("retention_days", 90)

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, document_id: str) -> RecoverySession:
        """Create a new recovery session.

        Args:
            document_id: Document identifier

        Returns:
            RecoverySession with initial metadata
        """
        session_id = f"RS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return RecoverySession(
            session_id=session_id,
            document_id=document_id,
            pipeline_version="2.0",
            recovery_engine_version="1.0.0",
            timestamp_start=datetime.now().isoformat(),
        )

    def log_quality_assessment(self, session: RecoverySession, report: QualityReport):
        """Log quality assessment results."""
        session.quality_report = {
            "overall_score": report.overall_score,
            "dimension_scores": report.dimension_scores,
            "total_fields": report.total_fields,
            "reported_fields": report.reported_fields,
            "pass_rate": report.pass_rate,
            "critical_failures": len(report.critical_failures),
            "high_failures": len(report.high_failures),
            "checks": [
                {
                    "name": r.check_name,
                    "status": r.status.value,
                    "severity": r.severity.value,
                    "message": r.message,
                }
                for r in report.check_results
            ],
        }
        session.input_quality_score = report.overall_score
        session.components_executed.append("QualityAssessment")
        session.audit_trail.append(f"QualityAssessment: score={report.overall_score:.2f}")

    def log_failure_classification(self, session: RecoverySession, classified: ClassifiedFailures):
        """Log failure classification results."""
        session.classified_failures = {
            "total_failures": classified.total_failures,
            "recoverable_count": classified.recoverable_count,
            "manual_review_count": classified.manual_review_count,
            "not_recoverable_count": classified.not_recoverable_count,
            "by_type": {
                ft.value: len(failures)
                for ft, failures in classified.by_type().items()
            },
            "failures": [
                {
                    "field_path": f.field_path,
                    "failure_type": f.failure_type.value,
                    "severity": f.severity.value,
                    "recoverability": f.recoverability.value,
                    "suggested_strategy": f.suggested_strategy,
                }
                for f in classified.failures
            ],
        }
        session.components_executed.append("FailureClassifier")
        session.audit_trail.append(f"FailureClassifier: {classified.total_failures} failures classified")

    def log_recovery_plan(self, session: RecoverySession, plan: RecoveryPlan):
        """Log recovery plan."""
        if self.include_plan:
            session.recovery_plan = {
                "plan_id": plan.plan_id,
                "created_at": plan.created_at,
                "total_actions": len(plan.actions),
                "total_estimated_tokens": plan.total_estimated_tokens,
                "total_estimated_cost_usd": plan.total_estimated_cost_usd,
                "recoverable_count": plan.recoverable_count,
                "manual_review_count": plan.manual_review_count,
                "actions": [
                    {
                        "action_id": a.action_id,
                        "target_field": a.target_field,
                        "strategy": a.strategy.value,
                        "model": a.model_config.model_name,
                        "priority": a.priority,
                        "estimated_tokens": a.estimated_tokens,
                    }
                    for a in plan.actions
                ],
            }
        session.components_executed.append("RecoveryPlanner")
        session.audit_trail.append(f"RecoveryPlanner: {len(plan.actions)} actions planned")

    def log_extraction(self, session: RecoverySession, extracted: list[ExtractedField]):
        """Log extraction results."""
        if self.include_field_level:
            session.extracted_fields = [
                {
                    "field_path": e.field_path,
                    "value": e.value,
                    "status": e.status,
                    "confidence": e.confidence,
                    "extraction_method": e.extraction_method,
                    "validation_passed": e.validation_passed,
                }
                for e in extracted
            ]
        session.components_executed.append("TargetedExtractor")
        session.recovery_metrics.llm_calls += len(extracted)
        session.audit_trail.append(f"TargetedExtractor: {len(extracted)} fields extracted")

    def log_merge(self, session: RecoverySession, merged: MergedResults):
        """Log merge results."""
        session.merged_results = {
            "merge_id": merged.merge_id,
            "merged_at": merged.merged_at,
            "total_fields_merged": merged.total_fields_merged,
            "fields_replaced": merged.fields_replaced,
            "fields_preserved": merged.fields_preserved,
            "fields_flagged": merged.fields_flagged,
            "fields_skipped": merged.fields_skipped,
            "audit_trail": merged.audit_trail,
        }
        session.recovery_metrics.fields_recovered = merged.fields_replaced
        session.recovery_metrics.fields_preserved = merged.fields_preserved
        session.recovery_metrics.fields_flagged = merged.fields_flagged
        session.recovery_metrics.fields_skipped = merged.fields_skipped
        session.components_executed.append("RecoveryMerger")
        session.audit_trail.append(f"RecoveryMerger: {merged.fields_replaced} fields replaced")

    def log_validation(self, session: RecoverySession, report: ValidationReport):
        """Log validation results."""
        session.validation_report = {
            "report_id": report.report_id,
            "validated_at": report.validated_at,
            "overall_status": report.overall_status.value,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "warning_checks": report.warning_checks,
            "validated_fields": report.validated_fields,
            "rejected_fields": report.rejected_fields,
            "checks": [
                {
                    "name": c.check_name,
                    "status": c.status.value,
                    "message": c.message,
                }
                for c in report.checks
            ],
        }
        session.output_quality_score = report.passed_checks / max(report.total_checks, 1)
        session.components_executed.append("RecoveryValidator")
        session.audit_trail.append(f"RecoveryValidator: {report.overall_status.value}")

    def log_error(self, session: RecoverySession, error: str):
        """Log an error."""
        session.errors.append(error)
        session.audit_trail.append(f"ERROR: {error}")
        logger.error(f"[{session.session_id}] {error}")

    def finalize_session(self, session: RecoverySession):
        """Finalize and save session."""
        session.timestamp_end = datetime.now().isoformat()

        # Calculate duration
        start = datetime.fromisoformat(session.timestamp_start)
        end = datetime.fromisoformat(session.timestamp_end)
        session.recovery_metrics.duration_seconds = (end - start).total_seconds()

        # Calculate success rate
        total_attempted = (
            session.recovery_metrics.fields_recovered
            + session.recovery_metrics.fields_preserved
            + session.recovery_metrics.fields_flagged
            + session.recovery_metrics.fields_skipped
        )
        if total_attempted > 0:
            session.recovery_metrics.recovery_success_rate = (
                session.recovery_metrics.fields_recovered / total_attempted
            )

        # Save session
        self._save_session(session)

    def _save_session(self, session: RecoverySession):
        """Save session to file."""
        filename = f"{session.session_id}_{session.document_id}.json"
        filepath = self.log_dir / filename

        # Convert to dict
        session_dict = asdict(session)

        # Write JSON
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Recovery session saved: {filepath}")

    def load_session(self, session_id: str, document_id: str) -> Optional[RecoverySession]:
        """Load a session from file."""
        filename = f"{session_id}_{document_id}.json"
        filepath = self.log_dir / filename

        if not filepath.exists():
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            session_dict = json.load(f)

        # Convert back to RecoverySession
        return RecoverySession(**session_dict)

    def list_sessions(self, document_id: Optional[str] = None) -> list[str]:
        """List all session IDs."""
        sessions = []
        for filepath in self.log_dir.glob("RS_*.json"):
            if document_id is None or document_id in filepath.name:
                sessions.append(filepath.stem)
        return sorted(sessions)
