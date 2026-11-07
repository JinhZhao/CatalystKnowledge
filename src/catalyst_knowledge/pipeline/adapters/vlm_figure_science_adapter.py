"""Adapter for VLM Figure Science pipeline stage.

Wraps the VLM Figure Science Adapter (validated in 005-C/005-D/005-E)
into a formal pipeline stage that integrates with the PipelineOrchestrator.

This stage is OPTIONAL and DISABLED by default.
When disabled, the existing pipeline behavior is unchanged.

Dependencies: figure_parser, document_ir
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
_VLM_ADAPTER_PATH = _PROJECT_ROOT / "runs" / "pipeline_001_fix" / "PIPELINE_005_E"


def _load_vlm_module():
    """Dynamically load the VLM adapter module from 005-E."""
    if str(_VLM_ADAPTER_PATH) not in sys.path:
        sys.path.insert(0, str(_VLM_ADAPTER_PATH))
    import vlm_figure_science_adapter as mod
    return mod


def run_vlm_figure_science_stage(
    document_id: str,
    figure_parser_output_path: str = "",
    namespace: str = "",
    output_dir: str = "",
    model_id: str = "Qwen/Qwen3-VL-32B-Instruct",
    body_text_path: str = "",
    dry_run: bool = False,
    **kwargs,
) -> dict:
    """Pipeline-stage entry point for VLM Figure Science.

    Reads FigureParser output, calls VLM adapter for each figure,
    and writes structured science records.

    Returns a dict matching the output contract.
    """
    mod = _load_vlm_module()

    if not namespace:
        namespace = document_id
    if not output_dir:
        output_dir = str(_PROJECT_ROOT / "runs" / "pipeline_001_fix" / "PIPELINE_005_G")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not figure_parser_output_path:
        return {
            "vlm_figure_science_status": "FAILED",
            "error": "figure_parser_output_path not provided",
            "implementation_status": "MISSING_INPUT",
        }

    fp_path = Path(figure_parser_output_path)
    if not fp_path.exists():
        return {
            "vlm_figure_science_status": "FAILED",
            "error": f"FigureParser output not found: {fp_path}",
            "implementation_status": "FILE_NOT_FOUND",
        }

    with open(fp_path, "r", encoding="utf-8") as f:
        fp_data = json.load(f)

    figures = fp_data.get("figures", [])
    if not figures:
        return {
            "vlm_figure_science_status": "PARTIAL",
            "error": "No figures found in FigureParser output",
            "total_records": 0,
            "figures_processed": 0,
            "implementation_status": "NO_FIGURES",
        }

    body_text = ""
    if body_text_path and Path(body_text_path).exists():
        with open(body_text_path, "r", encoding="utf-8") as f:
            body_text = f.read()

    result = mod.run_vlm_figure_science(
        document_id=document_id,
        figure_records=figures,
        body_text=body_text,
        model_id=model_id,
        output_dir=output_dir,
        namespace=namespace,
        dry_run=dry_run,
    )

    vlm_status = result.get("adapter_status", "FAILED")

    return {
        "vlm_figure_science_status": vlm_status,
        "vlm_output_path": result.get("output_path", ""),
        "total_records": result.get("total_records", 0),
        "figures_processed": result.get("figures_processed", 0),
        "namespace": namespace,
        "implementation_status": "IMPLEMENTED",
        "model_id": model_id,
        "dry_run": dry_run,
    }


def create_vlm_figure_science_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for VLM Figure Science.

    This stage is controlled by config:
        stages.vlm_figure_science.enabled: true/false (default: false)
    """
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("vlm_figure_science", {})

    adapter = StageAdapter(
        stage_name="vlm_figure_science",
        version="005-G-v1",
        input_contract=DataContract(
            required_inputs=["document_id", "figure_parser_output_path"],
            optional_inputs=["namespace", "body_text_path", "model_id"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "vlm_figure_science_status",
                "vlm_output_path",
                "total_records",
                "implementation_status",
            ],
            optional_outputs=[
                "figures_processed", "namespace", "model_id", "dry_run",
            ],
        ),
        dependencies=["figure_parser", "document_ir"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 600),
    )

    output_dir = str(
        Path(paths.get("pipeline_runs", "runs/pipeline_001_fix"))
        / "PIPELINE_005_G"
    )

    adapter.set_function(
        run_vlm_figure_science_stage,
        output_dir=output_dir,
        model_id=stage_cfg.get("model_id", "Qwen/Qwen3-VL-32B-Instruct"),
        body_text_path=stage_cfg.get("body_text_path", ""),
    )
    return adapter
