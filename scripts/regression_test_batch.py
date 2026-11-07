#!/usr/bin/env python3
"""
P0回归测试：选取3份不同类型PDF验证批处理脚本
- F02: T1 Frontiers论文
- P02: T2 Nature SI
- PAT02: T3 专利
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

OUTPUT_BASE = Path(r"D:\Knowledge_World\data\test_corpus\mineru_output")
MANIFEST_PATH = Path(r"D:\Knowledge_World\data\test_corpus\unified_test_manifest.json")


def load_test_files():
    """Load test files from manifest"""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    docs = {d["document_id"]: d for d in manifest["documents"]}
    
    test_ids = [
        "F02",  # T1 Frontiers paper
        "P02_41467_2025_59321_MOESM1_ESM",  # T2 Nature SI
        "PAT02",  # T3 Patent
    ]
    
    test_files = []
    for doc_id in test_ids:
        if doc_id in docs:
            doc = docs[doc_id]
            test_files.append({
                "id": doc_id,
                "path": doc["file_path"],
                "group": doc["group"],
            })
    
    return test_files


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)


def test_single(doc, index, total):
    doc_id = doc["id"]
    pdf_path = doc["path"]
    output_dir = OUTPUT_BASE / f"{doc_id}_regression"
    
    log(f"\n{'='*70}")
    log(f"[{index}/{total}] Regression test: {doc_id} ({doc['group']})")
    log(f"Input: {pdf_path}")
    log(f"Output: {output_dir}")
    
    # Check if file exists
    if not Path(pdf_path).exists():
        log(f"ERROR: File not found: {pdf_path}", "ERROR")
        return {"id": doc_id, "status": "FILE_NOT_FOUND"}
    
    start = time.time()
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = ["magic-pdf", "-p", pdf_path, "-o", str(output_dir), "-m", "auto"]
        log(f"Command: {' '.join(cmd)}")
        
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            encoding="utf-8",
            errors="replace",
        )
        
        elapsed = time.time() - start
        
        if proc.returncode == 0:
            # Check output
            auto_dir = output_dir / "main" / "auto"
            if not auto_dir.exists():
                auto_dir = output_dir / "auto"
            
            if auto_dir.exists():
                md_files = list(auto_dir.glob("*.md"))
                json_files = list(auto_dir.glob("*.json"))
                
                log(f"PASS in {elapsed:.1f}s: {len(md_files)} MD, {len(json_files)} JSON")
                return {
                    "id": doc_id,
                    "status": "PASS",
                    "time": elapsed,
                    "md_count": len(md_files),
                    "json_count": len(json_files),
                    "output_dir": str(auto_dir),
                }
            else:
                log(f"WARN: No auto directory found", "WARN")
                return {"id": doc_id, "status": "NO_OUTPUT", "time": elapsed}
        else:
            log(f"FAIL: returncode={proc.returncode}", "ERROR")
            log(f"STDERR: {proc.stderr[:500]}", "ERROR")
            return {
                "id": doc_id,
                "status": "FAILED",
                "time": elapsed,
                "error": proc.stderr[:500],
            }
    
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        log(f"TIMEOUT after {elapsed:.1f}s", "ERROR")
        return {"id": doc_id, "status": "TIMEOUT", "time": elapsed}
    
    except Exception as e:
        elapsed = time.time() - start
        log(f"EXCEPTION: {e}", "ERROR")
        return {"id": doc_id, "status": "EXCEPTION", "time": elapsed, "error": str(e)}


def main():
    log("="*70)
    log("P0 Regression Test: 3 PDFs (T1 paper, T2 SI, T3 patent)")
    log("="*70)
    
    test_files = load_test_files()
    log(f"Loaded {len(test_files)} test files from manifest")
    
    results = []
    for i, doc in enumerate(test_files, 1):
        result = test_single(doc, i, len(test_files))
        results.append(result)
    
    # Summary
    log(f"\n{'='*70}")
    log("Regression Test Summary")
    log("="*70)
    
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    log(f"PASS: {pass_count}/{len(results)}")
    
    for r in results:
        status = r["status"]
        time_str = f"{r.get('time', 0):.1f}s" if "time" in r else "N/A"
        log(f"  {r['id']}: {status} ({time_str})")
    
    # Save results
    result_file = OUTPUT_BASE / "regression_test_results.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log(f"\nResults saved: {result_file}")
    
    return 0 if pass_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
