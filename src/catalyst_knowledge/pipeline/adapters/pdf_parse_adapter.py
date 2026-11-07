"""Adapter for batch_pdf_parse.py — PDF parsing via MinerU.

Wraps the existing batch_pdf_parse.py script to support:
- Single-document processing (vs batch)
- Config-driven paths
- Proper input/output recording
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)


def _find_doc_in_manifest(document_id: str, manifest_path: Path) -> Optional[dict]:
    """Find document entry in unified_test_manifest.json."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    for doc in manifest["documents"]:
        if doc["document_id"] == document_id:
            return doc
    return None


def _parse_single_pdf(
    document_id: str,
    pdf_path: str,
    output_base: str,
    timeout_seconds: int = 900,
) -> dict:
    """Parse a single PDF using magic-pdf CLI.

    Returns result dict with status, output_dir, processing_time, etc.
    """
    output_dir = Path(output_base) / f"{document_id}_batch"
    result = {
        "document_id": document_id,
        "file_path": pdf_path,
        "status": "UNKNOWN",
        "output_dir": str(output_dir),
        "processing_time": 0,
        "timestamp": datetime.now().isoformat(),
    }

    start_time = time.time()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = ["magic-pdf", "-p", pdf_path, "-o", str(output_dir), "-m", "auto"]
        logger.info("[%s] Executing: %s", document_id, " ".join(cmd))

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
        )

        result["processing_time"] = time.time() - start_time

        if proc.returncode == 0:
            result["status"] = "PASS"
            auto_dir = output_dir / "main" / "auto"
            if not auto_dir.exists():
                auto_dir = output_dir / "auto"
            if auto_dir.exists():
                result["md_count"] = len(list(auto_dir.glob("*.md")))
                result["json_count"] = len(list(auto_dir.glob("*.json")))
                result["content_list_path"] = str(
                    auto_dir / f"{document_id}_content_list.json"
                    if (auto_dir / f"{document_id}_content_list.json").exists()
                    else auto_dir / "main_content_list.json"
                )
        else:
            result["status"] = "FAILED"
            result["error"] = proc.stderr[:500] if proc.stderr else "Unknown error"

    except subprocess.TimeoutExpired:
        result["status"] = "TIMEOUT"
        result["error"] = f"Exceeded {timeout_seconds}s timeout"
        result["processing_time"] = time.time() - start_time
    except FileNotFoundError:
        result["status"] = "FAILED"
        result["error"] = "magic-pdf command not found"
        result["processing_time"] = time.time() - start_time
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        result["processing_time"] = time.time() - start_time

    return result


def _check_existing_output(document_id: str, output_base: str) -> bool:
    """Check if valid output already exists for this document."""
    base = Path(output_base)
    for out_dir in base.iterdir():
        if not out_dir.is_dir():
            continue
        if document_id in out_dir.name:
            md_files = list(out_dir.rglob("*.md"))
            if md_files:
                return True
    return False


def run_pdf_parse(
    document_id: str,
    manifest_path: str,
    output_base: str,
    timeout_seconds: int = 900,
    force: bool = False,
    **kwargs,
) -> dict:
    """Pipeline-callable PDF parse entry point.

    Args:
        document_id: Document to process
        manifest_path: Path to unified_test_manifest.json
        output_base: Path to mineru_output directory
        timeout_seconds: Per-PDF timeout
        force: Re-process even if output exists

    Returns:
        Dict with mineru_output_dir, parse_result, etc.
    """
    if not force and _check_existing_output(document_id, output_base):
        logger.info("[%s] Output already exists, skipping (use force=True to re-process)", document_id)
        return {
            "document_id": document_id,
            "mineru_output_dir": output_base,
            "parse_status": "SKIPPED",
            "skip_reason": "output_exists",
        }

    doc_entry = _find_doc_in_manifest(document_id, Path(manifest_path))
    if not doc_entry:
        return {
            "document_id": document_id,
            "mineru_output_dir": output_base,
            "parse_status": "FAILED",
            "error": f"Document '{document_id}' not found in manifest",
        }

    if doc_entry.get("signature_type") != "PDF":
        return {
            "document_id": document_id,
            "mineru_output_dir": output_base,
            "parse_status": "SKIPPED",
            "skip_reason": f"not_a_pdf ({doc_entry.get('signature_type')})",
        }

    result = _parse_single_pdf(
        document_id=document_id,
        pdf_path=doc_entry["file_path"],
        output_base=output_base,
        timeout_seconds=timeout_seconds,
    )

    return {
        "document_id": document_id,
        "mineru_output_dir": result["output_dir"],
        "parse_status": result["status"],
        "parse_result": result,
    }


def create_pdf_parse_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for PDF parsing.

    Args:
        config: Pipeline config dict (from ConfigLoader.config)

    Returns:
        Configured StageAdapter
    """
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("pdf_parse", {})

    adapter = StageAdapter(
        stage_name="pdf_parse",
        version="2.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=["manifest_path"],
            input_file_patterns=["*.pdf"],
        ),
        output_contract=DataContract(
            required_outputs=["mineru_output_dir", "parse_status"],
            output_file_patterns=["*content_list.json"],
        ),
        timeout_seconds=stage_cfg.get("timeout_seconds", 900),
    )

    manifest_path = paths.get("manifest", "")
    output_base = paths.get("mineru_output", "")

    adapter.set_function(
        run_pdf_parse,
        manifest_path=manifest_path,
        output_base=output_base,
        timeout_seconds=stage_cfg.get("timeout_seconds", 900),
    )

    return adapter
