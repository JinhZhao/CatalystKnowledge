"""Adapter for the formal FigureParser pipeline stage.

Replaces the figure_parser stub in reserved_interfaces.py with a real
implementation that reads MinerU output and produces structured figure records.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..stage_adapter import DataContract, StageAdapter
from ..figure_parser import run_figure_parser

logger = logging.getLogger(__name__)


def create_figure_parser_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for the formal FigureParser."""
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("figure_parser", {})

    adapter = StageAdapter(
        stage_name="figure_parser",
        version="1.0.0",
        input_contract=DataContract(
            required_inputs=["document_id", "namespace", "document_ir_path"],
            optional_inputs=["mineru_output_dir"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "figure_parser_status",
                "figure_parser_output_path",
                "namespace",
                "implementation_status",
            ],
            optional_outputs=[
                "figures_processed", "figures_failed", "figure_count",
                "extraction_source", "source_anchor_preserved",
            ],
        ),
        dependencies=["document_ir"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 300),
    )

    mineru_output = paths.get("mineru_output", "")
    output_dir = str(Path(paths.get("pipeline_runs", "runs/pipeline_001")) / "figure_parser")

    adapter.set_function(
        run_figure_parser,
        mineru_output=mineru_output,
        output_dir=output_dir,
    )
    return adapter
