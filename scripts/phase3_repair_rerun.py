#!/usr/bin/env python3
"""
PIPELINE-001 Phase 3 Repair: Re-run 6 failed stages with fixed adapters.

Fixes applied:
1. _find_mineru_auto_dir now checks base/"main"/"auto" (bare output without doc_id subfolder)
2. num_unit: extraction_output_path + quantity_definitions_path parameter names
3. quality_gate: extraction_output_path parameter name
4. store: qa_report_path + extraction_output_path + store_dir parameter names

Skips: src001 (PASS), pdf_parse (PASS) — reuses existing output.
"""

import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

os.environ['LLM_API_BASE'] = 'https://api.siliconflow.cn/v1'
os.environ['LLM_API_KEY'] = 'sk-axbgbaleimmmpyepwhbgnpldiesqfmwerrwvxbxnscczspdv'
os.environ['LLM_MODEL'] = 'deepseek-ai/DeepSeek-V4-Flash'

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

RUN_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3" / "f02_e2e"

STAGE_DIRS = {
    "src001": RUN_DIR / "01_src001_identity",
    "pdf_parse": RUN_DIR / "02_pdf_parse",
    "document_ir": RUN_DIR / "03_document_ir",
    "figure_text": RUN_DIR / "04_figure_text",
    "extraction": RUN_DIR / "05_extraction",
    "num_unit": RUN_DIR / "06_num_unit",
    "quality_gate": RUN_DIR / "07_quality_gate",
    "store": RUN_DIR / "08_store",
    "report": RUN_DIR / "09_report",
}


def compute_sha256(file_path: Path) -> str:
    if not file_path.exists():
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_dir_sha256(dir_path: Path) -> Dict[str, str]:
    hashes = {}
    if dir_path.exists():
        for f in sorted(dir_path.rglob("*")):
            if f.is_file():
                rel = f.relative_to(dir_path)
                hashes[str(rel)] = compute_sha256(f)
    return hashes


def load_existing_manifest():
    manifest_file = RUN_DIR / "PHASE3_EXECUTION_MANIFEST.json"
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def run_document_ir():
    print("\n=== Stage 3: Document IR (REPAIR) ===")
    from catalyst_knowledge.pipeline.adapters.document_ir_adapter import run_document_ir

    mineru_output = str(STAGE_DIRS["pdf_parse"])
    output_dir = str(STAGE_DIRS["document_ir"])

    result = run_document_ir(
        document_id="F02",
        mineru_output=mineru_output,
        output_dir=output_dir,
    )

    status = "PASS" if result.get("document_ir_status") == "PASS" else "FAILED"
    print(f"  Result: {status}")
    if status == "FAILED":
        print(f"  Error: {result.get('error', 'unknown')}")

    output_hashes = {}
    for key in ["document_ir_path", "blocks_output", "content_list_output"]:
        if key in result and result[key]:
            p = Path(result[key])
            if p.exists():
                output_hashes[key] = compute_sha256(p)

    return status, result, output_hashes


def run_figure_text():
    print("\n=== Stage 4: Figure-Text Association (REPAIR) ===")
    from catalyst_knowledge.pipeline.adapters.figure_text_adapter import (
        run_figure_text_association,
    )

    mineru_output = str(STAGE_DIRS["pdf_parse"])
    output_dir = str(STAGE_DIRS["figure_text"])

    result = run_figure_text_association(
        document_id="F02",
        mineru_output=mineru_output,
        output_dir=output_dir,
    )

    status = result.get("figure_text_status", "FAILED")
    print(f"  Result: {status}")
    if status == "FAILED":
        print(f"  Error: {result.get('error', 'unknown')}")

    output_hashes = {}
    if "figure_associations_path" in result and result["figure_associations_path"]:
        p = Path(result["figure_associations_path"])
        if p.exists():
            output_hashes["figure_associations"] = compute_sha256(p)

    return status, result, output_hashes


def run_extraction():
    print("\n=== Stage 5: Six-Dimension Extraction (REPAIR - Real LLM) ===")
    from catalyst_knowledge.pipeline.adapters.extraction_adapter import run_extraction
    from catalyst_knowledge.pipeline.config_loader import ConfigLoader

    config = ConfigLoader()
    config.load(str(PROJECT_ROOT / "config" / "pipeline.yaml"))

    mineru_output = str(STAGE_DIRS["pdf_parse"])
    output_dir = str(STAGE_DIRS["extraction"])

    result = run_extraction(
        document_id="F02",
        mineru_output=mineru_output,
        output_dir=output_dir,
        config=config.config,
        use_cache=False,
    )

    status = result.get("extraction_status", "FAILED")
    print(f"  Result: {status}")
    if status == "FAILED":
        print(f"  Error: {result.get('error', 'unknown')}")

    output_hashes = compute_dir_sha256(STAGE_DIRS["extraction"] / "F02")
    return status, result, output_hashes


def run_num_unit():
    print("\n=== Stage 6: Num-Unit Normalization (REPAIR) ===")
    from catalyst_knowledge.pipeline.adapters.num_unit_adapter import (
        run_num_unit_normalization,
    )

    extraction_output = str(STAGE_DIRS["extraction"] / "F02")
    output_dir = str(STAGE_DIRS["num_unit"])
    quantity_defs = str(PROJECT_ROOT / "config" / "quantity_definitions.yaml")

    result = run_num_unit_normalization(
        document_id="F02",
        extraction_output_path=extraction_output,
        output_dir=output_dir,
        quantity_definitions_path=quantity_defs,
    )

    status = result.get("num_unit_status", "FAILED")
    print(f"  Result: {status}")
    if status == "FAILED":
        print(f"  Error: {result.get('error', 'unknown')}")

    output_hashes = {}
    if "num_unit_output_path" in result and result["num_unit_output_path"]:
        p = Path(result["num_unit_output_path"])
        if p.exists():
            output_hashes["num_unit_output"] = compute_sha256(p)

    return status, result, output_hashes


def run_quality_gate():
    print("\n=== Stage 7: Quality Gate (REPAIR) ===")
    from catalyst_knowledge.pipeline.adapters.quality_gate_adapter import (
        run_quality_gate,
    )

    extraction_output = str(STAGE_DIRS["extraction"] / "F02")
    output_dir = str(STAGE_DIRS["quality_gate"])

    result = run_quality_gate(
        document_id="F02",
        extraction_output_path=extraction_output,
        output_dir=output_dir,
    )

    status = result.get("qa_status", "FAILED")
    print(f"  Result: {status}")
    if status in ("FAILED", "PARTIAL"):
        print(f"  Details: pass={result.get('pass_count', 0)} fail={result.get('fail_count', 0)}")

    output_hashes = {}
    if "qa_report_path" in result and result["qa_report_path"]:
        p = Path(result["qa_report_path"])
        if p.exists():
            output_hashes["qa_report"] = compute_sha256(p)

    return status, result, output_hashes


def run_store():
    print("\n=== Stage 8: Canonical Store (REPAIR) ===")
    from catalyst_knowledge.pipeline.adapters.store_adapter import (
        run_canonical_store,
    )

    store_dir = str(STAGE_DIRS["store"])
    extraction_output = str(STAGE_DIRS["extraction"] / "F02")
    qa_report = str(STAGE_DIRS["quality_gate"] / "F02_qa_report.json")

    result = run_canonical_store(
        document_id="F02",
        qa_report_path=qa_report,
        extraction_output_path=extraction_output,
        store_dir=store_dir,
    )

    status = result.get("store_status", "FAILED")
    print(f"  Result: {status}")
    if status == "FAILED":
        print(f"  Error: {result.get('error', 'unknown')}")

    output_hashes = compute_dir_sha256(STAGE_DIRS["store"])
    return status, result, output_hashes


def run_report():
    print("\n=== Stage 9: Report Generation (RE-RUN with fresh data) ===")
    from catalyst_knowledge.pipeline.adapters.report_adapter import (
        run_report_generation,
    )

    store_path = str(STAGE_DIRS["store"])
    output_dir = str(STAGE_DIRS["report"])

    result = run_report_generation(
        document_id="F02",
        store_path=store_path,
        output_dir=output_dir,
    )

    status = result.get("report_status", "FAILED")
    print(f"  Result: {status}")

    output_hashes = {}
    report_dir = STAGE_DIRS["report"]
    if report_dir.exists():
        output_hashes = compute_dir_sha256(report_dir)

    return status, result, output_hashes


def main():
    print("=" * 70)
    print("PIPELINE-001 Phase 3 REPAIR: Re-running 6 failed stages")
    print(f"Start: {datetime.now().isoformat()}")
    print("=" * 70)

    existing = load_existing_manifest()
    repair_start = datetime.now()

    stages = [
        ("document_ir", run_document_ir),
        ("figure_text", run_figure_text),
        ("extraction", run_extraction),
        ("num_unit", run_num_unit),
        ("quality_gate", run_quality_gate),
        ("store", run_store),
        ("report", run_report),
    ]

    results = {}
    statuses = {}
    hashes = {}

    for stage_name, stage_func in stages:
        try:
            status, output, output_hashes = stage_func()
            statuses[stage_name] = status
            results[stage_name] = {
                "stage_name": stage_name,
                "status": status,
                "execution_type": "FRESH_EXECUTION",
                "output": output,
                "error": None,
                "timestamp": datetime.now().isoformat(),
            }
            hashes[stage_name] = {
                "input": {},
                "output": output_hashes,
            }
        except Exception as e:
            print(f"\n  ERROR: {stage_name} raised exception: {e}")
            traceback.print_exc()
            statuses[stage_name] = "FAILED"
            results[stage_name] = {
                "stage_name": stage_name,
                "status": "FAILED",
                "execution_type": "FRESH_EXECUTION",
                "output": {},
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            hashes[stage_name] = {"input": {}, "output": {}}

    repair_end = datetime.now()
    duration = (repair_end - repair_start).total_seconds()

    if existing:
        for stage_name in results:
            existing["stages"][stage_name] = results[stage_name]
        for stage_name in statuses:
            existing["stage_status_summary"][stage_name] = statuses[stage_name]
        for stage_name in hashes:
            existing["stage_hashes"][stage_name] = hashes[stage_name]
        existing["repair_timestamp"] = repair_end.isoformat()
        existing["repair_duration_seconds"] = duration
        manifest = existing
    else:
        manifest = {
            "run_id": "phase3_f02_e2e_repair",
            "document_id": "F02",
            "phase": 3,
            "repair_timestamp": repair_end.isoformat(),
            "repair_duration_seconds": duration,
            "stages": results,
            "stage_status_summary": statuses,
            "stage_hashes": hashes,
        }

    manifest_file = RUN_DIR / "PHASE3_REPAIR_MANIFEST.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'=' * 70}")
    print(f"Phase 3 Repair Complete")
    print(f"Duration: {duration:.1f}s")
    print(f"Stage Results:")
    for name, status in statuses.items():
        marker = "OK" if status in ("PASS", "PARTIAL", "WARN") else "FAIL"
        print(f"  [{marker}] {name}: {status}")

    pass_count = sum(1 for s in statuses.values() if s in ("PASS", "PARTIAL", "WARN"))
    fail_count = len(statuses) - pass_count
    print(f"\nPass: {pass_count}/{len(statuses)}")
    if fail_count > 0:
        print(f"FAIL: {fail_count}/{len(statuses)}")
    print(f"Manifest: {manifest_file}")
    print(f"{'=' * 70}")

    return manifest


if __name__ == "__main__":
    main()
