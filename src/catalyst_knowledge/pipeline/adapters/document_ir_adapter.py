"""Adapter for document_ir_enhancer_v2.py — Document IR with Element IDs.

Wraps the existing document_ir_enhancer_v2.py functions to support:
- Single-document processing
- Config-driven paths
- Proper input/output recording
- Unified output contract for downstream stages
- Namespace support for multi-document scenarios
- Hierarchy tracking (block → line → span)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)

_SCRIPT_LOADED = False
_doc_ir_module = None


@dataclass
class DocumentIRHierarchy:
    """Tracks the hierarchical structure of a document."""
    total_blocks: int = 0
    total_lines: int = 0
    total_spans: int = 0
    blocks_by_type: dict[str, int] = field(default_factory=dict)
    pages_with_content: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_blocks": self.total_blocks,
            "total_lines": self.total_lines,
            "total_spans": self.total_spans,
            "blocks_by_type": self.blocks_by_type,
            "pages_with_content": self.pages_with_content,
        }


@dataclass
class DocumentIRResult:
    """Unified output from Document IR processing.
    
    This is the contract that downstream stages depend on.
    """
    document_id: str
    namespace: str  # Document namespace (e.g., "F02", "P01")
    document_ir_path: Path
    blocks_output: Path
    content_list_output: Path
    element_count: int
    hierarchy: DocumentIRHierarchy
    status: str  # PASS, FAILED, SKIPPED
    error: Optional[str] = None
    source_anchor_schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "document_ir_path": str(self.document_ir_path),
            "blocks_output": str(self.blocks_output),
            "content_list_output": str(self.content_list_output),
            "element_count": self.element_count,
            "hierarchy": self.hierarchy.to_dict(),
            "status": self.status,
            "error": self.error,
            "source_anchor_schema_version": self.source_anchor_schema_version,
        }

    def get_element_id_prefix(self) -> str:
        """Return the element ID prefix for this document."""
        return f"{self.namespace}_p"

    def validate_element_id(self, element_id: str) -> bool:
        """Check if an element ID belongs to this document's namespace."""
        return element_id.startswith(self.get_element_id_prefix())


def _load_doc_ir_module():
    """Dynamically load document_ir_enhancer_v2.py from scripts/."""
    global _SCRIPT_LOADED, _doc_ir_module
    if _SCRIPT_LOADED and _doc_ir_module is not None:
        return _doc_ir_module

    project_root = Path(__file__).parent.parent.parent.parent.parent
    script_path = project_root / "scripts" / "document_ir_enhancer_v2.py"
    if not script_path.exists():
        raise FileNotFoundError(f"document_ir_enhancer_v2.py not found at {script_path}")

    spec = importlib.util.spec_from_file_location("document_ir_enhancer_v2", script_path)
    _doc_ir_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_doc_ir_module)
    _SCRIPT_LOADED = True
    return _doc_ir_module


def _find_mineru_auto_dir(mineru_output: str, document_id: str) -> Optional[Path]:
    """Find the auto/ directory for a document's MinerU output."""
    base = Path(mineru_output)
    if not base.exists():
        return None
    candidates = [
        base / f"{document_id}_batch" / "main" / "auto",
        base / f"{document_id}_batch" / "auto",
        base / document_id / "main" / "auto",
        base / document_id / "auto",
        base / "main" / "auto",
        base / "auto",
    ]
    for c in candidates:
        if c.exists() and (c / "main_content_list.json").exists():
            return c
        if c.exists() and list(c.glob("*content_list.json")):
            return c

    for d in base.iterdir():
        if d.is_dir() and document_id in d.name:
            auto = d / "main" / "auto"
            if auto.exists():
                return auto
            auto = d / "auto"
            if auto.exists():
                return auto
    return None


def _compute_hierarchy(blocks_with_ids: list[dict]) -> DocumentIRHierarchy:
    """Compute hierarchy statistics from blocks with IDs."""
    hierarchy = DocumentIRHierarchy()
    pages_set = set()
    
    for block in blocks_with_ids:
        hierarchy.total_blocks += 1
        page_idx = block.get("page_idx", 0)
        pages_set.add(page_idx)
        
        block_type = block.get("type", "unknown")
        hierarchy.blocks_by_type[block_type] = hierarchy.blocks_by_type.get(block_type, 0) + 1
        
        for line in block.get("lines", []):
            hierarchy.total_lines += 1
            for span in line.get("spans", []):
                hierarchy.total_spans += 1
    
    hierarchy.pages_with_content = sorted(pages_set)
    return hierarchy


def run_document_ir(
    document_id: str,
    mineru_output: str,
    output_dir: str,
    namespace: Optional[str] = None,
    **kwargs,
) -> dict:
    """Pipeline-callable Document IR entry point.

    Args:
        document_id: Document to process
        mineru_output: Path to MinerU output base directory
        output_dir: Path to write Document IR output
        namespace: Optional namespace for element IDs (defaults to document_id)

    Returns:
        Dict matching DocumentIRResult.to_dict() structure
    """
    mod = _load_doc_ir_module()
    
    if namespace is None:
        namespace = document_id

    auto_dir = _find_mineru_auto_dir(mineru_output, document_id)
    if auto_dir is None:
        return {
            "document_id": document_id,
            "namespace": namespace,
            "document_ir_status": "FAILED",
            "error": f"MinerU auto/ directory not found for '{document_id}' in {mineru_output}",
        }

    content_list_files = list(auto_dir.glob("*content_list.json"))
    middle_json = auto_dir / "main_middle.json"
    if not middle_json.exists():
        middle_json_candidates = list(auto_dir.glob("*_middle.json"))
        if middle_json_candidates:
            middle_json = middle_json_candidates[0]
        else:
            return {
                "document_id": document_id,
                "namespace": namespace,
                "document_ir_status": "FAILED",
                "error": f"No *_middle.json found in {auto_dir}",
            }

    try:
        blocks_with_ids = mod.extract_blocks_with_ids(middle_json, namespace)

        content_list_path = content_list_files[0] if content_list_files else None
        enhanced_content = []
        if content_list_path:
            enhanced_content = mod.map_content_list_to_blocks(
                content_list_path, blocks_with_ids, namespace
            )

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        blocks_out = out_path / f"{document_id}_blocks_with_ids.json"
        with open(blocks_out, "w", encoding="utf-8") as f:
            json.dump(blocks_with_ids, f, indent=2, ensure_ascii=False)

        content_out = out_path / f"{document_id}_content_list_enhanced.json"
        with open(content_out, "w", encoding="utf-8") as f:
            json.dump(enhanced_content, f, indent=2, ensure_ascii=False)

        hierarchy = _compute_hierarchy(blocks_with_ids)
        
        doc_ir = {
            "document_id": document_id,
            "namespace": namespace,
            "blocks": blocks_with_ids,
            "content_list": enhanced_content,
            "element_count": len(blocks_with_ids),
            "hierarchy": hierarchy.to_dict(),
            "source_anchor_schema_version": "1.0.0",
        }
        doc_ir_out = out_path / f"{document_id}_document_ir.json"
        with open(doc_ir_out, "w", encoding="utf-8") as f:
            json.dump(doc_ir, f, indent=2, ensure_ascii=False, default=str)

        return {
            "document_id": document_id,
            "namespace": namespace,
            "document_ir_path": str(doc_ir_out),
            "document_ir_status": "PASS",
            "element_count": len(blocks_with_ids),
            "blocks_output": str(blocks_out),
            "content_list_output": str(content_out),
            "hierarchy": hierarchy.to_dict(),
            "source_anchor_schema_version": "1.0.0",
        }

    except Exception as e:
        logger.error("[%s] Document IR failed: %s", document_id, e)
        return {
            "document_id": document_id,
            "namespace": namespace,
            "document_ir_status": "FAILED",
            "error": str(e),
        }


def create_document_ir_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for Document IR enhancement."""
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("document_ir", {})

    adapter = StageAdapter(
        stage_name="document_ir",
        version="2.1.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=["mineru_output_dir", "namespace"],
        ),
        output_contract=DataContract(
            required_outputs=[
                "document_ir_path",
                "document_ir_status",
                "namespace",
                "element_count",
            ],
            optional_outputs=["hierarchy", "source_anchor_schema_version"],
        ),
        dependencies=["pdf_parse"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 120),
    )

    mineru_output = paths.get("mineru_output", "")
    output_dir = paths.get("pipeline_runs", "") + "/document_ir"

    adapter.set_function(
        run_document_ir,
        mineru_output=mineru_output,
        output_dir=output_dir,
    )

    return adapter
