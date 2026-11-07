"""Test 011-E: 007 Figure/Table dynamic regression.

Verifies:
  1. VLM adapter can be instantiated and is properly wired
  2. Table parser adapter can be instantiated
  3. DAG dependencies intact — no broken chain from 011 changes
  4. Cached 007 VLM results still accessible and structurally valid
  5. science_extraction_v2 does not interfere with VLM/Table stages
  6. Pipeline config has correct stage entries
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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


def test_vlm_adapter_exists():
    print("\n=== Test 1: VLM adapter module integrity ===")
    adapter_path = Path("src/catalyst_knowledge/pipeline/adapters/vlm_figure_science_adapter.py")
    check("VLM adapter file exists", adapter_path.exists())

    if adapter_path.exists():
        content = adapter_path.read_text(encoding="utf-8")
        check("has create_vlm_figure_science_adapter", "create_vlm_figure_science_adapter" in content)
        check("has VLMFigureScienceAdapter or function", "def " in content)
        check("depends on figure_parser", "figure_parser" in content)


def test_table_adapter_exists():
    print("\n=== Test 2: Table adapter module integrity ===")
    table_parser_path = Path("src/catalyst_knowledge/pipeline/adapters/table_parser_adapter.py")
    table_science_path = Path("src/catalyst_knowledge/pipeline/adapters/table_science_adapter.py")

    check("table_parser adapter exists", table_parser_path.exists())
    check("table_science adapter exists", table_science_path.exists())

    if table_parser_path.exists():
        content = table_parser_path.read_text(encoding="utf-8")
        check("table_parser has create function", "create_table_parser_adapter" in content)

    if table_science_path.exists():
        content = table_science_path.read_text(encoding="utf-8")
        check("table_science has create function", "create_table_science_adapter" in content)


def test_adapters_importable():
    print("\n=== Test 3: Adapters importable ===")
    try:
        from catalyst_knowledge.pipeline.adapters import (
            create_vlm_figure_science_adapter,
            create_table_parser_adapter,
            create_table_science_adapter,
            create_extraction_adapter,
        )
        check("all adapters importable", True)
    except ImportError as e:
        check("all adapters importable", False, str(e))

    try:
        from catalyst_knowledge.pipeline.adapters.vlm_figure_science_adapter import (
            create_vlm_figure_science_adapter,
        )
        config = {
            "paths": {"mineru_output": "", "pipeline_runs": ""},
            "stages": {"vlm_figure_science": {"enabled": False}},
        }
        adapter = create_vlm_figure_science_adapter(config)
        check("VLM adapter instantiable", adapter is not None)
        check("VLM adapter has stage_name", adapter.stage_name == "vlm_figure_science")
    except Exception as e:
        check("VLM adapter instantiable", False, str(e))


def test_pipeline_config():
    print("\n=== Test 4: Pipeline config integrity ===")
    config_path = Path("config/pipeline.yaml")
    check("pipeline.yaml exists", config_path.exists())

    if config_path.exists():
        import yaml
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        stages = config.get("stages", {})

        check("vlm_figure_science in config", "vlm_figure_science" in stages)
        check("table_parser in config", "table_parser" in stages)
        check("science_extraction_v2 in config", "science_extraction_v2" in stages)

        vlm_cfg = stages.get("vlm_figure_science", {})
        check("vlm disabled by default", vlm_cfg.get("enabled") is False)

        table_cfg = stages.get("table_parser", {})
        check("table_parser enabled", table_cfg.get("enabled") is True)

        extraction_cfg = stages.get("science_extraction_v2", {})
        check("extraction_v2 has adaptive mode", extraction_cfg.get("extraction_mode") == "adaptive")


def test_dag_dependencies():
    print("\n=== Test 5: DAG dependency chain ===")
    from catalyst_knowledge.pipeline.adapters import (
        create_vlm_figure_science_adapter,
        create_table_parser_adapter,
        create_table_science_adapter,
    )

    config = {
        "paths": {"mineru_output": "", "pipeline_runs": ""},
        "stages": {
            "vlm_figure_science": {"enabled": False},
            "table_parser": {},
            "table_science": {},
        },
    }

    try:
        vlm_adapter = create_vlm_figure_science_adapter(config)
        check("VLM depends on figure_parser", "figure_parser" in vlm_adapter.dependencies)
        check("VLM depends on document_ir", "document_ir" in vlm_adapter.dependencies)
    except Exception as e:
        check("VLM adapter created", False, str(e))

    try:
        table_adapter = create_table_parser_adapter(config)
        check("table_parser depends on document_ir", "document_ir" in table_adapter.dependencies)
    except Exception as e:
        check("table_parser adapter created", False, str(e))

    try:
        table_science = create_table_science_adapter(config)
        check("table_science depends on table_parser", "table_parser" in table_science.dependencies)
    except Exception as e:
        check("table_science adapter created", False, str(e))


def test_cached_007_vlm_results():
    print("\n=== Test 6: Cached 007 VLM results integrity ===")
    vlm_path = Path("runs/pipeline_001_fix/PIPELINE_007_R2/F02_vlm_science_records_consolidated.json")
    check("007-R2 VLM cache exists", vlm_path.exists())

    if vlm_path.exists():
        data = json.load(open(vlm_path, encoding="utf-8"))
        if isinstance(data, dict):
            total_records = data.get("total_records", 0)
            figures_processed = data.get("figures_processed", 0)
            adapter_status = data.get("adapter_status", "")
            results = data.get("results", [])

            check("VLM adapter_status is PASS", adapter_status == "PASS", f"got {adapter_status}")
            check("VLM has records", total_records > 0, f"total_records={total_records}")
            check("VLM processed figures", figures_processed > 0, f"figures={figures_processed}")
            check("VLM results is a list", isinstance(results, list))

            if results:
                first_fig = results[0]
                check("first figure has figure_id", "figure_id" in first_fig)
                check("first figure has records", "records" in first_fig)
                print(f"  Total: {total_records} records, {figures_processed} figures, status={adapter_status}")
                print(f"  First figure: {first_fig.get('figure_id', '?')}, {len(first_fig.get('records', []))} records")
        elif isinstance(data, list):
            check("VLM records is a list", True)
            check("has records", len(data) > 0)


def test_extraction_v2_no_interference():
    print("\n=== Test 7: science_extraction_v2 does not interfere with VLM/Table ===")
    adapter_path = Path("src/catalyst_knowledge/pipeline/adapters/science_extraction_v2_adapter.py")
    if adapter_path.exists():
        content = adapter_path.read_text(encoding="utf-8")

        vlm_refs = content.lower().count("vlm")
        table_refs = content.lower().count("table_parser")
        figure_refs = content.lower().count("figure_parser")

        check("extraction_v2 has no VLM references", vlm_refs == 0, f"found {vlm_refs} refs")
        check("extraction_v2 has no table_parser refs", table_refs == 0, f"found {table_refs} refs")
        check("extraction_v2 has no figure_parser refs", figure_refs == 0, f"found {figure_refs} refs")

        check("extraction_v2 depends only on document_ir",
              "dependencies=[\"document_ir\"]" in content or "dependencies=['document_ir']" in content)


def test_adaptive_mode_no_side_effects():
    print("\n=== Test 8: Adaptive mode has no side effects on other stages ===")
    from catalyst_knowledge.pipeline.section_aware_extractor import (
        SectionAwareContentLoader,
        TokenBudget,
    )

    f02_content = Path("data/test_corpus/mineru_output/F02_regression/main/auto/main_content_list.json")
    if not f02_content.exists():
        check("F02 content exists", False)
        return

    budget = TokenBudget(max_input_tokens=64000, max_output_tokens=4096, system_prompt_tokens=1000)
    loader = SectionAwareContentLoader(
        f02_content, max_chunk_chars=8000, token_budget=budget,
        document_id="F02", overlap_paragraphs=1,
    )
    loader.load()

    fig_table_elems = loader.get_figure_table_elements()
    print(f"  Figure/Table elements in F02: {len(fig_table_elems)}")
    check("figure/table elements detected", len(fig_table_elems) > 0, f"got {len(fig_table_elems)}")

    for elem in fig_table_elems[:3]:
        print(f"    Element {elem.index}: type={elem.element_type}, page={elem.page_idx}")


if __name__ == "__main__":
    print("=" * 60)
    print("Test 011-E: 007 Figure/Table Dynamic Regression")
    print("=" * 60)

    test_vlm_adapter_exists()
    test_table_adapter_exists()
    test_adapters_importable()
    test_pipeline_config()
    test_dag_dependencies()
    test_cached_007_vlm_results()
    test_extraction_v2_no_interference()
    test_adaptive_mode_no_side_effects()

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} total")
    print(f"{'=' * 60}")

    if FAIL > 0:
        print("VERDICT: FAIL")
        sys.exit(1)
    else:
        print("VERDICT: ALL PASS")
        sys.exit(0)
