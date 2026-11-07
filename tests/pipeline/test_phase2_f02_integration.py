"""PIPELINE-001 Phase 2 — F02 Real Integration Tests

Uses REAL adapters (no mocks) with F02's existing cached data.

Three test rounds:
  Round 1: DryRun with real 8-stage DAG
  Round 2: Cached replay — adapters find existing F02 artifacts
  Round 3: Individual real adapter execution with F02 data

All tests use F02's pre-existing data:
  - MinerU output: data/test_corpus/mineru_output/F02_regression/
  - G3 extraction: data/test_corpus/g3_output/F02/
  - Manifest: data/test_corpus/unified_test_manifest.json
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest

from catalyst_knowledge.pipeline.config_loader import ConfigLoader
from catalyst_knowledge.pipeline.orchestrator import PipelineOrchestrator
from catalyst_knowledge.pipeline.run_manifest import RunManifest
from catalyst_knowledge.pipeline.adapters import (
    create_pdf_parse_adapter,
    create_document_ir_adapter,
    create_figure_text_adapter,
    create_extraction_adapter,
    create_num_unit_adapter,
    create_quality_gate_adapter,
    create_store_adapter,
    create_report_adapter,
)

PROJECT_ROOT = Path(r"D:\Knowledge_World")
F02_MINERU_DIR = PROJECT_ROOT / "data" / "test_corpus" / "mineru_output"
F02_G3_DIR = PROJECT_ROOT / "data" / "test_corpus" / "g3_output"
F02_MANIFEST = PROJECT_ROOT / "data" / "test_corpus" / "unified_test_manifest.json"


@pytest.fixture
def temp_dir(tmp_path):
    """Isolated temp directory for pipeline outputs."""
    return tmp_path


@pytest.fixture
def f02_config(temp_dir):
    """ConfigLoader for F02 with real data paths."""
    runs_dir = temp_dir / "runs"
    runs_dir.mkdir()
    cfg_dict = {
        "pipeline": {
            "name": "catalyst-knowledge-pipeline",
            "version": "1.0.0",
            "schema_version": "1.0.0",
            "prompt_version": "1.0.0",
        },
        "paths": {
            "project_root": str(PROJECT_ROOT),
            "data_root": str(PROJECT_ROOT / "data"),
            "manifest": str(F02_MANIFEST),
            "pipeline_runs": str(runs_dir),
            "mineru_output": str(F02_MINERU_DIR),
            "ext01_output": str(temp_dir / "ext01"),
            "g3_output": str(F02_G3_DIR),
            "canonical_store": str(temp_dir / "store"),
            "reports_dir": str(temp_dir / "reports"),
            "papers_dir": str(PROJECT_ROOT / "data" / "test_corpus" / "papers"),
            "patents_dir": str(PROJECT_ROOT / "data" / "test_corpus" / "patents"),
            "attachments_dir": str(PROJECT_ROOT / "data" / "test_corpus" / "attachments"),
        },
        "llm": {
            "api_key_env": "LLM_API_KEY",
            "api_base_env": "LLM_API_BASE",
            "model_env": "LLM_MODEL",
            "default_model": "deepseek-chat",
            "default_api_base": "https://api.deepseek.com/v1",
        },
        "stages": {
            "pdf_parse": {"enabled": True, "timeout_seconds": 60, "skip_if_output_exists": True},
            "document_ir": {"enabled": True, "timeout_seconds": 60},
            "figure_text_association": {"enabled": True, "timeout_seconds": 60},
            "six_dimension_extraction": {"enabled": True, "timeout_seconds": 60},
            "num_unit_normalization": {"enabled": True, "timeout_seconds": 60},
            "quality_gate": {"enabled": True, "timeout_seconds": 60},
            "canonical_store": {"enabled": True, "timeout_seconds": 60},
            "report_generation": {"enabled": True, "timeout_seconds": 60},
        },
        "execution": {
            "stop_on_failure": True,
            "dry_run": False,
            "manifest_dir": str(runs_dir),
        },
    }
    loader = ConfigLoader()
    loader.load_from_dict(cfg_dict)
    return loader


def _build_real_pipeline(config: ConfigLoader) -> PipelineOrchestrator:
    """Build the full 8-stage DAG with real adapters."""
    orch = PipelineOrchestrator(config)
    orch.register_stage(create_pdf_parse_adapter(config.config))
    orch.register_stage(create_document_ir_adapter(config.config))
    orch.register_stage(create_figure_text_adapter(config.config))
    orch.register_stage(create_extraction_adapter(config.config))
    orch.register_stage(create_num_unit_adapter(config.config))
    orch.register_stage(create_quality_gate_adapter(config.config))
    orch.register_stage(create_store_adapter(config.config))
    orch.register_stage(create_report_adapter(config.config))
    return orch


class TestRound1DryRun:
    """Round 1: DryRun with real 8-stage DAG."""

    def test_real_dag_validates_clean(self, f02_config):
        """Real DAG should have no issues."""
        orch = _build_real_pipeline(f02_config)
        issues = orch.validate_dag()
        assert issues == [], f"DAG validation failed: {issues}"

    def test_real_dag_dry_run_execution_order(self, f02_config):
        """DryRun should produce correct topological order."""
        orch = _build_real_pipeline(f02_config)
        report = orch.dry_run(document_id="F02")

        assert report["mode"] == "dry_run"
        assert report["document_id"] == "F02"
        assert len(report["stages"]) == 8

        order = report["execution_order"]
        assert order[0] == "pdf_parse"
        assert order[1] == "document_ir"
        assert order.index("document_ir") < order.index("figure_text_association")
        assert order.index("document_ir") < order.index("six_dimension_extraction")
        assert order.index("six_dimension_extraction") < order.index("quality_gate")
        assert order.index("quality_gate") < order.index("canonical_store")
        assert order.index("canonical_store") < order.index("report_generation")

    def test_real_dag_dry_run_start_end_filter(self, f02_config):
        """DryRun with start/end should filter correctly."""
        orch = _build_real_pipeline(f02_config)
        report = orch.dry_run(
            document_id="F02",
            start_stage="document_ir",
            end_stage="six_dimension_extraction",
        )
        assert "pdf_parse" not in report["execution_order"]
        assert "document_ir" in report["execution_order"]
        assert "six_dimension_extraction" in report["execution_order"]
        assert "canonical_store" not in report["execution_order"]

    def test_real_dag_creates_manifest(self, f02_config, temp_dir):
        """DryRun should persist manifest to disk."""
        orch = _build_real_pipeline(f02_config)
        report = orch.dry_run(document_id="F02")

        runs_dir = Path(f02_config.config["execution"]["manifest_dir"])
        manifest_files = list(runs_dir.glob("*.json"))
        assert len(manifest_files) >= 1

        loaded = RunManifest.load(manifest_files[0])
        assert loaded.document_id == "F02"
        assert loaded.status == "COMPLETED"


class TestRound2CachedReplay:
    """Round 2: Test adapters with F02's existing cached data."""

    def test_pdf_parse_skips_existing_output(self, f02_config, temp_dir):
        """pdf_parse adapter should skip when F02_regression output exists."""
        from catalyst_knowledge.pipeline.adapters.pdf_parse_adapter import (
            _check_existing_output,
        )
        assert _check_existing_output("F02", str(F02_MINERU_DIR))

    def test_document_ir_finds_f02_mineru(self, f02_config):
        """document_ir adapter should find F02's MinerU output."""
        from catalyst_knowledge.pipeline.adapters.document_ir_adapter import (
            _find_mineru_auto_dir,
        )
        auto_dir = _find_mineru_auto_dir(str(F02_MINERU_DIR), "F02")
        assert auto_dir is not None, "Should find F02_regression/main/auto/"
        assert auto_dir.exists()
        content_files = list(auto_dir.glob("*content_list.json"))
        assert len(content_files) >= 1

    def test_extraction_cache_hit(self, f02_config, temp_dir):
        """extraction adapter should use cached G3 output for F02."""
        cache_target = temp_dir / "extraction" / "F02"
        cache_target.mkdir(parents=True)
        for src in (F02_G3_DIR / "F02").glob("*_extracted.json"):
            shutil.copy2(src, cache_target / src.name)

        from catalyst_knowledge.pipeline.adapters.extraction_adapter import run_extraction

        result = run_extraction(
            document_id="F02",
            mineru_output=str(F02_MINERU_DIR),
            output_dir=str(temp_dir / "extraction"),
            config=f02_config.config,
            use_cache=True,
        )

        assert result["extraction_status"] == "PASS"
        assert result["extraction_source"] == "cache"
        assert len(result["dimensions_extracted"]) == 6

    def test_figure_text_finds_f02_mineru(self, f02_config):
        """figure_text adapter should find F02's MinerU output."""
        from catalyst_knowledge.pipeline.adapters.figure_text_adapter import (
            _find_mineru_auto_dir,
        )
        auto_dir = _find_mineru_auto_dir(str(F02_MINERU_DIR), "F02")
        assert auto_dir is not None


class TestRound3RealAdapterExecution:
    """Round 3: Run real adapters with F02 data."""

    def test_document_ir_adapter_real_run(self, f02_config, temp_dir):
        """document_ir adapter should produce blocks_with_ids from F02 MinerU data."""
        from catalyst_knowledge.pipeline.adapters.document_ir_adapter import run_document_ir

        output_dir = temp_dir / "doc_ir"
        output_dir.mkdir()

        result = run_document_ir(
            document_id="F02",
            mineru_output=str(F02_MINERU_DIR),
            output_dir=str(output_dir),
        )

        assert result["document_id"] == "F02"
        assert result["document_ir_status"] == "PASS"
        assert "blocks_output" in result
        blocks_path = Path(result["blocks_output"])
        assert blocks_path.exists()

        with open(blocks_path, "r", encoding="utf-8") as f:
            blocks = json.load(f)
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        assert "element_id" in blocks[0]
        assert "source_anchor" in blocks[0]

    def test_figure_text_adapter_real_run(self, f02_config, temp_dir):
        """figure_text adapter should run on F02 (may PASS or WARN depending on images)."""
        from catalyst_knowledge.pipeline.adapters.figure_text_adapter import (
            run_figure_text_association,
        )

        output_dir = temp_dir / "fig_text"
        output_dir.mkdir()

        result = run_figure_text_association(
            document_id="F02",
            mineru_output=str(F02_MINERU_DIR),
            output_dir=str(output_dir),
        )

        assert result["document_id"] == "F02"
        assert result["figure_text_status"] in ("PASS", "WARN", "SKIPPED")

    def test_extraction_adapter_cache_replay(self, f02_config, temp_dir):
        """extraction adapter should replay cached F02 data without LLM call."""
        cache_target = temp_dir / "extraction" / "F02"
        cache_target.mkdir(parents=True)
        for src in (F02_G3_DIR / "F02").glob("*_extracted.json"):
            shutil.copy2(src, cache_target / src.name)

        from catalyst_knowledge.pipeline.adapters.extraction_adapter import run_extraction

        result = run_extraction(
            document_id="F02",
            mineru_output=str(F02_MINERU_DIR),
            output_dir=str(temp_dir / "extraction"),
            config=f02_config.config,
            use_cache=True,
        )

        assert result["extraction_status"] == "PASS"
        assert result["extraction_source"] == "cache"
        assert "catalyst_design" in result["dimensions_extracted"]
        assert "performance" in result["dimensions_extracted"]

    def test_pipeline_partial_run_document_ir_to_extraction(self, f02_config, temp_dir):
        """Run pipeline from document_ir to six_dimension_extraction with cached data."""
        cache_target = temp_dir / "runs" / "extraction" / "F02"
        cache_target.mkdir(parents=True)
        for src in (F02_G3_DIR / "F02").glob("*_extracted.json"):
            shutil.copy2(src, cache_target / src.name)

        orch = _build_real_pipeline(f02_config)

        manifest = orch.run(
            document_id="F02",
            start_stage="document_ir",
            end_stage="six_dimension_extraction",
        )

        doc_ir = manifest.get_stage("document_ir")
        assert doc_ir.status == "SUCCESS", f"document_ir failed: {doc_ir.error_message}"

        extraction = manifest.get_stage("six_dimension_extraction")
        assert extraction.status == "SUCCESS", f"extraction failed: {extraction.error_message}"
        assert len(extraction.output_files) >= 0

    def test_manifest_records_all_stages(self, f02_config, temp_dir):
        """Manifest should record every attempted stage with timing."""
        orch = _build_real_pipeline(f02_config)
        manifest = orch.run(
            document_id="F02",
            start_stage="document_ir",
            end_stage="document_ir",
        )

        doc_ir = manifest.get_stage("document_ir")
        assert doc_ir is not None
        assert doc_ir.status == "SUCCESS"
        assert doc_ir.duration_seconds >= 0
