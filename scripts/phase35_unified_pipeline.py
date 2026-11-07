"""Phase 3.5 Unified Pipeline — Complete F02 processing with Recovery Engine.

Integrates:
- All existing adapters (PDF parse, Document IR, extraction, etc.)
- Recovery Engine (7 components)
- Quality gates and validation
- HTML report generation
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from catalyst_knowledge.recovery_engine import (
    QualityAssessment,
    FailureClassifier,
    RecoveryPlanner,
    TargetedExtractor,
    RecoveryMerger,
    RecoveryValidator,
    RecoveryAuditLogger,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Phase35Pipeline:
    """Phase 3.5 unified pipeline for F02 complete processing."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize pipeline with configuration."""
        self.config = self._load_config(config_path)
        self.run_dir = Path(self.config.get("run_dir", "runs/pipeline_001/phase3_5/f02"))
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Recovery Engine components
        self.quality_assessor = QualityAssessment()
        self.failure_classifier = FailureClassifier()
        self.recovery_planner = RecoveryPlanner()
        self.targeted_extractor = TargetedExtractor()
        self.recovery_merger = RecoveryMerger()
        self.recovery_validator = RecoveryValidator()
        self.audit_logger = RecoveryAuditLogger({"log_dir": str(self.run_dir / "recovery_logs")})

        # Pipeline state
        self.document_ir: Optional[dict] = None
        self.extraction_results: Optional[dict] = None
        self.recovery_session: Optional[Any] = None

    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load configuration from YAML or use defaults."""
        if config_path and Path(config_path).exists():
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

        return {
            "run_dir": "runs/pipeline_001/phase3_5/f02",
            "document_id": "F02",
            "use_recovery_engine": True,
            "generate_html_report": True,
            "llm_api_key_env": "LLM_API_KEY",
            "llm_api_base_env": "LLM_API_BASE",
            "llm_model_env": "LLM_MODEL",
        }

    def run_full_pipeline(self) -> dict:
        """Run complete pipeline with all stages.

        Returns:
            Pipeline execution results
        """
        logger.info("=" * 80)
        logger.info("Phase 3.5 Unified Pipeline - Starting")
        logger.info("=" * 80)

        results = {
            "pipeline_id": f"PIPELINE_35_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "document_id": self.config.get("document_id", "F02"),
            "started_at": datetime.now().isoformat(),
            "stages": [],
            "recovery_metrics": {},
            "quality_metrics": {},
            "status": "RUNNING",
        }

        try:
            # Stage 1: Load existing extraction results
            stage1_result = self._stage1_load_existing_results()
            results["stages"].append(stage1_result)

            # Stage 2: Quality Assessment
            stage2_result = self._stage2_quality_assessment()
            results["stages"].append(stage2_result)
            results["quality_metrics"]["input_quality_score"] = stage2_result.get("quality_score", 0)

            # Stage 3: Recovery Engine (if enabled)
            if self.config.get("use_recovery_engine", True):
                stage3_result = self._stage3_recovery_engine()
                results["stages"].append(stage3_result)
                results["recovery_metrics"] = stage3_result.get("metrics", {})

            # Stage 4: Final Validation
            stage4_result = self._stage4_final_validation()
            results["stages"].append(stage4_result)
            results["quality_metrics"]["output_quality_score"] = stage4_result.get("quality_score", 0)

            # Stage 5: Generate HTML Report
            if self.config.get("generate_html_report", True):
                stage5_result = self._stage5_generate_html_report()
                results["stages"].append(stage5_result)

            # Stage 6: Save Results
            stage6_result = self._stage6_save_results(results)
            results["stages"].append(stage6_result)

            results["status"] = "COMPLETED"
            results["completed_at"] = datetime.now().isoformat()

            logger.info("=" * 80)
            logger.info("Phase 3.5 Pipeline - COMPLETED")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            results["status"] = "FAILED"
            results["error"] = str(e)
            results["failed_at"] = datetime.now().isoformat()

        return results

    def _stage1_load_existing_results(self) -> dict:
        """Stage 1: Load existing F02 extraction results."""
        logger.info("Stage 1: Loading existing extraction results...")

        # Load Phase 3.4.5 final results
        phase345_path = Path("runs/pipeline_001/phase3_4_5/f02/PHASE345_SIX_DIMENSION_FINAL.json")

        if phase345_path.exists():
            with open(phase345_path, "r", encoding="utf-8") as f:
                self.extraction_results = json.load(f)
            logger.info(f"Loaded existing results from {phase345_path}")
            return {
                "stage": "load_existing_results",
                "status": "PASS",
                "source": str(phase345_path),
                "dimensions_loaded": len(self.extraction_results.get("dimensions", {})),
            }
        else:
            logger.warning(f"Existing results not found at {phase345_path}")
            # Create minimal structure
            self.extraction_results = {
                "document_id": "F02",
                "dimensions": {},
            }
            return {
                "stage": "load_existing_results",
                "status": "WARNING",
                "message": "Using empty structure",
            }

    def _stage2_quality_assessment(self) -> dict:
        """Stage 2: Run quality assessment."""
        logger.info("Stage 2: Running quality assessment...")

        # Load document text for cross-reference
        document_text = self._load_document_text()

        # Run quality assessment
        quality_report = self.quality_assessor.assess(
            extraction_results=self.extraction_results,
            document_text=document_text,
        )

        logger.info(f"Quality score: {quality_report.overall_score:.2f}")
        logger.info(f"Reported fields: {quality_report.reported_fields}/{quality_report.total_fields}")

        return {
            "stage": "quality_assessment",
            "status": "PASS" if quality_report.overall_score >= 0.7 else "WARNING",
            "quality_score": quality_report.overall_score,
            "total_fields": quality_report.total_fields,
            "reported_fields": quality_report.reported_fields,
            "pass_rate": quality_report.pass_rate,
            "critical_failures": len(quality_report.critical_failures),
            "high_failures": len(quality_report.high_failures),
        }

    def _stage3_recovery_engine(self) -> dict:
        """Stage 3: Run Recovery Engine."""
        logger.info("Stage 3: Running Recovery Engine...")

        # Create recovery session
        self.recovery_session = self.audit_logger.create_session(
            document_id=self.extraction_results.get("document_id", "F02")
        )

        # Load document text
        document_text = self._load_document_text()

        # Step 1: Quality Assessment
        quality_report = self.quality_assessor.assess(
            extraction_results=self.extraction_results,
            document_text=document_text,
        )
        self.audit_logger.log_quality_assessment(self.recovery_session, quality_report)

        # Step 2: Failure Classification
        classified_failures = self.failure_classifier.classify(quality_report)
        self.audit_logger.log_failure_classification(self.recovery_session, classified_failures)

        logger.info(f"Classified {classified_failures.total_failures} failures")
        logger.info(f"  Recoverable: {classified_failures.recoverable_count}")
        logger.info(f"  Manual review: {classified_failures.manual_review_count}")

        # Step 3: Recovery Planning
        recovery_plan = self.recovery_planner.plan(
            classified_failures=classified_failures,
            document_text=document_text,
        )
        self.audit_logger.log_recovery_plan(self.recovery_session, recovery_plan)

        logger.info(f"Planned {len(recovery_plan.actions)} recovery actions")
        logger.info(f"  Estimated tokens: {recovery_plan.total_estimated_tokens}")
        logger.info(f"  Estimated cost: ${recovery_plan.total_estimated_cost_usd:.4f}")

        # Step 4: Targeted Extraction (skip if no LLM client)
        extracted_fields = []
        if self._has_llm_client():
            for action in recovery_plan.actions[:5]:  # Limit to 5 actions for demo
                extracted = self.targeted_extractor.extract(
                    action=action,
                    document_text=document_text,
                )
                extracted_fields.append(extracted)
            self.audit_logger.log_extraction(self.recovery_session, extracted_fields)
            logger.info(f"Extracted {len(extracted_fields)} fields")
        else:
            logger.warning("No LLM client available, skipping targeted extraction")

        # Step 5: Merge Results
        merged_results = self.recovery_merger.merge(
            original=self.extraction_results,
            recovered=extracted_fields,
            phase_tag="phase3_5",
        )
        self.audit_logger.log_merge(self.recovery_session, merged_results)

        logger.info(f"Merged results:")
        logger.info(f"  Replaced: {merged_results.fields_replaced}")
        logger.info(f"  Preserved: {merged_results.fields_preserved}")
        logger.info(f"  Flagged: {merged_results.fields_flagged}")

        # Step 6: Validation
        validation_report = self.recovery_validator.validate(merged_results)
        self.audit_logger.log_validation(self.recovery_session, validation_report)

        logger.info(f"Validation status: {validation_report.overall_status.value}")

        # Finalize session
        self.audit_logger.finalize_session(self.recovery_session)

        # Update extraction results
        self.extraction_results["dimensions"] = merged_results.merged_dimensions

        return {
            "stage": "recovery_engine",
            "status": "PASS" if validation_report.overall_status.value == "PASS" else "WARNING",
            "metrics": {
                "total_failures": classified_failures.total_failures,
                "recoverable": classified_failures.recoverable_count,
                "actions_planned": len(recovery_plan.actions),
                "fields_extracted": len(extracted_fields),
                "fields_replaced": merged_results.fields_replaced,
                "fields_preserved": merged_results.fields_preserved,
                "validation_status": validation_report.overall_status.value,
                "estimated_cost_usd": recovery_plan.total_estimated_cost_usd,
            },
        }

    def _stage4_final_validation(self) -> dict:
        """Stage 4: Final validation."""
        logger.info("Stage 4: Running final validation...")

        # Count final statistics
        dimensions = self.extraction_results.get("dimensions", {})
        total_fields = 0
        reported_fields = 0

        for dim_data in dimensions.values():
            for field_data in dim_data.get("fields", {}).values():
                total_fields += 1
                if field_data.get("status") == "REPORTED":
                    reported_fields += 1

        quality_score = reported_fields / max(total_fields, 1)

        logger.info(f"Final quality score: {quality_score:.2f}")
        logger.info(f"Reported fields: {reported_fields}/{total_fields}")

        return {
            "stage": "final_validation",
            "status": "PASS" if quality_score >= 0.7 else "WARNING",
            "quality_score": quality_score,
            "total_fields": total_fields,
            "reported_fields": reported_fields,
        }

    def _stage5_generate_html_report(self) -> dict:
        """Stage 5: Generate HTML report."""
        logger.info("Stage 5: Generating HTML report...")

        # Generate HTML report
        html_content = self._build_html_report()

        # Save HTML
        html_path = self.run_dir / "F02_COMPLETE_SCIENTIFIC_AUDIT.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"HTML report saved: {html_path}")

        return {
            "stage": "generate_html_report",
            "status": "PASS",
            "output_path": str(html_path),
        }

    def _stage6_save_results(self, results: dict) -> dict:
        """Stage 6: Save pipeline results."""
        logger.info("Stage 6: Saving pipeline results...")

        # Save results JSON
        results_path = self.run_dir / "PHASE35_PIPELINE_RESULTS.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved: {results_path}")

        # Save updated extraction results
        extraction_path = self.run_dir / "F02_SIX_DIMENSION_PHASE35.json"
        with open(extraction_path, "w", encoding="utf-8") as f:
            json.dump(self.extraction_results, f, indent=2, ensure_ascii=False)

        logger.info(f"Extraction results saved: {extraction_path}")

        return {
            "stage": "save_results",
            "status": "PASS",
            "output_files": [
                str(results_path),
                str(extraction_path),
            ],
        }

    def _load_document_text(self) -> str:
        """Load F02 document text."""
        doc_path = Path("runs/pipeline_001/phase3/f02_e2e/02_pdf_parse/main/auto/main.md")
        if doc_path.exists():
            with open(doc_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def _has_llm_client(self) -> bool:
        """Check if LLM client is available."""
        api_key = os.environ.get(self.config.get("llm_api_key_env", "LLM_API_KEY"))
        return api_key is not None and len(api_key) > 0

    def _build_html_report(self) -> str:
        """Build comprehensive HTML report."""
        dimensions = self.extraction_results.get("dimensions", {})

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>F02 Complete Scientific Audit - Phase 3.5</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 10px; }}
        h3 {{ color: #7f8c8d; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 5px; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; padding: 10px 15px; background: #3498db; color: white; border-radius: 5px; }}
        .metric.pass {{ background: #27ae60; }}
        .metric.warning {{ background: #f39c12; }}
        .metric.fail {{ background: #e74c3c; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background: #3498db; color: white; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
        .status-pass {{ color: #27ae60; font-weight: bold; }}
        .status-fail {{ color: #e74c3c; font-weight: bold; }}
        .status-warning {{ color: #f39c12; font-weight: bold; }}
        .field-card {{ border: 1px solid #ddd; padding: 10px; margin: 10px 0; border-radius: 5px; }}
        .field-name {{ font-weight: bold; color: #2c3e50; }}
        .field-value {{ margin: 5px 0; }}
        .field-status {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.9em; }}
        .field-status.reported {{ background: #27ae60; color: white; }}
        .field-status.not-reported {{ background: #95a5a6; color: white; }}
        .field-status.unresolved {{ background: #f39c12; color: white; }}
    </style>
</head>
<body>
    <h1>F02 Complete Scientific Audit Report</h1>
    <p><strong>Document ID:</strong> F02 (DOI: 10.3389/fchem.2024.1439185)</p>
    <p><strong>Pipeline Version:</strong> Phase 3.5</p>
    <p><strong>Generated:</strong> {datetime.now().isoformat()}</p>

    <div class="section">
        <h2>1. 文献基本信息</h2>
        <p><strong>Title:</strong> Photothermal oxidative dehydrogenation of propane to propylene over Cu/BN catalysts</p>
        <p><strong>Authors:</strong> Wang et al.</p>
        <p><strong>Journal:</strong> Frontiers in Chemistry, 2024</p>
        <p><strong>DOI:</strong> 10.3389/fchem.2024.1439185</p>
    </div>

    <div class="section">
        <h2>2. 六维科学知识概览</h2>
        <div class="metric pass">Dimensions: {len(dimensions)}</div>
        <div class="metric pass">Total Fields: {sum(len(d.get('fields', {})) for d in dimensions.values())}</div>
        <div class="metric pass">Reported: {sum(1 for d in dimensions.values() for f in d.get('fields', {}).values() if f.get('status') == 'REPORTED')}</div>
    </div>

    <div class="section">
        <h2>3. 催化剂设计与合成 (Catalyst Design)</h2>
        {self._render_dimension(dimensions.get('catalyst_design', {}))}
    </div>

    <div class="section">
        <h2>4. 催化剂表征 (Characterization)</h2>
        {self._render_dimension(dimensions.get('characterization', {}))}
    </div>

    <div class="section">
        <h2>5. 催化性能与反应条件 (Performance)</h2>
        {self._render_dimension(dimensions.get('performance', {}))}
    </div>

    <div class="section">
        <h2>6. 反应机理 (Mechanism)</h2>
        {self._render_dimension(dimensions.get('mechanism', {}))}
    </div>

    <div class="section">
        <h2>7. 构效关系 (Structure-Activity)</h2>
        {self._render_dimension(dimensions.get('structure_activity', {}))}
    </div>

    <div class="section">
        <h2>8. 稳定性与可靠性 (Reliability)</h2>
        {self._render_dimension(dimensions.get('reliability', {}))}
    </div>

    <div class="section">
        <h2>9. 质量检查结果</h2>
        <p>Phase 3.5 pipeline completed with Recovery Engine integration.</p>
        <p>See detailed metrics in PHASE35_PIPELINE_RESULTS.json</p>
    </div>

</body>
</html>
"""
        return html

    def _render_dimension(self, dim_data: dict) -> str:
        """Render a single dimension as HTML."""
        fields = dim_data.get("fields", {})
        if not fields:
            return "<p>No data available</p>"

        html = "<table><tr><th>Field</th><th>Value</th><th>Status</th><th>Origin</th></tr>"
        for field_name, field_data in fields.items():
            status = field_data.get("status", "UNKNOWN")
            status_class = "reported" if status == "REPORTED" else "not-reported" if status == "NOT_REPORTED" else "unresolved"
            value = field_data.get("value", "N/A")
            origin = field_data.get("origin", "UNKNOWN")

            # Truncate long values
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:100] + "..."

            html += f"<tr><td>{field_name}</td><td>{value_str}</td><td class='field-status {status_class}'>{status}</td><td>{origin}</td></tr>"
        html += "</table>"
        return html


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 3.5 Unified Pipeline")
    parser.add_argument("--config", type=str, help="Configuration file path")
    parser.add_argument("--no-recovery", action="store_true", help="Disable Recovery Engine")
    parser.add_argument("--no-html", action="store_true", help="Disable HTML report generation")

    args = parser.parse_args()

    # Build config
    config = {}
    if args.config:
        config["config_path"] = args.config
    if args.no_recovery:
        config["use_recovery_engine"] = False
    if args.no_html:
        config["generate_html_report"] = False

    # Run pipeline
    pipeline = Phase35Pipeline(config_path=args.config)
    results = pipeline.run_full_pipeline()

    # Print summary
    print("\n" + "=" * 80)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 80)
    print(f"Status: {results['status']}")
    print(f"Document: {results['document_id']}")
    print(f"Stages completed: {len(results['stages'])}")

    if results.get("recovery_metrics"):
        print("\nRecovery Metrics:")
        for key, value in results["recovery_metrics"].items():
            print(f"  {key}: {value}")

    if results.get("quality_metrics"):
        print("\nQuality Metrics:")
        for key, value in results["quality_metrics"].items():
            print(f"  {key}: {value:.2f}" if isinstance(value, float) else f"  {key}: {value}")

    print("=" * 80)

    return 0 if results["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
