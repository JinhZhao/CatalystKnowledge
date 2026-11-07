# -*- coding: utf-8 -*-
"""Optimized XLSX processor using SQLite for structured cell data.

Avoids memory explosion by:
- Using SQLite instead of JSON for cell storage
- Streaming row-by-row processing
- Preserving all metadata (sheet names, cell positions, types, formulas)
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

import openpyxl
from openpyxl.utils import get_column_letter


MANIFEST_PATH = Path(r"D:\Knowledge_World\data\test_corpus\unified_test_manifest.json")
OUTPUT_DIR = Path(r"D:\Knowledge_World\data\test_corpus\xlsx_sqlite")
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


def create_database(db_path: Path) -> sqlite3.Connection:
    """Create SQLite database with schema for spreadsheet data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # File metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_metadata (
            id INTEGER PRIMARY KEY,
            document_id TEXT,
            parent_document_id TEXT,
            doi TEXT,
            file_name TEXT,
            file_path TEXT,
            file_size_bytes INTEGER,
            sha256 TEXT,
            processed_at TEXT,
            status TEXT,
            error TEXT
        )
    """)
    
    # Sheet metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sheets (
            id INTEGER PRIMARY KEY,
            file_metadata_id INTEGER,
            sheet_name TEXT,
            dimensions TEXT,
            max_row INTEGER,
            max_column INTEGER,
            FOREIGN KEY (file_metadata_id) REFERENCES file_metadata(id)
        )
    """)
    
    # Cell data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cells (
            id INTEGER PRIMARY KEY,
            sheet_id INTEGER,
            row_num INTEGER,
            col_num INTEGER,
            col_letter TEXT,
            coordinate TEXT,
            value TEXT,
            value_type TEXT,
            data_type TEXT,
            formula TEXT,
            cached_value TEXT,
            cached_type TEXT,
            FOREIGN KEY (sheet_id) REFERENCES sheets(id)
        )
    """)
    
    # Indexes for fast querying
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cells_sheet ON cells(sheet_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cells_coordinate ON cells(sheet_id, coordinate)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cells_type ON cells(value_type)")
    
    conn.commit()
    return conn


def process_xlsx_to_sqlite(xlsx_path: Path, document_info: dict) -> dict:
    """Process XLSX file and store in SQLite database."""
    print(f"Processing: {xlsx_path.name}")
    
    file_hash = sha256_file(xlsx_path)
    file_size = xlsx_path.stat().st_size
    
    # Create database
    db_name = f"{xlsx_path.stem}.db"
    db_path = OUTPUT_DIR / db_name
    conn = create_database(db_path)
    cursor = conn.cursor()
    
    result = {
        "file_name": xlsx_path.name,
        "file_path": str(xlsx_path.resolve()),
        "file_size_bytes": file_size,
        "sha256": file_hash,
        "database": str(db_path.resolve()),
        "database_size_bytes": 0,
        "sheets": [],
        "total_cells": 0,
        "status": "OK",
        "error": None
    }
    
    try:
        # Insert file metadata
        cursor.execute("""
            INSERT INTO file_metadata 
            (document_id, parent_document_id, doi, file_name, file_path, 
             file_size_bytes, sha256, processed_at, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            document_info.get("document_id"),
            document_info.get("parent_document_id"),
            document_info.get("doi"),
            xlsx_path.name,
            str(xlsx_path.resolve()),
            file_size,
            file_hash,
            datetime.now().isoformat(),
            "OK",
            None
        ))
        file_metadata_id = cursor.lastrowid
        
        # Load workbook with formulas
        wb = openpyxl.load_workbook(xlsx_path, data_only=False)
        
        for sheet_name in wb.sheetnames:
            print(f"  Sheet: {sheet_name}")
            ws = wb[sheet_name]
            
            # Insert sheet metadata
            cursor.execute("""
                INSERT INTO sheets 
                (file_metadata_id, sheet_name, dimensions, max_row, max_column)
                VALUES (?, ?, ?, ?, ?)
            """, (
                file_metadata_id,
                sheet_name,
                ws.dimensions,
                ws.max_row,
                ws.max_column
            ))
            sheet_id = cursor.lastrowid
            
            sheet_info = {
                "sheet_name": sheet_name,
                "dimensions": ws.dimensions,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
                "cell_count": 0
            }
            
            # Process cells in batches
            cell_batch = []
            batch_size = 1000
            
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cell_data = (
                            sheet_id,
                            cell.row,
                            cell.column,
                            get_column_letter(cell.column),
                            cell.coordinate,
                            str(cell.value) if cell.value is not None else None,
                            cell_value_type(cell),
                            cell.data_type,
                            cell.value if cell.data_type == 'f' else None,  # formula
                            None,  # cached_value (will fill later)
                            None   # cached_type
                        )
                        cell_batch.append(cell_data)
                        
                        if len(cell_batch) >= batch_size:
                            cursor.executemany("""
                                INSERT INTO cells 
                                (sheet_id, row_num, col_num, col_letter, coordinate,
                                 value, value_type, data_type, formula, cached_value, cached_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, cell_batch)
                            conn.commit()
                            cell_batch = []
            
            # Insert remaining cells
            if cell_batch:
                cursor.executemany("""
                    INSERT INTO cells 
                    (sheet_id, row_num, col_num, col_letter, coordinate,
                     value, value_type, data_type, formula, cached_value, cached_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, cell_batch)
                conn.commit()
            
            # Count cells for this sheet
            cursor.execute("SELECT COUNT(*) FROM cells WHERE sheet_id = ?", (sheet_id,))
            cell_count = cursor.fetchone()[0]
            sheet_info["cell_count"] = cell_count
            result["total_cells"] += cell_count
            
            result["sheets"].append(sheet_info)
        
        # Now load with data_only=True to get cached formula results
        print(f"  Loading cached values...")
        wb_data = openpyxl.load_workbook(xlsx_path, data_only=True)
        
        for sheet_name in wb_data.sheetnames:
            ws_data = wb_data[sheet_name]
            
            # Get sheet_id
            cursor.execute("""
                SELECT id FROM sheets 
                WHERE file_metadata_id = ? AND sheet_name = ?
            """, (file_metadata_id, sheet_name))
            sheet_row = cursor.fetchone()
            if not sheet_row:
                continue
            sheet_id = sheet_row[0]
            
            # Update cached values for formula cells
            update_batch = []
            for row in ws_data.iter_rows():
                for cell in row:
                    if cell.data_type == 'f':  # formula
                        cached_val = cell.value
                        cached_type = cell_value_type(cell) if cached_val is not None else "null"
                        update_batch.append((
                            str(cached_val) if cached_val is not None else None,
                            cached_type,
                            sheet_id,
                            cell.coordinate
                        ))
            
            if update_batch:
                cursor.executemany("""
                    UPDATE cells 
                    SET cached_value = ?, cached_type = ?
                    WHERE sheet_id = ? AND coordinate = ?
                """, update_batch)
                conn.commit()
        
        wb.close()
        wb_data.close()
        conn.close()
        
        # Get database size
        result["database_size_bytes"] = db_path.stat().st_size
        
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        print(f"  ERROR: {e}")
        conn.close()
    
    return result


def main():
    print("=" * 80)
    print("Optimized XLSX Processor (SQLite)")
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
        
        result = process_xlsx_to_sqlite(xlsx_path, doc)
        results.append(result)
        
        # Save individual result metadata
        metadata_file = OUTPUT_DIR / f"{doc['document_id']}_metadata.json"
        metadata_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        print(f"  Metadata saved: {metadata_file.name}")
        print()
    
    # Save summary
    summary = {
        "processed_at": datetime.now().isoformat(),
        "total_files": len(results),
        "successful": sum(1 for r in results if r["status"] == "OK"),
        "failed": sum(1 for r in results if r["status"] == "FAILED"),
        "total_cells": sum(r["total_cells"] for r in results),
        "total_database_size_bytes": sum(r["database_size_bytes"] for r in results),
        "results": results
    }
    
    summary_file = OUTPUT_DIR / "processing_summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )
    
    print("=" * 80)
    print(f"Processing complete:")
    print(f"  Total files: {summary['total_files']}")
    print(f"  Successful: {summary['successful']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Total cells: {summary['total_cells']:,}")
    print(f"  Total database size: {summary['total_database_size_bytes'] / 1024 / 1024:.1f} MB")
    print(f"  Summary saved: {summary_file}")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
