"""Adapter for qa001_quality_gates.py — QA validation gates.

Wraps QAGateValidator from the existing script.
Consumes VLM figure science records AND table science records.
Reports unified Figure+Table QA with EV coverage requirements.
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
_vlm_module = None


def _load_module():
    global _module
    if _module is not None:
        return _module
    project_root = Path(__file__).parent.parent.parent.parent.parent
    script_path = project_root / "scripts" / "qa001_quality_gates.py"
    if not script_path.exists():
        raise FileNotFoundError(f"qa001_quality_gates.py not found at {script_path}")
    spec = importlib.util.spec_from_file_location("qa001_quality_gates", script_path)
    _module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_module)
    return _module


def _load_vlm_module():
    """Dynamically load 005-E VLM adapter for validation functions."""
    global _vlm_module
    if _vlm_module is not None:
        return _vlm_module
    project_root = Path(__file__).parent.parent.parent.parent.parent
    vlm_path = project_root / "runs" / "pipeline_001_fix" / "PIPELINE_005_E"
    if str(vlm_path) not in sys.path:
        sys.path.insert(0, str(vlm_path))
    try:
        import vlm_figure_science_adapter as mod
        _vlm_module = mod
        return _vlm_module
    except ImportError:
        logger.warning("VLM adapter module not available for QA consumption")
        return None


def _consume_vlm_records(vlm_output_path: str) -> dict:
    """Load and QA-validate VLM science records.

    Returns a dict with VLM QA results:
    - vlm_record_count: total records loaded
    - vlm_qa_passed: records passing QA gates (quality_state != REJECTED)
    - vlm_quality_states: distribution of quality states
    - vlm_no_auto_verify: True if no records were auto-VERIFIED
    """
    vlm_mod = _load_vlm_module()

    vlm_path = Path(vlm_output_path)
    if not vlm_path.exists():
        return {"vlm_error": f"VLM output not found: {vlm_path}"}
    try:
        with open(vlm_path, "r", encoding="utf-8") as f:
            vlm_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"vlm_error": f"VLM output malformed: {e}"}

    results = vlm_data.get("results", [])
    all_records = []
    for result in results:
        all_records.extend(result.get("records", []))

    if not all_records:
        return {
            "vlm_record_count": 0,
            "vlm_qa_passed": 0,
            "vlm_quality_states": {},
            "vlm_no_auto_verify": True,
        }

    quality_states = {}
    for rec in all_records:
        qs = rec.get("quality_state", "CANDIDATE")
        quality_states[qs] = quality_states.get(qs, 0) + 1

    no_auto_verify = quality_states.get("VERIFIED", 0) == 0

    vlm_qa_result = {}
    if vlm_mod and hasattr(vlm_mod, "validate_qa_gate_compatibility"):
        try:
            vlm_qa_result = vlm_mod.validate_qa_gate_compatibility(all_records)
        except Exception as e:
            logger.warning("VLM QA validation failed: %s", e)
            vlm_qa_result = {"verdict": "ERROR", "error": str(e)}

    return {
        "vlm_record_count": len(all_records),
        "vlm_qa_passed": sum(1 for r in all_records if r.get("quality_state") != "REJECTED"),
        "vlm_quality_states": quality_states,
        "vlm_no_auto_verify": no_auto_verify,
        "vlm_qa_validation": vlm_qa_result,
    }


def _consume_table_records(table_output_path: str) -> dict:
    """Load and QA-validate table science records.

    Returns a dict with Table QA results:
    - table_record_count: total records loaded
    - table_qa_passed: records passing QA gates (quality_state != REJECTED)
    - table_quality_states: distribution of quality states
    - table_no_auto_verify: True if no records were auto-VERIFIED
    """
    table_path = Path(table_output_path)
    if not table_path.exists():
        return {"table_error": f"Table output not found: {table_path}"}
    try:
        with open(table_path, "r", encoding="utf-8") as f:
            table_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"table_error": f"Table output malformed: {e}"}

    all_records = table_data.get("records", [])

    if not all_records:
        return {
            "table_record_count": 0,
            "table_qa_passed": 0,
            "table_quality_states": {},
            "table_no_auto_verify": True,
        }

    quality_states = {}
    for rec in all_records:
        qs = rec.get("quality_state", "CANDIDATE")
        quality_states[qs] = quality_states.get(qs, 0) + 1

    no_auto_verify = quality_states.get("VERIFIED", 0) == 0

    table_ids = set()
    for rec in all_records:
        tid = rec.get("table_id", "")
        if tid:
            table_ids.add(tid)

    return {
        "table_record_count": len(all_records),
        "table_qa_passed": sum(1 for r in all_records if r.get("quality_state") != "REJECTED"),
        "table_quality_states": quality_states,
        "table_no_auto_verify": no_auto_verify,
        "table_ids": sorted(table_ids),
    }


def _consume_evidence_verification(verification_output_path: str) -> dict:
    """Load EvidenceVerifier results for VLM and Table records.

    Returns verification summary including per-record verdicts and coverage stats.
    Supports both VLM-only and UNIFIED verification modes.
    """
    v_path = Path(verification_output_path)
    if not v_path.exists():
        return {"ev_error": f"Verification output not found: {v_path}"}
    try:
        with open(v_path, "r", encoding="utf-8") as f:
            ev_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"ev_error": f"Verification output malformed: {e}"}

    if "verification_status" in ev_data and ev_data["verification_status"] == "FAILED":
        return {"ev_error": ev_data.get("error", "Evidence verification failed")}

    return {
        "ev_status": ev_data.get("verification_status", "UNKNOWN"),
        "ev_mode": ev_data.get("verification_mode", "UNKNOWN"),
        "ev_vlm_records": ev_data.get("vlm_records_verified", 0),
        "ev_table_records": ev_data.get("table_records_verified", 0),
        "ev_total_records": ev_data.get("total_records_verified", 0),
        "ev_total_checks": ev_data.get("total_checks", 0),
        "ev_pass_count": ev_data.get("pass_count", 0),
        "ev_fail_count": ev_data.get("fail_count", 0),
        "ev_warn_count": ev_data.get("warn_count", 0),
        "ev_skip_count": ev_data.get("skip_count", 0),
        "ev_per_record_verdicts": ev_data.get("per_record_verdicts", {}),
        "ev_important_note": ev_data.get("important_note", ""),
        "ev_vlm_verification": ev_data.get("vlm_verification", {}),
        "ev_table_verification": ev_data.get("table_verification", {}),
    }


def _compute_ev_coverage(
    vlm_qa_result: dict,
    table_qa_result: dict,
    ev_result: dict,
) -> dict:
    """Compute EV coverage statistics.

    Returns:
    - total_records: total VLM + Table records
    - ev_covered_records: records with EV results
    - ev_coverage_pct: coverage percentage
    - unverified_records: records without EV
    - vlm_covered: VLM records with EV
    - table_covered: Table records with EV
    """
    vlm_count = vlm_qa_result.get("vlm_record_count", 0)
    table_count = table_qa_result.get("table_record_count", 0)
    total = vlm_count + table_count

    ev_vlm = ev_result.get("ev_vlm_records", 0)
    ev_table = ev_result.get("ev_table_records", 0)
    ev_covered = ev_vlm + ev_table

    coverage_pct = (ev_covered / total * 100) if total > 0 else 0.0

    return {
        "total_records": total,
        "ev_covered_records": ev_covered,
        "ev_coverage_pct": round(coverage_pct, 1),
        "unverified_records": total - ev_covered,
        "vlm_input": vlm_count,
        "vlm_ev_covered": ev_vlm,
        "table_input": table_count,
        "table_ev_covered": ev_table,
    }


def _determine_overall_status(
    vlm_qa_result: dict,
    table_qa_result: dict,
    ev_result: dict,
    extraction_results: list,
    ev_coverage: dict,
    config: dict | None = None,
) -> str:
    """Determine overall QA status based on unified Figure+Table results.

    Rules:
    - If EV is missing entirely → FAILED (or CONDITIONAL_PASS if explicitly disabled)
    - If EV coverage < 100% → PARTIAL (with warning)
    - If any extraction FAIL → PARTIAL or FAILED
    - If all pass → PASS
    """
    has_ev = bool(ev_result) and "ev_error" not in ev_result
    has_vlm = bool(vlm_qa_result) and "vlm_error" not in vlm_qa_result
    has_table = bool(table_qa_result) and "table_error" not in table_qa_result

    if not has_vlm and not has_table and not extraction_results:
        return "FAILED"

    if not has_ev:
        ev_cfg = (config or {}).get("stages", {}).get("evidence_verification", {})
        ev_explicitly_disabled = ev_cfg.get("enabled", True) is False
        if ev_explicitly_disabled:
            logger.warning(
                "EV disabled in config — downgrading QA from PASS to CONDITIONAL_PASS"
            )
            return "CONDITIONAL_PASS"
        return "FAILED"

    extraction_fail = sum(1 for r in extraction_results if not r.get("is_valid", True))
    extraction_pass = sum(1 for r in extraction_results if r.get("is_valid", False))

    if evcoverage := ev_coverage.get("ev_coverage_pct", 0):
        if evcoverage < 100:
            return "PARTIAL"

    if extraction_fail > 0 and extraction_pass == 0:
        return "FAILED"
    elif extraction_fail > 0:
        return "PARTIAL"

    vlm_rejected = vlm_qa_result.get("vlm_quality_states", {}).get("REJECTED", 0)
    table_rejected = table_qa_result.get("table_quality_states", {}).get("REJECTED", 0)
    if vlm_rejected > 0 or table_rejected > 0:
        return "PARTIAL"

    return "PASS"


def run_quality_gate(
    document_id: str,
    extraction_output_path: str = "",
    output_dir: str = "",
    vlm_figure_science_output_path: str = "",
    table_science_output_path: str = "",
    evidence_verification_output_path: str = "",
    **kwargs,
) -> dict:
    """Pipeline-callable QA gate entry point.

    Unified QA for Figure (VLM) and Table records.
    Reports:
    - Figure input/pass/fail counts
    - Table input/pass/fail counts
    - EV coverage (how many records have EV results)
    - Unverified record count
    - Missing EV → not PASS
    """
    mod = _load_module()

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    vlm_qa_result = {}
    vlm_output_path = vlm_figure_science_output_path or kwargs.get("vlm_output_path", "")
    if vlm_output_path:
        logger.info("[%s] Consuming VLM records from: %s", document_id, vlm_output_path)
        vlm_qa_result = _consume_vlm_records(vlm_output_path)
        if "vlm_error" in vlm_qa_result:
            logger.warning("[%s] VLM consumption error: %s", document_id, vlm_qa_result["vlm_error"])
            vlm_qa_result = {}
        else:
            logger.info(
                "[%s] VLM QA: %d records, %d passed, no_auto_verify=%s",
                document_id,
                vlm_qa_result.get("vlm_record_count", 0),
                vlm_qa_result.get("vlm_qa_passed", 0),
                vlm_qa_result.get("vlm_no_auto_verify", "N/A"),
            )

    table_qa_result = {}
    table_output_path = table_science_output_path or kwargs.get("table_output_path", "")
    if table_output_path:
        logger.info("[%s] Consuming Table records from: %s", document_id, table_output_path)
        table_qa_result = _consume_table_records(table_output_path)
        if "table_error" in table_qa_result:
            logger.warning("[%s] Table consumption error: %s", document_id, table_qa_result["table_error"])
            table_qa_result = {}
        else:
            logger.info(
                "[%s] Table QA: %d records, %d passed, no_auto_verify=%s",
                document_id,
                table_qa_result.get("table_record_count", 0),
                table_qa_result.get("table_qa_passed", 0),
                table_qa_result.get("table_no_auto_verify", "N/A"),
            )

    ev_result = {}
    ev_output_path = evidence_verification_output_path or kwargs.get("verification_output_path", "")
    if ev_output_path:
        logger.info("[%s] Consuming evidence verification from: %s", document_id, ev_output_path)
        ev_result = _consume_evidence_verification(ev_output_path)
        if "ev_error" in ev_result:
            logger.warning("[%s] Evidence verification error: %s", document_id, ev_result["ev_error"])
            ev_result = {}
        else:
            logger.info(
                "[%s] EV: mode=%s, %d records (%d VLM + %d Table), %d checks (%d pass, %d fail, %d warn)",
                document_id,
                ev_result.get("ev_mode", "UNKNOWN"),
                ev_result.get("ev_total_records", 0),
                ev_result.get("ev_vlm_records", 0),
                ev_result.get("ev_table_records", 0),
                ev_result.get("ev_total_checks", 0),
                ev_result.get("ev_pass_count", 0),
                ev_result.get("ev_fail_count", 0),
                ev_result.get("ev_warn_count", 0),
            )

    ev_coverage = _compute_ev_coverage(vlm_qa_result, table_qa_result, ev_result)

    extraction_results = []
    if extraction_output_path:
        extraction_dir = Path(extraction_output_path)
        if extraction_dir.exists():
            json_files = list(extraction_dir.glob("*_extracted.json"))
            validator = mod.QAGateValidator()
            for jf in json_files:
                try:
                    with open(jf, "r", encoding="utf-8") as f:
                        record = json.load(f)
                    is_valid, violations, warnings = validator.validate(record)
                    extraction_results.append({
                        "file": str(jf),
                        "is_valid": is_valid,
                        "violations": violations,
                        "warnings": warnings,
                    })
                except Exception as e:
                    extraction_results.append({
                        "file": str(jf),
                        "is_valid": False,
                        "error": str(e),
                    })

    overall_status = _determine_overall_status(
        vlm_qa_result, table_qa_result, ev_result, extraction_results, ev_coverage,
        config=kwargs.get("config"),
    )

    extraction_pass = sum(1 for r in extraction_results if r.get("is_valid", False))
    extraction_fail = sum(1 for r in extraction_results if not r.get("is_valid", True))

    qa_timestamp = datetime.now(timezone.utc).isoformat()

    report_file = out_path / f"{document_id}_qa_report.json"
    report = {
        "document_id": document_id,
        "qa_timestamp": qa_timestamp,
        "qa_version": "2.0.0",
        "files_checked": len(extraction_results),
        "pass_count": extraction_pass,
        "fail_count": extraction_fail,
        "overall_status": overall_status,
        "results": extraction_results,
        "unified_summary": {
            "figure": {
                "input_count": vlm_qa_result.get("vlm_record_count", 0),
                "pass_count": vlm_qa_result.get("vlm_qa_passed", 0),
                "fail_count": vlm_qa_result.get("vlm_record_count", 0) - vlm_qa_result.get("vlm_qa_passed", 0),
                "quality_states": vlm_qa_result.get("vlm_quality_states", {}),
                "no_auto_verify": vlm_qa_result.get("vlm_no_auto_verify", False),
            },
            "table": {
                "input_count": table_qa_result.get("table_record_count", 0),
                "pass_count": table_qa_result.get("table_qa_passed", 0),
                "fail_count": table_qa_result.get("table_record_count", 0) - table_qa_result.get("table_qa_passed", 0),
                "quality_states": table_qa_result.get("table_quality_states", {}),
                "no_auto_verify": table_qa_result.get("table_no_auto_verify", False),
                "table_ids": table_qa_result.get("table_ids", []),
            },
            "total_records": ev_coverage["total_records"],
            "total_pass": vlm_qa_result.get("vlm_qa_passed", 0) + table_qa_result.get("table_qa_passed", 0),
            "total_fail": (
                vlm_qa_result.get("vlm_record_count", 0) - vlm_qa_result.get("vlm_qa_passed", 0)
                + table_qa_result.get("table_record_count", 0) - table_qa_result.get("table_qa_passed", 0)
            ),
        },
        "ev_coverage": ev_coverage,
    }

    if vlm_qa_result:
        report["vlm_qa"] = vlm_qa_result
    if table_qa_result:
        report["table_qa"] = table_qa_result
    if ev_result:
        report["evidence_verification"] = ev_result

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    output = {
        "document_id": document_id,
        "qa_report_path": str(report_file),
        "qa_status": overall_status,
        "qa_timestamp": qa_timestamp,
        "files_checked": len(extraction_results),
        "pass_count": extraction_pass,
        "fail_count": extraction_fail,
        "figure_record_count": vlm_qa_result.get("vlm_record_count", 0),
        "figure_qa_passed": vlm_qa_result.get("vlm_qa_passed", 0),
        "table_record_count": table_qa_result.get("table_record_count", 0),
        "table_qa_passed": table_qa_result.get("table_qa_passed", 0),
        "total_record_count": ev_coverage["total_records"],
        "total_qa_passed": ev_coverage["total_records"] - (
            vlm_qa_result.get("vlm_record_count", 0) - vlm_qa_result.get("vlm_qa_passed", 0)
            + table_qa_result.get("table_record_count", 0) - table_qa_result.get("table_qa_passed", 0)
        ),
        "ev_coverage_pct": ev_coverage["ev_coverage_pct"],
        "ev_unverified": ev_coverage["unverified_records"],
    }
    if ev_result:
        output["ev_total_records"] = ev_result.get("ev_total_records", 0)
        output["ev_vlm_records"] = ev_result.get("ev_vlm_records", 0)
        output["ev_table_records"] = ev_result.get("ev_table_records", 0)

    return output


def create_quality_gate_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for QA quality gates.

    Unified QA for Figure (VLM) and Table records.
    Dependencies include vlm_figure_science, table_science, and evidence_verification.
    """
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("quality_gate", {})

    adapter = StageAdapter(
        stage_name="quality_gate",
        version="2.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=[
                "extraction_output_path",
                "vlm_figure_science_output_path",
                "table_science_output_path",
                "evidence_verification_output_path",
            ],
        ),
        output_contract=DataContract(
            required_outputs=["qa_report_path", "qa_status", "qa_timestamp"],
            optional_outputs=[
                "figure_record_count", "figure_qa_passed",
                "table_record_count", "table_qa_passed",
                "total_record_count", "total_qa_passed",
                "ev_coverage_pct", "ev_unverified",
                "ev_total_records", "ev_vlm_records", "ev_table_records",
            ],
        ),
        dependencies=[
            "six_dimension_extraction", "science_extraction_v2", "num_unit_normalization",
            "vlm_figure_science", "table_science", "evidence_verification",
        ],
        timeout_seconds=stage_cfg.get("timeout_seconds", 30),
    )

    output_dir = paths.get("pipeline_runs", "") + "/qa"

    adapter.set_function(
        run_quality_gate,
        output_dir=output_dir,
    )
    return adapter
