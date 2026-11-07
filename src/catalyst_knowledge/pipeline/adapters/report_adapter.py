"""Adapter for single_doc_report_generator.py — Report generation.

Wraps generate_single_doc_report() from the existing script.
Optionally includes VLM figure science records in the report.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from collections import Counter
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
    script_path = project_root / "scripts" / "single_doc_report_generator.py"
    if not script_path.exists():
        raise FileNotFoundError(f"single_doc_report_generator.py not found at {script_path}")
    spec = importlib.util.spec_from_file_location("single_doc_report_generator", script_path)
    _module = importlib.util.module_from_spec(spec)
    old_path = sys.path.copy()
    sys.path.insert(0, str(project_root / "scripts"))
    try:
        spec.loader.exec_module(_module)
    finally:
        sys.path = old_path
    return _module


def _consume_vlm_from_store(store_path: str, document_id: str,
                             verification_output_path: str = "") -> dict:
    """Load VLM records from Store's vlm_records/ directory (chain of custody).
    
    This is the authoritative data source for reports — NOT the raw VLM file.
    Records read from Store include all annotations (verification verdicts, etc.).
    
    Returns a dict with VLM report data organized by quality state.
    If store_path is missing or invalid, returns error dict.
    """
    store = Path(store_path)
    vlm_records_dir = store / "vlm_records"
    
    if not vlm_records_dir.exists():
        return {"vlm_report_error": f"Store vlm_records directory not found: {vlm_records_dir}"}
    
    all_records = []
    for rec_file in sorted(vlm_records_dir.glob("*.json")):
        try:
            with open(rec_file, "r", encoding="utf-8") as f:
                rec = json.load(f)
            if rec.get("document_id") == document_id:
                all_records.append(rec)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    
    if not all_records:
        return {"vlm_report_error": f"No VLM records found in Store for document {document_id}"}
    
    verified = [r for r in all_records if r.get("quality_state") == "VERIFIED"]
    candidate = [r for r in all_records if r.get("quality_state") == "CANDIDATE"]
    needs_review = [r for r in all_records if r.get("quality_state") == "NEEDS_REVIEW"]
    rejected = [r for r in all_records if r.get("quality_state") == "REJECTED"]
    
    by_figure = dict(Counter(r.get("figure_id") for r in all_records))
    by_evidence = dict(Counter(r.get("evidence_type") for r in all_records))
    by_execution = dict(Counter(r.get("execution_type", "UNKNOWN") for r in all_records))
    
    vlm_sections = {
        "verified_facts": {
            "count": len(verified),
            "note": "VLM-only records cannot be VERIFIED without independent validation",
            "records": verified,
        },
        "candidate_observations": {
            "count": len(candidate),
            "note": "VLM-generated observations awaiting independent verification",
            "records": candidate,
        },
        "needs_review": {
            "count": len(needs_review),
            "note": "Low confidence or unresolved records requiring human review",
            "records": needs_review,
        },
        "rejected": {
            "count": len(rejected),
            "note": "Records rejected due to contradictions or structural failures",
            "records": rejected,
        },
    }
    
    result = {
        "vlm_total": len(all_records),
        "vlm_sections": vlm_sections,
        "vlm_summary": {
            "by_figure": by_figure,
            "by_evidence_type": by_evidence,
            "by_execution_type": by_execution,
        },
        "data_source": "canonical_store",
        "store_path": str(store),
    }
    
    if verification_output_path:
        ev_file = Path(verification_output_path)
        if ev_file.exists():
            try:
                with open(ev_file, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                result["evidence_verification"] = {
                    "status": ev_data.get("verification_status", "UNKNOWN"),
                    "mode": ev_data.get("verification_mode", "UNKNOWN"),
                    "records_verified": ev_data.get("vlm_records_verified", 0),
                    "total_checks": ev_data.get("total_checks", 0),
                    "pass_count": ev_data.get("pass_count", 0),
                    "fail_count": ev_data.get("fail_count", 0),
                    "warn_count": ev_data.get("warn_count", 0),
                    "per_record_verdicts": ev_data.get("per_record_verdicts", {}),
                    "important_note": ev_data.get("important_note", ""),
                }
            except Exception as e:
                result["evidence_verification_error"] = str(e)

    return result


def _consume_table_from_store(store_path: str, document_id: str,
                               verification_output_path: str = "") -> dict:
    """Load table records from Store's table_records/ directory (chain of custody).

    Returns a dict with table report data organized by quality state.
    """
    store = Path(store_path)
    table_records_dir = store / "table_records"

    if not table_records_dir.exists():
        return {}

    all_records = []
    for rec_file in sorted(table_records_dir.glob("*.json")):
        try:
            with open(rec_file, "r", encoding="utf-8") as f:
                rec = json.load(f)
            if rec.get("document_id") == document_id:
                all_records.append(rec)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

    if not all_records:
        return {}

    candidate = [r for r in all_records if r.get("quality_state") == "CANDIDATE"]
    needs_review = [r for r in all_records if r.get("quality_state") == "NEEDS_REVIEW"]
    rejected = [r for r in all_records if r.get("quality_state") == "REJECTED"]

    by_table = dict(Counter(r.get("table_id") for r in all_records))

    table_sections = {
        "candidate_observations": {
            "count": len(candidate),
            "note": "Table-generated observations awaiting independent verification",
            "records": candidate,
        },
        "needs_review": {
            "count": len(needs_review),
            "note": "Low confidence or unresolved table records requiring human review",
            "records": needs_review,
        },
        "rejected": {
            "count": len(rejected),
            "note": "Table records rejected due to contradictions or structural failures",
            "records": rejected,
        },
    }

    result = {
        "table_total": len(all_records),
        "table_sections": table_sections,
        "table_summary": {
            "by_table": by_table,
        },
        "data_source": "canonical_store",
        "store_path": str(store),
    }

    if verification_output_path:
        ev_file = Path(verification_output_path)
        if ev_file.exists():
            try:
                with open(ev_file, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                result["evidence_verification"] = {
                    "status": ev_data.get("verification_status", "UNKNOWN"),
                    "mode": ev_data.get("verification_mode", "UNKNOWN"),
                    "table_records_verified": ev_data.get("table_records_verified", 0),
                    "total_records_verified": ev_data.get("total_records_verified", 0),
                    "total_checks": ev_data.get("total_checks", 0),
                    "pass_count": ev_data.get("pass_count", 0),
                    "fail_count": ev_data.get("fail_count", 0),
                    "warn_count": ev_data.get("warn_count", 0),
                    "important_note": ev_data.get("important_note", ""),
                }
            except Exception as e:
                result["evidence_verification_error"] = str(e)

    return result


def _consume_vlm_for_report(vlm_output_path: str, document_id: str,
                             verification_output_path: str = "") -> dict:
    """Load VLM records and prepare report sections.
    
    DEPRECATED: Use _consume_vlm_from_store() for chain of custody.
    This function reads from raw VLM file — only used as fallback when Store is unavailable.
    
    Returns a dict with VLM report data organized by quality state.
    If verification output is provided, includes verification summary.
    """
    vlm_file = Path(vlm_output_path)
    if not vlm_file.exists():
        return {"vlm_report_error": f"VLM output not found: {vlm_file}"}
    
    try:
        with open(vlm_file, "r", encoding="utf-8") as f:
            vlm_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"vlm_report_error": f"VLM output malformed: {e}"}
    
    results = vlm_data.get("results", [])
    all_records = []
    for result in results:
        all_records.extend(result.get("records", []))
    
    if not all_records:
        return {"vlm_total": 0, "vlm_sections": {}}
    
    verified = [r for r in all_records if r.get("quality_state") == "VERIFIED"]
    candidate = [r for r in all_records if r.get("quality_state") == "CANDIDATE"]
    needs_review = [r for r in all_records if r.get("quality_state") == "NEEDS_REVIEW"]
    rejected = [r for r in all_records if r.get("quality_state") == "REJECTED"]
    
    by_figure = dict(Counter(r.get("figure_id") for r in all_records))
    by_evidence = dict(Counter(r.get("evidence_type") for r in all_records))
    by_execution = dict(Counter(r.get("execution_type", "UNKNOWN") for r in all_records))
    
    vlm_sections = {
        "verified_facts": {
            "count": len(verified),
            "note": "VLM-only records cannot be VERIFIED without independent validation",
            "records": verified,
        },
        "candidate_observations": {
            "count": len(candidate),
            "note": "VLM-generated observations awaiting independent verification",
            "records": candidate,
        },
        "needs_review": {
            "count": len(needs_review),
            "note": "Low confidence or unresolved records requiring human review",
            "records": needs_review,
        },
        "rejected": {
            "count": len(rejected),
            "note": "Records rejected due to contradictions or structural failures",
            "records": rejected,
        },
    }
    
    result = {
        "vlm_total": len(all_records),
        "vlm_sections": vlm_sections,
        "vlm_summary": {
            "by_figure": by_figure,
            "by_evidence_type": by_evidence,
            "by_execution_type": by_execution,
        },
        "data_source": "raw_vlm_file",
    }
    
    if verification_output_path:
        ev_file = Path(verification_output_path)
        if ev_file.exists():
            try:
                with open(ev_file, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                result["evidence_verification"] = {
                    "status": ev_data.get("verification_status", "UNKNOWN"),
                    "mode": ev_data.get("verification_mode", "UNKNOWN"),
                    "records_verified": ev_data.get("vlm_records_verified", 0),
                    "total_checks": ev_data.get("total_checks", 0),
                    "pass_count": ev_data.get("pass_count", 0),
                    "fail_count": ev_data.get("fail_count", 0),
                    "warn_count": ev_data.get("warn_count", 0),
                    "per_record_verdicts": ev_data.get("per_record_verdicts", {}),
                    "important_note": ev_data.get("important_note", ""),
                }
            except Exception as e:
                result["evidence_verification_error"] = str(e)
    
    return result


def run_report_generation(
    document_id: str,
    store_path: str = "",
    output_dir: str = "",
    vlm_figure_science_output_path: str = "",
    table_science_output_path: str = "",
    evidence_verification_output_path: str = "",
    qa_report_path: str = "",
    **kwargs,
) -> dict:
    """Pipeline-callable report generation entry point.

    Chain of custody: VLM and Table records are read from Store (not raw files).
    When store_path is provided and VLM/Table data was produced, Store is authoritative.
    When Store is missing/failed but VLM was expected, report status = BLOCKED.
    """
    mod = _load_module()

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    vlm_report_data = {}
    vlm_output_path = vlm_figure_science_output_path or kwargs.get("vlm_output_path", "")
    ev_output_path = evidence_verification_output_path or kwargs.get("verification_output_path", "")

    if vlm_output_path:
        if store_path:
            logger.info("[%s] Consuming VLM records from Store: %s", document_id, store_path)
            vlm_report_data = _consume_vlm_from_store(store_path, document_id, ev_output_path)
            if "vlm_report_error" in vlm_report_data:
                logger.error("[%s] Store-based VLM consumption failed: %s",
                             document_id, vlm_report_data["vlm_report_error"])
                report_file = out_path / f"{document_id}_knowledge_report.json"
                error_report = {
                    "document_id": document_id,
                    "report_status": "BLOCKED",
                    "report_path": str(report_file),
                    "error": vlm_report_data["vlm_report_error"],
                    "chain_of_custody": "store_required",
                }
                try:
                    with open(report_file, "w", encoding="utf-8") as f:
                        json.dump(error_report, f, indent=2, ensure_ascii=False, default=str)
                except Exception:
                    pass
                return {
                    "document_id": document_id,
                    "report_path": str(report_file),
                    "report_status": "BLOCKED",
                    "error": vlm_report_data["vlm_report_error"],
                    "chain_of_custody": "store_required",
                }
            logger.info("[%s] VLM report from Store: %d total records",
                        document_id, vlm_report_data.get("vlm_total", 0))
        else:
            logger.warning("[%s] No store_path — falling back to raw VLM file (chain of custody gap)",
                           document_id)
            vlm_report_data = _consume_vlm_for_report(vlm_output_path, document_id, ev_output_path)
            logger.info("[%s] VLM report from raw file: %d total records",
                        document_id, vlm_report_data.get("vlm_total", 0))

    table_report_data = {}
    table_output_path = table_science_output_path or kwargs.get("table_output_path", "")
    if table_output_path and store_path:
        logger.info("[%s] Consuming Table records from Store: %s", document_id, store_path)
        table_report_data = _consume_table_from_store(store_path, document_id, ev_output_path)
        if table_report_data:
            logger.info("[%s] Table report from Store: %d total records",
                        document_id, table_report_data.get("table_total", 0))

    qa_timestamp = ""
    if qa_report_path:
        qa_file = Path(qa_report_path)
        if qa_file.exists():
            try:
                with open(qa_file, "r", encoding="utf-8") as f:
                    qa_data = json.load(f)
                qa_timestamp = qa_data.get("qa_timestamp", "")
            except Exception:
                pass

    try:
        if hasattr(mod, "generate_single_doc_report"):
            report_data, report_path = mod.generate_single_doc_report(
                document_id,
                output_dir=out_path,
            )
            if vlm_report_data:
                report_data["vlm_science_records"] = vlm_report_data
            if table_report_data:
                report_data["table_science_records"] = table_report_data
            if qa_timestamp:
                report_data["qa_timestamp"] = qa_timestamp
            report_file = out_path / f"{document_id}_knowledge_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            return {
                "document_id": document_id,
                "report_path": str(report_file),
                "report_status": "PASS",
                "report_data_keys": list(report_data.keys()) if isinstance(report_data, dict) else [],
                "vlm_total": vlm_report_data.get("vlm_total", 0),
                "table_total": table_report_data.get("table_total", 0),
            }
        else:
            logger.warning("[%s] generate_single_doc_report not found, generating unified report", document_id)
            report_data = _generate_unified_report(document_id, store_path, vlm_report_data, table_report_data, qa_timestamp)
            report_file = out_path / f"{document_id}_knowledge_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            return {
                "document_id": document_id,
                "report_path": str(report_file),
                "report_status": "PASS",
                "report_data_keys": list(report_data.keys()),
                "generation_mode": "unified" if (vlm_report_data or table_report_data) else "minimal",
                "vlm_total": vlm_report_data.get("vlm_total", 0),
                "table_total": table_report_data.get("table_total", 0),
            }
    except Exception as e:
        logger.error("[%s] Report generation failed: %s", document_id, e)
        report_data = _generate_unified_report(document_id, store_path, vlm_report_data, table_report_data, qa_timestamp)
        report_data["generation_error"] = str(e)
        report_file = out_path / f"{document_id}_knowledge_report.json"
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            return {
                "document_id": document_id,
                "report_path": str(report_file),
                "report_status": "PARTIAL",
                "error": str(e),
                "vlm_total": vlm_report_data.get("vlm_total", 0),
                "table_total": table_report_data.get("table_total", 0),
            }
        except Exception:
            return {
                "document_id": document_id,
                "report_path": str(out_path),
                "report_status": "FAILED",
                "error": str(e),
            }


def _generate_unified_report(document_id: str, store_path: str,
                              vlm_report_data: dict, table_report_data: dict,
                              qa_timestamp: str = "") -> dict:
    """Generate a unified report that includes both VLM and Table science records."""
    store = Path(store_path) if store_path else None
    report = {
        "document_id": document_id,
        "report_version": "3.0.0",
        "generation_mode": "unified" if (vlm_report_data or table_report_data) else "minimal",
        "qa_timestamp": qa_timestamp,
        "sections": {},
    }

    if store:
        doc_file = store / "documents" / f"{document_id}.json"
        if doc_file.exists():
            with open(doc_file, "r", encoding="utf-8") as f:
                report["sections"]["document_metadata"] = json.load(f)

        ext_dir = store / "extractions"
        if ext_dir.exists():
            extractions = {}
            for ef in ext_dir.glob(f"{document_id}*"):
                with open(ef, "r", encoding="utf-8") as f:
                    extractions[ef.stem] = json.load(f)
            if extractions:
                report["sections"]["extractions"] = extractions

    if vlm_report_data:
        report["sections"]["vlm_science_records"] = vlm_report_data
    if table_report_data:
        report["sections"]["table_science_records"] = table_report_data

    return report


def _generate_vlm_aware_report(document_id: str, store_path: str, vlm_report_data: dict) -> dict:
    """Generate a report that includes VLM science records.

    DEPRECATED: Use _generate_unified_report() for new reports.
    """
    store = Path(store_path) if store_path else None
    report = {
        "document_id": document_id,
        "report_version": "2.1.0",
        "generation_mode": "vlm_aware" if vlm_report_data else "minimal",
        "sections": {},
    }

    if store:
        doc_file = store / "documents" / f"{document_id}.json"
        if doc_file.exists():
            with open(doc_file, "r", encoding="utf-8") as f:
                report["sections"]["document_metadata"] = json.load(f)

        ext_dir = store / "extractions"
        if ext_dir.exists():
            extractions = {}
            for ef in ext_dir.glob(f"{document_id}*"):
                with open(ef, "r", encoding="utf-8") as f:
                    extractions[ef.stem] = json.load(f)
            if extractions:
                report["sections"]["extractions"] = extractions

    if vlm_report_data:
        report["sections"]["vlm_science_records"] = vlm_report_data

    return report


def create_report_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for report generation.

    Dependencies include vlm_figure_science, table_science, and evidence_verification:
    - When VLM is enabled, report includes VLM science record sections
    - When table_science runs, report includes Table science record sections
    - When EvidenceVerifier runs, report includes verification conclusions
    """
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("report_generation", {})

    adapter = StageAdapter(
        stage_name="report_generation",
        version="3.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=[
                "store_path",
                "vlm_figure_science_output_path",
                "table_science_output_path",
                "evidence_verification_output_path",
                "qa_report_path",
            ],
        ),
        output_contract=DataContract(
            required_outputs=["report_path", "report_status"],
            optional_outputs=[
                "vlm_total", "table_total", "generation_mode", "data_source",
            ],
        ),
        dependencies=["canonical_store", "vlm_figure_science", "table_science", "evidence_verification"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 120),
    )

    output_dir = paths.get("pipeline_runs", "") + "/reports"

    adapter.set_function(
        run_report_generation,
        output_dir=output_dir,
    )
    return adapter
