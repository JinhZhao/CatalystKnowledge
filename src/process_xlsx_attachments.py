# -*- coding: utf-8 -*-
"""Process XLSX attachments from Nature supplementary materials.

Extracts:
- Sheet names
- Cell positions (row, column)
- Cell values (preserving types: number, string, formula, null)
- Formulas and cached results where available
"""

import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime

import openpyxl
from openpyxl.utils import get_column_letter


# Load manifest to get XLSX file paths
MANIFEST_PATH = Path(r"D:\Knowledge_World\data\test_corpus\unified_test_manifest.json")
OUTPUT_DIR = Path(r"D:\Knowledge_World\data\test_corpus\xlsx_processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def cell_value_type(cell) -> str:
    """Determine the type of a cell value."""
    if cell.value is None:
        return "null"
    elif isinstance(cell.value, (int, float)):
        return "number"
    elif isinstance(cell.value, str):
        if cell.value.startswith("="):
            return "formula"
        return "string"
    elif isinstance(cell.value, datetime):
        return "datetime"
    elif isinstance(cell.value, bool):
        return "boolean"
    else:
        return "unknown"


def process_xlsx(xlsx_path: Path) -> dict:
    """Process a single XLSX file and extract structured data."""
    print(f"Processing: {xlsx_path.name}")
    
    file_hash = sha256_file(xlsx_path)
    file_size = xlsx_path.stat().st_size
    
    result = {
        "file_name": xlsx_path.name,
        "file_path": str(xlsx_path.resolve()),
        "file_size_bytes": file_size,
        "sha256": file_hash,
        "sheets": []
    }
    
    try:
        # Load workbook with data_only=False to get formulas
        wb = openpyxl.load_workbook(xlsx_path, data_only=False)
        
        for sheet_name in wb.sheetnames:
            print(f"  Sheet: {sheet_name}")
            ws = wb[sheet_name]
            
            sheet_data = {
                "sheet_name": sheet_name,
                "dimensions": ws.dimensions,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
                "cells": []
            }
            
            # Iterate through all cells
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cell_info = {
                            "row": cell.row,
                            "column": cell.column,
                            "column_letter": get_column_letter(cell.column),
                            "coordinate": cell.coordinate,
                            "value": cell.value,
                            "type": cell_value_type(cell),
                            "data_type": cell.data_type
                        }
                        
                        # If it's a formula, try to get cached value
                        if cell.data_type == 'f':  # formula
                            cell_info["formula"] = cell.value
                            # Load with data_only=True to get cached result
                            # (This requires reloading the workbook)
                        
                        sheet_data["cells"].append(cell_info)
            
            result["sheets"].append(sheet_data)
        
        # Now load with data_only=True to get cached formula results
        wb_data = openpyxl.load_workbook(xlsx_path, data_only=True)
        for sheet_name in wb_data.sheetnames:
            ws_data = wb_data[sheet_name]
            sheet_result = next((s for s in result["sheets"] if s["sheet_name"] == sheet_name), None)
            
            if sheet_result:
                for row in ws_data.iter_rows():
                    for cell in row:
                        if cell.data_type == 'f':  # formula
                            # Find matching cell in our result
                            cell_result = next(
                                (c for c in sheet_result["cells"] 
                                 if c["coordinate"] == cell.coordinate),
                                None
                            )
                            if cell_result:
                                cell_result["cached_value"] = cell.value
                                cell_result["cached_type"] = cell_value_type(cell)
        
        wb.close()
        wb_data.close()
        
        result["status"] = "OK"
        result["error"] = None
        
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        print(f"  ERROR: {e}")
    
    return result


def main():
    print("=" * 80)
    print("XLSX Attachment Processor")
    print("=" * 80)
    print()
    
    # Load manifest
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    
    # Find XLSX files
    xlsx_docs = [
        doc for doc in manifest["documents"]
        if doc.get("document_type") == "supplementary_xlsx"
    ]
    
    print(f"Found {len(xlsx_docs)} XLSX files in manifest")
    print()
    
    results = []
    for doc in xlsx_docs:
        xlsx_path = Path(doc["file_path"])
        if not xlsx_path.exists():
            print(f"WARNING: File not found: {xlsx_path}")
            continue
        
        result = process_xlsx(xlsx_path)
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
        "failed": sum(1 for r in results if r["status"] == "FAILED"),
        "results": results
    }
    
    summary_file = OUTPUT_DIR / "xlsx_processing_summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )
    
    print("=" * 80)
    print(f"Processing complete: {summary['successful']}/{summary['total_files']} successful")
    print(f"Summary saved: {summary_file}")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
