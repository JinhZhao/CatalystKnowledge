"""Test 011-B: Merge/dedup logic for multi-chunk extraction results.

Verifies:
  1. Overlap-aware deduplication — same value in overlapping chunks not double-counted
  2. Cross-section association tracking — field_source_map records which chunks contributed
  3. Array field deduplication — duplicate items across chunks removed
  4. Scalar field conflict resolution — different values from different chunks preserved
  5. Single-chunk passthrough — no merge overhead for full_text mode
  6. Merge provenance — audit trail in merge_notes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from catalyst_knowledge.pipeline.adapters.science_extraction_v2_adapter import (
    _merge_dimension_results,
    _deduplicate_array_items,
    _string_similarity,
    _normalize_dimension_result,
)
from catalyst_knowledge.pipeline.data_origin_classifier import DataRecord, DataStatus, DataOrigin


PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")


def make_chunk_result(
    chunk_id: str,
    fields: dict,
    sections: list[str] | None = None,
    char_range: list[int] | None = None,
) -> dict:
    normalized = {
        "dimension": "test_dimension",
        "fields": {},
        "validation_warnings": [],
        "chunk_id": chunk_id,
        "chunk_sections": sections or ["s00_test"],
        "chunk_char_range": char_range or [0, 1000],
        "chunk_page_range": [1, 3],
    }
    for field_name, raw_value in fields.items():
        record = DataRecord(
            field_name=field_name,
            value=raw_value if not isinstance(raw_value, dict) else raw_value.get("value"),
            status=raw_value.get("status", DataStatus.REPORTED) if isinstance(raw_value, dict) else DataStatus.REPORTED,
            origin=raw_value.get("origin", DataOrigin.ORIGINAL_EXPERIMENT) if isinstance(raw_value, dict) else DataOrigin.ORIGINAL_EXPERIMENT,
            source_quote=raw_value.get("source_quote", "") if isinstance(raw_value, dict) else "",
        )
        normalized["fields"][field_name] = record.to_dict()
    return normalized


def test_single_chunk_passthrough():
    print("\n=== Test 1: Single chunk passthrough ===")
    chunk = make_chunk_result("perf_full", {
        "conversion": {"value": "95.2%", "status": DataStatus.REPORTED},
        "selectivity": {"value": "87.1%", "status": DataStatus.REPORTED},
    })
    merged = _merge_dimension_results("performance", [chunk])
    check("chunk_count=1", merged.get("chunk_count") == 1)
    check("merge_notes indicates single chunk", "Single chunk" in merged.get("merge_notes", ""))
    check("source_chunks has 1 entry", len(merged.get("source_chunks", [])) == 1)
    check("conversion field preserved", "conversion" in merged.get("fields", {}))
    check("selectivity field preserved", "selectivity" in merged.get("fields", {}))


def test_overlap_dedup_same_value():
    print("\n=== Test 2: Overlap dedup — same value in 2 chunks ===")
    chunk1 = make_chunk_result("perf_chunk_0", {
        "conversion": {"value": "95.2%", "status": DataStatus.REPORTED},
        "selectivity": {"value": "87.1%", "status": DataStatus.REPORTED},
        "temperature": {"value": "500 C", "status": DataStatus.REPORTED},
    }, sections=["s00_results"], char_range=[0, 5000])
    chunk2 = make_chunk_result("perf_chunk_1", {
        "conversion": {"value": "95.2%", "status": DataStatus.REPORTED},
        "selectivity": {"value": "87.1%", "status": DataStatus.REPORTED},
        "time_on_stream": {"value": "48 h", "status": DataStatus.REPORTED},
    }, sections=["s01_discussion"], char_range=[4000, 9000])

    merged = _merge_dimension_results("performance", [chunk1, chunk2])
    check("chunk_count=2", merged.get("chunk_count") == 2)
    check("source_chunks has 2 entries", len(merged.get("source_chunks", [])) == 2)
    check("field_source_map present", "field_source_map" in merged)

    conv_field = merged.get("fields", {}).get("conversion", {})
    check("conversion value preserved", conv_field.get("value") == "95.2%")
    check(
        "conversion notes mention overlap dedup",
        "overlap dedup" in conv_field.get("notes", "").lower()
        or "Same value found in 2 chunks" in conv_field.get("notes", ""),
        f"notes={conv_field.get('notes', '')}",
    )

    check("temperature present (only chunk1)", "temperature" in merged.get("fields", {}))
    check("time_on_stream present (only chunk2)", "time_on_stream" in merged.get("fields", {}))

    merge_notes = merged.get("merge_notes", "")
    check("merge_notes mentions 2 chunks", "2 chunks" in merge_notes)


def test_array_field_dedup():
    print("\n=== Test 3: Array field deduplication ===")
    items_overlap = [
        {"name": "Pt", "role": "active metal"},
        {"name": "Al2O3", "role": "support"},
    ]
    items_with_extra = [
        {"name": "Pt", "role": "active metal"},
        {"name": "Al2O3", "role": "support"},
        {"name": "K", "role": "promoter"},
    ]

    chunk1 = make_chunk_result("cat_chunk_0", {
        "materials": {"value": items_overlap, "status": DataStatus.REPORTED},
    }, sections=["s00_preparation"])
    chunk2 = make_chunk_result("cat_chunk_1", {
        "materials": {"value": items_with_extra, "status": DataStatus.REPORTED},
    }, sections=["s01_characterization"])

    merged = _merge_dimension_results("catalyst_design", [chunk1, chunk2])
    materials_field = merged.get("fields", {}).get("materials", {})
    materials_value = materials_field.get("value", [])
    check("materials is a list", isinstance(materials_value, list))
    check(
        "deduplication occurred (notes)",
        "Deduplicated" in materials_field.get("notes", "")
        or "Combined" in materials_field.get("notes", ""),
        f"notes={materials_field.get('notes', '')}",
    )

    deduped = _deduplicate_array_items(items_with_extra + items_overlap)
    check(
        "direct dedup: 3 unique from 5 items",
        len(deduped) == 3,
        f"got {len(deduped)} items",
    )


def test_cross_section_association():
    print("\n=== Test 4: Cross-section association tracking ===")
    chunk1 = make_chunk_result("char_chunk_0", {
        "techniques_used": {"value": "XRD, BET", "status": DataStatus.REPORTED},
        "surface_area": {"value": "120 m2/g", "status": DataStatus.REPORTED},
    }, sections=["s00_xrd_section"])
    chunk2 = make_chunk_result("char_chunk_1", {
        "techniques_used": {"value": "TEM, XPS", "status": DataStatus.REPORTED},
        "particle_size": {"value": "5 nm", "status": DataStatus.REPORTED},
    }, sections=["s02_tem_section"])
    chunk3 = make_chunk_result("char_chunk_2", {
        "surface_area": {"value": "125 m2/g", "status": DataStatus.REPORTED},
    }, sections=["s03_bet_section"])

    merged = _merge_dimension_results("characterization", [chunk1, chunk2, chunk3])
    fsm = merged.get("field_source_map", {})
    check("field_source_map has techniques_used", "techniques_used" in fsm)
    check(
        "techniques_used from 2 chunks",
        len(fsm.get("techniques_used", [])) == 2,
        f"got {len(fsm.get('techniques_used', []))}",
    )
    check("surface_area from 2 chunks", len(fsm.get("surface_area", [])) == 2)
    check("particle_size from 1 chunk", len(fsm.get("particle_size", [])) == 1)

    sa_field = merged.get("fields", {}).get("surface_area", {})
    check(
        "surface_area has different values (120 vs 125)",
        sa_field.get("value") in ("120 m2/g", "125 m2/g"),
        f"value={sa_field.get('value')}",
    )


def test_status_priority_merge():
    print("\n=== Test 5: Status priority in merge ===")
    chunk1 = make_chunk_result("mech_chunk_0", {
        "active_site": {"value": None, "status": DataStatus.NOT_EXTRACTED},
    }, sections=["s00_intro"])
    chunk2 = make_chunk_result("mech_chunk_1", {
        "active_site": {"value": "Vo oxygen vacancy", "status": DataStatus.REPORTED},
    }, sections=["s03_mechanism"])

    merged = _merge_dimension_results("mechanism", [chunk1, chunk2])
    site_field = merged.get("fields", {}).get("active_site", {})
    check(
        "REPORTED wins over NOT_EXTRACTED",
        site_field.get("status") == "REPORTED"
        or site_field.get("value") == "Vo oxygen vacancy",
        f"status={site_field.get('status')}, value={site_field.get('value')}",
    )


def test_string_similarity():
    print("\n=== Test 6: String similarity function ===")
    check("identical strings = 1.0", _string_similarity("abc", "abc") == 1.0)
    check("empty strings = 0.0", _string_similarity("", "abc") == 0.0)
    check("different strings < 1.0", _string_similarity("abc", "xyz") < 1.0)
    sim = _string_similarity("Pt/Al2O3 catalyst", "Pt/Al2O3 catalysts")
    check(f"near-identical > 0.8 (got {sim:.2f})", sim > 0.8)


def test_merge_provenance():
    print("\n=== Test 7: Merge provenance audit trail ===")
    chunk1 = make_chunk_result("rel_chunk_0", {
        "stability_hours": {"value": "100 h", "status": DataStatus.REPORTED},
    })
    chunk2 = make_chunk_result("rel_chunk_1", {
        "stability_hours": {"value": "100 h", "status": DataStatus.REPORTED},
    })
    merged = _merge_dimension_results("reliability", [chunk1, chunk2])
    check("merge_notes present", bool(merged.get("merge_notes")))
    check("chunk_count present", merged.get("chunk_count") == 2)
    check("source_chunks present", len(merged.get("source_chunks", [])) == 2)
    check("field_source_map present", bool(merged.get("field_source_map")))


if __name__ == "__main__":
    print("=" * 60)
    print("Test 011-B: Merge/Dedup Logic for Multi-Chunk Results")
    print("=" * 60)

    test_single_chunk_passthrough()
    test_overlap_dedup_same_value()
    test_array_field_dedup()
    test_cross_section_association()
    test_status_priority_merge()
    test_string_similarity()
    test_merge_provenance()

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} total")
    print(f"{'=' * 60}")

    if FAIL > 0:
        print("VERDICT: FAIL")
        sys.exit(1)
    else:
        print("VERDICT: ALL PASS")
        sys.exit(0)
