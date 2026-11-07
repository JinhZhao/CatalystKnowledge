"""Tests for pipeline/stage_adapter.py."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from catalyst_knowledge.pipeline.stage_adapter import (
    ContractValidationError,
    DataContract,
    StageAdapter,
    StageResult,
)
from catalyst_knowledge.pipeline.run_manifest import StageRecord


class TestStageAdapterFunction:
    def test_execute_simple_function(self):
        def my_func(document_id, **kwargs):
            return {"result": f"processed_{document_id}"}

        adapter = StageAdapter(
            stage_name="test_func",
            version="1.0.0",
            input_contract=DataContract(required_inputs=["document_id"]),
            output_contract=DataContract(required_outputs=["result"]),
        )
        adapter.set_function(my_func)

        record = StageRecord("test_func")
        result = adapter.execute({"document_id": "F02"}, record)

        assert result.success is True
        assert result.output["result"] == "processed_F02"
        assert record.status == "SUCCESS"

    def test_execute_with_fixed_kwargs(self):
        def my_func(document_id, extra_param=None, **kwargs):
            return {"result": f"{document_id}_{extra_param}"}

        adapter = StageAdapter(stage_name="test_fixed", version="1.0.0")
        adapter.set_function(my_func, extra_param="FIXED")

        record = StageRecord("test_fixed")
        result = adapter.execute({"document_id": "F02"}, record)

        assert result.success is True
        assert result.output["result"] == "F02_FIXED"

    def test_execute_function_raises_exception(self):
        def bad_func(**kwargs):
            raise ValueError("intentional error")

        adapter = StageAdapter(stage_name="test_bad", version="1.0.0")
        adapter.set_function(bad_func)

        record = StageRecord("test_bad")
        result = adapter.execute({}, record)

        assert result.success is False
        assert "intentional error" in result.error
        assert result.traceback_str is not None
        assert record.status == "FAILED"

    def test_execute_function_timeout(self):
        def slow_func(**kwargs):
            time.sleep(10)
            return {"result": "done"}

        adapter = StageAdapter(
            stage_name="test_timeout",
            version="1.0.0",
            timeout_seconds=1,
        )
        adapter.set_function(slow_func)

        record = StageRecord("test_timeout")
        result = adapter.execute({}, record)

        assert result.success is False
        assert "timed out" in result.error.lower()
        assert record.status == "FAILED"

    def test_execute_no_executor(self):
        adapter = StageAdapter(stage_name="test_none", version="1.0.0")
        record = StageRecord("test_none")
        result = adapter.execute({}, record)

        assert result.success is False
        assert "No executor" in result.error


class TestStageAdapterDryRun:
    def test_dry_run_skips_execution(self):
        executed = []

        def my_func(**kwargs):
            executed.append(True)
            return {"result": "done"}

        adapter = StageAdapter(stage_name="test_dry", version="1.0.0")
        adapter.set_function(my_func)

        record = StageRecord("test_dry")
        result = adapter.execute({}, record, dry_run=True)

        assert result.success is True
        assert result.skipped is True
        assert result.skip_reason == "dry_run"
        assert len(executed) == 0
        assert record.status == "SKIPPED"


class TestStageAdapterContracts:
    def test_input_validation_missing_required(self):
        adapter = StageAdapter(
            stage_name="test_contract",
            version="1.0.0",
            input_contract=DataContract(required_inputs=["document_id", "config"]),
        )
        adapter.set_function(lambda **kw: {"result": "ok"})

        record = StageRecord("test_contract")
        result = adapter.execute({"document_id": "F02"}, record)

        assert result.success is False
        assert "config" in result.error.lower()
        assert record.status == "FAILED"

    def test_input_validation_passes(self):
        adapter = StageAdapter(
            stage_name="test_contract_ok",
            version="1.0.0",
            input_contract=DataContract(required_inputs=["document_id"]),
        )
        adapter.set_function(lambda document_id, **kw: {"result": document_id})

        record = StageRecord("test_contract_ok")
        result = adapter.execute({"document_id": "F02"}, record)

        assert result.success is True

    def test_output_validation_missing_required(self):
        def bad_output(**kwargs):
            return {"wrong_key": "value"}

        adapter = StageAdapter(
            stage_name="test_out",
            version="1.0.0",
            output_contract=DataContract(required_outputs=["expected_key"]),
        )
        adapter.set_function(bad_output)

        record = StageRecord("test_out")
        result = adapter.execute({}, record)

        assert result.success is False
        assert "expected_key" in result.error


class TestStageAdapterScript:
    def test_set_script_function(self, tmp_path):
        script = tmp_path / "my_script.py"
        script.write_text(
            "def process(document_id=None, **kwargs):\n"
            "    return {'result': f'script_{document_id}'}\n"
            "\n"
            "def main(**kwargs):\n"
            "    return process(**kwargs)\n",
            encoding="utf-8",
        )

        adapter = StageAdapter(
            stage_name="test_script",
            version="1.0.0",
        )
        adapter.set_script_function(script, func_name="main")

        record = StageRecord("test_script")
        result = adapter.execute({"document_id": "F02"}, record)

        assert result.success is True
        assert result.output["result"] == "script_F02"

    def test_set_script_function_missing_func(self, tmp_path):
        script = tmp_path / "no_func.py"
        script.write_text("x = 1\n", encoding="utf-8")

        adapter = StageAdapter(stage_name="test_no_func", version="1.0.0")
        adapter.set_script_function(script, func_name="nonexistent")

        record = StageRecord("test_no_func")
        result = adapter.execute({}, record)

        assert result.success is False
        assert "nonexistent" in result.error.lower() or "not found" in result.error.lower()

    def test_set_script_class_method(self, tmp_path):
        script = tmp_path / "my_class.py"
        script.write_text(
            "class Processor:\n"
            "    def __init__(self, prefix='default'):\n"
            "        self.prefix = prefix\n"
            "    def process(self, document_id=None, **kwargs):\n"
            "        return {'result': f'{self.prefix}_{document_id}'}\n",
            encoding="utf-8",
        )

        adapter = StageAdapter(stage_name="test_class", version="1.0.0")
        adapter.set_script_class_method(
            script,
            class_name="Processor",
            method_name="process",
            init_kwargs={"prefix": "TEST"},
        )

        record = StageRecord("test_class")
        result = adapter.execute({"document_id": "F02"}, record)

        assert result.success is True
        assert result.output["result"] == "TEST_F02"

    def test_script_not_found(self, tmp_path):
        adapter = StageAdapter(stage_name="test_missing", version="1.0.0")
        adapter.set_script_function(tmp_path / "nonexistent.py")

        record = StageRecord("test_missing")
        result = adapter.execute({}, record)

        assert result.success is False


class TestStageAdapterFileRecording:
    def test_input_files_recorded(self, tmp_path):
        input_file = tmp_path / "input.txt"
        input_file.write_text("data", encoding="utf-8")

        adapter = StageAdapter(stage_name="test_files", version="1.0.0")
        adapter.set_function(lambda **kw: {"result": "ok"})

        record = StageRecord("test_files")
        result = adapter.execute({"input_file": str(input_file)}, record)

        assert result.success is True
        assert str(input_file) in record.input_files
        assert str(input_file) in record.input_hashes

    def test_output_files_recorded(self, tmp_path):
        output_file = tmp_path / "output.txt"

        def write_output(**kwargs):
            output_file.write_text("result", encoding="utf-8")
            return {"output_path": str(output_file)}

        adapter = StageAdapter(stage_name="test_out_files", version="1.0.0")
        adapter.set_function(write_output)

        record = StageRecord("test_out_files")
        result = adapter.execute({}, record)

        assert result.success is True
        assert str(output_file) in record.output_files
