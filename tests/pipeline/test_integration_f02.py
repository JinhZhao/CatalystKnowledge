"""Integration tests for PIPELINE-001 Phase 1 with F02 document.

Three test rounds:
1. DryRun — validate DAG without executing
2. Cached artifacts — test idempotency with existing F02 data
3. Isolated full run — end-to-end in temp directory
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest

from catalyst_knowledge.pipeline.config_loader import ConfigLoader
from catalyst_knowledge.pipeline.orchestrator import PipelineOrchestrator
from catalyst_knowledge.pipeline.run_manifest import RunManifest
from catalyst_knowledge.pipeline.stage_adapter import DataContract, StageAdapter


PROJECT_ROOT = Path(r"D:\Knowledge_World")
F02_MINERU_DIR = PROJECT_ROOT / "data" / "test_corpus" / "mineru_output" / "F02_regression"


@pytest.fixture
def temp_pipeline_dir(tmp_path):
    """Create isolated temp directory for pipeline runs."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    return tmp_path


@pytest.fixture
def f02_config(temp_pipeline_dir):
    """ConfigLoader pointing to temp directory."""
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
            "manifest": str(temp_pipeline_dir / "runs"),
            "pipeline_runs": str(temp_pipeline_dir / "runs"),
            "mineru_output": str(F02_MINERU_DIR),
            "ext01_output": str(temp_pipeline_dir / "ext01"),
            "g3_output": str(temp_pipeline_dir / "g3"),
            "canonical_store": str(temp_pipeline_dir / "store"),
            "reports_dir": str(temp_pipeline_dir / "reports"),
        },
        "llm": {
            "api_base": "https://test.example.com",
            "api_key_env": "LLM_API_KEY",
            "default_model": "test-model",
        },
        "stages": {
            "pdf_parse": {"enabled": True, "timeout_seconds": 60},
            "document_ir": {"enabled": True, "timeout_seconds": 60},
            "figure_text_association": {"enabled": True, "timeout_seconds": 60},
            "six_dimension_extraction": {"enabled": True, "timeout_seconds": 60},
            "quality_gate": {"enabled": True, "timeout_seconds": 60},
            "canonical_store": {"enabled": True, "timeout_seconds": 60},
            "report_generation": {"enabled": True, "timeout_seconds": 60},
        },
        "execution": {
            "stop_on_failure": True,
            "dry_run": False,
            "manifest_dir": str(temp_pipeline_dir / "runs"),
        },
    }
    loader = ConfigLoader()
    loader.load_from_dict(cfg_dict)
    return loader


def make_mock_adapter(name, output_data=None, deps=None):
    """Create a mock StageAdapter that returns canned data."""
    adapter = StageAdapter(
        stage_name=name,
        version="1.0.0",
        timeout_seconds=30,
        input_contract=DataContract(),
        output_contract=DataContract(),
        dependencies=deps or [],
    )

    def mock_func(**kwargs):
        return output_data or {f"_out_{name}": True}

    adapter.set_function(mock_func)
    return adapter


class TestRound1DryRun:
    """Round 1: DryRun validation without execution."""

    def test_dry_run_returns_execution_plan(self, f02_config):
        """DryRun should return a plan without executing any stages."""
        orch = PipelineOrchestrator(f02_config)

        orch.register_stage(make_mock_adapter("pdf_parse"))
        orch.register_stage(make_mock_adapter("document_ir", deps=["pdf_parse"]))
        orch.register_stage(make_mock_adapter("six_dimension_extraction", deps=["document_ir"]))

        report = orch.dry_run(document_id="F02")

        assert report["mode"] == "dry_run"
        assert report["document_id"] == "F02"
        assert len(report["stages"]) == 3
        assert report["execution_order"] == ["pdf_parse", "document_ir", "six_dimension_extraction"]

    def test_dry_run_validates_dag(self, f02_config):
        """DryRun should detect DAG issues."""
        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_mock_adapter("stage_a"))
        orch.register_stage(make_mock_adapter("stage_b", deps=["stage_a"]))
        orch.register_stage(make_mock_adapter("stage_c", deps=["stage_b"]))

        issues = orch.validate_dag()
        assert issues == []

        report = orch.dry_run(document_id="F02")
        assert report["execution_order"] == ["stage_a", "stage_b", "stage_c"]

    def test_dry_run_respects_start_end(self, f02_config):
        """DryRun should honor start_stage and end_stage filters."""
        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_mock_adapter("pdf_parse"))
        orch.register_stage(make_mock_adapter("document_ir", deps=["pdf_parse"]))
        orch.register_stage(make_mock_adapter("extraction", deps=["document_ir"]))
        orch.register_stage(make_mock_adapter("store", deps=["extraction"]))

        report = orch.dry_run(
            document_id="F02",
            start_stage="document_ir",
            end_stage="extraction",
        )

        assert report["execution_order"] == ["document_ir", "extraction"]
        assert len(report["stages"]) == 2

    def test_dry_run_creates_manifest(self, f02_config, temp_pipeline_dir):
        """DryRun should persist a manifest file."""
        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_mock_adapter("pdf_parse"))

        report = orch.dry_run(document_id="F02")

        manifest_path = temp_pipeline_dir / "runs" / f"{report['run_id']}.json"
        assert manifest_path.exists()

        loaded = RunManifest.load(manifest_path)
        assert loaded.status == "COMPLETED"
        assert loaded.document_id == "F02"


class TestRound2CachedArtifacts:
    """Round 2: Test idempotency with existing F02 artifacts."""

    def test_stage_skipped_when_output_exists(self, f02_config, temp_pipeline_dir):
        """Stages with skip_if_output_exists should skip when output files exist."""
        f02_config.config["stages"]["pdf_parse"]["skip_if_output_exists"] = True

        orch = PipelineOrchestrator(f02_config)

        pdf_adapter = make_mock_adapter("pdf_parse", {"mineru_output_dir": str(F02_MINERU_DIR)})
        pdf_adapter.output_contract = DataContract(
            output_file_patterns=[str(F02_MINERU_DIR / "main" / "auto" / "main_content_list.json")],
        )
        orch.register_stage(pdf_adapter)

        manifest = orch.run(document_id="F02")

        pdf_record = manifest.get_stage("pdf_parse")
        assert pdf_record.status == "SKIPPED"
        assert "output exists" in pdf_record.skip_reason

    def test_resume_skips_succeeded_stages(self, f02_config, temp_pipeline_dir):
        """Resume should skip stages that already succeeded in previous run."""
        prev_manifest = RunManifest(
            document_id="F02",
            manifest_dir=temp_pipeline_dir / "runs",
        )
        prev_stage = prev_manifest.add_stage("pdf_parse")
        prev_stage.mark_success()
        prev_manifest.mark_completed()
        prev_manifest.save()

        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_mock_adapter("pdf_parse", {"result": "new"}))
        orch.register_stage(make_mock_adapter("document_ir", deps=["pdf_parse"]))

        manifest = orch.run(
            document_id="F02",
            resume_from=prev_manifest.manifest_file,
        )

        pdf_record = manifest.get_stage("pdf_parse")
        assert pdf_record.status == "SKIPPED"
        assert "already succeeded" in pdf_record.skip_reason.lower()

        doc_ir_record = manifest.get_stage("document_ir")
        assert doc_ir_record.status == "SUCCESS"

    def test_idempotent_rerun(self, f02_config, temp_pipeline_dir):
        """Rerunning the same stage should produce consistent results."""
        call_count = {"n": 0}

        def counting_func(**kwargs):
            call_count["n"] += 1
            return {"count": call_count["n"]}

        orch = PipelineOrchestrator(f02_config)
        adapter = StageAdapter(
            stage_name="counter",
            version="1.0.0",
            timeout_seconds=30,
            input_contract=DataContract(),
            output_contract=DataContract(),
        )
        adapter.set_function(counting_func)
        orch.register_stage(adapter)

        m1 = orch.rerun_stage(document_id="F02", stage_name="counter", cascade_downstream=False)
        m2 = orch.rerun_stage(document_id="F02", stage_name="counter", cascade_downstream=False)

        assert call_count["n"] == 2
        assert m1.get_stage("counter").status == "SUCCESS"
        assert m2.get_stage("counter").status == "SUCCESS"


class TestRound3IsolatedFullRun:
    """Round 3: Full end-to-end run in isolated temp directory."""

    def test_full_pipeline_execution(self, f02_config, temp_pipeline_dir):
        """Execute full pipeline with mock stages in isolation."""
        from pathlib import Path
        # Create actual files at the paths the mock adapters will return
        # This is required because the new output file validation checks file existence
        (temp_pipeline_dir / "ir.json").write_text("{}")
        (temp_pipeline_dir / "fig.json").write_text("{}")
        (temp_pipeline_dir / "ext.json").write_text("{}")
        (temp_pipeline_dir / "qa.json").write_text("{}")
        (temp_pipeline_dir / "store").write_text("{}")
        (temp_pipeline_dir / "report").write_text("{}")

        orch = PipelineOrchestrator(f02_config)

        orch.register_stage(make_mock_adapter("pdf_parse", {"mineru_output_dir": str(temp_pipeline_dir)}))
        orch.register_stage(make_mock_adapter("document_ir", {"document_ir_path": str(temp_pipeline_dir / "ir.json")}, deps=["pdf_parse"]))
        orch.register_stage(make_mock_adapter("figure_text_association", {"figure_associations_path": str(temp_pipeline_dir / "fig.json")}, deps=["document_ir"]))
        orch.register_stage(make_mock_adapter("six_dimension_extraction", {"extraction_output_path": str(temp_pipeline_dir / "ext.json")}, deps=["document_ir"]))
        orch.register_stage(make_mock_adapter("quality_gate", {"qa_report_path": str(temp_pipeline_dir / "qa.json")}, deps=["six_dimension_extraction"]))
        orch.register_stage(make_mock_adapter("canonical_store", {"store_path": str(temp_pipeline_dir / "store")}, deps=["quality_gate"]))
        orch.register_stage(make_mock_adapter("report_generation", {"report_path": str(temp_pipeline_dir / "report")}, deps=["canonical_store"]))

        manifest = orch.run(document_id="F02")

        assert manifest.status == "COMPLETED"
        assert manifest.document_id == "F02"
        assert len(manifest.stages) == 7

        for name in ["pdf_parse", "document_ir", "figure_text_association",
                     "six_dimension_extraction", "quality_gate", "canonical_store",
                     "report_generation"]:
            record = manifest.get_stage(name)
            assert record is not None, f"Stage {name} not in manifest"
            assert record.status == "SUCCESS", f"Stage {name} failed: {record.error_message}"

    def test_manifest_persistence(self, f02_config, temp_pipeline_dir):
        """Manifest should be saved to disk and reloadable."""
        output_file = temp_pipeline_dir / "pdf_parse_output.json"
        output_file.write_text("{}")

        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_mock_adapter("pdf_parse", {"output_path": str(output_file)}))

        manifest = orch.run(document_id="F02")

        assert manifest.manifest_file.exists()

        reloaded = RunManifest.load(manifest.manifest_file)
        assert reloaded.run_id == manifest.run_id
        assert reloaded.document_id == "F02"
        assert reloaded.status == "COMPLETED"

    def test_config_hash_in_manifest(self, f02_config, temp_pipeline_dir):
        """Manifest should record config SHA256 for traceability."""
        output_file = temp_pipeline_dir / "pdf_parse_output.json"
        output_file.write_text("{}")

        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_mock_adapter("pdf_parse", {"output_path": str(output_file)}))

        manifest = orch.run(document_id="F02")

        assert manifest.config_hash is not None
        assert len(manifest.config_hash) == 64


class TestCascadeRerun:
    """Test cascade re-execution of downstream stages."""

    def test_rerun_cascades_to_dependents(self, f02_config, temp_pipeline_dir):
        """Rerunning a stage should cascade to all downstream dependents."""
        execution_order = []

        def make_tracking_adapter(name, deps=None):
            adapter = StageAdapter(
                stage_name=name,
                version="1.0.0",
                timeout_seconds=30,
                input_contract=DataContract(),
                output_contract=DataContract(),
                dependencies=deps or [],
            )

            def track(**kwargs):
                execution_order.append(name)
                return {f"out_{name}": True}

            adapter.set_function(track)
            return adapter

        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_tracking_adapter("A"))
        orch.register_stage(make_tracking_adapter("B", deps=["A"]))
        orch.register_stage(make_tracking_adapter("C", deps=["B"]))
        orch.register_stage(make_tracking_adapter("D", deps=["A"]))

        manifest = orch.rerun_stage(document_id="F02", stage_name="A", cascade_downstream=True)

        assert "A" in execution_order
        assert "B" in execution_order
        assert "C" in execution_order
        assert "D" in execution_order
        assert execution_order.index("A") < execution_order.index("B")
        assert execution_order.index("B") < execution_order.index("C")

    def test_rerun_without_cascade(self, f02_config, temp_pipeline_dir):
        """Rerunning with cascade_downstream=False should only rerun the target."""
        execution_order = []

        def make_tracking_adapter(name, deps=None):
            adapter = StageAdapter(
                stage_name=name,
                version="1.0.0",
                timeout_seconds=30,
                input_contract=DataContract(),
                output_contract=DataContract(),
                dependencies=deps or [],
            )

            def track(**kwargs):
                execution_order.append(name)
                return {f"out_{name}": True}

            adapter.set_function(track)
            return adapter

        orch = PipelineOrchestrator(f02_config)
        orch.register_stage(make_tracking_adapter("A"))
        orch.register_stage(make_tracking_adapter("B", deps=["A"]))

        manifest = orch.rerun_stage(document_id="F02", stage_name="A", cascade_downstream=False)

        assert execution_order == ["A"]
