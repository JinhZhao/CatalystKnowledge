"""Tests for pipeline/run_manifest.py."""

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from catalyst_knowledge.pipeline.run_manifest import (
    RunManifest,
    StageRecord,
    compute_file_sha256,
)


@pytest.fixture
def manifest_dir(tmp_path):
    return tmp_path / "manifests"


@pytest.fixture
def sample_file(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("hello world", encoding="utf-8")
    return p


class TestStageRecord:
    def test_create(self):
        rec = StageRecord("test_stage")
        assert rec.stage_name == "test_stage"
        assert rec.status == "PENDING"
        assert rec.start_time is None

    def test_mark_start(self):
        rec = StageRecord("test_stage")
        rec.mark_start()
        assert rec.status == "RUNNING"
        assert rec.start_time is not None

    def test_mark_success(self):
        rec = StageRecord("test_stage")
        rec.mark_start()
        rec.mark_success()
        assert rec.status == "SUCCESS"
        assert rec.end_time is not None
        assert rec.duration_seconds is not None
        assert rec.duration_seconds >= 0

    def test_mark_failed(self):
        rec = StageRecord("test_stage")
        rec.mark_start()
        rec.mark_failed("something broke", "Traceback...")
        assert rec.status == "FAILED"
        assert rec.error_message == "something broke"
        assert rec.error_traceback == "Traceback..."
        assert rec.duration_seconds is not None

    def test_mark_skipped(self):
        rec = StageRecord("test_stage")
        rec.mark_skipped("output exists")
        assert rec.status == "SKIPPED"
        assert rec.skip_reason == "output exists"

    def test_to_dict_roundtrip(self):
        rec = StageRecord("test_stage")
        rec.mark_start()
        rec.mark_success()
        rec.input_files = ["/tmp/a.txt"]
        rec.input_hashes = {"/tmp/a.txt": "abc123"}
        d = rec.to_dict()
        rec2 = StageRecord.from_dict(d)
        assert rec2.stage_name == "test_stage"
        assert rec2.status == "SUCCESS"
        assert rec2.input_files == ["/tmp/a.txt"]
        assert rec2.input_hashes == {"/tmp/a.txt": "abc123"}


class TestRunManifest:
    def test_create(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        assert m.document_id == "F02"
        assert m.status == "INITIALIZED"
        assert m.run_id.startswith("run_")
        assert len(m.stages) == 0

    def test_set_model(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        m.set_model("deepseek-flash")
        assert m.model_name == "deepseek-flash"

    def test_set_config_hash(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        m.set_config_hash("abc123def456")
        assert m.config_hash == "abc123def456"

    def test_add_input_file(self, manifest_dir, sample_file):
        m = RunManifest("F02", manifest_dir)
        m.add_input_file(str(sample_file))
        assert str(sample_file) in m.input_files
        assert str(sample_file) in m.input_hashes
        assert len(m.input_hashes[str(sample_file)]) == 64

    def test_add_input_file_no_hash(self, manifest_dir, sample_file):
        m = RunManifest("F02", manifest_dir)
        m.add_input_file(str(sample_file), compute_hash=False)
        assert str(sample_file) in m.input_files
        assert str(sample_file) not in m.input_hashes

    def test_add_stage(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        rec = m.add_stage("pdf_parse")
        assert isinstance(rec, StageRecord)
        assert "pdf_parse" in m.stages
        assert "pdf_parse" in m.stage_order

    def test_add_stage_idempotent_order(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        m.add_stage("stage_a")
        m.add_stage("stage_b")
        m.add_stage("stage_a")
        assert m.stage_order == ["stage_a", "stage_b"]

    def test_mark_running(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        m.mark_running()
        assert m.status == "RUNNING"

    def test_mark_completed(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        m.mark_running()
        m.mark_completed()
        assert m.status == "COMPLETED"

    def test_mark_failed(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        m.mark_running()
        m.mark_failed("stage X exploded")
        assert m.status == "FAILED"
        assert m.error_message == "stage X exploded"

    def test_save_and_load(self, manifest_dir):
        m = RunManifest("F02", manifest_dir, pipeline_version="1.0.0",
                        schema_version="1.0.0", prompt_version="1.0.0")
        m.set_model("test-model")
        m.set_config_hash("cfg_hash_123")
        m.add_input_file(str(manifest_dir), compute_hash=False)
        rec = m.add_stage("test_stage")
        rec.mark_start()
        rec.mark_success()
        m.mark_running()
        m.mark_completed()
        path = m.save()

        m2 = RunManifest.load(path)
        assert m2.run_id == m.run_id
        assert m2.document_id == "F02"
        assert m2.pipeline_version == "1.0.0"
        assert m2.model_name == "test-model"
        assert m2.config_hash == "cfg_hash_123"
        assert m2.status == "COMPLETED"
        assert "test_stage" in m2.stages
        assert m2.stages["test_stage"].status == "SUCCESS"

    def test_load_missing_file(self, manifest_dir):
        with pytest.raises(FileNotFoundError):
            RunManifest.load(manifest_dir / "nonexistent.json")

    def test_to_dict(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        d = m.to_dict()
        assert "run_id" in d
        assert "document_id" in d
        assert d["document_id"] == "F02"
        assert "stages" in d
        assert isinstance(d["stages"], dict)

    def test_get_summary(self, manifest_dir):
        m = RunManifest("F02", manifest_dir)
        m.set_model("test-model")
        m.add_stage("stage_a")
        m.add_stage("stage_b")
        m.mark_running()
        m.mark_completed()
        summary = m.get_summary()
        assert summary["run_id"] == m.run_id
        assert summary["status"] == "COMPLETED"
        assert len(summary["stages"]) == 2
        assert summary["stages"][0]["stage"] == "stage_a"


class TestComputeFileSha256:
    def test_hash_existing_file(self, sample_file):
        h = compute_file_sha256(sample_file)
        assert h is not None
        assert len(h) == 64

    def test_hash_consistent(self, sample_file):
        h1 = compute_file_sha256(sample_file)
        h2 = compute_file_sha256(sample_file)
        assert h1 == h2

    def test_hash_nonexistent_file(self, tmp_path):
        h = compute_file_sha256(tmp_path / "nope.txt")
        assert h is None

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")
        assert compute_file_sha256(f1) != compute_file_sha256(f2)
