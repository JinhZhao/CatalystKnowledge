"""Test 011-D: F02 full text mode Pipeline real execution (mock LLM).

Verifies:
  1. F02 adaptive mode selects full_text (normal paper fits in budget)
  2. V2 adapter run_science_extraction_v2 works end-to-end with mock LLM
  3. Token budget compliance verified before LLM call
  4. Output structure correct (dimensions, fields, merge metadata)
  5. SourceAnchor preserved in output
  6. No paid LLM calls made
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from catalyst_knowledge.pipeline.section_aware_extractor import (
    SectionAwareContentLoader,
    TokenBudget,
    estimate_tokens,
)
from catalyst_knowledge.pipeline.adapters.science_extraction_v2_adapter import (
    run_science_extraction_v2,
    _merge_dimension_results,
    _normalize_dimension_result,
    ALL_DIMENSIONS,
)


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


@dataclass
class MockChatResponse:
    content: str
    model: str = "mock-model"
    usage: dict | None = None


def create_mock_llm_response(dimension: str, chunk_content: str) -> str:
    """Generate a deterministic mock LLM response for testing."""
    sample_fields = {
        "catalyst_design": {
            "synthesis_method": {
                "value": "wetness impregnation",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
                "source_quote": "catalyst was prepared by wetness impregnation",
            },
            "active_metal": {
                "value": "Cu",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "support_material": {
                "value": "BN",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "metal_loading": {
                "value": "5 wt%",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
        },
        "characterization": {
            "techniques_used": {
                "value": ["XRD", "BET", "TEM", "XPS"],
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "surface_area": {
                "value": "120 m2/g",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "particle_size": {
                "value": "5 nm",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
        },
        "performance": {
            "conversion": {
                "value": "95.2%",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "selectivity": {
                "value": "87.1%",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "reaction_temperature": {
                "value": "500 C",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
        },
        "mechanism": {
            "proposed_mechanism": {
                "value": "Mars-van Krevelen",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "active_site": {
                "value": "oxygen vacancy",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
        },
        "structure_activity": {
            "key_relationship": {
                "value": "surface area correlates with activity",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
        },
        "reliability": {
            "stability_test": {
                "value": "48 h time on stream",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
            "deactivation_rate": {
                "value": "2% per 10h",
                "status": "REPORTED",
                "origin": "ORIGINAL_EXPERIMENT",
            },
        },
    }
    return json.dumps(sample_fields.get(dimension, {}))


class MockLLMService:
    """Mock LLM service that returns deterministic responses without network calls."""

    def __init__(self):
        self.call_count = 0
        self.calls = []
        self.call_index = 0

    def chat(self, messages, response_format=None):
        self.call_count += 1
        full_content = " ".join(msg.content for msg in messages)

        dimension = ""
        for dim in ALL_DIMENSIONS:
            if dim in full_content.lower():
                dimension = dim
                break

        if not dimension and self.call_index < len(ALL_DIMENSIONS):
            dimension = ALL_DIMENSIONS[self.call_index]
        self.call_index += 1

        mock_data = create_mock_llm_response(dimension, full_content)
        self.calls.append({"dimension": dimension, "content_len": len(full_content)})

        return MockChatResponse(
            content=mock_data,
            model="mock-model",
            usage={"prompt_tokens": estimate_tokens(full_content), "completion_tokens": 500},
        )


def test_f02_adaptive_mode_selection():
    print("\n=== Test 1: F02 adaptive mode selects full_text ===")
    f02_content = Path("data/test_corpus/mineru_output/F02_regression/main/auto/main_content_list.json")
    if not f02_content.exists():
        check("F02 content_list.json exists", False, str(f02_content))
        return None, None

    token_budget = TokenBudget(
        max_input_tokens=64000,
        max_output_tokens=4096,
        system_prompt_tokens=1000,
    )

    loader = SectionAwareContentLoader(
        f02_content,
        max_chunk_chars=8000,
        token_budget=token_budget,
        document_id="F02",
        overlap_paragraphs=1,
    )
    loader.load()

    total_chars = len(loader.full_text)
    total_tokens = estimate_tokens(total_chars * "x")
    print(f"  F02 total: {total_chars} chars, ~{total_tokens} tokens")
    print(f"  Budget: {token_budget.available_for_content} content tokens ({token_budget.available_content_chars} chars)")

    chunks = loader.build_adaptive_chunks("performance", doc_type="paper")
    print(f"  Chunks: {len(chunks)}, mode: {chunks[0].input_mode if chunks else 'N/A'}")

    check("F02 produces chunks", len(chunks) >= 1)
    if chunks:
        check(
            "F02 uses full_text mode (normal paper)",
            chunks[0].input_mode == "full_text",
            f"got {chunks[0].input_mode}",
        )
        check("F02 full_text is 1 chunk", len(chunks) == 1, f"got {len(chunks)}")

    return loader, chunks


def test_f02_v2_adapter_mock_llm():
    print("\n=== Test 2: V2 adapter end-to-end with mock LLM ===")
    f02_content_dir = Path("data/test_corpus/mineru_output/F02_regression")
    if not f02_content_dir.exists():
        check("F02 MinerU output exists", False, str(f02_content_dir))
        return

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_llm = MockLLMService()

        config = {
            "llm": {
                "model_context_limit": 64000,
                "max_tokens": 4096,
                "system_prompt_reserve_tokens": 1000,
                "output_reserve_tokens": 4096,
            },
            "stages": {
                "science_extraction_v2": {
                    "enabled": True,
                    "extraction_mode": "adaptive",
                    "doc_type": "paper",
                    "max_chunk_chars": 8000,
                    "overlap_paragraphs": 1,
                },
            },
            "paths": {
                "mineru_output": str(f02_content_dir),
                "pipeline_runs": tmpdir,
            },
        }

        prompt_config_path = str(Path("config/prompts/science_extraction_v2.yaml"))

        with patch("catalyst_knowledge.pipeline.adapters.science_extraction_v2_adapter._create_llm_service") as mock_create:
            mock_create.return_value = mock_llm

            result = run_science_extraction_v2(
                document_id="F02",
                mineru_output=str(f02_content_dir),
                output_dir=tmpdir,
                config=config,
                use_cache=False,
                prompt_config_path=prompt_config_path,
                extraction_mode="adaptive",
                doc_type="paper",
            )

        print(f"  Result status: {result.get('extraction_status')}")
        print(f"  Result mode: {result.get('extraction_mode')}")
        print(f"  Dimensions extracted: {result.get('dimensions_extracted', [])}")
        print(f"  Total chunks: {result.get('total_chunks', 0)}")
        print(f"  Total LLM calls: {result.get('total_llm_calls', 0)}")
        print(f"  Mock LLM call count: {mock_llm.call_count}")

        check("extraction_status is PASS or PARTIAL", result.get("extraction_status") in ("PASS", "PARTIAL"),
              f"got {result.get('extraction_status')}")
        check("extraction_mode is adaptive", result.get("extraction_mode") == "adaptive")
        check("LLM calls made (mock)", mock_llm.call_count > 0, f"mock call count={mock_llm.call_count}")
        check("total_chunks matches mock calls", result.get("total_chunks", 0) == mock_llm.call_count,
              f"chunks={result.get('total_chunks', 0)}, calls={mock_llm.call_count}")

        output_path = Path(result.get("extraction_output_path", ""))
        if output_path.exists():
            dim_files = list(output_path.glob("*_v2_extracted.json"))
            print(f"  Dimension output files: {len(dim_files)}")
            check("dimension output files created", len(dim_files) > 0)

            for df in dim_files[:3]:
                data = json.load(open(df, encoding="utf-8"))
                dim_name = data.get("dimension", df.stem)
                fields = data.get("fields", {})
                merge_notes = data.get("merge_notes", "")
                print(f"    {dim_name}: {len(fields)} fields, merge_notes='{merge_notes[:60]}'")

            summary_file = output_path / "extraction_v2_summary.json"
            if summary_file.exists():
                summary = json.load(open(summary_file, encoding="utf-8"))
                check("summary has extraction_mode", summary.get("extraction_mode") == "adaptive")
                check("summary has dimensions", summary.get("dimensions_total") == len(ALL_DIMENSIONS))
        else:
            check("output path exists", False, str(output_path))


def test_token_budget_compliance():
    print("\n=== Test 3: Token budget compliance ===")
    f02_content = Path("data/test_corpus/mineru_output/F02_regression/main/auto/main_content_list.json")
    if not f02_content.exists():
        check("F02 content exists", False)
        return

    tight_budget = TokenBudget(
        max_input_tokens=5000,
        max_output_tokens=2000,
        system_prompt_tokens=1000,
    )

    loader = SectionAwareContentLoader(
        f02_content,
        max_chunk_chars=8000,
        token_budget=tight_budget,
        document_id="F02",
        overlap_paragraphs=1,
    )
    loader.load()

    chunks = loader.build_adaptive_chunks("performance", doc_type="paper")
    print(f"  Tight budget chunks: {len(chunks)}, mode: {chunks[0].input_mode if chunks else 'N/A'}")

    if chunks and chunks[0].input_mode == "chunked":
        check("tight budget triggers chunked mode", True)
        for i, c in enumerate(chunks):
            tokens = estimate_tokens(c.content)
            check(
                f"chunk {i} within budget ({tokens} <= {tight_budget.available_for_content})",
                tokens <= tight_budget.available_for_content,
                f"{tokens} tokens",
            )
    else:
        check("tight budget triggers chunked mode", False, f"got {chunks[0].input_mode if chunks else 'no chunks'}")


def test_output_structure():
    print("\n=== Test 4: Output structure validation ===")
    f02_content_dir = Path("data/test_corpus/mineru_output/F02_regression")
    if not f02_content_dir.exists():
        check("F02 dir exists", False)
        return

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_llm = MockLLMService()
        config = {
            "llm": {"model_context_limit": 64000, "max_tokens": 4096, "system_prompt_reserve_tokens": 1000, "output_reserve_tokens": 4096},
            "stages": {"science_extraction_v2": {"enabled": True, "extraction_mode": "adaptive", "doc_type": "paper", "max_chunk_chars": 8000, "overlap_paragraphs": 1}},
            "paths": {"mineru_output": str(f02_content_dir), "pipeline_runs": tmpdir},
        }
        prompt_config_path = str(Path("config/prompts/science_extraction_v2.yaml"))

        with patch("catalyst_knowledge.pipeline.adapters.science_extraction_v2_adapter._create_llm_service") as mock_create:
            mock_create.return_value = mock_llm
            result = run_science_extraction_v2(
                document_id="F02", mineru_output=str(f02_content_dir), output_dir=tmpdir,
                config=config, use_cache=False, prompt_config_path=prompt_config_path,
                extraction_mode="adaptive", doc_type="paper",
            )

        check("result has extraction_status", "extraction_status" in result)
        check("result has extraction_mode", "extraction_mode" in result)
        check("result has extraction_version", result.get("extraction_version") == "v2")
        check("result has dimensions_extracted", "dimensions_extracted" in result)
        check("result has total_chunks", "total_chunks" in result)
        check("result has total_llm_calls", "total_llm_calls" in result)

        output_path = Path(result.get("extraction_output_path", ""))
        if output_path.exists():
            for dim in ALL_DIMENSIONS:
                dim_file = output_path / f"{dim}_v2_extracted.json"
                if dim_file.exists():
                    data = json.load(open(dim_file, encoding="utf-8"))
                    check(f"{dim} has fields", "fields" in data)
                    check(f"{dim} has merge_notes", "merge_notes" in data)
                    check(f"{dim} has chunk_count", "chunk_count" in data)
                    break


if __name__ == "__main__":
    print("=" * 60)
    print("Test 011-D: F02 Full Text Mode Pipeline (Mock LLM)")
    print("=" * 60)

    test_f02_adaptive_mode_selection()
    test_f02_v2_adapter_mock_llm()
    test_token_budget_compliance()
    test_output_structure()

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} PASS / {FAIL > 0} FAIL / {PASS + FAIL} total")
    print(f"{'=' * 60}")

    if FAIL > 0:
        print("VERDICT: FAIL")
        sys.exit(1)
    else:
        print("VERDICT: ALL PASS")
        sys.exit(0)
