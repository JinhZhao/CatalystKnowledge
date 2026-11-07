#!/usr/bin/env python3
"""Failure injection tests for 007-R2 audit.

Tests failure propagation through EV -> QA -> Store -> Report chain.
All tests run in isolated temp directory.
"""

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from catalyst_knowledge.pipeline.adapters.evidence_verifier_adapter import run_vlm_evidence_verification
from catalyst_knowledge.pipeline.adapters.quality_gate_adapter import run_quality_gate
from catalyst_knowledge.pipeline.adapters.store_adapter import run_canonical_store
from catalyst_knowledge.pipeline.adapters.report_adapter import run_report_generation

R2_DIR = PROJECT_ROOT / "runs" / "pipeline_001_fix" / "PIPELINE_007_R2"
RESULTS = []


def log_result(test_id, name, status, details):
    RESULTS.append({
        "test_id": test_id,
        "name": name,
        "status": status,
        "details": details,
    })
    icon = {"PASS": "+", "FAIL": "!", "WARN": "?", "SKIP": "-"}.get(status, "?")
    print(f"  [{icon}] {test_id}: {name} -> {status}")
    if details:
        print(f"      {details[:200]}")


def make_minimal_vlm_file(path, n_records=3):
    records = []
    for i in range(n_records):
        records.append({
            "record_id": f"SR_VLM-TEST_fig_01_R1_{i+1:03d}",
            "figure_id": "F02_fig_01",
            "statement": f"Test statement {i+1} with enough text for crossref",
            "evidence_type": "IMAGE_ONLY_OBSERVATION",
            "quality_state": "CANDIDATE",
            "source_anchor": {
                "document_id": "F02",
                "element_id": "F02_p2_b30",
                "element_type": "IMAGE",
                "page_idx": 2,
                "bbox": [100, 200, 300, 400],
                "image_sha256": "abc123def456",
                "anchor_version": "test-v1",
            },
        })
    data = {"results": [{"records": records}]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return n_records


def make_malformed_json(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("{this is not valid json,,,")


def make_empty_vlm_file(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"results": [{"records": []}]}, f)


# ============================================================
# Test FI-001: EV with missing VLM file
# ============================================================
def test_fi001():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ev_output"
        out.mkdir()
        result = run_vlm_evidence_verification(
            document_id="F02",
            output_dir=str(out),
            vlm_figure_science_output_path=str(Path(tmp) / "nonexistent.json"),
        )
        status = result.get("verification_status", "UNKNOWN")
        verified = result.get("vlm_records_verified", -1)
        if status == "SKIP" and verified == 0:
            log_result("FI-001", "EV missing VLM file -> SKIP", "PASS",
                       f"status={status}, verified={verified}")
        else:
            log_result("FI-001", "EV missing VLM file -> SKIP", "FAIL",
                       f"Expected SKIP/0, got {status}/{verified}")


# ============================================================
# Test FI-002: EV with malformed JSON
# ============================================================
def test_fi002():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        make_malformed_json(bad)
        out = Path(tmp) / "ev_output"
        out.mkdir()
        result = run_vlm_evidence_verification(
            document_id="F02",
            output_dir=str(out),
            vlm_figure_science_output_path=str(bad),
        )
        status = result.get("verification_status", "UNKNOWN")
        if status == "FAILED":
            log_result("FI-002", "EV malformed JSON -> FAILED", "PASS",
                       f"status={status}")
        else:
            log_result("FI-002", "EV malformed JSON -> FAILED", "FAIL",
                       f"Expected FAILED, got {status}")


# ============================================================
# Test FI-003: QA with missing EV + missing VLM -> FAILED
# ============================================================
def test_fi003():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "qa_output"
        out.mkdir()
        result = run_quality_gate(
            document_id="F02",
            output_dir=str(out),
            extraction_output_path="",
            vlm_figure_science_output_path="",
            evidence_verification_output_path="",
        )
        status = result.get("qa_status", "UNKNOWN")
        if status == "FAILED":
            log_result("FI-003", "QA no data sources -> FAILED", "PASS",
                       f"status={status}")
        else:
            log_result("FI-003", "QA no data sources -> FAILED", "FAIL",
                       f"Expected FAILED, got {status}")


# ============================================================
# Test FI-004: QA with failed EV (ev_error) -> continues with warning
# ============================================================
def test_fi004():
    with tempfile.TemporaryDirectory() as tmp:
        bad_ev = Path(tmp) / "bad_ev.json"
        with open(bad_ev, "w", encoding="utf-8") as f:
            json.dump({"verification_status": "FAILED", "error": "test"}, f)
        vlm_file = Path(tmp) / "vlm.json"
        make_minimal_vlm_file(vlm_file, 3)
        out = Path(tmp) / "qa_output"
        out.mkdir()
        result = run_quality_gate(
            document_id="F02",
            output_dir=str(out),
            extraction_output_path="",
            vlm_figure_science_output_path=str(vlm_file),
            evidence_verification_output_path=str(bad_ev),
        )
        status = result.get("qa_status", "UNKNOWN")
        if status == "PASS":
            log_result("FI-004", "QA with failed EV + valid VLM -> PASS (EV advisory)", "PASS",
                       f"status={status}, EV correctly treated as advisory")
        else:
            log_result("FI-004", "QA with failed EV + valid VLM -> PASS", "FAIL",
                       f"Expected PASS, got {status}")


# ============================================================
# Test FI-005: Store with missing QA report -> still PASS
# ============================================================
def test_fi005():
    with tempfile.TemporaryDirectory() as tmp:
        store_dir = Path(tmp) / "store"
        store_dir.mkdir()
        vlm_file = Path(tmp) / "vlm.json"
        make_minimal_vlm_file(vlm_file, 3)
        result = run_canonical_store(
            document_id="F02",
            qa_report_path=str(Path(tmp) / "nonexistent_qa.json"),
            store_dir=str(store_dir),
            vlm_figure_science_output_path=str(vlm_file),
        )
        status = result.get("store_status", "UNKNOWN")
        if status == "PASS":
            log_result("FI-005", "Store missing QA report -> PASS (QA not validated)", "PASS",
                       f"status={status}")
        else:
            log_result("FI-005", "Store missing QA report -> PASS", "FAIL",
                       f"Expected PASS, got {status}")


# ============================================================
# Test FI-006: Report with missing Store -> BLOCKED
# ============================================================
def test_fi006():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report_output"
        out.mkdir()
        fake_store = Path(tmp) / "empty_store"
        fake_store.mkdir()
        result = run_report_generation(
            document_id="F02",
            store_path=str(fake_store),
            output_dir=str(out),
            vlm_figure_science_output_path=str(Path(tmp) / "also_missing.json"),
        )
        status = result.get("report_status", "UNKNOWN")
        if status == "BLOCKED":
            log_result("FI-006", "Report missing Store + missing VLM -> BLOCKED", "PASS",
                       f"status={status}, chain_of_custody enforced")
        else:
            log_result("FI-006", "Report missing Store + missing VLM -> BLOCKED", "FAIL",
                       f"Expected BLOCKED, got {status}")


# ============================================================
# Test FI-007: bbox format error (list vs dict)
# ============================================================
def test_fi007():
    with tempfile.TemporaryDirectory() as tmp:
        vlm_file = Path(tmp) / "vlm_bbox.json"
        records = []
        for i, bbox in enumerate([
            [100, 200, 300, 400],
            {"x0": 100, "y0": 200, "x1": 300, "y1": 400},
            None,
        ]):
            r = {
                "record_id": f"SR_VLM-TEST_fig_01_R1_{i+1:03d}",
                "figure_id": "F02_fig_01",
                "statement": f"Test {i}",
                "evidence_type": "IMAGE_ONLY_OBSERVATION",
                "quality_state": "CANDIDATE",
                "source_anchor": {
                    "document_id": "F02",
                    "element_id": "F02_p2_b30",
                    "page_idx": 2,
                    "image_sha256": "abc123",
                    "anchor_version": "test-v1",
                },
            }
            if bbox is not None:
                r["source_anchor"]["bbox"] = bbox
            records.append(r)
        data = {"results": [{"records": records}]}
        with open(vlm_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        out = Path(tmp) / "ev_output"
        out.mkdir()
        try:
            result = run_vlm_evidence_verification(
                document_id="F02",
                output_dir=str(out),
                vlm_figure_science_output_path=str(vlm_file),
            )
            status = result.get("verification_status", "UNKNOWN")
            verified = result.get("vlm_records_verified", 0)
            if status in ("PASS", "PARTIAL") and verified == 3:
                log_result("FI-007", "EV handles both bbox formats", "PASS",
                           f"status={status}, verified={verified}")
            else:
                log_result("FI-007", "EV handles both bbox formats", "WARN",
                           f"status={status}, verified={verified}")
        except Exception as e:
            log_result("FI-007", "EV handles both bbox formats", "FAIL",
                       f"Exception: {e}")


# ============================================================
# Test FI-008: Record count mismatch (VLM says 3, file has 5)
# ============================================================
def test_fi008():
    with tempfile.TemporaryDirectory() as tmp:
        vlm_file = Path(tmp) / "vlm.json"
        n = make_minimal_vlm_file(vlm_file, 5)
        out = Path(tmp) / "ev_output"
        out.mkdir()
        result = run_vlm_evidence_verification(
            document_id="F02",
            output_dir=str(out),
            vlm_figure_science_output_path=str(vlm_file),
        )
        verified = result.get("vlm_records_verified", 0)
        if verified == 5:
            log_result("FI-008", "EV actual count matches file", "PASS",
                       f"verified={verified} (file has {n} records)")
        else:
            log_result("FI-008", "EV actual count matches file", "FAIL",
                       f"verified={verified}, expected {n}")


# ============================================================
# Test FI-009: Duplicate execution (idempotency)
# ============================================================
def test_fi009():
    with tempfile.TemporaryDirectory() as tmp:
        vlm_file = Path(tmp) / "vlm.json"
        make_minimal_vlm_file(vlm_file, 3)
        store_dir = Path(tmp) / "store"
        store_dir.mkdir()
        r1 = run_canonical_store(
            document_id="F02",
            store_dir=str(store_dir),
            vlm_figure_science_output_path=str(vlm_file),
        )
        r2 = run_canonical_store(
            document_id="F02",
            store_dir=str(store_dir),
            vlm_figure_science_output_path=str(vlm_file),
        )
        s1 = r1.get("store_status")
        s2 = r2.get("store_status")
        vlm_dir = store_dir / "vlm_records"
        count = len(list(vlm_dir.glob("*.json"))) if vlm_dir.exists() else 0
        if s1 == "PASS" and s2 == "PASS" and count == 3:
            log_result("FI-009", "Store idempotent on duplicate execution", "PASS",
                       f"Both runs PASS, {count} files (no duplicates)")
        else:
            log_result("FI-009", "Store idempotent on duplicate execution", "FAIL",
                       f"r1={s1}, r2={s2}, files={count}")


# ============================================================
# Test FI-010: Full chain failure propagation
# EV FAILED -> QA sees ev_error -> Store gets no EV annotation -> Report still works
# ============================================================
def test_fi010():
    with tempfile.TemporaryDirectory() as tmp:
        vlm_file = Path(tmp) / "vlm.json"
        make_minimal_vlm_file(vlm_file, 3)
        ev_out = Path(tmp) / "ev"
        ev_out.mkdir()
        qa_out = Path(tmp) / "qa"
        qa_out.mkdir()
        store_dir = Path(tmp) / "store"
        store_dir.mkdir()
        report_out = Path(tmp) / "report"
        report_out.mkdir()

        ev_result = run_vlm_evidence_verification(
            document_id="F02",
            output_dir=str(ev_out),
            vlm_figure_science_output_path=str(Path(tmp) / "nonexistent.json"),
        )
        ev_status = ev_result.get("verification_status", "UNKNOWN")

        qa_result = run_quality_gate(
            document_id="F02",
            output_dir=str(qa_out),
            extraction_output_path="",
            vlm_figure_science_output_path=str(vlm_file),
            evidence_verification_output_path=str(ev_out / "nonexistent_ev.json"),
        )
        qa_status = qa_result.get("qa_status", "UNKNOWN")

        store_result = run_canonical_store(
            document_id="F02",
            store_dir=str(store_dir),
            vlm_figure_science_output_path=str(vlm_file),
            qa_report_path=str(qa_out / "F02_qa_report.json"),
        )
        store_status = store_result.get("store_status", "UNKNOWN")

        report_result = run_report_generation(
            document_id="F02",
            store_path=str(store_dir),
            output_dir=str(report_out),
            vlm_figure_science_output_path=str(vlm_file),
        )
        report_status = report_result.get("report_status", "UNKNOWN")

        chain_ok = (
            ev_status == "SKIP"
            and qa_status == "PASS"
            and store_status == "PASS"
            and report_status == "PASS"
        )
        detail = f"EV={ev_status} -> QA={qa_status} -> Store={store_status} -> Report={report_status}"
        if chain_ok:
            log_result("FI-010", "Full chain: EV SKIP degrades gracefully", "PASS", detail)
        else:
            log_result("FI-010", "Full chain: EV SKIP degrades gracefully", "FAIL", detail)


# ============================================================
# Test FI-011: Old Store pollution check
# ============================================================
def test_fi011():
    with tempfile.TemporaryDirectory() as tmp:
        store_dir = Path(tmp) / "store"
        store_dir.mkdir()
        vlm_dir = store_dir / "vlm_records"
        vlm_dir.mkdir()
        old_record = {
            "record_id": "SR_VLM-OLD_F02_fig_99_R1_001",
            "figure_id": "F02_fig_99",
            "quality_state": "CANDIDATE",
            "document_id": "F02",
        }
        with open(vlm_dir / "old_record.json", "w", encoding="utf-8") as f:
            json.dump(old_record, f)

        vlm_file = Path(tmp) / "vlm.json"
        make_minimal_vlm_file(vlm_file, 3)
        run_canonical_store(
            document_id="F02",
            store_dir=str(store_dir),
            vlm_figure_science_output_path=str(vlm_file),
        )
        files = list(vlm_dir.glob("*.json"))
        old_still_there = any("OLD" in f.name for f in files)
        new_count = len([f for f in files if "OLD" not in f.name])
        if old_still_there and new_count == 3:
            log_result("FI-011", "Old Store records not deleted by new run", "PASS",
                       f"Old record preserved, {new_count} new records added")
        elif not old_still_there:
            log_result("FI-011", "Old Store records not deleted by new run", "FAIL",
                       "Old record was deleted!")
        else:
            log_result("FI-011", "Old Store records not deleted by new run", "WARN",
                       f"old={old_still_there}, new={new_count}")


# ============================================================
# Run all tests
# ============================================================
def main():
    print("=" * 60)
    print("007-R2 AUDIT: Failure Injection Tests")
    print("=" * 60)
    tests = [
        test_fi001, test_fi002, test_fi003, test_fi004, test_fi005,
        test_fi006, test_fi007, test_fi008, test_fi009, test_fi010,
        test_fi011,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            log_result(t.__name__.replace("test_", "").upper(), t.__doc__ or "", "FAIL",
                       f"Exception: {e}\n{traceback.format_exc()[:200]}")

    pass_count = sum(1 for r in RESULTS if r["status"] == "PASS")
    fail_count = sum(1 for r in RESULTS if r["status"] == "FAIL")
    warn_count = sum(1 for r in RESULTS if r["status"] == "WARN")
    print()
    print(f"Results: {pass_count} PASS, {fail_count} FAIL, {warn_count} WARN out of {len(RESULTS)} tests")

    output = {
        "audit_id": "007-R2-FAILURE-INJECTION",
        "total_tests": len(RESULTS),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "tests": RESULTS,
    }
    out_path = R2_DIR.parent / "PIPELINE_007_R2_AUDIT" / "FAILURE_INJECTION_RESULTS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {out_path}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
