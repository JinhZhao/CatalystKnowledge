# -*- coding: utf-8 -*-
"""Build unified test manifest for FLOW-VERIFY-001.

Scans two download directories, verifies file integrity, and creates
a unified manifest with absolute paths (no file copying).
"""

import hashlib
import json
import sys
from pathlib import Path

# Paths
FRONTIERS_DIR = Path(r"D:\Knowledge_World\_test_download_frontiers\Frontiers_Catalysis_PDF_Alternative_Kit\downloaded_frontiers")
NATURE_DIR = Path(r"D:\Knowledge_World\_download_kit\downloaded_corpus")
OUTPUT_DIR = Path(r"D:\Knowledge_World\data\test_corpus")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path, chunk_size: int = 8192) -> str:
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def verify_signature(path: Path) -> tuple[bool, str]:
    """Verify file signature (magic bytes)."""
    try:
        with open(path, "rb") as f:
            header = f.read(8)
        
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            # PDF: %PDF-
            valid = header.lstrip()[:5] == b"%PDF-"
            return valid, "PDF" if valid else "INVALID"
        elif suffix in (".xlsx", ".docx", ".zip"):
            # ZIP-based: PK\x03\x04
            valid = header[:4] == b"PK\x03\x04"
            return valid, "ZIP-based" if valid else "INVALID"
        elif suffix == ".png":
            # PNG: \x89PNG\r\n\x1a\n
            valid = header[:8] == b"\x89PNG\r\n\x1a\n"
            return valid, "PNG" if valid else "INVALID"
        else:
            return True, "UNKNOWN"
    except Exception as e:
        return False, f"ERROR: {e}"


def scan_frontiers_papers() -> list[dict]:
    """Scan Frontiers papers (T1 group)."""
    papers_dir = FRONTIERS_DIR / "papers"
    manifest_path = FRONTIERS_DIR / "manifest.csv"
    report_path = FRONTIERS_DIR / "download_report.json"
    
    # Load metadata from download report
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"papers": []}
    meta_map = {p["id"]: p for p in report.get("papers", [])}
    
    results = []
    for paper_dir in sorted(papers_dir.iterdir()):
        if not paper_dir.is_dir():
            continue
        
        paper_id = paper_dir.name  # F01, F02, etc.
        pdf_path = paper_dir / "main.pdf"
        
        if not pdf_path.exists():
            continue
        
        meta = meta_map.get(paper_id, {})
        file_hash = sha256_file(pdf_path)
        sig_valid, sig_type = verify_signature(pdf_path)
        
        results.append({
            "document_id": paper_id,
            "group": "T1_Frontiers_Paper",
            "document_type": "research_article",
            "file_path": str(pdf_path.resolve()),
            "file_size_bytes": pdf_path.stat().st_size,
            "sha256": file_hash,
            "signature_valid": sig_valid,
            "signature_type": sig_type,
            "doi": meta.get("doi", ""),
            "title": meta.get("title", ""),
            "source_url": meta.get("source_url", ""),
            "publisher_pdf_urls": meta.get("publisher_pdf_urls", []),
            "focus": meta.get("focus", ""),
            "parent_document_id": None,
            "notes": "Complete research article from Frontiers in Chemistry"
        })
    
    return results


def scan_nature_supplements() -> list[dict]:
    """Scan Nature supplementary materials (T2 group)."""
    attachments_dir = NATURE_DIR / "attachments"
    sources_path = NATURE_DIR / "sources.json"
    
    # Load metadata from sources.json
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {"papers": []}
    paper_map = {p["id"]: p for p in sources.get("papers", [])}
    
    results = []
    if not attachments_dir.exists():
        return results
    
    for paper_dir in sorted(attachments_dir.iterdir()):
        if not paper_dir.is_dir():
            continue
        
        paper_id = paper_dir.name  # P01, P02, etc.
        meta = paper_map.get(paper_id, {})
        
        for file_path in sorted(paper_dir.iterdir()):
            if not file_path.is_file():
                continue
            
            file_hash = sha256_file(file_path)
            sig_valid, sig_type = verify_signature(file_path)
            
            # Determine document type from filename
            fname = file_path.name
            if "MOESM" in fname and fname.endswith(".pdf"):
                doc_type = "supplementary_pdf"
            elif fname.endswith(".xlsx"):
                doc_type = "supplementary_xlsx"
            elif fname.endswith(".zip"):
                doc_type = "supplementary_zip"
            else:
                doc_type = "supplementary_other"
            
            results.append({
                "document_id": f"{paper_id}_{file_path.stem}",
                "group": "T2_Nature_Supplement",
                "document_type": doc_type,
                "file_path": str(file_path.resolve()),
                "file_size_bytes": file_path.stat().st_size,
                "sha256": file_hash,
                "signature_valid": sig_valid,
                "signature_type": sig_type,
                "doi": meta.get("doi", ""),
                "title": meta.get("title", ""),
                "source_url": "",
                "publisher_pdf_urls": [],
                "focus": meta.get("focus", ""),
                "parent_document_id": paper_id,
                "filename": fname,
                "notes": f"Nature Communications supplementary material for {paper_id}"
            })
    
    return results


def scan_patents() -> list[dict]:
    """Scan patent PDFs (T3 group)."""
    patents_dir = NATURE_DIR / "patents"
    sources_path = NATURE_DIR / "sources.json"
    
    # Load metadata
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {"patents": []}
    patent_map = {p["id"]: p for p in sources.get("patents", [])}
    
    results = []
    if not patents_dir.exists():
        return results
    
    for pdf_path in sorted(patents_dir.iterdir()):
        if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
            continue
        
        # Extract patent number from filename
        patent_num = pdf_path.stem  # e.g., US20100029974A1
        
        # Find matching metadata
        meta = None
        patent_id = None
        for pid, pm in patent_map.items():
            if pm.get("publication_number") == patent_num:
                meta = pm
                patent_id = pid
                break
        
        file_hash = sha256_file(pdf_path)
        sig_valid, sig_type = verify_signature(pdf_path)
        
        results.append({
            "document_id": patent_id or patent_num,
            "group": "T3_Patent",
            "document_type": "patent",
            "file_path": str(pdf_path.resolve()),
            "file_size_bytes": pdf_path.stat().st_size,
            "sha256": file_hash,
            "signature_valid": sig_valid,
            "signature_type": sig_type,
            "doi": "",
            "title": meta.get("title", "") if meta else "",
            "source_url": meta.get("source_page", "") if meta else "",
            "publisher_pdf_urls": [meta.get("pdf_url", "")] if meta else [],
            "publication_number": patent_num,
            "focus": meta.get("focus", "") if meta else "",
            "parent_document_id": None,
            "notes": "Public patent from Google Patents"
        })
    
    return results


def main():
    print("=" * 80)
    print("FLOW-VERIFY-001: Unified Test Manifest Builder")
    print("=" * 80)
    print()
    
    # Scan all three groups
    print("[1/4] Scanning Frontiers papers (T1)...")
    t1_docs = scan_frontiers_papers()
    print(f"  Found {len(t1_docs)} documents")
    
    print("[2/4] Scanning Nature supplements (T2)...")
    t2_docs = scan_nature_supplements()
    print(f"  Found {len(t2_docs)} documents")
    
    print("[3/4] Scanning patents (T3)...")
    t3_docs = scan_patents()
    print(f"  Found {len(t3_docs)} documents")
    
    # Combine all
    all_docs = t1_docs + t2_docs + t3_docs
    
    # Statistics
    total_files = len(all_docs)
    valid_sigs = sum(1 for d in all_docs if d["signature_valid"])
    total_size = sum(d["file_size_bytes"] for d in all_docs)
    
    print()
    print("[4/4] Summary:")
    print(f"  Total documents: {total_files}")
    print(f"  Valid signatures: {valid_sigs}/{total_files}")
    print(f"  Total size: {total_size / 1024 / 1024:.1f} MB")
    print(f"  T1 Frontiers: {len(t1_docs)}")
    print(f"  T2 Nature SI: {len(t2_docs)}")
    print(f"  T3 Patents:   {len(t3_docs)}")
    
    # Save manifest
    manifest_path = OUTPUT_DIR / "unified_test_manifest.json"
    manifest_data = {
        "project": "Catalyst Knowledge Base V2",
        "task": "FLOW-VERIFY-001",
        "created": "2026-11-03",
        "description": "Unified test corpus manifest with absolute paths (no file copying)",
        "summary": {
            "total_documents": total_files,
            "valid_signatures": valid_sigs,
            "total_size_bytes": total_size,
            "groups": {
                "T1_Frontiers_Paper": len(t1_docs),
                "T2_Nature_Supplement": len(t2_docs),
                "T3_Patent": len(t3_docs)
            }
        },
        "documents": all_docs
    }
    
    manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Manifest saved: {manifest_path}")
    
    # Print sample entries
    print()
    print("Sample entries:")
    for doc in all_docs[:3]:
        print(f"  {doc['document_id']}: {doc['group']} - {doc['file_size_bytes']:,} bytes - {doc['signature_type']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
