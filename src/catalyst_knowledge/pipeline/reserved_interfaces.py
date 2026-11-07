"""Reserved interfaces for future pipeline modules.

This module defines the interface contracts for modules that will be implemented
in future phases. These are STUBS only — no implementation logic.

All stubs:
- Return status "NOT_IMPLEMENTED" (distinct from "FAILED")
- Include namespace in output for multi-document isolation
- Preserve document_id and source_anchor traceability
- Never return fake success or mock data
- StageStatus.NOT_IMPLEMENTED = module not yet built
- StageStatus.FAILED = module executed but crashed

Unified types:
- StageStatus: Standard execution status enum
- ErrorInfo: Structured error information
- ExecutionContext: Runtime context passed to all stages
- ExecutionResult: Standard return type wrapping stage output

Modules covered (7 stubs):
- FigureParser (Phase 2)
- TableParser (Phase 2)
- QuantityProcessor (Phase 2)
- ObjectRelationManager (Phase 3)
- QAEnhancer (Phase 2)
- RecoveryOrchestrator (Phase 2)
- ReportGeneratorEnhanced (Phase 2)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .stage_adapter import DataContract, StageAdapter, StageResult


# ============================================================================
# Unified Execution Types
# ============================================================================

class StageStatus(str, Enum):
    """Standard execution status for all pipeline stages."""
    PASS = "PASS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    BLOCKED = "BLOCKED"


@dataclass
class ErrorInfo:
    """Structured error information for stage failures."""
    error_code: str
    error_message: str
    stage_name: str
    recoverable: bool = False
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "error_message": self.error_message,
            "stage_name": self.stage_name,
            "recoverable": self.recoverable,
            "details": self.details,
        }


@dataclass
class ExecutionContext:
    """Runtime context passed to all pipeline stages.
    
    Provides common information that every stage needs:
    - document_id and namespace for isolation
    - config for runtime parameters
    - upstream_outputs for accessing previous stage results
    """
    document_id: str
    namespace: str
    config: dict = field(default_factory=dict)
    upstream_outputs: dict = field(default_factory=dict)
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "config": self.config,
            "upstream_outputs": self.upstream_outputs,
            "dry_run": self.dry_run,
        }


@dataclass
class ExecutionResult:
    """Standard return type wrapping stage output.
    
    Every stage (including stubs) should produce output compatible with this.
    """
    stage_name: str
    status: StageStatus
    document_id: str
    namespace: str
    output_path: str = ""
    output_data: dict = field(default_factory=dict)
    error: Optional[ErrorInfo] = None
    implementation_status: str = "NOT_IMPLEMENTED"
    source_anchor_preserved: bool = True

    def to_dict(self) -> dict[str, Any]:
        result = {
            "stage_name": self.stage_name,
            "status": self.status.value,
            "document_id": self.document_id,
            "namespace": self.namespace,
            "output_path": self.output_path,
            "implementation_status": self.implementation_status,
            "source_anchor_preserved": self.source_anchor_preserved,
        }
        if self.error:
            result["error"] = self.error.to_dict()
        result.update(self.output_data)
        return result

    def to_stage_output(self, status_key: Optional[str] = None, path_key: Optional[str] = None) -> dict[str, Any]:
        """Convert to the dict format expected by StageAdapter.execute().
        
        Args:
            status_key: Override the status key name (default: {stage_name}_status)
            path_key: Override the path key name (default: {stage_name}_output_path)
        """
        output = {
            "document_id": self.document_id,
            "namespace": self.namespace,
        }
        if status_key is None:
            status_key = f"{self.stage_name}_status"
        if path_key is None:
            path_key = f"{self.stage_name}_output_path"
        output[status_key] = self.status.value
        output[path_key] = self.output_path
        output["implementation_status"] = self.implementation_status
        output["source_anchor_preserved"] = self.source_anchor_preserved
        if self.error:
            output["error"] = self.error.to_dict()
        output.update(self.output_data)
        return output


def make_not_implemented_result(
    stage_name: str,
    document_id: str,
    namespace: str,
) -> ExecutionResult:
    """Create a standard NOT_IMPLEMENTED result for stub stages.
    
    Uses StageStatus.NOT_IMPLEMENTED (not FAILED) to distinguish
    "module not yet built" from "module executed but crashed".
    """
    return ExecutionResult(
        stage_name=stage_name,
        status=StageStatus.NOT_IMPLEMENTED,
        document_id=document_id,
        namespace=namespace,
        error=ErrorInfo(
            error_code="NOT_IMPLEMENTED",
            error_message=f"{stage_name} is a Phase 2+ stub, not yet implemented",
            stage_name=stage_name,
            recoverable=False,
        ),
        implementation_status="NOT_IMPLEMENTED",
    )


# ============================================================================
# Figure Parser Interface (Phase 2)
# ============================================================================

@dataclass
class FigureParserInput:
    """Expected input for FigureParser module."""
    document_id: str
    namespace: str
    document_ir_path: str
    figure_associations_path: str
    mineru_output_dir: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "document_ir_path": self.document_ir_path,
            "figure_associations_path": self.figure_associations_path,
            "mineru_output_dir": self.mineru_output_dir,
        }


@dataclass
class FigureParserOutput:
    """Expected output from FigureParser module."""
    document_id: str
    namespace: str
    figure_parser_status: str  # PASS, FAILED, PARTIAL, SKIPPED
    figure_parser_output_path: str
    figures_processed: int
    figures_failed: int
    extraction_source: str  # FRESH, CACHE_REUSE, LLM
    figure_records: list[dict]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "figure_parser_status": self.figure_parser_status,
            "figure_parser_output_path": self.figure_parser_output_path,
            "figures_processed": self.figures_processed,
            "figures_failed": self.figures_failed,
            "extraction_source": self.extraction_source,
            "figure_records": self.figure_records,
        }


def create_figure_parser_adapter_stub(config: dict) -> StageAdapter:
    """Stub adapter for FigureParser (Phase 2).
    
    This is a PLACEHOLDER — returns FAILED status with NOT_IMPLEMENTED error.
    Never returns fake success or mock data.
    """
    adapter = StageAdapter(
        stage_name="figure_parser",
        version="0.0.1-stub",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "document_ir_path"],
            optional_inputs=["figure_associations_path", "mineru_output_dir"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "figure_parser_status",
                "figure_parser_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "figures_processed", "figures_failed",
                "extraction_source", "source_anchor_preserved",
            ],
        ),
        dependencies=["document_ir", "figure_text_association"],
        timeout_seconds=config.get("stages", {}).get("figure_parser", {}).get("timeout_seconds", 300),
    )
    
    def stub_executor(**kwargs):
        result = make_not_implemented_result(
            "figure_parser",
            kwargs.get("document_id", "UNKNOWN"),
            kwargs.get("namespace", kwargs.get("document_id", "UNKNOWN")),
        )
        return result.to_stage_output()
    
    adapter.set_function(stub_executor)
    return adapter


# ============================================================================
# Table Parser Interface (Phase 2)
# ============================================================================

@dataclass
class TableParserInput:
    """Expected input for TableParser module."""
    document_id: str
    namespace: str
    document_ir_path: str
    figure_associations_path: str
    mineru_output_dir: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "document_ir_path": self.document_ir_path,
            "figure_associations_path": self.figure_associations_path,
            "mineru_output_dir": self.mineru_output_dir,
        }


@dataclass
class TableParserOutput:
    """Expected output from TableParser module."""
    document_id: str
    namespace: str
    table_parser_status: str
    table_parser_output_path: str
    tables_processed: int
    tables_failed: int
    extraction_source: str
    table_records: list[dict]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "table_parser_status": self.table_parser_status,
            "table_parser_output_path": self.table_parser_output_path,
            "tables_processed": self.tables_processed,
            "tables_failed": self.tables_failed,
            "extraction_source": self.extraction_source,
            "table_records": self.table_records,
        }


def create_table_parser_adapter_stub(config: dict) -> StageAdapter:
    """Stub adapter for TableParser (Phase 2).
    
    PLACEHOLDER — returns FAILED with NOT_IMPLEMENTED error.
    """
    adapter = StageAdapter(
        stage_name="table_parser",
        version="0.0.1-stub",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "document_ir_path"],
            optional_inputs=["figure_associations_path", "mineru_output_dir"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "table_parser_status",
                "table_parser_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "tables_processed", "tables_failed",
                "extraction_source", "source_anchor_preserved",
            ],
        ),
        dependencies=["document_ir", "figure_text_association"],
        timeout_seconds=config.get("stages", {}).get("table_parser", {}).get("timeout_seconds", 300),
    )
    
    def stub_executor(**kwargs):
        result = make_not_implemented_result(
            "table_parser",
            kwargs.get("document_id", "UNKNOWN"),
            kwargs.get("namespace", kwargs.get("document_id", "UNKNOWN")),
        )
        return result.to_stage_output()
    
    adapter.set_function(stub_executor)
    return adapter


# ============================================================================
# Quantity Processor Interface (Phase 2)
# ============================================================================

@dataclass
class QuantityProcessorInput:
    """Expected input for advanced quantity processing."""
    document_id: str
    namespace: str
    extraction_output_path: str
    num_unit_output_path: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "extraction_output_path": self.extraction_output_path,
            "num_unit_output_path": self.num_unit_output_path,
        }


@dataclass
class QuantityProcessorOutput:
    """Expected output from advanced quantity processing."""
    document_id: str
    namespace: str
    quantity_processor_status: str
    quantity_processor_output_path: str
    quantities_normalized: int
    quantities_failed: int
    si_conversions: list[dict]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "quantity_processor_status": self.quantity_processor_status,
            "quantity_processor_output_path": self.quantity_processor_output_path,
            "quantities_normalized": self.quantities_normalized,
            "quantities_failed": self.quantities_failed,
            "si_conversions": self.si_conversions,
        }


def create_quantity_processor_adapter_stub(config: dict) -> StageAdapter:
    """Stub adapter for QuantityProcessor (Phase 2).
    
    PLACEHOLDER — returns FAILED with NOT_IMPLEMENTED error.
    """
    adapter = StageAdapter(
        stage_name="quantity_processor",
        version="0.0.1-stub",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "extraction_output_path"],
            optional_inputs=["num_unit_output_path"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "quantity_processor_status",
                "quantity_processor_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "quantities_normalized", "quantities_failed",
                "source_anchor_preserved",
            ],
        ),
        dependencies=["six_dimension_extraction", "num_unit_normalization"],
        timeout_seconds=config.get("stages", {}).get("quantity_processor", {}).get("timeout_seconds", 120),
    )
    
    def stub_executor(**kwargs):
        result = make_not_implemented_result(
            "quantity_processor",
            kwargs.get("document_id", "UNKNOWN"),
            kwargs.get("namespace", kwargs.get("document_id", "UNKNOWN")),
        )
        return result.to_stage_output()
    
    adapter.set_function(stub_executor)
    return adapter


# ============================================================================
# Object-Relation Manager Interface (Phase 3)
# ============================================================================

@dataclass
class ObjectRelationManagerInput:
    """Expected input for object-relation organization."""
    document_id: str
    namespace: str
    extraction_output_path: str
    figure_parser_output_path: Optional[str]
    table_parser_output_path: Optional[str]
    quantity_processor_output_path: Optional[str]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "extraction_output_path": self.extraction_output_path,
            "figure_parser_output_path": self.figure_parser_output_path,
            "table_parser_output_path": self.table_parser_output_path,
            "quantity_processor_output_path": self.quantity_processor_output_path,
        }


@dataclass
class ObjectRelationManagerOutput:
    """Expected output from object-relation organization."""
    document_id: str
    namespace: str
    object_relation_status: str
    object_relation_output_path: str
    objects_extracted: int
    relations_extracted: int
    knowledge_graph: dict
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "object_relation_status": self.object_relation_status,
            "object_relation_output_path": self.object_relation_output_path,
            "objects_extracted": self.objects_extracted,
            "relations_extracted": self.relations_extracted,
            "knowledge_graph": self.knowledge_graph,
        }


def create_object_relation_manager_adapter_stub(config: dict) -> StageAdapter:
    """Stub adapter for ObjectRelationManager (Phase 3).
    
    PLACEHOLDER — returns FAILED with NOT_IMPLEMENTED error.
    """
    adapter = StageAdapter(
        stage_name="object_relation_manager",
        version="0.0.1-stub",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "extraction_output_path"],
            optional_inputs=[
                "figure_parser_output_path",
                "table_parser_output_path",
                "quantity_processor_output_path",
            ],
        ),
        output_contract=DataContract(
            required_outputs=[
                "object_relation_status",
                "object_relation_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "objects_extracted", "relations_extracted",
                "source_anchor_preserved",
            ],
        ),
        dependencies=["six_dimension_extraction"],
        timeout_seconds=config.get("stages", {}).get("object_relation_manager", {}).get("timeout_seconds", 180),
    )
    
    def stub_executor(**kwargs):
        result = make_not_implemented_result(
            "object_relation_manager",
            kwargs.get("document_id", "UNKNOWN"),
            kwargs.get("namespace", kwargs.get("document_id", "UNKNOWN")),
        )
        return result.to_stage_output(
            status_key="object_relation_status",
            path_key="object_relation_output_path",
        )
    
    adapter.set_function(stub_executor)
    return adapter


# ============================================================================
# QA Enhancer Interface (Phase 2)
# ============================================================================

@dataclass
class QAEnhancerInput:
    """Expected input for enhanced quality assessment."""
    document_id: str
    namespace: str
    extraction_output_path: str
    qa_report_path: str
    figure_parser_output_path: Optional[str]
    table_parser_output_path: Optional[str]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "extraction_output_path": self.extraction_output_path,
            "qa_report_path": self.qa_report_path,
            "figure_parser_output_path": self.figure_parser_output_path,
            "table_parser_output_path": self.table_parser_output_path,
        }


@dataclass
class QAEnhancerOutput:
    """Expected output from enhanced quality assessment."""
    document_id: str
    namespace: str
    qa_enhancer_status: str
    qa_enhancer_output_path: str
    scientific_validations: list[dict]
    overall_confidence: float
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "qa_enhancer_status": self.qa_enhancer_status,
            "qa_enhancer_output_path": self.qa_enhancer_output_path,
            "scientific_validations": self.scientific_validations,
            "overall_confidence": self.overall_confidence,
        }


def create_qa_enhancer_adapter_stub(config: dict) -> StageAdapter:
    """Stub adapter for QAEnhancer (Phase 2).
    
    PLACEHOLDER — returns FAILED with NOT_IMPLEMENTED error.
    """
    adapter = StageAdapter(
        stage_name="qa_enhancer",
        version="0.0.1-stub",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "extraction_output_path", "qa_report_path"],
            optional_inputs=["figure_parser_output_path", "table_parser_output_path"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "qa_enhancer_status",
                "qa_enhancer_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "scientific_validations", "overall_confidence",
                "source_anchor_preserved",
            ],
        ),
        dependencies=["quality_gate"],
        timeout_seconds=config.get("stages", {}).get("qa_enhancer", {}).get("timeout_seconds", 60),
    )
    
    def stub_executor(**kwargs):
        result = make_not_implemented_result(
            "qa_enhancer",
            kwargs.get("document_id", "UNKNOWN"),
            kwargs.get("namespace", kwargs.get("document_id", "UNKNOWN")),
        )
        return result.to_stage_output()
    
    adapter.set_function(stub_executor)
    return adapter


# ============================================================================
# Recovery Orchestrator Interface (Phase 2)
# ============================================================================

@dataclass
class RecoveryOrchestratorInput:
    """Expected input for recovery coordination."""
    document_id: str
    namespace: str
    qa_enhancer_output_path: str
    extraction_output_path: str
    recovery_config: Optional[dict]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "qa_enhancer_output_path": self.qa_enhancer_output_path,
            "extraction_output_path": self.extraction_output_path,
            "recovery_config": self.recovery_config,
        }


@dataclass
class RecoveryOrchestratorOutput:
    """Expected output from recovery coordination."""
    document_id: str
    namespace: str
    recovery_orchestrator_status: str
    recovery_orchestrator_output_path: str
    recovery_actions_taken: list[dict]
    fields_recovered: int
    recovery_success_rate: float
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "recovery_orchestrator_status": self.recovery_orchestrator_status,
            "recovery_orchestrator_output_path": self.recovery_orchestrator_output_path,
            "recovery_actions_taken": self.recovery_actions_taken,
            "fields_recovered": self.fields_recovered,
            "recovery_success_rate": self.recovery_success_rate,
        }


def create_recovery_orchestrator_adapter_stub(config: dict) -> StageAdapter:
    """Stub adapter for RecoveryOrchestrator (Phase 2).
    
    PLACEHOLDER — returns FAILED with NOT_IMPLEMENTED error.
    Note: Recovery engine already exists in recovery_engine/ module.
    This orchestrator will integrate it with the unified pipeline flow.
    """
    adapter = StageAdapter(
        stage_name="recovery_orchestrator",
        version="0.0.1-stub",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "qa_enhancer_output_path"],
            optional_inputs=["extraction_output_path", "recovery_config"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "recovery_orchestrator_status",
                "recovery_orchestrator_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "recovery_actions_taken", "fields_recovered",
                "recovery_success_rate", "source_anchor_preserved",
            ],
        ),
        dependencies=["qa_enhancer"],
        timeout_seconds=config.get("stages", {}).get("recovery_orchestrator", {}).get("timeout_seconds", 600),
    )
    
    def stub_executor(**kwargs):
        result = make_not_implemented_result(
            "recovery_orchestrator",
            kwargs.get("document_id", "UNKNOWN"),
            kwargs.get("namespace", kwargs.get("document_id", "UNKNOWN")),
        )
        return result.to_stage_output()
    
    adapter.set_function(stub_executor)
    return adapter


# ============================================================================
# Report Generator Interface (Phase 2)
# ============================================================================

@dataclass
class ReportGeneratorInput:
    """Expected input for comprehensive report generation."""
    document_id: str
    namespace: str
    store_path: str
    object_relation_output_path: Optional[str]
    qa_enhancer_output_path: Optional[str]
    recovery_orchestrator_output_path: Optional[str]
    report_template: Optional[str]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "store_path": self.store_path,
            "object_relation_output_path": self.object_relation_output_path,
            "qa_enhancer_output_path": self.qa_enhancer_output_path,
            "recovery_orchestrator_output_path": self.recovery_orchestrator_output_path,
            "report_template": self.report_template,
        }


@dataclass
class ReportGeneratorOutput:
    """Expected output from comprehensive report generation."""
    document_id: str
    namespace: str
    report_generator_status: str
    report_generator_output_path: str
    report_format: str  # JSON, HTML, PDF, MD
    report_sections: list[str]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "report_generator_status": self.report_generator_status,
            "report_generator_output_path": self.report_generator_output_path,
            "report_format": self.report_format,
            "report_sections": self.report_sections,
        }


def create_report_generator_adapter_stub(config: dict) -> StageAdapter:
    """Stub adapter for enhanced ReportGenerator (Phase 2).
    
    PLACEHOLDER — returns FAILED with NOT_IMPLEMENTED error.
    Note: Basic report generation already exists in report_adapter.py.
    This enhanced version will integrate all Phase 2 outputs.
    """
    adapter = StageAdapter(
        stage_name="report_generator_enhanced",
        version="0.0.1-stub",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "store_path"],
            optional_inputs=[
                "object_relation_output_path",
                "qa_enhancer_output_path",
                "recovery_orchestrator_output_path",
                "report_template",
            ],
        ),
        output_contract=DataContract(
            required_outputs=[
                "report_generator_status",
                "report_generator_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "report_format", "report_sections",
                "source_anchor_preserved",
            ],
        ),
        dependencies=["canonical_store"],
        timeout_seconds=config.get("stages", {}).get("report_generator_enhanced", {}).get("timeout_seconds", 180),
    )
    
    def stub_executor(**kwargs):
        result = make_not_implemented_result(
            "report_generator_enhanced",
            kwargs.get("document_id", "UNKNOWN"),
            kwargs.get("namespace", kwargs.get("document_id", "UNKNOWN")),
        )
        return result.to_stage_output(
            status_key="report_generator_status",
            path_key="report_generator_output_path",
        )
    
    adapter.set_function(stub_executor)
    return adapter


# ============================================================================
# Interface Registry
# ============================================================================

STUB_ADAPTERS = {
    "figure_parser": create_figure_parser_adapter_stub,
    "table_parser": create_table_parser_adapter_stub,
    "quantity_processor": create_quantity_processor_adapter_stub,
    "object_relation_manager": create_object_relation_manager_adapter_stub,
    "qa_enhancer": create_qa_enhancer_adapter_stub,
    "recovery_orchestrator": create_recovery_orchestrator_adapter_stub,
    "report_generator_enhanced": create_report_generator_adapter_stub,
}


def get_stub_adapter_names() -> list[str]:
    """Return list of all stub adapter names."""
    return list(STUB_ADAPTERS.keys())


def is_stub_adapter(stage_name: str) -> bool:
    """Check if a stage name corresponds to a stub adapter."""
    return stage_name in STUB_ADAPTERS


def create_stub_adapter(stage_name: str, config: dict) -> Optional[StageAdapter]:
    """Create a stub adapter by name.
    
    Args:
        stage_name: Name of the stub adapter to create
        config: Pipeline configuration
        
    Returns:
        StageAdapter stub or None if not found
    """
    factory = STUB_ADAPTERS.get(stage_name)
    if factory is None:
        return None
    return factory(config)
