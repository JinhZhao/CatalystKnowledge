"""Adapter for table_parser.py — Table extraction with SourceAnchors.

Wraps the existing table_parser.py functions to support:
- Single-document processing
- Config-driven paths
- Proper input/output recording
- Unified output contract for downstream stages
- Namespace support for multi-document scenarios
- Cache Manager integration
- Orchestrator integration
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from ..stage_adapter import DataContract, StageAdapter
from ..table_parser import run_table_parser

logger = logging.getLogger(__name__)


def create_table_parser_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for table parsing.
    
    Args:
        config: Pipeline configuration dict
    
    Returns:
        StageAdapter configured for table parsing
    """
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("table_parser", {})

    adapter = StageAdapter(
        stage_name="table_parser",
        version="1.0.0",
        input_contract=DataContract(
            required_inputs=[
                "document_id",
                "namespace",
            ],
            optional_inputs=[
                "mineru_output_dir",
                "document_ir_path",
            ],
        ),
        output_contract=DataContract(
            required_outputs=[
                "table_parser_status",
                "table_parser_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "tables_processed",
                "tables_failed",
                "table_count",
                "extraction_source",
                "source_anchor_preserved",
            ],
        ),
        dependencies=["document_ir"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 300),
    )

    mineru_output = paths.get("mineru_output", "")
    output_dir = paths.get("pipeline_runs", "") + "/table_parser"

    adapter.set_function(
        run_table_parser,
        mineru_output=mineru_output,
        output_dir=output_dir,
    )

    return adapter
