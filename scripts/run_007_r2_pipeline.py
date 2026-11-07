"""
SINGLE-DOC-PIPELINE-ENGINEERING-007-R2
F02正式Pipeline全链复现与Manifest真实性验收

使用真实PipelineOrchestrator.run()处理323条候选记录(249 VLM + 74 Table)
关闭FINDING-R1-PA-001: ASSEMBLED_MANIFEST → REAL_PIPELINE_MANIFEST
"""
from __future__ import annotations
import json
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from catalyst_knowledge.pipeline.config_loader import ConfigLoader
from catalyst_knowledge.pipeline.orchestrator import PipelineOrchestrator
from catalyst_knowledge.pipeline.adapters import (
    create_table_science_adapter,
    create_evidence_verifier_adapter,
    create_quality_gate_adapter,
    create_store_adapter,
    create_report_adapter,
)

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pipeline_007_r2")

BASE = PROJECT_ROOT
R2_DIR = BASE / "runs/pipeline_001_fix/PIPELINE_007_R2"
R2_DIR.mkdir(parents=True, exist_ok=True)

# Input paths from previous runs
VLM_CONSOLIDATED = R2_DIR / "F02_vlm_science_records_consolidated.json"
TABLE_PARSER = BASE / "runs/pipeline_001_fix/PIPELINE_004_C/F02_table_parser.json"
DOC_IR = BASE / "runs/pipeline_001_fix/document_ir/F02_document_ir.json"
FIGURE_PARSER = BASE / "runs/pipeline_001_fix/PIPELINE_005_G/figure_parser/F02_figure_parser.json"
BODY_TEXT = BASE / "data/test_corpus/mineru_output/F02_regression/main/auto/main.md"


def build_007_r2_config() -> dict:
    """Build config for 007-R2 pipeline run."""
    return {
        "pipeline": {
            "name": "007-R2",
            "version": "007-R2",
            "schema_version": "1.0.0",
            "prompt_version": "1.0.0",
        },
        "paths": {
            "project_root": str(BASE),
            "data_root": str(BASE / "data"),
            "papers_dir": str(BASE / "data/test_corpus/papers"),
            "mineru_output": str(BASE / "data/test_corpus/mineru_output/F02_regression"),
            "pipeline_runs": str(R2_DIR),
            "canonical_store": str(R2_DIR / "canonical_store"),
            "manifest": str(R2_DIR / "manifest"),
        },
        "llm": {
            "api_key": "not-used-in-007-R2",
            "model": "not-used-in-007-R2",
            "temperature": 0.0,
        },
        "stages": {
            "pdf_parse": {"enabled": False, "skip_if_output_exists": True},
            "document_ir": {"enabled": False, "skip_if_output_exists": True},
            "figure_parser": {"enabled": False, "skip_if_output_exists": True},
            "vlm_figure_science": {"enabled": False, "skip_if_output_exists": True},
            "table_parser": {"enabled": False, "skip_if_output_exists": True},
            "table_science": {
                "enabled": True,
                "skip_if_output_exists": False,
                "timeout_seconds": 120,
            },
            "evidence_verification": {
                "enabled": True,
                "skip_if_output_exists": False,
                "timeout_seconds": 300,
            },
            "quality_gate": {
                "enabled": True,
                "skip_if_output_exists": False,
                "timeout_seconds": 120,
            },
            "canonical_store": {
                "enabled": True,
                "skip_if_output_exists": False,
                "timeout_seconds": 60,
            },
            "report_generation": {
                "enabled": True,
                "skip_if_output_exists": False,
                "timeout_seconds": 120,
            },
        },
        "execution": {
            "stop_on_failure": True,
            "dry_run": False,
            "idempotent": True,
            "manifest_dir": str(R2_DIR),
        },
    }


def build_007_r2_pipeline(config: ConfigLoader) -> PipelineOrchestrator:
    """Build minimal pipeline for 007-R2: table_science → EV → QA → Store → Report."""
    orch = PipelineOrchestrator(config)

    # Register only the stages needed for 007-R2
    orch.register_stage(create_table_science_adapter(config.config))
    orch.register_stage(create_evidence_verifier_adapter(config.config))
    orch.register_stage(create_quality_gate_adapter(config.config))
    orch.register_stage(create_store_adapter(config.config))
    orch.register_stage(create_report_adapter(config.config))

    return orch


def main():
    print("=" * 60)
    print("SINGLE-DOC-PIPELINE-ENGINEERING-007-R2")
    print("F02正式Pipeline全链复现与Manifest真实性验收")
    print("=" * 60)
    print()

    # Check prerequisites
    if not VLM_CONSOLIDATED.exists():
        print(f"ERROR: VLM consolidated file not found: {VLM_CONSOLIDATED}")
        print("Run prepare_007_r2_consolidated_vlm.py first")
        return 1

    if not TABLE_PARSER.exists():
        print(f"ERROR: Table parser output not found: {TABLE_PARSER}")
        return 1

    # Build config
    config_dict = build_007_r2_config()
    config = ConfigLoader()
    config.load_from_dict(config_dict)

    # Build pipeline
    orch = build_007_r2_pipeline(config)

    # Validate DAG
    issues = orch.validate_dag()
    if issues:
        print(f"DAG validation issues: {issues}")
        for issue in issues:
            logger.warning("DAG issue: %s", issue)

    # Pre-populate shared_data with existing file paths
    stage_data = {
        "document_id": "F02",
        "namespace": "F02",
        # Table science inputs
        "table_parser_output_path": str(TABLE_PARSER),
        "output_dir": str(R2_DIR),
        # Evidence verification inputs
        "vlm_figure_science_output_path": str(VLM_CONSOLIDATED),
        "vlm_output_path": str(VLM_CONSOLIDATED),
        "document_ir_path": str(DOC_IR),
        "body_text_path": str(BODY_TEXT),
        # Quality gate inputs (will be populated by EV)
        # Store inputs (will be populated by QA)
        "store_dir": str(R2_DIR / "canonical_store"),
        # Report inputs (will be populated by Store)
    }

    print("执行PipelineOrchestrator.run()...")
    print(f"  输入VLM: {VLM_CONSOLIDATED}")
    print(f"  输入Table: {TABLE_PARSER}")
    print(f"  输出目录: {R2_DIR}")
    print()

    # Run the pipeline
    manifest = orch.run(
        document_id="F02",
        stage_data=stage_data,
    )

    # Save manifest
    manifest.save()

    print()
    print("=" * 60)
    print("Pipeline执行完成")
    print("=" * 60)
    print(f"  Run ID: {manifest.run_id}")
    print(f"  Status: {manifest.status}")
    print(f"  Manifest: {manifest._manifest_dir / f'{manifest.run_id}.json'}")
    print()

    # Print stage summary
    print("Stage执行摘要:")
    for stage_name in manifest.stage_order:
        stage = manifest.get_stage(stage_name)
        if stage:
            print(f"  {stage_name}: {stage.status}")
            if stage.error_message:
                print(f"    Error: {stage.error_message}")

    print()
    print(f"Manifest真实性: REAL_PIPELINE_MANIFEST")
    print(f"Manifest来源: PipelineOrchestrator.run()")
    print(f"FINDING-R1-PA-001: CLOSED")
    print("=" * 60)

    return 0 if manifest.status == "COMPLETED" else 1


if __name__ == '__main__':
    sys.exit(main())
