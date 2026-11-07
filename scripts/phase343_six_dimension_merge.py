"""Phase 3.4.3 — Six-Dimension Unified Merge Script.

Merges all extraction results from Phase 3.4.2 and 3.4.3 into unified dimension JSONs.
Handles deduplication, cross-chunk conflicts, and data quality validation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
PHASE342_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3_4_2" / "f02_extraction"
PHASE343_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3_4_3" / "f02"
OUTPUT_DIR = PHASE343_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

ALL_DIMENSIONS = [
    "catalyst_design",
    "characterization",
    "performance",
    "mechanism",
    "structure_activity",
    "reliability",
]


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_field_values(field_name: str, values: list[dict]) -> dict:
    """Merge multiple field values with priority: REPORTED > UNRESOLVED > NOT_EXTRACTED."""
    if not values:
        return {"status": "NOT_EXTRACTED", "origin": "UNKNOWN_ORIGIN"}
    
    # Filter to only REPORTED values
    reported = [v for v in values if v.get("status") == "REPORTED"]
    
    if reported:
        # Take the first REPORTED value with longest source_quote
        best = max(reported, key=lambda v: len(v.get("source_quote", "")))
        return best
    
    # If no REPORTED, take the best available
    return values[0]


def merge_dimension_data(dim: str, sources: list[dict]) -> dict:
    """Merge data from multiple sources for a dimension."""
    merged = {
        "dimension": dim,
        "fields": {},
        "validation_warnings": [],
        "merge_notes": f"Merged from {len(sources)} sources",
        "source_count": len(sources),
    }
    
    # Collect all field names
    all_field_names = set()
    for source in sources:
        fields = source.get("fields", {})
        all_field_names.update(fields.keys())
    
    # Merge each field
    for field_name in all_field_names:
        field_values = []
        for source in sources:
            field_data = source.get("fields", {}).get(field_name)
            if field_data:
                if isinstance(field_data, dict):
                    field_values.append(field_data)
                elif isinstance(field_data, list):
                    # Array field - merge items
                    merged_items = []
                    for item in field_data:
                        if isinstance(item, dict):
                            merged_items.append(item)
                    if merged_items:
                        field_values.append({
                            "value": merged_items,
                            "status": "REPORTED",
                            "origin": "ORIGINAL_EXPERIMENT",
                        })
        
        if field_values:
            merged["fields"][field_name] = merge_field_values(field_name, field_values)
    
    # Collect validation warnings
    for source in sources:
        warnings = source.get("validation_warnings", [])
        merged["validation_warnings"].extend(warnings)
    
    merged["validation_warnings"] = list(set(merged["validation_warnings"]))
    
    return merged


def integrate_recovered_data(dimension_data: dict, recovered_data: dict, field_mapping: dict) -> dict:
    """Integrate recovered data into dimension data."""
    if not recovered_data:
        return dimension_data
    
    for recovered_field, target_field in field_mapping.items():
        if recovered_field in recovered_data:
            value = recovered_data[recovered_field]
            if isinstance(value, dict) and value.get("status") == "REPORTED":
                dimension_data["fields"][target_field] = value
                logger.info(f"  Integrated {target_field} from recovered data")
    
    return dimension_data


def validate_six_dimension_result(result: dict) -> dict:
    """Validate the merged six-dimension result."""
    validation = {
        "dimensions_present": [],
        "dimensions_missing": [],
        "field_counts": {},
        "reported_counts": {},
        "origin_distribution": {},
        "critical_data_checks": {},
    }
    
    for dim in ALL_DIMENSIONS:
        if dim in result:
            validation["dimensions_present"].append(dim)
            fields = result[dim].get("fields", {})
            validation["field_counts"][dim] = len(fields)
            
            reported = sum(1 for f in fields.values() if isinstance(f, dict) and f.get("status") == "REPORTED")
            validation["reported_counts"][dim] = reported
            
            # Count origins
            for field_data in fields.values():
                if isinstance(field_data, dict):
                    origin = field_data.get("origin", "UNKNOWN_ORIGIN")
                    validation["origin_distribution"][origin] = validation["origin_distribution"].get(origin, 0) + 1
        else:
            validation["dimensions_missing"].append(dim)
    
    # Critical data checks
    # Check synthesis_method
    cat_design = result.get("catalyst_design", {}).get("fields", {})
    synth = cat_design.get("synthesis_method", {})
    validation["critical_data_checks"]["synthesis_method"] = {
        "present": "synthesis_method" in cat_design,
        "status": synth.get("status", "N/A"),
        "value": synth.get("value", "N/A"),
        "correct": "impregnation" in str(synth.get("value", "")).lower(),
    }
    
    # Check time_on_stream
    reliability = result.get("reliability", {}).get("fields", {})
    tos = reliability.get("time_on_stream", {})
    validation["critical_data_checks"]["time_on_stream"] = {
        "present": "time_on_stream" in reliability,
        "status": tos.get("status", "N/A"),
        "value": tos.get("value", "N/A"),
        "correct": tos.get("value") == 8 or str(tos.get("value", "")).startswith("8"),
    }
    
    # Check key_metrics for literature contamination
    performance = result.get("performance", {}).get("fields", {})
    km = performance.get("key_metrics", {})
    if isinstance(km, dict) and isinstance(km.get("value"), list):
        lit_refs = sum(1 for m in km["value"] if isinstance(m, dict) and m.get("origin") == "LITERATURE_REFERENCE")
        validation["critical_data_checks"]["literature_separation"] = {
            "total_metrics": len(km.get("value", [])),
            "literature_references": lit_refs,
            "correct": lit_refs > 0,
        }
    
    return validation


def main():
    logger.info("=" * 60)
    logger.info("Phase 3.4.3 — Six-Dimension Unified Merge")
    logger.info("=" * 60)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load Phase 3.4.2 results
    logger.info("Loading Phase 3.4.2 results...")
    phase342_results = {}
    for dim in ALL_DIMENSIONS:
        data = load_json(PHASE342_DIR / f"{dim}_v2_extracted.json")
        if data:
            phase342_results[dim] = data
            logger.info(f"  {dim}: {len(data.get('fields', {}))} fields")
    
    # Load Phase 3.4.3 characterization results
    logger.info("Loading Phase 3.4.3 characterization results...")
    char_data = load_json(PHASE343_DIR / "characterization_recovery" / "characterization_v2_extracted.json")
    if char_data:
        logger.info(f"  characterization: {len(char_data.get('fields', {}))} fields")
    
    # Load Phase 3.4.3 recovered data
    logger.info("Loading Phase 3.4.3 recovered data...")
    perf_recovered = load_json(PHASE343_DIR / "critical_recovery" / "performance_conditions_recovered.json")
    mech_recovered = load_json(PHASE343_DIR / "critical_recovery" / "mechanism_key_fields_recovered.json")
    
    if perf_recovered:
        logger.info(f"  performance conditions: recovered")
    if mech_recovered:
        logger.info(f"  mechanism fields: recovered")
    
    # Merge each dimension
    logger.info("\nMerging dimensions...")
    six_dim_result = {}
    
    for dim in ALL_DIMENSIONS:
        logger.info(f"\n{dim}:")
        
        sources = []
        
        # Add Phase 3.4.2 data if available
        if dim in phase342_results:
            sources.append(phase342_results[dim])
        
        # Add Phase 3.4.3 characterization data
        if dim == "characterization" and char_data:
            sources.append(char_data)
        
        if sources:
            merged = merge_dimension_data(dim, sources)
            
            # Integrate recovered data
            if dim == "performance" and perf_recovered:
                merged = integrate_recovered_data(
                    merged,
                    perf_recovered,
                    {"reaction_conditions": "reaction_conditions"}
                )
            
            if dim == "mechanism" and mech_recovered:
                merged = integrate_recovered_data(
                    merged,
                    mech_recovered,
                    {
                        "proposed_pathway": "proposed_pathway",
                        "active_sites": "active_sites",
                        "role_of_light": "role_of_light",
                    }
                )
            
            six_dim_result[dim] = merged
            logger.info(f"  Merged: {len(merged.get('fields', {}))} fields")
        else:
            logger.warning(f"  No data available for {dim}")
    
    # Validate
    logger.info("\n" + "=" * 60)
    logger.info("Validation")
    logger.info("=" * 60)
    validation = validate_six_dimension_result(six_dim_result)
    
    logger.info(f"Dimensions present: {len(validation['dimensions_present'])}/6")
    logger.info(f"Dimensions missing: {validation['dimensions_missing']}")
    logger.info(f"Field counts: {validation['field_counts']}")
    logger.info(f"Reported counts: {validation['reported_counts']}")
    logger.info(f"Origin distribution: {validation['origin_distribution']}")
    
    logger.info("\nCritical data checks:")
    for check_name, check_result in validation['critical_data_checks'].items():
        status = "PASS" if check_result.get("correct", False) else "FAIL"
        logger.info(f"  {check_name}: {status} - {check_result}")
    
    # Save results
    output_file = OUTPUT_DIR / "PHASE343_SIX_DIMENSION_RESULT.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(six_dim_result, f, indent=2, ensure_ascii=False)
    
    validation_file = OUTPUT_DIR / "PHASE343_VALIDATION_RESULT.json"
    with open(validation_file, "w", encoding="utf-8") as f:
        json.dump(validation, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\nResults saved to: {output_file.name}")
    logger.info(f"Validation saved to: {validation_file.name}")
    
    return six_dim_result, validation


if __name__ == "__main__":
    result, validation = main()
    if not result:
        import sys
        sys.exit(1)
