"""RunManifest — pipeline execution traceability.

Records every pipeline run with:
- Unique run_id
- Document identity and input file hashes
- Pipeline/Schema/Prompt versions
- Model configuration
- Stage execution sequence with timing and status
- Output file hashes
- Error diagnostics

Supports JSON persistence, incremental updates, and replay.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StageRecord:
    """Record of a single stage execution."""

    def __init__(self, stage_name: str):
        self.stage_name = stage_name
        self.status: str = "PENDING"  # PENDING / RUNNING / SUCCESS / FAILED / SKIPPED / NOT_IMPLEMENTED / BLOCKED
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.duration_seconds: Optional[float] = None
        self.input_files: list[str] = []
        self.input_hashes: dict[str, str] = {}
        self.output_files: list[str] = []
        self.output_hashes: dict[str, str] = {}
        self.error_message: Optional[str] = None
        self.error_traceback: Optional[str] = None
        self.skip_reason: Optional[str] = None
        self.metadata: dict[str, Any] = {}

    def mark_start(self):
        self.status = "RUNNING"
        self.start_time = datetime.now().isoformat()

    def mark_success(self):
        self.status = "SUCCESS"
        self.end_time = datetime.now().isoformat()
        if self.start_time:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
            self.duration_seconds = (end - start).total_seconds()

    def mark_failed(self, error: str, traceback_str: str = ""):
        self.status = "FAILED"
        self.end_time = datetime.now().isoformat()
        self.error_message = error
        self.error_traceback = traceback_str
        if self.start_time:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
            self.duration_seconds = (end - start).total_seconds()

    def mark_skipped(self, reason: str):
        self.status = "SKIPPED"
        self.skip_reason = reason

    def mark_not_implemented(self, reason: str = ""):
        """Mark stage as a stub that is not yet implemented.
        
        Distinct from mark_failed: the code ran correctly but the module
        is a placeholder. Pipeline should NOT treat this as a crash.
        """
        self.status = "NOT_IMPLEMENTED"
        self.skip_reason = reason or "Module not yet implemented (stub)"
        self.end_time = datetime.now().isoformat()
        if self.start_time:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
            self.duration_seconds = (end - start).total_seconds()

    def mark_blocked(self, reason: str = ""):
        """Mark stage as blocked by an unresolvable dependency.
        
        A required dependency is NOT_IMPLEMENTED or FAILED,
        so this stage cannot produce valid output.
        """
        self.status = "BLOCKED"
        self.skip_reason = reason or "Blocked by upstream dependency"
        self.end_time = datetime.now().isoformat()
        if self.start_time:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
            self.duration_seconds = (end - start).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "input_files": self.input_files,
            "input_hashes": self.input_hashes,
            "output_files": self.output_files,
            "output_hashes": self.output_hashes,
            "error_message": self.error_message,
            "error_traceback": self.error_traceback,
            "skip_reason": self.skip_reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageRecord:
        rec = cls(data["stage_name"])
        rec.status = data.get("status", "PENDING")
        rec.start_time = data.get("start_time")
        rec.end_time = data.get("end_time")
        rec.duration_seconds = data.get("duration_seconds")
        rec.input_files = data.get("input_files", [])
        rec.input_hashes = data.get("input_hashes", {})
        rec.output_files = data.get("output_files", [])
        rec.output_hashes = data.get("output_hashes", {})
        rec.error_message = data.get("error_message")
        rec.error_traceback = data.get("error_traceback")
        rec.skip_reason = data.get("skip_reason")
        rec.metadata = data.get("metadata", {})
        return rec


class RunManifest:
    """Pipeline execution manifest with JSON persistence."""

    def __init__(
        self,
        document_id: str,
        manifest_dir: Path | str,
        pipeline_version: str = "1.0.0",
        schema_version: str = "1.0.0",
        prompt_version: str = "1.0.0",
    ):
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.document_id = document_id
        self.pipeline_version = pipeline_version
        self.schema_version = schema_version
        self.prompt_version = prompt_version
        self.model_name: str = ""
        self.config_hash: str = ""
        self.created_at: str = datetime.now().isoformat()
        self.updated_at: str = self.created_at
        self.status: str = "INITIALIZED"  # INITIALIZED / RUNNING / COMPLETED / FAILED
        self.input_files: list[str] = []
        self.input_hashes: dict[str, str] = {}
        self.input_attachments: list[str] = []
        self.stages: dict[str, StageRecord] = {}
        self.stage_order: list[str] = []
        self.error_message: Optional[str] = None
        self.metadata: dict[str, Any] = {}

        self._manifest_dir = Path(manifest_dir)
        self._manifest_dir.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_file(self) -> Path:
        return self._manifest_dir / f"{self.run_id}.json"

    def set_model(self, model_name: str):
        self.model_name = model_name

    def set_config_hash(self, config_hash: str):
        self.config_hash = config_hash

    def add_input_file(self, file_path: str, compute_hash: bool = True):
        self.input_files.append(file_path)
        if compute_hash:
            h = compute_file_sha256(Path(file_path))
            if h:
                self.input_hashes[file_path] = h

    def add_input_attachment(self, file_path: str):
        self.input_attachments.append(file_path)

    def add_stage(self, stage_name: str) -> StageRecord:
        rec = StageRecord(stage_name)
        self.stages[stage_name] = rec
        if stage_name not in self.stage_order:
            self.stage_order.append(stage_name)
        return rec

    def get_stage(self, stage_name: str) -> Optional[StageRecord]:
        return self.stages.get(stage_name)

    def mark_running(self):
        self.status = "RUNNING"
        self.updated_at = datetime.now().isoformat()

    def mark_completed(self):
        self.status = "COMPLETED"
        self.updated_at = datetime.now().isoformat()

    def mark_failed(self, error: str):
        self.status = "FAILED"
        self.error_message = error
        self.updated_at = datetime.now().isoformat()

    def save(self) -> Path:
        """Persist manifest to JSON file. Returns file path."""
        data = self.to_dict()
        path = self.manifest_file
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Manifest saved: %s", path)
        return path

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "document_id": self.document_id,
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "model_name": self.model_name,
            "config_hash": self.config_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "input_files": self.input_files,
            "input_hashes": self.input_hashes,
            "input_attachments": self.input_attachments,
            "stage_order": self.stage_order,
            "stages": {name: rec.to_dict() for name, rec in self.stages.items()},
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def load(cls, manifest_path: Path | str) -> RunManifest:
        """Load manifest from JSON file."""
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Manifest file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        manifest = cls.__new__(cls)
        manifest.run_id = data["run_id"]
        manifest.document_id = data["document_id"]
        manifest.pipeline_version = data.get("pipeline_version", "1.0.0")
        manifest.schema_version = data.get("schema_version", "1.0.0")
        manifest.prompt_version = data.get("prompt_version", "1.0.0")
        manifest.model_name = data.get("model_name", "")
        manifest.config_hash = data.get("config_hash", "")
        manifest.created_at = data.get("created_at", "")
        manifest.updated_at = data.get("updated_at", "")
        manifest.status = data.get("status", "INITIALIZED")
        manifest.input_files = data.get("input_files", [])
        manifest.input_hashes = data.get("input_hashes", {})
        manifest.input_attachments = data.get("input_attachments", [])
        manifest.stage_order = data.get("stage_order", [])
        manifest.stages = {
            name: StageRecord.from_dict(rec_data)
            for name, rec_data in data.get("stages", {}).items()
        }
        manifest.error_message = data.get("error_message")
        manifest.metadata = data.get("metadata", {})
        manifest._manifest_dir = path.parent
        return manifest

    def get_summary(self) -> dict[str, Any]:
        """Return a concise summary of the run."""
        stage_summaries = []
        for name in self.stage_order:
            rec = self.stages.get(name)
            if rec:
                stage_summaries.append({
                    "stage": name,
                    "status": rec.status,
                    "duration_s": rec.duration_seconds,
                    "error": rec.error_message,
                })
        return {
            "run_id": self.run_id,
            "document_id": self.document_id,
            "status": self.status,
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "model_name": self.model_name,
            "stages": stage_summaries,
            "error_message": self.error_message,
        }


def compute_file_sha256(file_path: Path) -> Optional[str]:
    """Compute SHA256 hash of a file. Returns None if file doesn't exist."""
    if not file_path.exists():
        return None
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError) as e:
        logger.warning("Cannot hash file %s: %s", file_path, e)
        return None
