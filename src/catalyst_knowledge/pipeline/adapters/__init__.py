"""Pipeline stage adapters for existing scientific processing modules.

Each adapter wraps an existing script or library module, providing:
- Parameter injection (document_id, paths, config)
- Input/output contract validation
- Error handling and timeout control
- RunManifest integration
"""

__version__ = "1.0.0"

from .pdf_parse_adapter import create_pdf_parse_adapter
from .document_ir_adapter import create_document_ir_adapter
from .figure_parser_adapter import create_figure_parser_adapter
from .table_parser_adapter import create_table_parser_adapter
from .figure_text_adapter import create_figure_text_adapter
from .extraction_adapter import create_extraction_adapter
from .science_extraction_v2_adapter import create_science_extraction_v2_adapter
from .num_unit_adapter import create_num_unit_adapter
from .quality_gate_adapter import create_quality_gate_adapter
from .store_adapter import create_store_adapter
from .report_adapter import create_report_adapter
from .vlm_figure_science_adapter import create_vlm_figure_science_adapter
from .evidence_verifier_adapter import create_evidence_verifier_adapter
from .table_science_adapter import create_table_science_adapter

__all__ = [
    "create_pdf_parse_adapter",
    "create_document_ir_adapter",
    "create_figure_parser_adapter",
    "create_table_parser_adapter",
    "create_figure_text_adapter",
    "create_extraction_adapter",
    "create_science_extraction_v2_adapter",
    "create_num_unit_adapter",
    "create_quality_gate_adapter",
    "create_store_adapter",
    "create_report_adapter",
    "create_vlm_figure_science_adapter",
    "create_evidence_verifier_adapter",
    "create_table_science_adapter",
]
