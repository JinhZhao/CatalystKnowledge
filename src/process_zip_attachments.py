# -*- coding: utf-8 -*-
"""Process ZIP attachments from Nature supplementary materials.

Safety checks:
- Detect path traversal attempts
- List all files with sizes
- Extract only safe files
- No execution of scripts or executables
"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from datetime import datetime


MANIFEST_PATH = Path(r"D:\Knowledge_World\data\test_corpus\unified_test_manifest.json")
OUTPUT_DIR = Path(r"D:\Knowledge_World\data\test_corpus\zip_processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def is_safe_path(path: str) -> bool:
    """Check if a path is safe (no traversal attempts)."""
    # Normalize path
    normalized = Path(path).as_posix()
    
    # Check for path traversal
    if ".." in normalized:
        return False
    
    # Check for absolute paths
    if normalized.startswith("/") or normalized.startswith("\\"):
        return False
    
    # Check for Windows absolute paths
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    
    return True


def is_executable(path: Path) -> bool:
    """Check if a file is executable/script."""
    executable_extensions = {
        ".exe", ".bat", ".cmd", ".com", ".scr", ".pif",
        ".py", ".pyw", ".pyc", ".pyo",
        ".js", ".jse", ".vbs", ".vbe", ".wsf", ".wsm", ".wsc",
        ".ps1", ".ps1xml", ".ps2", ".ps2xml",
        ".sh", ".bash", ".csh", ".ksh",
        ".msi", ".msp", ".mst",
        ".dll", ".so", ".dylib",
    }
    return path.suffix.lower() in executable_extensions


def process_zip(zip_path: Path) -> dict:
    """Process a single ZIP file with safety checks."""
    print(f"Processing: {zip_path.name}")
    
    file_hash = sha256_file(zip_path)
    file_size = zip_path.stat().st_size
    
    result = {
        "file_name": zip_path.name,
        "file_path": str(zip_path.resolve()),
        "file_size_bytes": file_size,
        "sha256": file_hash,
        "status": "OK",
        "error": None,
        "contents": [],
        "extracted_files": [],
        "safety_issues": []
    }
    
    extract_dir = OUTPUT_DIR / zip_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # List all files
            print(f"  Contents ({len(zf.namelist())} files):")
            
            for info in zf.infolist():
                file_info = {
                    "filename": info.filename,
                    "file_size": info.file_size,
                    "compress_size": info.compress_size,
                    "is_safe": is_safe_path(info.filename),
                    "is_executable": is_executable(Path(info.filename))
                }
                
                result["contents"].append(file_info)
                
                # Check safety
                if not file_info["is_safe"]:
                    issue = f"Path traversal detected: {info.filename}"
                    result["safety_issues"].append(issue)
                    print(f"    [UNSAFE] {issue}")
                elif file_info["is_executable"]:
                    issue = f"Executable file: {info.filename}"
                    result["safety_issues"].append(issue)
                    print(f"    [EXECUTABLE] {issue}")
                else:
                    print(f"    [OK] {info.filename} ({info.file_size:,} bytes)")
            
            # Extract safe files only
            if not result["safety_issues"]:
                print(f"  Extracting to: {extract_dir}")
                zf.extractall(extract_dir)
                
                # Record extracted files
                for extracted in extract_dir.rglob("*"):
                    if extracted.is_file():
                        result["extracted_files"].append({
                            "path": str(extracted.relative_to(extract_dir)),
                            "size": extracted.stat().st_size,
                            "sha256": sha256_file(extracted)
                        })
            else:
                print(f"  ⚠️  Skipping extraction due to safety issues")
                result["status"] = "BLOCKED_SAFETY"
    
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        print(f"  ERROR: {e}")
    
    return result


def main():
    print("=" * 80)
    print("ZIP Attachment Processor")
    print("=" * 80)
    print()
    
    # Load manifest
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    
    # Find ZIP files
    zip_docs = [
        doc for doc in manifest["documents"]
        if doc.get("document_type") == "supplementary_zip"
    ]
    
    print(f"Found {len(zip_docs)} ZIP files in manifest")
    print()
    
    results = []
    for doc in zip_docs:
        zip_path = Path(doc["file_path"])
        if not zip_path.exists():
            print(f"WARNING: File not found: {zip_path}")
            continue
        
        result = process_zip(zip_path)
        result["document_id"] = doc["document_id"]
        result["parent_document_id"] = doc.get("parent_document_id")
        result["doi"] = doc.get("doi")
        
        results.append(result)
        
        # Save individual result
        output_file = OUTPUT_DIR / f"{doc['document_id']}.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        print(f"  Saved: {output_file.name}")
        print()
    
    # Save summary
    summary = {
        "processed_at": datetime.now().isoformat(),
        "total_files": len(results),
        "successful": sum(1 for r in results if r["status"] == "OK"),
        "blocked_safety": sum(1 for r in results if r["status"] == "BLOCKED_SAFETY"),
        "failed": sum(1 for r in results if r["status"] == "FAILED"),
        "total_files_listed": sum(len(r["contents"]) for r in results),
        "total_files_extracted": sum(len(r["extracted_files"]) for r in results),
        "safety_issues": sum(len(r["safety_issues"]) for r in results),
        "results": results
    }
    
    summary_file = OUTPUT_DIR / "zip_processing_summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )
    
    print("=" * 80)
    print(f"Processing complete:")
    print(f"  Total ZIP files: {summary['total_files']}")
    print(f"  Successful: {summary['successful']}")
    print(f"  Blocked (safety): {summary['blocked_safety']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Files listed: {summary['total_files_listed']}")
    print(f"  Files extracted: {summary['total_files_extracted']}")
    print(f"  Safety issues: {summary['safety_issues']}")
    print(f"Summary saved: {summary_file}")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
