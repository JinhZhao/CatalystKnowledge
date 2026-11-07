"""Table Science Adapter — Generate science records from table parser output.

Minimal adapter for 007-R2: converts TableParser cell data into structured
science records with SourceAnchor, evidence_type, and quality_state.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from ..stage_adapter import StageAdapter, DataContract
logger = logging.getLogger(__name__)


def _generate_table_science_records(table_parser_data: dict, document_id: str) -> list[dict]:
    """Generate science records from table parser cell data."""
    records = []
    tables = table_parser_data.get('tables', [])
    
    for table in tables:
        table_id = table.get('table_id', 'unknown')
        rows = table.get('rows', [])
        headers = table.get('headers', [])
        
        # Extract header names for statement generation
        header_names = []
        if headers and len(headers) > 0:
            header_row = headers[0]
            if isinstance(header_row, dict) and 'cells' in header_row:
                header_names = [cell.get('content', f'col_{i}') for i, cell in enumerate(header_row['cells'])]
        
        for row in rows:
            cells = row.get('cells', [])
            for cell in cells:
                if cell.get('is_header'):
                    continue
                raw_text = cell.get('raw_text', '').strip()
                if not raw_text:
                    continue
                
                row_idx = cell.get('row_idx', 0)
                col_idx = cell.get('col_idx', 0)
                header_name = header_names[col_idx] if col_idx < len(header_names) else f'col_{col_idx}'
                
                record_id = f"TABLE-{table_id}-R{row_idx}C{col_idx}"
                record = {
                    "record_id": record_id,
                    "table_id": table_id,
                    "document_id": document_id,
                    "namespace": "table_science",
                    "statement": f"{table_id} row {row_idx} {header_name}: {raw_text}",
                    "evidence_type": "TEXT_SUPPORTED_STATEMENT",
                    "quality_state": "CANDIDATE",
                    "confidence": "HIGH" if cell.get('verification_status') == 'UNVERIFIED' else "MEDIUM",
                    "source_anchor": {
                        "document_id": document_id,
                        "element_id": table.get('document_ir_element_id'),
                        "element_type": "table",
                        "page_idx": table.get('page_idx'),
                        "bbox": table.get('bbox'),
                        "image_sha256": table.get('image_sha256'),
                        "anchor_version": "007-R2-table-v1"
                    },
                    "raw_text": raw_text,
                    "header": header_name,
                    "row_idx": row_idx,
                    "col_idx": col_idx,
                    "unit": cell.get('unit'),
                    "verification_status": cell.get('verification_status', 'UNVERIFIED'),
                    "store_version": "007-R2-table",
                    "store_timestamp": datetime.now(timezone.utc).isoformat(),
                    "store_source": "TableParser cell data via table_science adapter"
                }
                records.append(record)
    
    return records


def run_table_science_stage(
    document_id: str,
    table_parser_output_path: str = "",
    output_dir: str = "",
    namespace: str = "",
    **kwargs
) -> dict:
    """Pipeline stage entry point for table science record generation."""
    logger.info(f"[table_science] document_id={document_id}")
    
    if not table_parser_output_path:
        return {
            "document_id": document_id,
            "table_science_status": "SKIP",
            "table_science_output_path": "",
            "total_records": 0,
            "implementation_status": "MISSING_INPUT",
            "namespace": namespace or document_id
        }
    
    tp_path = Path(table_parser_output_path)
    if not tp_path.exists():
        return {
            "document_id": document_id,
            "table_science_status": "SKIP",
            "table_science_output_path": "",
            "total_records": 0,
            "implementation_status": "FILE_NOT_FOUND",
            "namespace": namespace or document_id
        }
    
    with open(tp_path, encoding='utf-8') as f:
        tp_data = json.load(f)
    
    records = _generate_table_science_records(tp_data, document_id)
    
    # Write output
    out_dir = Path(output_dir) if output_dir else tp_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / f"{document_id}_table_science_records.json"
    
    output_data = {
        "adapter_version": "007-R2-table-science-v1",
        "document_id": document_id,
        "namespace": namespace or document_id,
        "total_records": len(records),
        "tables_processed": len(tp_data.get('tables', [])),
        "adapter_status": "PASS" if len(records) > 0 else "PARTIAL",
        "records": records,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"[table_science] Generated {len(records)} records from {len(tp_data.get('tables', []))} tables")
    
    return {
        "document_id": document_id,
        "table_science_status": "PASS" if len(records) > 0 else "PARTIAL",
        "table_science_output_path": str(output_file),
        "total_records": len(records),
        "tables_processed": len(tp_data.get('tables', [])),
        "implementation_status": "IMPLEMENTED",
        "namespace": namespace or document_id
    }


def create_table_science_adapter(config) -> StageAdapter:
    """Factory: create table_science stage adapter."""
    from ..config_loader import ConfigLoader
    cfg = config if isinstance(config, dict) else {}
    
    stage_cfg = cfg.get('stages', {}).get('table_science', {})
    timeout = stage_cfg.get('timeout_seconds', 120)
    
    adapter = StageAdapter(
        stage_name="table_science",
        version="007-R2-v1",
        input_contract=DataContract(
            required_inputs=["document_id", "table_parser_output_path"],
            optional_inputs=["namespace", "output_dir"],
        ),
        output_contract=DataContract(
            required_outputs=["table_science_status", "table_science_output_path", "total_records"],
            optional_outputs=["tables_processed", "implementation_status", "namespace"],
        ),
        dependencies=["table_parser"],
        timeout_seconds=timeout,
    )
    
    adapter.set_function(run_table_science_stage)
    return adapter
