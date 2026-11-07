"""Adapter for figure_text_association_v2.py — Figure/Table-Text association.

Wraps process_document() from the existing script.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Optional

from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)

_module = None


def _load_module():
    global _module
    if _module is not None:
        return _module
    project_root = Path(__file__).parent.parent.parent.parent.parent
    script_path = project_root / "scripts" / "figure_text_association_v2.py"
    if not script_path.exists():
        raise FileNotFoundError(f"figure_text_association_v2.py not found at {script_path}")
    spec = importlib.util.spec_from_file_location("figure_text_association_v2", script_path)
    _module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_module)
    return _module


def _find_mineru_auto_dir(mineru_output: str, document_id: str) -> Optional[Path]:
    base = Path(mineru_output)
    if not base.exists():
        return None
    candidates = [
        base / f"{document_id}_batch" / "main" / "auto",
        base / f"{document_id}_batch" / "auto",
        base / document_id / "main" / "auto",
        base / document_id / "auto",
        base / "main" / "auto",
        base / "auto",
    ]
    for c in candidates:
        if c.exists() and list(c.glob("*content_list.json")):
            return c
    for d in base.iterdir():
        if d.is_dir() and document_id in d.name:
            for sub in [d / "main" / "auto", d / "auto"]:
                if sub.exists() and list(sub.glob("*content_list.json")):
                    return sub
    return None


def run_figure_text_association(
    document_id: str,
    mineru_output: str,
    output_dir: str,
    figure_parser_output_path: Optional[str] = None,
    table_parser_output_path: Optional[str] = None,
    **kwargs,
) -> dict:
    """Pipeline-callable figure-text association entry point.
    
    FIX-003: Now consumes figure_parser and table_parser outputs if provided.
    """
    mod = _load_module()

    auto_dir = _find_mineru_auto_dir(mineru_output, document_id)
    if auto_dir is None:
        return {
            "document_id": document_id,
            "figure_text_status": "FAILED",
            "error": f"MinerU output not found for '{document_id}'",
        }

    try:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Run original association logic
        associations = mod.process_document(document_id, auto_dir)

        # FIX-003: Read and merge parser outputs
        figure_parser_data = None
        table_parser_data = None
        data_sources = ["MinerU content_list", "Document IR"]
        
        if figure_parser_output_path and Path(figure_parser_output_path).exists():
            with open(figure_parser_output_path, "r", encoding="utf-8") as f:
                figure_parser_data = json.load(f)
            data_sources.append("FigureParser")
            logger.info(
                "[%s] Merged FigureParser output: %d figures",
                document_id,
                figure_parser_data.get("figures_processed", 0)
            )
        
        if table_parser_output_path and Path(table_parser_output_path).exists():
            with open(table_parser_output_path, "r", encoding="utf-8") as f:
                table_parser_data = json.load(f)
            data_sources.append("TableParser")
            logger.info(
                "[%s] Merged TableParser output: %d tables",
                document_id,
                table_parser_data.get("tables_processed", 0)
            )

        # Build enhanced output with parser data
        output_file = out_path / f"{document_id}_figure_associations.json"
        enhanced_output = {
            "document_id": document_id,
            "associations": associations,
            "association_count": len(associations),
            "data_sources": data_sources,
            "figure_parser_integrated": figure_parser_data is not None,
            "table_parser_integrated": table_parser_data is not None,
        }
        
        if figure_parser_data:
            enhanced_output["figure_parser_summary"] = {
                "figures_processed": figure_parser_data.get("figures_processed", 0),
                "figure_count": figure_parser_data.get("figure_count", 0),
                "extraction_source": figure_parser_data.get("extraction_source", "unknown"),
            }
        
        if table_parser_data:
            enhanced_output["table_parser_summary"] = {
                "tables_processed": table_parser_data.get("tables_processed", 0),
                "table_count": table_parser_data.get("table_count", 0),
                "extraction_source": table_parser_data.get("extraction_source", "unknown"),
            }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(enhanced_output, f, indent=2, ensure_ascii=False, default=str)

        return {
            "document_id": document_id,
            "figure_associations_path": str(output_file),
            "figure_text_status": "PASS",
            "association_count": len(associations),
            "data_sources": data_sources,
            "figure_parser_integrated": figure_parser_data is not None,
            "table_parser_integrated": table_parser_data is not None,
        }
    except Exception as e:
        logger.error("[%s] Figure-text association failed: %s", document_id, e)
        return {
            "document_id": document_id,
            "figure_text_status": "FAILED",
            "error": str(e),
        }


def create_figure_text_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for figure-text association.
    
    FIX-003: Now depends on figure_parser and table_parser stages.
    """
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("figure_text_association", {})

    adapter = StageAdapter(
        stage_name="figure_text_association",
        version="2.1.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=[
                "mineru_output_dir",
                "figure_parser_output_path",
                "table_parser_output_path",
            ],
        ),
        output_contract=DataContract(
            required_outputs=["figure_associations_path"],
            optional_outputs=[
                "data_sources",
                "figure_parser_integrated",
                "table_parser_integrated",
            ],
        ),
        dependencies=["document_ir", "figure_parser", "table_parser"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 60),
    )

    mineru_output = paths.get("mineru_output", "")
    output_dir = paths.get("pipeline_runs", "") + "/figure_text"
    
    # FIX-003: Construct parser output paths
    pipeline_runs = paths.get("pipeline_runs", "runs/pipeline_001")
    figure_parser_output_path = f"{pipeline_runs}/figure_parser/{{document_id}}_figure_parser.json"
    table_parser_output_path = f"{pipeline_runs}/table_parser/{{document_id}}_table_parser.json"

    adapter.set_function(
        run_figure_text_association,
        mineru_output=mineru_output,
        output_dir=output_dir,
        figure_parser_output_path=figure_parser_output_path,
        table_parser_output_path=table_parser_output_path,
    )
    return adapter
