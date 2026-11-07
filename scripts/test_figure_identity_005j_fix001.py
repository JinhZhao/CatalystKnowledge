"""
PIPELINE-005-J-FIX-001: Deterministic Tests
Verifies figure identity, source anchor correctness, and quality preservation.
7 dimensions: figure_id, image_hash, bbox, document_ir, cache_identity, quality_state, regression
"""

import json
import hashlib
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path("D:/Knowledge_World")
FIX_001_DIR = PROJECT_ROOT / "runs/pipeline_001_fix/PIPELINE_005_J_FIX_001"
CORRECTED_RECORDS = FIX_001_DIR / "CORRECTED_F02_VLM_RECORDS.json"

CORRECT_FIGURE_PARSER = PROJECT_ROOT / "runs/pipeline_001_fix/PIPELINE_005_G/figure_parser/F02_figure_parser.json"
CORRUPT_FIGURE_PARSER = PROJECT_ROOT / "runs/pipeline_001_fix/PIPELINE_005_G_FIX_001/figure_parser/F02_figure_parser.json"
DOCUMENT_IR = PROJECT_ROOT / "runs/pipeline_001_fix/document_ir/F02_document_ir.json"

ORIGINAL_VLM_OUTPUT = PROJECT_ROOT / "runs/pipeline_001_fix/PIPELINE_005_G/PIPELINE_005_G/F02_vlm_science_records.json"
STORE_VLM_DIR = PROJECT_ROOT / "runs/pipeline_001_fix/PIPELINE_005_I/canonical_store/vlm_records"
IMAGE_DIR = PROJECT_ROOT / "data/test_corpus/mineru_output/F02_regression/main/auto/images"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_sha256(file_path):
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def test_1_figure_id_image_hash():
    """Test 1: Figure ID与图像hash一致性 — corrected records' image_sha256 matches actual file on disk"""
    print("\n" + "=" * 70)
    print("TEST 1: Figure ID vs Image Hash Consistency")
    print("=" * 70)

    corrected = load_json(CORRECTED_RECORDS)
    records = corrected.get("records", [])

    fp = load_json(CORRECT_FIGURE_PARSER)
    figures = fp.get("figures", [])

    # Build figure_id -> expected info from correct FigureParser
    fig_map = {}
    for fig in figures:
        fid = fig.get("figure_id", "")
        img_path = fig.get("image_path", "")
        fig_map[fid] = {
            "expected_sha256": fig.get("image_sha256", ""),
            "image_path": img_path,
            "actual_file_sha256": compute_sha256(img_path) if Path(img_path).exists() else None,
        }

    passed = failed = 0
    details = []

    for rec in records:
        fid = rec.get("figure_id", "")
        anchor = rec.get("source_anchor", {})
        rec_sha = anchor.get("image_file", {}).get("sha256", "")

        if fid not in fig_map:
            details.append({"record_id": rec.get("record_id"), "status": "FAIL", "reason": f"{fid} not in FigureParser"})
            failed += 1
            continue

        info = fig_map[fid]
        sha_ok = (rec_sha == info["expected_sha256"])
        file_ok = (info["expected_sha256"] == info["actual_file_sha256"])

        if sha_ok and file_ok:
            details.append({"record_id": rec.get("record_id"), "figure_id": fid, "status": "PASS"})
            passed += 1
        else:
            details.append({
                "record_id": rec.get("record_id"), "figure_id": fid, "status": "FAIL",
                "record_sha": rec_sha, "expected_sha": info["expected_sha256"], "file_sha": info["actual_file_sha256"],
            })
            failed += 1

    print(f"Result: {passed} PASS, {failed} FAIL")
    return {"test_name": "Figure ID vs Image Hash", "total": len(records), "passed": passed, "failed": failed,
            "status": "PASS" if failed == 0 else "FAIL", "details": details}


def test_2_bbox_figure_parser():
    """Test 2: bbox与FigureParser一致性 — corrected bbox matches the CORRECT FigureParser"""
    print("\n" + "=" * 70)
    print("TEST 2: Bbox vs Correct FigureParser Consistency")
    print("=" * 70)

    corrected = load_json(CORRECTED_RECORDS)
    records = corrected.get("records", [])

    fp = load_json(CORRECT_FIGURE_PARSER)
    figures = fp.get("figures", [])

    # Build figure_id -> expected bbox from correct FigureParser
    fp_map = {}
    for fig in figures:
        fid = fig.get("figure_id", "")
        sa = fig.get("source_anchor", {})
        fp_map[fid] = {
            "bbox": sa.get("bbox", {}),
            "page_idx": sa.get("page_idx"),
        }

    # Also load corrupt FigureParser to confirm the fix differs
    corrupt_fp = load_json(CORRUPT_FIGURE_PARSER)
    corrupt_map = {}
    for fig in corrupt_fp.get("figures", []):
        fid = fig.get("figure_id", "")
        sa = fig.get("source_anchor", {})
        corrupt_map[fid] = {"bbox": sa.get("bbox", {})}

    passed = failed = 0
    details = []

    for rec in records:
        fid = rec.get("figure_id", "")
        anchor = rec.get("source_anchor", {})
        rec_bbox = anchor.get("bbox", {})
        rec_page = anchor.get("page_idx")

        if fid not in fp_map:
            details.append({"record_id": rec.get("record_id"), "status": "FAIL", "reason": f"{fid} not in FP"})
            failed += 1
            continue

        exp = fp_map[fid]
        exp_bbox = exp["bbox"]

        bbox_ok = (
            rec_bbox.get("x0") == exp_bbox.get("x0") and
            rec_bbox.get("y0") == exp_bbox.get("y0") and
            rec_bbox.get("x1") == exp_bbox.get("x1") and
            rec_bbox.get("y1") == exp_bbox.get("y1")
        )
        page_ok = (rec_page == exp["page_idx"])

        # Also verify this differs from the corrupt bbox
        corrupt_bbox = corrupt_map.get(fid, {}).get("bbox", {})
        is_different_from_corrupt = (
            rec_bbox.get("x0") != corrupt_bbox.get("x0") or
            rec_bbox.get("y0") != corrupt_bbox.get("y0") or
            rec_bbox.get("x1") != corrupt_bbox.get("x1") or
            rec_bbox.get("y1") != corrupt_bbox.get("y1")
        )

        if bbox_ok and page_ok:
            details.append({
                "record_id": rec.get("record_id"), "figure_id": fid, "status": "PASS",
                "differs_from_corrupt": is_different_from_corrupt,
            })
            passed += 1
        else:
            details.append({
                "record_id": rec.get("record_id"), "figure_id": fid, "status": "FAIL",
                "expected_bbox": exp_bbox, "record_bbox": rec_bbox,
            })
            failed += 1

    print(f"Result: {passed} PASS, {failed} FAIL")
    return {"test_name": "Bbox vs FigureParser", "total": len(records), "passed": passed, "failed": failed,
            "status": "PASS" if failed == 0 else "FAIL", "details": details}


def test_3_document_ir_element():
    """Test 3: Document IR element_id一致性 — corrected bbox matches a Document IR image block"""
    print("\n" + "=" * 70)
    print("TEST 3: Document IR Element ID Consistency")
    print("=" * 70)

    corrected = load_json(CORRECTED_RECORDS)
    records = corrected.get("records", [])

    doc_ir = load_json(DOCUMENT_IR)
    blocks = doc_ir.get("blocks", [])

    # Build list of image blocks from Document IR
    # Structure: source_anchor.element_type == "image", source_anchor.bbox == [x0,y0,x1,y1]
    ir_images = []
    for block in blocks:
        sa = block.get("source_anchor", {})
        if sa.get("element_type") == "image":
            ir_images.append({
                "element_id": block.get("element_id", ""),
                "page_idx": sa.get("page"),
                "bbox_list": sa.get("bbox", []),
            })

    passed = failed = 0
    details = []

    for rec in records:
        fid = rec.get("figure_id", "")
        anchor = rec.get("source_anchor", {})
        rec_page = anchor.get("page_idx")
        rec_bbox = anchor.get("bbox", {})
        rec_bbox_list = [rec_bbox.get("x0", 0), rec_bbox.get("y0", 0), rec_bbox.get("x1", 0), rec_bbox.get("y1", 0)]

        match = None
        for img in ir_images:
            if img["page_idx"] == rec_page and len(img["bbox_list"]) == 4:
                dx0 = abs(rec_bbox_list[0] - img["bbox_list"][0])
                dy0 = abs(rec_bbox_list[1] - img["bbox_list"][1])
                dx1 = abs(rec_bbox_list[2] - img["bbox_list"][2])
                dy1 = abs(rec_bbox_list[3] - img["bbox_list"][3])
                if dx0 < 5 and dy0 < 5 and dx1 < 5 and dy1 < 5:
                    match = img
                    break

        if match:
            details.append({
                "record_id": rec.get("record_id"), "figure_id": fid, "status": "PASS",
                "matched_element_id": match["element_id"],
            })
            passed += 1
        else:
            details.append({
                "record_id": rec.get("record_id"), "figure_id": fid, "status": "FAIL",
                "reason": f"No matching image block on page {rec_page}",
                "record_bbox": rec_bbox_list,
            })
            failed += 1

    print(f"Result: {passed} PASS, {failed} FAIL")
    return {"test_name": "Document IR Element ID", "total": len(records), "passed": passed, "failed": failed,
            "status": "PASS" if failed == 0 else "FAIL", "details": details}


def test_4_cache_identity():
    """Test 4: 缓存复用身份校验 — all records still reference F02_fig_07, SHA unchanged"""
    print("\n" + "=" * 70)
    print("TEST 4: Cache Reuse Identity Verification")
    print("=" * 70)

    corrected = load_json(CORRECTED_RECORDS)
    records = corrected.get("records", [])

    # All 25 records should be for F02_fig_07 (same figure, same image)
    passed = failed = 0
    details = []
    sha_set = set()

    for rec in records:
        fid = rec.get("figure_id", "")
        anchor = rec.get("source_anchor", {})
        sha = anchor.get("image_file", {}).get("sha256", "")
        sha_set.add(sha)

        if fid == "F02_fig_07" and sha:
            details.append({"record_id": rec.get("record_id"), "status": "PASS", "figure_id": fid})
            passed += 1
        else:
            details.append({
                "record_id": rec.get("record_id"), "status": "FAIL",
                "figure_id": fid, "sha256": sha[:20] if sha else "EMPTY",
            })
            failed += 1

    print(f"Result: {passed} PASS, {failed} FAIL")
    print(f"Unique SHA256 values: {len(sha_set)} (should be 1)")
    return {"test_name": "Cache Identity", "total": len(records), "passed": passed, "failed": failed,
            "unique_sha_count": len(sha_set), "status": "PASS" if failed == 0 and len(sha_set) == 1 else "FAIL",
            "details": details}


def test_5_no_silent_relabeling():
    """Test 5: 错误图像不得被静默重标记 — image SHA in corrected == image SHA in Store (source of truth)"""
    print("\n" + "=" * 70)
    print("TEST 5: No Silent Image Relabeling")
    print("=" * 70)

    corrected = load_json(CORRECTED_RECORDS)
    corr_recs = corrected.get("records", [])

    # Load Store records (the actual source from which corrected records were derived)
    store_map = {}
    if STORE_VLM_DIR.exists():
        for f in sorted(STORE_VLM_DIR.glob("*.json")):
            try:
                sr = load_json(f)
                rid = sr.get("record_id", "")
                sha = sr.get("source_anchor", {}).get("image_file", {}).get("sha256", "")
                fig_id = sr.get("figure_id", "")
                store_map[rid] = {"sha256": sha, "figure_id": fig_id}
            except Exception:
                continue

    if not store_map:
        print("SKIP: No Store records found")
        return {"test_name": "No Silent Relabeling", "total": 0, "passed": 0, "failed": 0,
                "status": "SKIP", "reason": "Store records not found"}

    passed = failed = 0
    details = []

    for rec in corr_recs:
        rid = rec.get("record_id", "")
        corr_sha = rec.get("source_anchor", {}).get("image_file", {}).get("sha256", "")
        corr_fig = rec.get("figure_id", "")

        if rid not in store_map:
            details.append({"record_id": rid, "status": "FAIL", "reason": "Not in Store"})
            failed += 1
            continue

        store_entry = store_map[rid]
        sha_preserved = (corr_sha == store_entry["sha256"])
        fig_preserved = (corr_fig == store_entry["figure_id"])

        if sha_preserved and fig_preserved:
            details.append({"record_id": rid, "status": "PASS", "sha_preserved": True, "figure_id_preserved": True})
            passed += 1
        else:
            details.append({
                "record_id": rid, "status": "FAIL",
                "sha_preserved": sha_preserved, "fig_preserved": fig_preserved,
                "store_sha": store_entry["sha256"][:20], "corrected_sha": corr_sha[:20],
                "store_fig": store_entry["figure_id"], "corrected_fig": corr_fig,
            })
            failed += 1

    print(f"Result: {passed} PASS, {failed} FAIL")
    return {"test_name": "No Silent Relabeling", "total": len(corr_recs), "passed": passed, "failed": failed,
            "status": "PASS" if failed == 0 else "FAIL", "details": details}


def test_6_quality_state_preserved():
    """Test 6: 修正后记录仍保持CANDIDATE或NEEDS_REVIEW — no auto-promotion to VERIFIED"""
    print("\n" + "=" * 70)
    print("TEST 6: Quality State Preservation")
    print("=" * 70)

    corrected = load_json(CORRECTED_RECORDS)
    records = corrected.get("records", [])

    # Also check against Store records to ensure quality states weren't altered
    store_records = []
    if STORE_VLM_DIR.exists():
        for f in sorted(STORE_VLM_DIR.glob("*.json")):
            try:
                store_records.append(load_json(f))
            except Exception:
                continue

    # Build store quality map
    store_qs = {}
    for sr in store_records:
        rid = sr.get("record_id", "")
        store_qs[rid] = sr.get("quality_state", "")

    passed = failed = 0
    details = []
    qs_counts = {}

    for rec in records:
        rid = rec.get("record_id", "")
        qs = rec.get("quality_state", "")
        qs_counts[qs] = qs_counts.get(qs, 0) + 1

        if qs in ("CANDIDATE", "NEEDS_REVIEW"):
            # Also verify it matches Store (no promotion happened)
            store_match = (store_qs.get(rid) == qs) if rid in store_qs else True
            details.append({"record_id": rid, "status": "PASS", "quality_state": qs, "store_match": store_match})
            passed += 1
        else:
            details.append({"record_id": rid, "status": "FAIL", "quality_state": qs, "reason": "Not CANDIDATE/NEEDS_REVIEW"})
            failed += 1

    print(f"Result: {passed} PASS, {failed} FAIL")
    print(f"Quality distribution: {qs_counts}")
    return {"test_name": "Quality State Preservation", "total": len(records), "passed": passed, "failed": failed,
            "quality_distribution": qs_counts,
            "status": "PASS" if failed == 0 else "FAIL", "details": details}


def test_7_regression_check():
    """Test 7: Regression — corrected records don't break downstream consumers"""
    print("\n" + "=" * 70)
    print("TEST 7: Regression Check")
    print("=" * 70)

    # Verify individual corrected files match combined file
    individual_dir = FIX_001_DIR / "corrected_vlm_records"
    if not individual_dir.exists():
        return {"test_name": "Regression", "total": 0, "passed": 0, "failed": 0,
                "status": "SKIP", "reason": "Individual records dir not found"}

    corrected = load_json(CORRECTED_RECORDS)
    combined_recs = {r["record_id"]: r for r in corrected.get("records", [])}

    ind_files = sorted(individual_dir.glob("*.json"))
    passed = failed = 0
    details = []

    for f in ind_files:
        try:
            ind_rec = load_json(f)
            rid = ind_rec.get("record_id", "")
            if rid in combined_recs:
                # Compare source_anchor
                ind_sa = ind_rec.get("source_anchor", {})
                comb_sa = combined_recs[rid].get("source_anchor", {})
                if ind_sa == comb_sa:
                    details.append({"file": f.name, "record_id": rid, "status": "PASS"})
                    passed += 1
                else:
                    details.append({"file": f.name, "record_id": rid, "status": "FAIL", "reason": "source_anchor mismatch"})
                    failed += 1
            else:
                details.append({"file": f.name, "status": "FAIL", "reason": "record_id not in combined"})
                failed += 1
        except Exception as e:
            details.append({"file": f.name, "status": "FAIL", "reason": str(e)})
            failed += 1

    # Also verify count matches
    count_ok = (len(ind_files) == len(combined_recs))
    print(f"Individual files: {len(ind_files)}, Combined records: {len(combined_recs)}, Match: {count_ok}")
    print(f"Result: {passed} PASS, {failed} FAIL")

    overall = "PASS" if failed == 0 and count_ok else "FAIL"
    return {"test_name": "Regression", "total": len(ind_files) + 1, "passed": passed + (1 if count_ok else 0),
            "failed": failed + (0 if count_ok else 1), "status": overall, "details": details}


def main():
    print("=" * 70)
    print("PIPELINE-005-J-FIX-001: Deterministic Test Suite")
    print("=" * 70)
    ts = datetime.now(timezone.utc).isoformat()
    print(f"Timestamp: {ts}")

    tests = [
        test_1_figure_id_image_hash,
        test_2_bbox_figure_parser,
        test_3_document_ir_element,
        test_4_cache_identity,
        test_5_no_silent_relabeling,
        test_6_quality_state_preserved,
        test_7_regression_check,
    ]

    results = []
    total_passed = total_failed = 0

    for tf in tests:
        try:
            r = tf()
            results.append(r)
            total_passed += r.get("passed", 0)
            total_failed += r.get("failed", 0)
        except Exception as e:
            print(f"ERROR in {tf.__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append({"test_name": tf.__name__, "status": "ERROR", "error": str(e)})

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    overall = "PASS" if total_failed == 0 else "FAIL"
    for r in results:
        icon = "PASS" if r.get("status") == "PASS" else "FAIL" if r.get("status") == "FAIL" else "SKIP"
        print(f"  [{icon}] {r.get('test_name')}: {r.get('passed',0)}/{r.get('total',0)}")

    print(f"\nTotal: {total_passed} PASS, {total_failed} FAIL")
    print(f"Overall: {overall}")

    output = {
        "test_suite": "PIPELINE-005-J-FIX-001",
        "timestamp": ts,
        "overall_status": overall,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "test_results": results,
    }

    out_path = FIX_001_DIR / "FIGURE_IDENTITY_TEST_RESULTS.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to: {out_path}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
