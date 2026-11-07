"""Adapter for num_unit_001_phase3_normalizer.py — Quantity normalization.

Wraps QuantityNormalizer from the existing script.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)

_module = None
_loader_module = None


def _load_modules():
    """Dynamically load num_unit scripts."""
    global _module, _loader_module
    project_root = Path(__file__).parent.parent.parent.parent.parent
    scripts_dir = project_root / "scripts"

    if _loader_module is None:
        loader_path = scripts_dir / "num_unit_001_loader.py"
        if loader_path.exists():
            spec = importlib.util.spec_from_file_location("num_unit_001_loader", loader_path)
            _loader_module = importlib.util.module_from_spec(spec)
            old_path = sys.path.copy()
            sys.path.insert(0, str(scripts_dir))
            try:
                spec.loader.exec_module(_loader_module)
            finally:
                sys.path = old_path

    if _module is None:
        normalizer_path = scripts_dir / "num_unit_001_phase3_normalizer.py"
        if normalizer_path.exists():
            spec = importlib.util.spec_from_file_location("num_unit_001_normalizer", normalizer_path)
            _module = importlib.util.module_from_spec(spec)
            old_path = sys.path.copy()
            sys.path.insert(0, str(scripts_dir))
            try:
                spec.loader.exec_module(_module)
            finally:
                sys.path = old_path

    return _module, _loader_module


def run_num_unit_normalization(
    document_id: str,
    extraction_output_path: str,
    output_dir: str,
    quantity_definitions_path: str,
    **kwargs,
) -> dict:
    """Pipeline-callable quantity normalization entry point."""
    _module, _loader_module = _load_modules()

    if _module is None or _loader_module is None:
        return {
            "document_id": document_id,
            "num_unit_output_path": str(Path(output_dir) / f"{document_id}_normalized_quantities.json"),
            "num_unit_status": "FAILED",
            "error": "num_unit modules not available",
        }

    extraction_dir = Path(extraction_output_path)
    if not extraction_dir.exists():
        return {
            "document_id": document_id,
            "num_unit_output_path": str(Path(output_dir) / f"{document_id}_normalized_quantities.json"),
            "num_unit_status": "FAILED",
            "error": f"Extraction output not found: {extraction_dir}",
        }

    try:
        registry_loader = _loader_module.QuantityRegistryLoader(
            config_path=Path(quantity_definitions_path)
        )
        registry_loader.load()
        normalizer = _module.QuantityNormalizer(registry_loader)
    except Exception as e:
        return {
            "document_id": document_id,
            "num_unit_output_path": str(Path(output_dir) / f"{document_id}_normalized_quantities.json"),
            "num_unit_status": "FAILED",
            "error": f"Normalizer init failed: {e}",
        }

    json_files = list(extraction_dir.glob("*_extracted.json"))
    candidates = []
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
            _extract_quantity_candidates(data, candidates, document_id)
        except Exception as e:
            logger.warning("Failed to parse %s: %s", jf, e)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    normalized = []
    for c in candidates:
        try:
            record = normalizer.normalize(
                raw_value=c.get("raw_value"),
                raw_unit=c.get("raw_unit"),
                quantity_type=c.get("quantity_type", "unknown"),
                raw_text=c.get("raw_text", ""),
                document_id=document_id,
            )
            normalized.append({
                "quantity_type": record.quantity_type,
                "raw_value": record.raw_value,
                "raw_unit": record.raw_unit,
                "si_value": record.si_value,
                "si_unit": record.si_unit,
                "status": record.unit_conversion_status,
            })
        except Exception as e:
            normalized.append({
                "raw_value": c.get("raw_value"),
                "raw_unit": c.get("raw_unit"),
                "status": "FAILED",
                "error": str(e),
            })

    output_file = out_path / f"{document_id}_normalized_quantities.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False, default=str)

    success_count = sum(1 for n in normalized if n.get("status") != "FAILED")

    return {
        "document_id": document_id,
        "num_unit_output_path": str(output_file),
        "num_unit_status": "PASS" if success_count > 0 else "FAILED",
        "candidates_found": len(candidates),
        "normalized_count": success_count,
    }


_QUANTITY_RE = re.compile(
    r"(\d[\d,]*\.?\d*)\s*"
    r"(m2/g|m\u00b2/g|mg/g|ug/g|g/L|mol/L|mmol/g|cm2/g|cm3/g|"
    r"wt%|vol%|mol%|at%|%"
    r"|degC|\u00b0\s*C|\u00b0C|K\b"
    r"|mL/min|L/min|mL/h|L/h|mL/g"
    r"|nm|um|mm|cm\b"
    r"|cm\s*[-\u2212]\s*1|cm\u207b\u00b9"
    r"|kJ/mol|eV|Pa|MPa|kPa|GPa|bar|atm"
    r"|h\b|min\b|s\b|days?)\b"
)


def _parse_quantities_from_text(text: str, candidates: list, document_id: str, source_key: str):
    """Extract number+unit pairs from free-form text."""
    for m in _QUANTITY_RE.finditer(text):
        raw_value = m.group(1).replace(",", "")
        raw_unit = m.group(2)
        candidates.append({
            "raw_value": raw_value,
            "raw_unit": raw_unit,
            "quantity_type": source_key,
            "raw_text": text[max(0, m.start() - 40):m.end() + 40],
            "document_id": document_id,
        })


def _extract_quantity_candidates(data: dict, candidates: list, document_id: str):
    """Extract quantity candidates from extraction data (recursive)."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ("value", "raw_value") and isinstance(value, (str, int, float)):
                unit = data.get("unit", data.get("raw_unit", ""))
                if unit:
                    candidates.append({
                        "raw_value": str(value),
                        "raw_unit": str(unit),
                        "quantity_type": key,
                        "raw_text": str(data),
                        "document_id": document_id,
                    })
            elif isinstance(value, str) and len(value) > 3 and key not in ("document_id", "error"):
                _parse_quantities_from_text(value, candidates, document_id, key)
            elif isinstance(value, (dict, list)):
                _extract_quantity_candidates(value, candidates, document_id)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                _extract_quantity_candidates(item, candidates, document_id)


def create_num_unit_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for quantity normalization."""
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("num_unit_normalization", {})

    adapter = StageAdapter(
        stage_name="num_unit_normalization",
        version="1.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=["extraction_output_path"],
        ),
        output_contract=DataContract(
            required_outputs=["num_unit_output_path", "num_unit_status"],
        ),
        dependencies=["six_dimension_extraction", "science_extraction_v2"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 60),
    )

    output_dir = paths.get("pipeline_runs", "") + "/num_unit"
    qty_defs = paths.get("quantity_definitions", "")

    adapter.set_function(
        run_num_unit_normalization,
        output_dir=output_dir,
        quantity_definitions_path=qty_defs,
    )
    return adapter
