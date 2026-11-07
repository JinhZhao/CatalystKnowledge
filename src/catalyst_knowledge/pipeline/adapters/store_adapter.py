"""Adapter for store01_canonical.py — Canonical store writing.

Wraps CanonicalStore from the existing script.
Optionally persists VLM figure science records with CANDIDATE isolation.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)

_module = None


def _load_module():
    global _module
    if _module is not None:
        return _module
    project_root = Path(__file__).parent.parent.parent.parent.parent
    script_path = project_root / "scripts" / "store01_canonical.py"
    if not script_path.exists():
        raise FileNotFoundError(f"store01_canonical.py not found at {script_path}")
    spec = importlib.util.spec_from_file_location("store01_canonical", script_path)
    _module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_module)
    return _module


def _persist_vlm_records(vlm_output_path: str, store_path: Path, document_id: str,
                         verification_output_path: str = "") -> dict:
    """Load VLM records and persist to store with CANDIDATE isolation.
    
    CANDIDATE records go to candidate_observations/ — never to verified_facts/.
    If verification output is provided, annotate records with verification status.
    Returns persistence statistics.
    """
    vlm_file = Path(vlm_output_path)
    if not vlm_file.exists():
        return {"vlm_store_error": f"VLM output not found: {vlm_file}"}
    
    try:
        with open(vlm_file, "r", encoding="utf-8") as f:
            vlm_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"vlm_store_error": f"VLM output malformed: {e}"}
    
    results = vlm_data.get("results", [])
    all_records = []
    for result in results:
        all_records.extend(result.get("records", []))
    
    if not all_records:
        return {"vlm_stored": 0, "vlm_candidate": 0, "vlm_verified": 0}
    
    ev_verdicts = {}
    if verification_output_path:
        ev_file = Path(verification_output_path)
        if ev_file.exists():
            try:
                with open(ev_file, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                ev_verdicts = ev_data.get("per_record_verdicts", {})
            except Exception:
                pass

    vlm_records_dir = store_path / "vlm_records"
    vlm_records_dir.mkdir(parents=True, exist_ok=True)
    
    candidate_records = []
    verified_records = []
    review_records = []
    
    for rec in all_records:
        quality_state = rec.get("quality_state", "CANDIDATE")
        record_id = rec["record_id"]
        
        if record_id in ev_verdicts:
            rec["evidence_verification_verdict"] = ev_verdicts[record_id]
            rec["evidence_verification_applied"] = True
        else:
            rec["evidence_verification_applied"] = False
        
        rec_path = vlm_records_dir / f"{record_id}.json"
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
        
        if quality_state == "CANDIDATE":
            candidate_records.append(record_id)
        elif quality_state == "VERIFIED":
            verified_records.append(record_id)
        elif quality_state == "NEEDS_REVIEW":
            review_records.append(record_id)
    
    candidate_dir = store_path / "candidate_observations"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_index = {
        "source": "VLM Figure Science Adapter",
        "document_id": document_id,
        "records": candidate_records,
        "count": len(candidate_records),
        "note": "CANDIDATE records — not verified, not in verified_facts",
    }
    with open(candidate_dir / "candidate_index.json", "w", encoding="utf-8") as f:
        json.dump(candidate_index, f, indent=2, ensure_ascii=False)
    
    verified_dir = store_path / "verified_facts"
    verified_dir.mkdir(parents=True, exist_ok=True)
    verified_file = verified_dir / "verified_facts.json"
    existing_verified = {"records": [], "count": 0}
    if verified_file.exists():
        with open(verified_file, "r", encoding="utf-8") as f:
            existing_verified = json.load(f)
    existing_verified["note"] = "VLM CANDIDATE records must NOT enter this set"
    with open(verified_file, "w", encoding="utf-8") as f:
        json.dump(existing_verified, f, indent=2, ensure_ascii=False)
    
    if review_records:
        review_dir = store_path / "needs_review"
        review_dir.mkdir(parents=True, exist_ok=True)
        review_index = {
            "source": "VLM Figure Science Adapter",
            "document_id": document_id,
            "records": review_records,
            "count": len(review_records),
        }
        with open(review_dir / "review_index.json", "w", encoding="utf-8") as f:
            json.dump(review_index, f, indent=2, ensure_ascii=False)
    
    logger.info(
        "[%s] VLM store: %d total, %d candidate, %d verified, %d review",
        document_id, len(all_records), len(candidate_records),
        len(verified_records), len(review_records),
    )
    
    return {
        "vlm_stored": len(all_records),
        "vlm_candidate": len(candidate_records),
        "vlm_verified": len(verified_records),
        "vlm_review": len(review_records),
        "vlm_candidate_isolation": True,
    }


def _persist_table_records(table_science_output_path: str, store_path: Path, document_id: str,
                           verification_output_path: str = "") -> dict:
    """Load table science records and persist to store.

    Table records are stored separately from VLM records.
    Defensively injects document_id if missing (FINDING-R2-001 fix).
    Ensures record_id uniqueness.
    Annotates with EV verification verdicts if available.
    Returns persistence statistics.
    """
    table_file = Path(table_science_output_path)
    if not table_file.exists():
        return {"table_store_error": f"Table science output not found: {table_file}"}

    try:
        with open(table_file, "r", encoding="utf-8") as f:
            table_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"table_store_error": f"Table science output malformed: {e}"}

    all_records = table_data.get("records", [])

    if not all_records:
        return {"table_stored": 0}

    ev_verdicts = {}
    if verification_output_path:
        ev_file = Path(verification_output_path)
        if ev_file.exists():
            try:
                with open(ev_file, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                ev_verdicts = ev_data.get("per_record_verdicts", {})
            except Exception:
                pass

    table_records_dir = store_path / "table_records"
    table_records_dir.mkdir(parents=True, exist_ok=True)

    stored_ids = []
    for rec in all_records:
        # FINDING-R2-001 fix: defensively inject document_id
        if not rec.get("document_id"):
            rec["document_id"] = document_id

        # Ensure record_id present
        record_id = rec.get("record_id", "")
        if not record_id:
            table_id = rec.get("table_id", "unknown")
            row_idx = rec.get("row_idx", 0)
            col_idx = rec.get("col_idx", 0)
            record_id = f"TABLE-{table_id}-R{row_idx}C{col_idx}"
            rec["record_id"] = record_id

        # Annotate with EV verdict if available
        if record_id in ev_verdicts:
            rec["evidence_verification_verdict"] = ev_verdicts[record_id]
            rec["evidence_verification_applied"] = True
        else:
            rec["evidence_verification_applied"] = False

        rec["store_version"] = "007-R3"
        rec["store_timestamp"] = str(datetime.now(timezone.utc))

        rec_path = table_records_dir / f"{record_id}.json"
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)

        stored_ids.append(record_id)

    logger.info(
        "[%s] Table store: %d records",
        document_id, len(all_records),
    )

    return {
        "table_stored": len(all_records),
        "table_record_ids": stored_ids,
    }


def run_canonical_store(
    document_id: str,
    qa_report_path: str = "",
    extraction_output_path: str = "",
    store_dir: str = "",
    vlm_figure_science_output_path: str = "",
    evidence_verification_output_path: str = "",
    table_science_output_path: str = "",
    **kwargs,
) -> dict:
    """Pipeline-callable canonical store entry point."""
    mod = _load_module()

    store_path = Path(store_dir)
    store_path.mkdir(parents=True, exist_ok=True)

    try:
        store = mod.CanonicalStore(store_path)
    except Exception as e:
        return {
            "document_id": document_id,
            "store_path": str(store_path),
            "store_status": "FAILED",
            "error": f"CanonicalStore init failed: {e}",
        }

    if qa_report_path:
        qa_file = Path(qa_report_path)
        if qa_file.exists():
            try:
                with open(qa_file, "r", encoding="utf-8") as f:
                    qa_data = json.load(f)
                qa_status = qa_data.get("qa_status", qa_data.get("overall_status", ""))
                if qa_status == "FAILED":
                    logger.warning("[%s] QA status is FAILED — blocking Store write", document_id)
                    return {
                        "document_id": document_id,
                        "store_path": str(store_path),
                        "store_status": "BLOCKED",
                        "error": f"QA gate failed (qa_status={qa_status}). Records not written to Store.",
                        "qa_report_path": qa_report_path,
                    }
            except Exception as e:
                logger.warning("[%s] Could not read QA report: %s", document_id, e)

    metadata = {
        "document_id": document_id,
        "source": "pipeline_phase3",
        "qa_report_path": qa_report_path,
        "extraction_output_path": extraction_output_path,
    }
    save_ok = store.save_document(document_id, metadata)
    if not save_ok:
        logger.info("[%s] Document already in store (idempotent skip)", document_id)

    extraction_dir = Path(extraction_output_path) if extraction_output_path else None
    truncation_blocked_count = 0
    if extraction_dir and extraction_dir.exists():
        for jf in extraction_dir.glob("*_extracted.json"):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Truncation guard: refuse to persist extractions whose LLM output
                # was cut off at max_tokens. Incomplete JSON must not enter the
                # Canonical Store as if it were a successful extraction.
                has_truncation = bool(data.get("truncation_error"))
                if not has_truncation:
                    for dim_data in data.get("dimensions", {}).values():
                        if isinstance(dim_data, dict) and dim_data.get("truncation_error"):
                            has_truncation = True
                            break
                        for chunk in (dim_data.get("chunks") or []):
                            if isinstance(chunk, dict) and chunk.get("finish_reason") == "length":
                                has_truncation = True
                                break
                        if has_truncation:
                            break

                if has_truncation:
                    truncation_blocked_count += 1
                    logger.error(
                        "[%s] BLOCKED: extraction %s contains truncation_error — "
                        "refusing to write to Canonical Store",
                        document_id, jf.name,
                    )
                    continue

                store.save_extraction(document_id, {
                    "source_file": str(jf),
                    "data": data,
                })
            except Exception as e:
                logger.warning("[%s] Failed to save extraction %s: %s", document_id, jf.name, e)

    vlm_store_stats = {}
    vlm_output_path = vlm_figure_science_output_path or kwargs.get("vlm_output_path", "")
    ev_output_path = evidence_verification_output_path or kwargs.get("verification_output_path", "")
    if vlm_output_path:
        logger.info("[%s] Persisting VLM records to store: %s", document_id, vlm_output_path)
        vlm_store_stats = _persist_vlm_records(vlm_output_path, store_path, document_id, ev_output_path)

    table_store_stats = {}
    table_output_path = table_science_output_path or kwargs.get("table_science_output_path", "")
    if table_output_path:
        logger.info("[%s] Persisting table science records to store: %s", document_id, table_output_path)
        table_store_stats = _persist_table_records(table_output_path, store_path, document_id, ev_output_path)

    stats = store.get_statistics()

    output = {
        "document_id": document_id,
        "store_path": str(store_path),
        "store_status": "PASS",
        "statistics": stats,
        "truncation_blocked_count": truncation_blocked_count,
    }
    if truncation_blocked_count > 0:
        output["store_status"] = "BLOCKED"
        output["truncation_error"] = (
            f"{truncation_blocked_count} extraction file(s) contained "
            f"truncation_error — refused to write to Canonical Store"
        )
        logger.error(
            "[%s] Store write BLOCKED: %d extraction(s) truncated",
            document_id, truncation_blocked_count,
        )
    output.update(vlm_store_stats)
    output.update(table_store_stats)
    return output


def create_store_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for canonical store writing.
    
    Dependencies include vlm_figure_science, evidence_verification, and table_science as soft dependencies:
    - When VLM is enabled, VLM records are persisted with CANDIDATE isolation
    - When EvidenceVerifier runs, verification verdicts are annotated on stored records
    - When table_science runs, table records are persisted alongside VLM records
    - When any is disabled, store behavior is unchanged for available data
    """
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("canonical_store", {})

    adapter = StageAdapter(
        stage_name="canonical_store",
        version="2.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=[
                "qa_report_path",
                "extraction_output_path",
                "vlm_figure_science_output_path",
                "evidence_verification_output_path",
                "table_science_output_path",
            ],
        ),
        output_contract=DataContract(
            required_outputs=["store_path", "store_status"],
            optional_outputs=[
                "vlm_stored", "vlm_candidate", "vlm_candidate_isolation",
                "table_stored", "table_record_ids",
            ],
        ),
        dependencies=["quality_gate", "vlm_figure_science", "evidence_verification", "table_science"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 30),
    )

    store_dir = paths.get("pipeline_runs", "") + "/canonical_store"

    adapter.set_function(
        run_canonical_store,
        store_dir=store_dir,
    )
    return adapter
