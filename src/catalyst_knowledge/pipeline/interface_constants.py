"""Unified pipeline interface constants.

Standardizes output key naming and data contracts across all pipeline stages.
All adapters should use these constants to ensure consistency.

Naming convention:
- Status keys: {stage_name}_status (e.g., document_ir_status, extraction_status)
- Output path keys: {stage_name}_output_path or {stage_name}_path
- Count keys: {item}_count (e.g., element_count, figure_count)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StageOutputKeys:
    """Standardized output keys for a pipeline stage."""
    status: str
    output_path: str
    document_id: str = "document_id"
    
    def get_standard_output(self, document_id: str, status: str, output_path: str, **extra) -> dict[str, Any]:
        """Generate a standard output dict."""
        result = {
            self.document_id: document_id,
            self.status: status,
            self.output_path: output_path,
        }
        result.update(extra)
        return result


# Standard stage output keys
PDF_PARSE_KEYS = StageOutputKeys(
    status="parse_status",
    output_path="mineru_output_dir",
)

DOCUMENT_IR_KEYS = StageOutputKeys(
    status="document_ir_status",
    output_path="document_ir_path",
)

FIGURE_TEXT_KEYS = StageOutputKeys(
    status="figure_text_status",
    output_path="figure_associations_path",
)

FIGURE_TABLE_KEYS = StageOutputKeys(
    status="figure_table_status",
    output_path="figure_table_output_path",
)

EXTRACTION_KEYS = StageOutputKeys(
    status="extraction_status",
    output_path="extraction_output_path",
)

SCIENCE_EXTRACTION_V2_KEYS = StageOutputKeys(
    status="extraction_status",
    output_path="extraction_output_path",
)

NUM_UNIT_KEYS = StageOutputKeys(
    status="num_unit_status",
    output_path="num_unit_output_path",
)

QUALITY_GATE_KEYS = StageOutputKeys(
    status="qa_status",
    output_path="qa_report_path",
)

EVIDENCE_VERIFICATION_KEYS = StageOutputKeys(
    status="verification_status",
    output_path="verification_output_path",
)

CANONICAL_STORE_KEYS = StageOutputKeys(
    status="store_status",
    output_path="store_path",
)

REPORT_GENERATION_KEYS = StageOutputKeys(
    status="report_status",
    output_path="report_path",
)

# Reserved stub stage output keys (Phase 2+)
FIGURE_PARSER_KEYS = StageOutputKeys(
    status="figure_parser_status",
    output_path="figure_parser_output_path",
)

TABLE_PARSER_KEYS = StageOutputKeys(
    status="table_parser_status",
    output_path="table_parser_output_path",
)

QUANTITY_PROCESSOR_KEYS = StageOutputKeys(
    status="quantity_processor_status",
    output_path="quantity_processor_output_path",
)

OBJECT_RELATION_KEYS = StageOutputKeys(
    status="object_relation_status",
    output_path="object_relation_output_path",
)

QA_ENHANCER_KEYS = StageOutputKeys(
    status="qa_enhancer_status",
    output_path="qa_enhancer_output_path",
)

RECOVERY_ORCHESTRATOR_KEYS = StageOutputKeys(
    status="recovery_orchestrator_status",
    output_path="recovery_orchestrator_output_path",
)

REPORT_GENERATOR_ENHANCED_KEYS = StageOutputKeys(
    status="report_generator_status",
    output_path="report_generator_output_path",
)


# Standard status values
STATUS_PASS = "PASS"
STATUS_FAIL = "FAILED"
STATUS_PARTIAL = "PARTIAL"
STATUS_SKIP = "SKIPPED"
STATUS_RUNNING = "RUNNING"
STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
STATUS_BLOCKED = "BLOCKED"


# Standard source labels
SOURCE_FRESH = "FRESH"
SOURCE_CACHE = "CACHE_REUSE"
SOURCE_LLM = "llm"
SOURCE_LLM_V2 = "llm_v2"


def validate_stage_output(output: dict[str, Any], keys: StageOutputKeys) -> list[str]:
    """Validate that a stage output dict has all required keys.
    
    Args:
        output: The stage output dict
        keys: The expected output keys
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if keys.document_id not in output:
        errors.append(f"Missing required key: {keys.document_id}")
    
    if keys.status not in output:
        errors.append(f"Missing required key: {keys.status}")
    
    if keys.output_path not in output:
        errors.append(f"Missing required key: {keys.output_path}")
    
    status_value = output.get(keys.status)
    if status_value and status_value not in (
        STATUS_PASS, STATUS_FAIL, STATUS_PARTIAL, STATUS_SKIP,
        STATUS_RUNNING, STATUS_NOT_IMPLEMENTED, STATUS_BLOCKED
    ):
        errors.append(f"Invalid status value: {status_value}")
    
    return errors


def get_stage_label(output: dict[str, Any], keys: StageOutputKeys) -> str:
    """Get the stage execution label.
    
    Returns one of: FRESH / CACHE_REUSE / SKIPPED / NOT_IMPLEMENTED / BLOCKED / FAILED / PARTIAL
    
    NOT_IMPLEMENTED means the module is a stub (not yet built).
    BLOCKED means the stage cannot run due to upstream dependency failure.
    FAILED means the module ran but crashed.
    These are distinct — NOT_IMPLEMENTED is not a runtime error.
    """
    status = output.get(keys.status, STATUS_FAIL)
    source = output.get("extraction_source", output.get("source", ""))
    
    if status == STATUS_SKIP:
        return "SKIPPED"
    elif status == STATUS_NOT_IMPLEMENTED:
        return "NOT_IMPLEMENTED"
    elif status == STATUS_BLOCKED:
        return "BLOCKED"
    elif status == STATUS_FAIL:
        return "FAILED"
    elif status == STATUS_PARTIAL:
        return "PARTIAL"
    elif source in (SOURCE_CACHE, "cache"):
        return "CACHE_REUSE"
    else:
        return "FRESH"
