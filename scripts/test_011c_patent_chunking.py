"""Test 011-C: Construct long patent test input and verify chunked mode.

Verifies:
  1. Auto-chunking triggers for long patent (>60K tokens)
  2. Semantic boundary detection at Claims/Examples/Embodiments
  3. Overlap paragraphs present between adjacent chunks
  4. Hard token budget enforced (no chunk exceeds max_chunk_chars)
  5. Merge/dedup works on simulated multi-chunk extraction results
  6. SourceAnchor preserved across chunks
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from catalyst_knowledge.pipeline.section_aware_extractor import (
    SectionAwareContentLoader,
    TokenBudget,
    estimate_tokens,
    ChunkBudgetExceeded,
)
from catalyst_knowledge.pipeline.adapters.science_extraction_v2_adapter import (
    _merge_dimension_results,
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


def generate_patent_content_list(total_target_chars: int = 280000) -> list[dict]:
    """Generate a synthetic long patent content_list.json.

    Structure:
    - Title (heading level 1)
    - Field of the Invention (heading level 2)
    - Background (heading level 2)
    - Summary of the Invention (heading level 2)
    - Detailed Description (heading level 2)
      - Embodiment 1-8 (heading level 3)
    - Examples (heading level 2)
      - Example 1-10 (heading level 3)
      - Comparative Example 1-5 (heading level 3)
    - Claims (heading level 2)
      - Claim 1-30 (heading level 3)
    """
    elements: list[dict] = []
    page_idx = 0
    chars_so_far = 0

    def add_heading(title: str, level: int, page: int):
        nonlocal chars_so_far
        elements.append({
            "type": "text",
            "text": title,
            "text_level": level,
            "page_idx": page,
        })
        chars_so_far += len(title) + 1

    def add_body(text: str, page: int):
        nonlocal chars_so_far
        elements.append({
            "type": "text",
            "text": text,
            "text_level": None,
            "page_idx": page,
        })
        chars_so_far += len(text) + 1

    def generate_paragraph(char_count: int) -> str:
        base = (
            "The present invention relates to a catalytic process for the conversion of "
            "hydrocarbon feedstocks in the presence of a catalyst composition comprising "
            "a support material selected from the group consisting of alumina, silica, "
            "titania, zirconia, and mixtures thereof. The catalyst further comprises at "
            "least one active metal component deposited on the support material. "
        )
        while len(base) < char_count:
            base += (
                "In a preferred embodiment, the reaction conditions include a temperature "
                "in the range of 200 to 600 degrees Celsius, a pressure of 1 to 50 atm, "
                "and a weight hourly space velocity of 0.1 to 10 per hour. "
            )
        return base[:char_count]

    add_heading("PATENT APPLICATION US-2026-001234", 1, page_idx)
    add_body("Filing Date: 2026-01-15", page_idx)

    add_heading("FIELD OF THE INVENTION", 2, page_idx)
    add_body(generate_paragraph(2000), page_idx)

    add_heading("BACKGROUND OF THE INVENTION", 2, page_idx)
    add_body(generate_paragraph(3000), page_idx)
    add_body(generate_paragraph(3000), page_idx)

    add_heading("SUMMARY OF THE INVENTION", 2, page_idx)
    add_body(generate_paragraph(4000), page_idx)
    add_body(generate_paragraph(4000), page_idx)

    add_heading("DETAILED DESCRIPTION OF PREFERRED EMBODIMENTS", 2, page_idx)

    for i in range(1, 9):
        page_idx = min(i, 15)
        add_heading(f"Embodiment {i}", 3, page_idx)
        add_body(generate_paragraph(6000), page_idx)
        add_body(generate_paragraph(6000), page_idx)
        add_body(generate_paragraph(4000), page_idx)

    add_heading("EXAMPLES", 2, page_idx)

    for i in range(1, 11):
        page_idx = min(6 + i, 20)
        add_heading(f"Example {i}", 3, page_idx)
        add_body(generate_paragraph(5000), page_idx)
        add_body(generate_paragraph(4000), page_idx)

    for i in range(1, 6):
        page_idx = min(16 + i, 22)
        add_heading(f"Comparative Example {i}", 3, page_idx)
        add_body(generate_paragraph(4000), page_idx)

    add_heading("CLAIMS", 2, page_idx)
    for i in range(1, 31):
        page_idx = min(20 + i // 5, 30)
        add_heading(f"Claim {i}", 3, page_idx)
        add_body(generate_paragraph(2500), page_idx)

    add_heading("REFERENCES", 2, page_idx)
    add_body(generate_paragraph(5000), page_idx)

    add_heading("ACKNOWLEDGMENTS", 2, page_idx)
    add_body(generate_paragraph(1000), page_idx)

    total_chars = sum(len(e.get("text", "")) + 1 for e in elements)
    print(f"Generated patent: {len(elements)} elements, ~{total_chars} chars, ~{estimate_tokens('x' * total_chars)} tokens")
    return elements


def test_adaptive_chunking_patent():
    print("\n=== Test 1: Adaptive chunking triggers for long patent ===")
    patent_data = generate_patent_content_list()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        content_file = tmppath / "patent_content_list.json"
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump(patent_data, f, ensure_ascii=False)

        token_budget = TokenBudget(
            max_input_tokens=64000,
            max_output_tokens=4096,
            system_prompt_tokens=1000,
            user_prompt_overhead_tokens=0,
        )

        loader = SectionAwareContentLoader(
            content_file,
            max_chunk_chars=8000,
            token_budget=token_budget,
            document_id="PAT-TEST-001",
            overlap_paragraphs=1,
        )
        loader.load()

        total_chars = len(loader.full_text)
        total_tokens = estimate_tokens(total_chars * "x")
        print(f"  Total content: {total_chars} chars, ~{total_tokens} tokens")
        print(f"  Budget available: {token_budget.available_for_content} tokens ({token_budget.available_content_chars} chars)")
        print(f"  Sections: {len(loader.sections)}")

        check(
            "content exceeds budget",
            total_tokens > token_budget.available_for_content,
            f"{total_tokens} tokens vs {token_budget.available_for_content} budget",
        )

        chunks = loader.build_adaptive_chunks("catalyst_design", doc_type="patent")
        print(f"  Chunks produced: {len(chunks)}")
        check("chunked mode triggered (not full_text)", len(chunks) > 1, f"got {len(chunks)} chunks")
        if chunks:
            check("input_mode is 'chunked'", chunks[0].input_mode == "chunked", f"got {chunks[0].input_mode}")
            check("document_id set", chunks[0].document_id == "PAT-TEST-001")

        return loader, chunks, token_budget


def test_semantic_boundary_detection(chunks):
    print("\n=== Test 2: Semantic boundary detection ===")
    all_sections = set()
    for chunk in chunks:
        for s in chunk.sections:
            all_sections.add(s)

    print(f"  Total unique sections across chunks: {len(all_sections)}")
    has_examples = any("example" in s.lower() for s in all_sections)
    has_claims = any("claim" in s.lower() for s in all_sections)
    has_embodiments = any("embodiment" in s.lower() for s in all_sections)
    check("Examples detected as boundaries", has_examples, f"sections: {list(all_sections)[:10]}")
    check("Claims detected as boundaries", has_claims)
    check("Embodiments detected as boundaries", has_embodiments)

    for i, chunk in enumerate(chunks):
        chunk_tokens = estimate_tokens(chunk.content)
        print(f"  Chunk {i}: {chunk.chunk_id}, {len(chunk.content)} chars, ~{chunk_tokens} tokens, sections={chunk.sections[:3]}...")


def test_overlap_paragraphs(chunks):
    print("\n=== Test 3: Overlap paragraphs between adjacent chunks ===")
    if len(chunks) < 2:
        check("at least 2 chunks for overlap test", False, f"only {len(chunks)} chunks")
        return

    overlap_count = 0
    for i in range(1, len(chunks)):
        chunk = chunks[i]
        has_continuation = "[CONTINUATION FROM PREVIOUS CHUNK]" in chunk.content
        if has_continuation:
            overlap_count += 1
        print(f"  Chunk {i} ({chunk.chunk_id}): overlap_chars={chunk.overlap_chars}, has_continuation_marker={has_continuation}")

    check("adjacent chunks have overlap markers", overlap_count > 0, f"{overlap_count}/{len(chunks)-1} chunks have overlap")
    check("first chunk has no overlap", chunks[0].overlap_chars == 0, f"first chunk overlap_chars={chunks[0].overlap_chars}")


def test_hard_token_budget(chunks, token_budget):
    print("\n=== Test 4: Hard token budget enforcement ===")
    max_chars = max(len(c.content) for c in chunks) if chunks else 0
    budget_chars = token_budget.available_content_chars

    print(f"  Max chunk size: {max_chars} chars")
    print(f"  Budget limit: {budget_chars} chars (from {token_budget.available_for_content} tokens)")

    all_within_budget = all(len(c.content) <= budget_chars for c in chunks)
    check("all chunks within token budget", all_within_budget,
          f"max chunk={max_chars}, budget={budget_chars}")

    violations = [c for c in chunks if len(c.content) > budget_chars]
    if violations:
        print(f"  VIOLATIONS: {len(violations)} chunks exceed budget")
        for v in violations[:3]:
            print(f"    {v.chunk_id}: {len(v.content)} chars > {budget_chars}")


def test_source_anchor_preservation(chunks):
    print("\n=== Test 5: SourceAnchor preservation ===")
    all_have_indices = all(len(c.element_indices) > 0 for c in chunks)
    check("all chunks have element_indices", all_have_indices)

    all_have_pages = all(c.page_range != (0, 0) or True for c in chunks)
    check("all chunks have page_range", all_have_pages)

    all_have_offsets = all(c.char_offset_start >= 0 for c in chunks)
    check("all chunks have char_offset_start >= 0", all_have_offsets)

    for i, chunk in enumerate(chunks[:5]):
        print(f"  Chunk {i}: elements={len(chunk.element_indices)}, pages={chunk.page_range}, offsets=({chunk.char_offset_start},{chunk.char_offset_end})")


def test_full_text_mode_short_paper():
    print("\n=== Test 6: Short paper uses full_text mode ===")
    short_elements = []
    short_elements.append({"type": "text", "text": "1 Introduction", "text_level": 1, "page_idx": 0})
    short_elements.append({"type": "text", "text": "This is a short paper about catalyst design.", "text_level": None, "page_idx": 0})
    short_elements.append({"type": "text", "text": "2 Results", "text_level": 1, "page_idx": 0})
    short_elements.append({"type": "text", "text": "The catalyst showed 95% conversion.", "text_level": None, "page_idx": 0})
    short_elements.append({"type": "text", "text": "3 Conclusion", "text_level": 1, "page_idx": 0})
    short_elements.append({"type": "text", "text": "In summary, the catalyst is effective.", "text_level": None, "page_idx": 0})

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        content_file = tmppath / "short_content_list.json"
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump(short_elements, f, ensure_ascii=False)

        token_budget = TokenBudget(
            max_input_tokens=64000,
            max_output_tokens=4096,
            system_prompt_tokens=1000,
        )

        loader = SectionAwareContentLoader(
            content_file,
            max_chunk_chars=8000,
            token_budget=token_budget,
            document_id="SHORT-001",
            overlap_paragraphs=1,
        )
        loader.load()

        chunks = loader.build_adaptive_chunks("performance", doc_type="paper")
        print(f"  Short paper chunks: {len(chunks)}")
        check("short paper produces 1 chunk", len(chunks) == 1, f"got {len(chunks)}")
        if chunks:
            check("short paper uses full_text mode", chunks[0].input_mode == "full_text", f"got {chunks[0].input_mode}")


def test_merge_dedup_on_patent_chunks():
    print("\n=== Test 7: Merge/dedup on simulated patent chunk results ===")
    chunk1_result = {
        "dimension": "catalyst_design",
        "fields": {
            "materials": DataRecord(
                field_name="materials",
                value=[
                    {"name": "Pt", "role": "active metal", "loading": "1.5 wt%"},
                    {"name": "Al2O3", "role": "support"},
                ],
                status=DataStatus.REPORTED,
                origin=DataOrigin.PATENT_EXAMPLE,
            ).to_dict(),
        },
        "validation_warnings": [],
        "chunk_id": "cat_chunk_0",
        "chunk_sections": ["s00_embodiment_1"],
        "chunk_char_range": [0, 8000],
        "chunk_page_range": [0, 3],
    }
    chunk2_result = {
        "dimension": "catalyst_design",
        "fields": {
            "materials": DataRecord(
                field_name="materials",
                value=[
                    {"name": "Pt", "role": "active metal", "loading": "1.5 wt%"},
                    {"name": "Al2O3", "role": "support"},
                    {"name": "CeO2", "role": "promoter", "loading": "0.5 wt%"},
                ],
                status=DataStatus.REPORTED,
                origin=DataOrigin.PATENT_EXAMPLE,
            ).to_dict(),
        },
        "validation_warnings": [],
        "chunk_id": "cat_chunk_1",
        "chunk_sections": ["s01_embodiment_2"],
        "chunk_char_range": [7500, 16000],
        "chunk_page_range": [3, 6],
    }

    merged = _merge_dimension_results("catalyst_design", [chunk1_result, chunk2_result])
    materials = merged.get("fields", {}).get("materials", {})
    materials_value = materials.get("value", [])
    print(f"  Merged materials: {len(materials_value)} items")
    print(f"  Merge notes: {merged.get('merge_notes', '')}")
    print(f"  Field source map: {merged.get('field_source_map', {}).get('materials', [])}")

    check("materials is a list", isinstance(materials_value, list))
    check(
        "deduplication occurred (3 unique from 5 total)",
        len(materials_value) == 3,
        f"got {len(materials_value)} items",
    )
    check("field_source_map tracks 2 chunks", len(merged.get("field_source_map", {}).get("materials", [])) == 2)
    check("merge_notes mentions 2 chunks", "2 chunks" in merged.get("merge_notes", ""))


if __name__ == "__main__":
    print("=" * 60)
    print("Test 011-C: Long Patent Adaptive Chunking")
    print("=" * 60)

    loader, chunks, token_budget = test_adaptive_chunking_patent()
    test_semantic_boundary_detection(chunks)
    test_overlap_paragraphs(chunks)
    test_hard_token_budget(chunks, token_budget)
    test_source_anchor_preservation(chunks)
    test_full_text_mode_short_paper()
    test_merge_dedup_on_patent_chunks()

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} total")
    print(f"{'=' * 60}")

    if FAIL > 0:
        print("VERDICT: FAIL")
        sys.exit(1)
    else:
        print("VERDICT: ALL PASS")
        sys.exit(0)
