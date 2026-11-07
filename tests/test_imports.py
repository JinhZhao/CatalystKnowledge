"""Import verification test.

验证所有导入的模块可以正确加载。
"""

import sys
from pathlib import Path

# Add src to path - need to add the parent of catalyst_knowledge package
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    print(f"Added to sys.path: {src_path}")


def test_imports():
    """Test that all modules can be imported."""
    errors = []

    # Test core imports
    try:
        from catalyst_knowledge.core.six_dimension_schema import (
            SixDimensionView,
            CatalystDesign,
            Characterization,
            Performance,
            Mechanism,
            StructureActivity,
            Reliability,
        )
        print("[OK] six_dimension_schema imported")
    except Exception as e:
        errors.append(f"six_dimension_schema: {e}")

    try:
        from catalyst_knowledge.core.quality_assessor import (
            QualityReport,
            assess_quality,
        )
        print("[OK] quality_assessor imported")
    except Exception as e:
        errors.append(f"quality_assessor: {e}")

    try:
        from catalyst_knowledge.core.numeric_anchor_checker import (
            NumericAnchorChecker,
            NumericCheckResult,
        )
        print("[OK] numeric_anchor_checker imported")
    except Exception as e:
        errors.append(f"numeric_anchor_checker: {e}")

    try:
        from catalyst_knowledge.core.llm_service import LLMService, ChatMessage
        print("[OK] llm_service imported")
    except Exception as e:
        errors.append(f"llm_service: {e}")

    try:
        from catalyst_knowledge.core.six_dimension_summarizer import (
            SixDimensionSummarizer,
        )
        print("[OK] six_dimension_summarizer imported")
    except Exception as e:
        errors.append(f"six_dimension_summarizer: {e}")

    # Test prompts loader
    try:
        from catalyst_knowledge.prompts.loader import (
            load_prompt,
            list_available_prompts,
        )
        prompts = list_available_prompts()
        print(f"[OK] prompts.loader imported ({len(prompts)} prompts available)")
    except Exception as e:
        errors.append(f"prompts.loader: {e}")

    # Test agents
    try:
        from catalyst_knowledge.agents.quality_agent import QualityAgent
        print("[OK] quality_agent imported")
    except Exception as e:
        errors.append(f"quality_agent: {e}")

    try:
        from catalyst_knowledge.agents.summarizer_agent import SummarizerAgent
        print("[OK] summarizer_agent imported")
    except Exception as e:
        errors.append(f"summarizer_agent: {e}")

    # Test schema instantiation
    try:
        view = SixDimensionView(
            catalyst_design=CatalystDesign(catalyst_system="Pt/TiO2"),
            characterization=Characterization(),
            performance=Performance(),
            mechanism=Mechanism(),
            structure_activity=StructureActivity(),
            reliability=Reliability(),
        )
        assert view.catalyst_design.catalyst_system == "Pt/TiO2"
        print("[OK] SixDimensionView can be instantiated")
    except Exception as e:
        errors.append(f"SixDimensionView instantiation: {e}")

    # Test numeric anchor checker with config
    try:
        checker = NumericAnchorChecker()
        print("[OK] NumericAnchorChecker initialized with config")
    except Exception as e:
        errors.append(f"NumericAnchorChecker init: {e}")

    # Summary
    print("\n" + "=" * 50)
    if errors:
        print(f"FAILED: {len(errors)} errors")
        for err in errors:
            print(f"  [FAIL] {err}")
        return False
    else:
        print("PASSED: All imports successful")
        return True


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
