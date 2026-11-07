"""Tests for pipeline/orchestrator.py."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from catalyst_knowledge.pipeline.config_loader import ConfigLoader
from catalyst_knowledge.pipeline.orchestrator import PipelineError, PipelineOrchestrator
from catalyst_knowledge.pipeline.stage_adapter import DataContract, StageAdapter


MINIMAL_CONFIG = {
    "pipeline": {
        "name": "test-pipeline",
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "prompt_version": "1.0.0",
    },
    "paths": {
        "project_root": "/tmp/test",
        "data_root": "/tmp/test/data",
        "manifest": "/tmp/test/manifest.json",
        "pipeline_runs": "",
    },
    "llm": {
        "api_key_env": "LLM_API_KEY",
        "default_model": "test-model",
    },
    "stages": {
        "stage_a": {"enabled": True, "timeout_seconds": 60},
        "stage_b": {"enabled": True, "timeout_seconds": 60},
        "stage_c": {"enabled": True, "timeout_seconds": 60},
        "stage_disabled": {"enabled": False, "timeout_seconds": 60},
    },
    "execution": {
        "stop_on_failure": True,
        "dry_run": False,
        "manifest_dir": "",
    },
}


def make_config(tmp_path):
    cfg_dict = dict(MINIMAL_CONFIG)
    cfg_dict["paths"] = dict(MINIMAL_CONFIG["paths"])
    cfg_dict["paths"]["pipeline_runs"] = str(tmp_path / "runs")
    cfg_dict["execution"] = dict(MINIMAL_CONFIG["execution"])
    cfg_dict["execution"]["manifest_dir"] = str(tmp_path / "runs")
    loader = ConfigLoader()
    loader.load_from_dict(cfg_dict)
    return loader


def make_adapter(name, func=None, deps=None, timeout=30):
    adapter = StageAdapter(
        stage_name=name,
        version="1.0.0",
        timeout_seconds=timeout,
        input_contract=DataContract(),
        output_contract=DataContract(),
        dependencies=deps or [],
    )
    if func:
        adapter.set_function(func)
    else:
        adapter.set_function(lambda **kw: {f"_out_{name}": True})
    return adapter


class TestOrchestratorRegistration:
    def test_register_single_stage(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        assert "stage_a" in orch._stages

    def test_register_duplicate_raises(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        with pytest.raises(PipelineError, match="already registered"):
            orch.register_stage(make_adapter("stage_a"))

    def test_register_with_dependencies(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch.register_stage(make_adapter("stage_b"), dependencies=["stage_a"])
        assert orch._dependencies["stage_b"] == ["stage_a"]


class TestOrchestratorDAG:
    def test_linear_execution_order(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch.register_stage(make_adapter("stage_b"), dependencies=["stage_a"])
        orch.register_stage(make_adapter("stage_c"), dependencies=["stage_b"])
        order = orch.get_execution_order()
        assert order == ["stage_a", "stage_b", "stage_c"]

    def test_diamond_execution_order(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch.register_stage(make_adapter("stage_b"), dependencies=["stage_a"])
        orch.register_stage(make_adapter("stage_c"), dependencies=["stage_a"])
        orch.register_stage(make_adapter("stage_d"), dependencies=["stage_b", "stage_c"])
        order = orch.get_execution_order()
        assert order.index("stage_a") < order.index("stage_b")
        assert order.index("stage_a") < order.index("stage_c")
        assert order.index("stage_b") < order.index("stage_d")
        assert order.index("stage_c") < order.index("stage_d")

    def test_circular_dependency_detected(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch._dependencies["stage_a"] = ["stage_b"]
        orch._stages["stage_b"] = make_adapter("stage_b")
        orch._dependencies["stage_b"] = ["stage_a"]
        with pytest.raises(PipelineError, match="[Cc]ircular"):
            orch.get_execution_order()

    def test_validate_dag_clean(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch.register_stage(make_adapter("stage_b"), dependencies=["stage_a"])
        issues = orch.validate_dag()
        assert issues == []

    def test_validate_dag_missing_dependency(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"), dependencies=["nonexistent"])
        issues = orch.validate_dag()
        assert len(issues) > 0
        assert "nonexistent" in issues[0]


class TestOrchestratorDryRun:
    def test_dry_run_returns_plan(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch.register_stage(make_adapter("stage_b"), dependencies=["stage_a"])
        report = orch.dry_run("F02")
        assert report["mode"] == "dry_run"
        assert report["document_id"] == "F02"
        assert len(report["stages"]) == 2
        assert report["stages"][0]["name"] == "stage_a"

    def test_dry_run_respects_start_end(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch.register_stage(make_adapter("stage_b"), dependencies=["stage_a"])
        orch.register_stage(make_adapter("stage_c"), dependencies=["stage_b"])
        report = orch.dry_run("F02", start_stage="stage_b", end_stage="stage_c")
        names = [s["name"] for s in report["stages"]]
        assert "stage_a" not in names
        assert "stage_b" in names
        assert "stage_c" in names


class TestOrchestratorRun:
    def test_full_run_success(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        results = {}

        # Create actual output files for verification
        output_a = tmp_path / "stage_a_output.json"
        output_a.write_text("{}")
        output_b = tmp_path / "stage_b_output.json"
        output_b.write_text("{}")

        def stage_a_func(**kw):
            results["a"] = True
            return {"step_a_done": True, "output_path": str(output_a)}

        def stage_b_func(**kw):
            results["b"] = True
            return {"step_b_done": True, "output_path": str(output_b)}

        orch.register_stage(make_adapter("stage_a", func=stage_a_func))
        orch.register_stage(make_adapter("stage_b", func=stage_b_func, deps=["stage_a"]))
        manifest = orch.run("F02")

        assert manifest.status == "COMPLETED"
        assert results.get("a") is True
        assert results.get("b") is True

    def test_run_stop_on_failure(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        results = {}

        def failing_func(**kw):
            raise RuntimeError("stage_a exploded")

        def stage_b_func(**kw):
            results["b"] = True
            return {}

        orch.register_stage(make_adapter("stage_a", func=failing_func))
        orch.register_stage(make_adapter("stage_b", func=stage_b_func, deps=["stage_a"]))
        manifest = orch.run("F02")

        assert manifest.status == "FAILED"
        assert "b" not in results

    def test_run_disabled_stage_skipped(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        results = {}

        def disabled_func(**kw):
            results["disabled"] = True
            return {}

        orch.register_stage(make_adapter("stage_disabled", func=disabled_func))
        manifest = orch.run("F02")

        assert "disabled" not in results

    def test_run_partial_start_end(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        results = {}

        def stage_a_func(**kw):
            results["a"] = True
            return {}

        def stage_b_func(**kw):
            results["b"] = True
            return {}

        def stage_c_func(**kw):
            results["c"] = True
            return {}

        orch.register_stage(make_adapter("stage_a", func=stage_a_func))
        orch.register_stage(make_adapter("stage_b", func=stage_b_func, deps=["stage_a"]))
        orch.register_stage(make_adapter("stage_c", func=stage_c_func, deps=["stage_b"]))
        manifest = orch.run("F02", start_stage="stage_b", end_stage="stage_c")

        assert "a" not in results
        assert results.get("b") is True
        assert results.get("c") is True

    def test_data_passes_between_stages(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        received = {}

        def producer(**kw):
            return {"shared_value": 42}

        def consumer(shared_value=None, **kw):
            received["value"] = shared_value
            return {}

        orch.register_stage(make_adapter("stage_a", func=producer))
        orch.register_stage(make_adapter("stage_b", func=consumer, deps=["stage_a"]))
        orch.run("F02")

        assert received.get("value") == 42


class TestOrchestratorRerun:
    def test_rerun_single_stage(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        call_count = {"a": 0, "b": 0}

        def stage_a_func(**kw):
            call_count["a"] += 1
            return {}

        def stage_b_func(**kw):
            call_count["b"] += 1
            return {}

        orch.register_stage(make_adapter("stage_a", func=stage_a_func))
        orch.register_stage(make_adapter("stage_b", func=stage_b_func, deps=["stage_a"]))

        orch.run("F02")
        assert call_count["a"] == 1
        assert call_count["b"] == 1

        orch.rerun_stage("F02", "stage_a", cascade_downstream=False)
        assert call_count["a"] == 2
        assert call_count["b"] == 1

    def test_rerun_with_cascade(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        call_count = {"a": 0, "b": 0}

        def stage_a_func(**kw):
            call_count["a"] += 1
            return {}

        def stage_b_func(**kw):
            call_count["b"] += 1
            return {}

        orch.register_stage(make_adapter("stage_a", func=stage_a_func))
        orch.register_stage(make_adapter("stage_b", func=stage_b_func, deps=["stage_a"]))

        orch.run("F02")
        orch.rerun_stage("F02", "stage_a", cascade_downstream=True)
        assert call_count["a"] == 2
        assert call_count["b"] == 2

    def test_rerun_unknown_stage_raises(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        with pytest.raises(PipelineError, match="Unknown stage"):
            orch.rerun_stage("F02", "nonexistent")


class TestOrchestratorResume:
    def test_resume_skips_succeeded_stages(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        call_count = {"a": 0, "b": 0}

        def stage_a_func(**kw):
            call_count["a"] += 1
            return {}

        def stage_b_func(**kw):
            call_count["b"] += 1
            return {}

        orch.register_stage(make_adapter("stage_a", func=stage_a_func))
        orch.register_stage(make_adapter("stage_b", func=stage_b_func, deps=["stage_a"]))

        manifest1 = orch.run("F02")
        assert call_count["a"] == 1
        assert call_count["b"] == 1

        orch2 = PipelineOrchestrator(config)
        orch2.register_stage(make_adapter("stage_a", func=stage_a_func))
        orch2.register_stage(make_adapter("stage_b", func=stage_b_func, deps=["stage_a"]))
        manifest2 = orch2.run("F02", resume_from=manifest1.manifest_file)

        assert call_count["a"] == 1
        assert call_count["b"] == 1
        assert manifest2.status == "COMPLETED"


class TestOrchestratorDownstream:
    def test_get_downstream_stages(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        orch.register_stage(make_adapter("stage_a"))
        orch.register_stage(make_adapter("stage_b"), dependencies=["stage_a"])
        orch.register_stage(make_adapter("stage_c"), dependencies=["stage_b"])
        downstream = orch._get_downstream_stages("stage_a")
        assert "stage_b" in downstream
        assert "stage_c" in downstream

    def test_failed_dependency_skips_downstream(self, tmp_path):
        config = make_config(tmp_path)
        orch = PipelineOrchestrator(config)
        results = {}

        def failing_func(**kw):
            raise RuntimeError("boom")

        def stage_c_func(**kw):
            results["c"] = True
            return {}

        orch.register_stage(make_adapter("stage_a", func=failing_func))
        orch.register_stage(make_adapter("stage_b", func=lambda **kw: {}, deps=["stage_a"]))
        orch.register_stage(make_adapter("stage_c", func=stage_c_func, deps=["stage_b"]))
        manifest = orch.run("F02")

        assert manifest.status == "FAILED"
        assert "c" not in results
