#!/usr/bin/env python3
"""run_pipeline.py — CLI entry point for the Catalyst Knowledge Pipeline.

Usage:
    python scripts/run_pipeline.py --doc F02
    python scripts/run_pipeline.py --doc F02 --dry-run
    python scripts/run_pipeline.py --doc F02 --start pdf_parse --end document_ir
    python scripts/run_pipeline.py --doc F02 --resume runs/pipeline_001/run_xxx.json
    python scripts/run_pipeline.py --doc F02 --config config/pipeline.yaml
    python scripts/run_pipeline.py --doc F02 --rerun-stage six_dimension_extraction
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from catalyst_knowledge.pipeline.config_loader import ConfigLoader
from catalyst_knowledge.pipeline.orchestrator import PipelineOrchestrator
from catalyst_knowledge.pipeline.adapters import (
    create_pdf_parse_adapter,
    create_document_ir_adapter,
    create_figure_parser_adapter,
    create_table_parser_adapter,
    create_figure_text_adapter,
    create_extraction_adapter,
    create_science_extraction_v2_adapter,
    create_num_unit_adapter,
    create_quality_gate_adapter,
    create_store_adapter,
    create_report_adapter,
    create_vlm_figure_science_adapter,
    create_evidence_verifier_adapter,
    create_table_science_adapter,
)

logger = logging.getLogger("pipeline")


def build_pipeline(config: ConfigLoader) -> PipelineOrchestrator:
    """Register all pipeline stages with real adapters.

    All stages are registered unconditionally; the orchestrator reads each
    stage's `enabled` flag from config at execution time and marks disabled
    stages as SKIPPED. This ensures dependency validation passes even when
    optional stages (VLM, EV, table_science) are disabled.

    DAG structure:
        pdf_parse
            └── document_ir
                    ├── figure_parser ──┬── vlm_figure_science (optional)
                    │                   └── figure_text_association
                    ├── table_parser ─── table_science (optional)
                    ├── six_dimension_extraction (V1, deprecated) ─┐
                    ├── science_extraction_v2 (V2, preferred) ─────┤
                    │                                               └── num_unit_normalization
                    │                                                       │
                    └─────────────────────────────────────────── quality_gate
                                                                         │
                                                         evidence_verification (optional)
                                                                         │
                                                               canonical_store
                                                                         │
                                                              report_generation

        [optional] = registered but disabled by default; config controls activation
    """
    orch = PipelineOrchestrator(config)

    # --- Core ingestion chain ---
    orch.register_stage(create_pdf_parse_adapter(config.config))
    orch.register_stage(create_document_ir_adapter(config.config))

    # --- Figure chain ---
    orch.register_stage(create_figure_parser_adapter(config.config))
    orch.register_stage(create_vlm_figure_science_adapter(config.config))

    # --- Table chain ---
    orch.register_stage(create_table_parser_adapter(config.config))
    orch.register_stage(create_table_science_adapter(config.config))

    # --- Figure/Table text association ---
    orch.register_stage(create_figure_text_adapter(config.config))

    # --- Text extraction (V1 deprecated + V2 preferred) ---
    orch.register_stage(create_extraction_adapter(config.config))  # V1 (deprecated)
    orch.register_stage(create_science_extraction_v2_adapter(config.config))  # V2

    # --- Post-extraction chain ---
    orch.register_stage(create_num_unit_adapter(config.config))
    orch.register_stage(create_quality_gate_adapter(config.config))

    # --- Evidence verification ---
    orch.register_stage(create_evidence_verifier_adapter(config.config))

    # --- Store + Report ---
    orch.register_stage(create_store_adapter(config.config))
    orch.register_stage(create_report_adapter(config.config))

    # Log which stages are enabled for this run
    stages_cfg = config.config.get("stages", {})
    enabled = [n for n, c in stages_cfg.items() if c.get("enabled", False)]
    disabled = [n for n, c in stages_cfg.items() if not c.get("enabled", False)]
    logger.info("Enabled stages: %s", enabled)
    logger.info("Disabled stages (registered, will be SKIPPED): %s", disabled)

    return orch


def main():
    parser = argparse.ArgumentParser(
        description="Catalyst Knowledge Pipeline — unified execution entry point",
    )
    parser.add_argument(
        "--doc", "--document-id",
        required=True,
        dest="document_id",
        help="Document ID to process (e.g. F02, F07, P01, PAT01)",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "pipeline.yaml"),
        help="Path to pipeline config YAML",
    )
    parser.add_argument("--start", default=None, help="First stage to execute")
    parser.add_argument("--end", default=None, help="Last stage to execute")
    parser.add_argument("--dry-run", action="store_true", help="Validate DAG without executing")
    parser.add_argument("--resume", default=None, help="Path to previous run manifest to resume from")
    parser.add_argument("--rerun-stage", default=None, help="Re-execute a specific stage")
    parser.add_argument("--no-cascade", action="store_true", help="With --rerun-stage: don't cascade downstream")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        help="Override config values: key=value (repeatable)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = ConfigLoader(args.config)

    orch = build_pipeline(config)

    issues = orch.validate_dag()
    if issues:
        logger.error("DAG validation failed:")
        for issue in issues:
            logger.error("  - %s", issue)
        sys.exit(1)

    if args.dry_run:
        report = orch.dry_run(
            document_id=args.document_id,
            start_stage=args.start,
            end_stage=args.end,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    if args.rerun_stage:
        manifest = orch.rerun_stage(
            document_id=args.document_id,
            stage_name=args.rerun_stage,
            cascade_downstream=not args.no_cascade,
        )
    else:
        manifest = orch.run(
            document_id=args.document_id,
            start_stage=args.start,
            end_stage=args.end,
            resume_from=args.resume,
        )

    summary = manifest.get_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if manifest.status == "FAILED":
        logger.error("Pipeline FAILED: %s", manifest.error_message)
        sys.exit(1)
    else:
        logger.info("Pipeline completed: run_id=%s, status=%s", manifest.run_id, manifest.status)


if __name__ == "__main__":
    main()
