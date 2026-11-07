#!/usr/bin/env python3
"""Unified Pipeline Entry Point.

Single entry point for running either:
1. Standard 8-stage DAG pipeline (pdf_parse → document_ir → ... → report)
2. Recovery 6-stage pipeline (load_existing → quality_assessment → recovery_engine → ...)

Usage:
    # Standard pipeline (default)
    python scripts/run_unified_pipeline.py --doc F02

    # Recovery pipeline
    python scripts/run_unified_pipeline.py --doc F02 --mode recovery

    # Partial execution
    python scripts/run_unified_pipeline.py --doc F02 --start document_ir --end quality_gate

    # Dry run (validate without executing)
    python scripts/run_unified_pipeline.py --doc F02 --dry-run

    # Resume from previous run
    python scripts/run_unified_pipeline.py --doc F02 --resume runs/pipeline_001/manifest_*.json

    # Rerun specific stage
    python scripts/run_unified_pipeline.py --doc F02 --rerun-stage six_dimension_extraction

Environment Variables:
    LLM_API_KEY: API key for LLM service
    LLM_API_BASE: API base URL (optional, defaults to DeepSeek)
    LLM_MODEL: Model name (optional, defaults to deepseek-chat)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from catalyst_knowledge.pipeline.config_loader import ConfigLoader
from catalyst_knowledge.pipeline.orchestrator import PipelineOrchestrator
from catalyst_knowledge.pipeline.unified_input import LiteratureInputResolver, save_literature_input_metadata

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for pipeline execution."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_standard_pipeline(config: ConfigLoader) -> PipelineOrchestrator:
    """Build the standard 8-stage DAG pipeline."""
    from catalyst_knowledge.pipeline.adapters.pdf_parse_adapter import create_pdf_parse_adapter
    from catalyst_knowledge.pipeline.adapters.document_ir_adapter import create_document_ir_adapter
    from catalyst_knowledge.pipeline.adapters.figure_parser_adapter import create_figure_parser_adapter
    from catalyst_knowledge.pipeline.adapters.table_parser_adapter import create_table_parser_adapter
    from catalyst_knowledge.pipeline.adapters.figure_text_adapter import create_figure_text_adapter
    from catalyst_knowledge.pipeline.adapters.extraction_adapter import create_extraction_adapter
    from catalyst_knowledge.pipeline.adapters.num_unit_adapter import create_num_unit_adapter
    from catalyst_knowledge.pipeline.adapters.quality_gate_adapter import create_quality_gate_adapter
    from catalyst_knowledge.pipeline.adapters.store_adapter import create_store_adapter
    from catalyst_knowledge.pipeline.adapters.report_adapter import create_report_adapter

    orchestrator = PipelineOrchestrator(config)

    orchestrator.register_stage(create_pdf_parse_adapter(config.config), dependencies=[])
    orchestrator.register_stage(create_document_ir_adapter(config.config), dependencies=["pdf_parse"])
    orchestrator.register_stage(create_figure_parser_adapter(config.config), dependencies=["document_ir"])
    orchestrator.register_stage(create_table_parser_adapter(config.config), dependencies=["document_ir"])
    orchestrator.register_stage(create_figure_text_adapter(config.config), dependencies=["document_ir", "figure_parser", "table_parser"])
    orchestrator.register_stage(create_extraction_adapter(config.config), dependencies=["document_ir"])
    orchestrator.register_stage(create_num_unit_adapter(config.config), dependencies=["six_dimension_extraction"])
    orchestrator.register_stage(create_quality_gate_adapter(config.config), dependencies=["six_dimension_extraction", "num_unit_normalization"])
    orchestrator.register_stage(create_store_adapter(config.config), dependencies=["quality_gate"])
    orchestrator.register_stage(create_report_adapter(config.config), dependencies=["canonical_store"])

    return orchestrator


def build_recovery_pipeline(config: ConfigLoader) -> Any:
    """Build the recovery 6-stage pipeline."""
    from scripts.phase35_unified_pipeline import Phase35Pipeline
    
    config_path = config.config.get("paths", {}).get("recovery_config")
    pipeline = Phase35Pipeline(config_path)
    return pipeline


def resolve_document_input(
    document_id: str,
    config: ConfigLoader,
    input_file: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve document input and prepare stage data.
    
    Args:
        document_id: Document identifier
        config: Pipeline configuration
        input_file: Optional explicit input file path
        
    Returns:
        Stage data dict with document metadata
    """
    paths = config.config.get("paths", {})
    
    if input_file:
        input_path = Path(input_file)
    else:
        manifest_path = Path(paths.get("manifest", ""))
        if manifest_path.exists():
            import json
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            for doc in manifest.get("documents", []):
                if doc["document_id"] == document_id:
                    input_path = Path(doc["file_path"])
                    break
            else:
                raise ValueError(f"Document '{document_id}' not found in manifest")
        else:
            papers_dir = Path(paths.get("papers_dir", ""))
            candidates = list(papers_dir.glob(f"*{document_id}*"))
            if not candidates:
                raise ValueError(f"No input file found for document '{document_id}'")
            input_path = candidates[0]
    
    resolver = LiteratureInputResolver(
        output_base=Path(paths.get("pipeline_runs", "runs/pipeline_001"))
    )
    
    literature_input = resolver.resolve(input_path, document_id=document_id)
    
    output_dir = Path(paths.get("pipeline_runs", "runs/pipeline_001")) / "identity"
    save_literature_input_metadata(literature_input, output_dir)
    
    return {
        "document_id": document_id,
        "input_file": str(literature_input.content_path),
        "input_metadata": literature_input.to_dict(),
        "mineru_output_dir": paths.get("mineru_output", ""),
    }


def run_pipeline(
    document_id: str,
    config_path: str,
    mode: str = "standard",
    start_stage: Optional[str] = None,
    end_stage: Optional[str] = None,
    dry_run: bool = False,
    resume_from: Optional[str] = None,
    rerun_stage: Optional[str] = None,
    no_cascade: bool = False,
    input_file: Optional[str] = None,
    overrides: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run the unified pipeline.
    
    Args:
        document_id: Document to process
        config_path: Path to pipeline config YAML
        mode: Pipeline mode ("standard" or "recovery")
        start_stage: First stage to execute
        end_stage: Last stage to execute
        dry_run: Validate without executing
        resume_from: Path to previous manifest to resume from
        rerun_stage: Specific stage to re-run
        no_cascade: Don't cascade downstream when re-running
        input_file: Explicit input file path
        overrides: Config overrides (key=value pairs)
        
    Returns:
        Execution results dict
    """
    config = ConfigLoader(config_path)
    if overrides:
        for override in overrides:
            if "=" in override:
                key, value = override.split("=", 1)
                config.set(key, value)
    
    if mode == "recovery":
        logger.info("Running recovery pipeline for document: %s", document_id)
        pipeline = build_recovery_pipeline(config)
        results = pipeline.run_full_pipeline()
        return results
    
    logger.info("Running standard pipeline for document: %s", document_id)
    orchestrator = build_standard_pipeline(config)
    
    issues = orchestrator.validate_dag()
    if issues:
        logger.error("DAG validation failed: %s", issues)
        return {"status": "FAILED", "error": f"DAG validation failed: {issues}"}
    
    try:
        stage_data = resolve_document_input(document_id, config, input_file)
    except Exception as e:
        logger.error("Failed to resolve document input: %s", e)
        return {"status": "FAILED", "error": str(e)}
    
    if dry_run:
        report = orchestrator.dry_run(document_id, start_stage, end_stage)
        return report
    
    if rerun_stage:
        manifest = orchestrator.rerun_stage(
            document_id,
            rerun_stage,
            stage_data,
            cascade_downstream=not no_cascade,
        )
        return manifest.get_summary()
    
    manifest = orchestrator.run(
        document_id,
        stage_data,
        start_stage,
        end_stage,
        resume_from,
    )
    
    return manifest.get_summary()


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Unified Pipeline Entry Point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "--doc", "--document-id",
        dest="document_id",
        required=True,
        help="Document identifier (e.g., F02, F07, P01)",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "pipeline.yaml"),
        help="Path to pipeline config YAML",
    )
    parser.add_argument(
        "--mode",
        choices=["standard", "recovery"],
        default="standard",
        help="Pipeline mode (default: standard)",
    )
    parser.add_argument(
        "--start",
        dest="start_stage",
        help="First stage to execute",
    )
    parser.add_argument(
        "--end",
        dest="end_stage",
        help="Last stage to execute",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without executing",
    )
    parser.add_argument(
        "--resume",
        dest="resume_from",
        help="Path to previous manifest to resume from",
    )
    parser.add_argument(
        "--rerun-stage",
        dest="rerun_stage",
        help="Specific stage to re-run",
    )
    parser.add_argument(
        "--no-cascade",
        action="store_true",
        help="Don't cascade downstream when re-running",
    )
    parser.add_argument(
        "--input",
        dest="input_file",
        help="Explicit input file path",
    )
    parser.add_argument(
        "--override",
        action="append",
        help="Config overrides (key=value)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    try:
        results = run_pipeline(
            document_id=args.document_id,
            config_path=args.config,
            mode=args.mode,
            start_stage=args.start_stage,
            end_stage=args.end_stage,
            dry_run=args.dry_run,
            resume_from=args.resume_from,
            rerun_stage=args.rerun_stage,
            no_cascade=args.no_cascade,
            input_file=args.input_file,
            overrides=args.override,
        )
        
        status = results.get("status", results.get("pipeline_status", "UNKNOWN"))
        logger.info("Pipeline completed with status: %s", status)
        
        print("\n" + "=" * 60)
        print("PIPELINE EXECUTION SUMMARY")
        print("=" * 60)
        for key, value in results.items():
            if isinstance(value, (str, int, float, bool)):
                print(f"  {key}: {value}")
            elif isinstance(value, list) and len(value) < 10:
                print(f"  {key}: {value}")
        print("=" * 60)
        
        return 0 if status in ("COMPLETED", "SUCCESS") else 1
        
    except Exception as e:
        logger.error("Pipeline execution failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
