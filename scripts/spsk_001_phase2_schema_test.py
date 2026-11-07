"""SINGLE-PAPER-KNOWLEDGE-001 Phase 2 — Schema 扩展向后兼容性测试。

测试目标：
1. 现有模型（Assertion, Evidence, Observation, Experiment）可正常创建
2. 新模型（Limitation, OpenQuestion, Feasibility, ValidationPlan）可正常创建
3. 扩展模型（*Extended）可与原模型共存
4. 所有新字段均为 Optional，不影响现有数据
5. 枚举类型正确定义
"""

import sys
import traceback
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def test_separator(name: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def test_pass(name: str) -> None:
    print(f"  [PASS] {name}")


def test_fail(name: str, error: str) -> None:
    print(f"  [FAIL] {name}: {error}")


def test_original_models() -> int:
    """测试 1: 现有模型向后兼容"""
    test_separator("Test 1: Original Models Backward Compatibility")
    passed = 0
    total = 4

    try:
        from catalyst_knowledge.schema.catalysis_schema_v1 import (
            Assertion, Evidence, Observation, Experiment, Reaction,
            SourceAnchor, ElementType, DataStatus
        )

        # Test Assertion (original)
        assertion = Assertion(
            content="Pt catalyst shows high activity",
            assertion_type="finding",
            document_id="doc_001",
        )
        assert assertion.assertion_id is not None
        assert assertion.confidence == 1.0
        assert assertion.experiment_ids == []
        test_pass("Assertion (original fields only)")
        passed += 1

        # Test Evidence (original)
        evidence = Evidence(
            assertion_id=assertion.assertion_id,
            evidence_type="experimental",
            data_source="table",
        )
        assert evidence.evidence_id is not None
        assert evidence.observation_ids == []
        test_pass("Evidence (original fields only)")
        passed += 1

        # Test Observation (original)
        from catalyst_knowledge.schema.catalysis_schema_v1 import ValueWithSource
        obs = Observation(
            experiment_id="exp_001",
            metric_name="conversion",
            value=ValueWithSource(raw_value="95%"),
        )
        assert obs.observation_id is not None
        test_pass("Observation (original fields only)")
        passed += 1

        # Test Experiment (original)
        reaction = Reaction(reaction_type="hydrogenation", name="test reaction")
        exp = Experiment(
            reaction=reaction,
            procedure="Standard procedure",
        )
        assert exp.experiment_id is not None
        test_pass("Experiment (original fields only)")
        passed += 1

    except Exception as e:
        test_fail("Original models", str(e))
        traceback.print_exc()

    print(f"\n  Result: {passed}/{total} passed")
    return passed


def test_new_models() -> int:
    """测试 2: 新模型可正常创建"""
    test_separator("Test 2: New Models Creation")
    passed = 0
    total = 4

    try:
        from catalyst_knowledge.schema.catalysis_schema_v1_extensions import (
            Limitation, OpenQuestion, Feasibility, ValidationPlan,
            LimitationType, QuestionType, FeasibilityStatus, PlanStatus,
        )

        # Test Limitation
        limitation = Limitation(
            document_id="doc_001",
            content="Only tested at laboratory scale",
            limitation_type=LimitationType.SCOPE,
        )
        assert limitation.limitation_id is not None
        assert limitation.limitation_type == LimitationType.SCOPE
        test_pass("Limitation model")
        passed += 1

        # Test OpenQuestion
        question = OpenQuestion(
            document_id="doc_001",
            content="What is the rate-determining step?",
            question_type=QuestionType.MECHANISM,
        )
        assert question.question_id is not None
        assert question.question_type == QuestionType.MECHANISM
        test_pass("OpenQuestion model")
        passed += 1

        # Test Feasibility
        feasibility = Feasibility(
            document_id="doc_001",
            target_type="scale-up",
            target_id="hypothesis_001",
            feasibility_status=FeasibilityStatus.CHALLENGING,
            constraints=["Heat transfer at large scale"],
        )
        assert feasibility.feasibility_id is not None
        assert feasibility.feasibility_status == FeasibilityStatus.CHALLENGING
        test_pass("Feasibility model")
        passed += 1

        # Test ValidationPlan
        plan = ValidationPlan(
            document_id="doc_001",
            method_description="Isotope labeling experiment",
            validates_hypothesis_id="hyp_001",
            evaluation_metrics=["Kinetic isotope effect"],
        )
        assert plan.plan_id is not None
        assert plan.plan_status == PlanStatus.PROPOSED
        test_pass("ValidationPlan model")
        passed += 1

    except Exception as e:
        test_fail("New models", str(e))
        traceback.print_exc()

    print(f"\n  Result: {passed}/{total} passed")
    return passed


def test_extended_models() -> int:
    """测试 3: 扩展模型与原模型共存"""
    test_separator("Test 3: Extended Models Coexistence")
    passed = 0
    total = 4

    try:
        from catalyst_knowledge.schema.catalysis_schema_v1 import (
            Assertion, Evidence, Observation, Experiment, Reaction,
            ValueWithSource,
        )
        from catalyst_knowledge.schema.catalysis_schema_v1_extensions import (
            AssertionExtended, EvidenceExtended,
            ObservationExtended, ExperimentExtended,
            AssertionSource, EvidencePolarity, ExperimentStatus,
        )

        # Test AssertionExtended
        assertion = Assertion(
            content="Test assertion",
            assertion_type="finding",
            document_id="doc_001",
        )
        ext = AssertionExtended(
            assertion_id=assertion.assertion_id,
            assertion_source=AssertionSource.AUTHOR_STATED,
            validation_status="unvalidated",
        )
        assert ext.assertion_id == assertion.assertion_id
        assert ext.assertion_source == AssertionSource.AUTHOR_STATED
        test_pass("AssertionExtended coexists with Assertion")
        passed += 1

        # Test EvidenceExtended
        evidence = Evidence(
            assertion_id=assertion.assertion_id,
            evidence_type="experimental",
            data_source="table",
        )
        ext2 = EvidenceExtended(
            evidence_id=evidence.evidence_id,
            evidence_polarity=EvidencePolarity.SUPPORTING,
            evidence_strength="strong",
        )
        assert ext2.evidence_id == evidence.evidence_id
        test_pass("EvidenceExtended coexists with Evidence")
        passed += 1

        # Test ObservationExtended
        obs = Observation(
            experiment_id="exp_001",
            metric_name="yield",
            value=ValueWithSource(raw_value="85%"),
        )
        ext3 = ObservationExtended(
            observation_id=obs.observation_id,
            reliability="HIGH",
        )
        assert ext3.observation_id == obs.observation_id
        test_pass("ObservationExtended coexists with Observation")
        passed += 1

        # Test ExperimentExtended
        reaction = Reaction(reaction_type="test", name="test")
        exp = Experiment(reaction=reaction)
        ext4 = ExperimentExtended(
            experiment_id=exp.experiment_id,
            experiment_status=ExperimentStatus.EXECUTED,
        )
        assert ext4.experiment_id == exp.experiment_id
        test_pass("ExperimentExtended coexists with Experiment")
        passed += 1

    except Exception as e:
        test_fail("Extended models", str(e))
        traceback.print_exc()

    print(f"\n  Result: {passed}/{total} passed")
    return passed


def test_enums() -> int:
    """测试 4: 枚举类型正确定义"""
    test_separator("Test 4: Enum Definitions")
    passed = 0
    total = 8

    try:
        from catalyst_knowledge.schema.catalysis_schema_v1_extensions import (
            AssertionSource, EvidencePolarity, ExperimentStatus,
            LimitationType, QuestionType, ResolutionStatus,
            FeasibilityStatus, PlanStatus,
        )

        enums = [
            ("AssertionSource", AssertionSource, ["AUTHOR_STATED", "SYSTEM_INFERRED"]),
            ("EvidencePolarity", EvidencePolarity, ["SUPPORTING", "CHALLENGING", "QUALIFYING"]),
            ("ExperimentStatus", ExperimentStatus, ["EXECUTED", "PROPOSED"]),
            ("LimitationType", LimitationType, ["SCOPE", "ACCURACY", "ASSUMPTION"]),
            ("QuestionType", QuestionType, ["MECHANISM", "SCOPE", "OPTIMIZATION"]),
            ("ResolutionStatus", ResolutionStatus, ["OPEN", "PARTIAL", "RESOLVED"]),
            ("FeasibilityStatus", FeasibilityStatus, ["FEASIBLE", "CHALLENGING", "INFEASIBLE"]),
            ("PlanStatus", PlanStatus, ["PROPOSED", "IN_PROGRESS", "COMPLETED"]),
        ]

        for name, enum_cls, expected_values in enums:
            for val in expected_values:
                assert hasattr(enum_cls, val), f"{name} missing {val}"
            test_pass(f"{name} enum defined correctly")
            passed += 1

    except Exception as e:
        test_fail("Enums", str(e))
        traceback.print_exc()

    print(f"\n  Result: {passed}/{total} passed")
    return passed


def test_aggregation_model() -> int:
    """测试 5: SinglePaperKnowledge 聚合模型"""
    test_separator("Test 5: SinglePaperKnowledge Aggregation")
    passed = 0
    total = 1

    try:
        from catalyst_knowledge.schema.catalysis_schema_v1_extensions import (
            SinglePaperKnowledge, Limitation, OpenQuestion,
            LimitationType, QuestionType,
        )

        spk = SinglePaperKnowledge(
            document_id="doc_001",
            limitations=[
                Limitation(
                    document_id="doc_001",
                    content="Test limitation",
                    limitation_type=LimitationType.SCOPE,
                )
            ],
            open_questions=[
                OpenQuestion(
                    document_id="doc_001",
                    content="Test question",
                    question_type=QuestionType.MECHANISM,
                )
            ],
            relationship_count=15,
            object_count=35,
        )

        assert spk.document_id == "doc_001"
        assert len(spk.limitations) == 1
        assert len(spk.open_questions) == 1
        assert spk.relationship_count == 15
        assert spk.object_count == 35
        test_pass("SinglePaperKnowledge aggregation model")
        passed += 1

    except Exception as e:
        test_fail("Aggregation model", str(e))
        traceback.print_exc()

    print(f"\n  Result: {passed}/{total} passed")
    return passed


def test_serialization() -> int:
    """测试 6: 序列化/反序列化"""
    test_separator("Test 6: Serialization")
    passed = 0
    total = 2

    try:
        from catalyst_knowledge.schema.catalysis_schema_v1_extensions import (
            Limitation, LimitationType, SinglePaperKnowledge,
        )

        # Test model_dump
        limitation = Limitation(
            document_id="doc_001",
            content="Test limitation",
            limitation_type=LimitationType.SCOPE,
        )
        data = limitation.model_dump()
        assert "limitation_id" in data
        assert "document_id" in data
        assert data["limitation_type"] == "SCOPE"
        test_pass("model_dump() serialization")
        passed += 1

        # Test model_validate_json round-trip
        json_str = limitation.model_dump_json()
        restored = Limitation.model_validate_json(json_str)
        assert restored.limitation_id == limitation.limitation_id
        assert restored.content == limitation.content
        test_pass("JSON round-trip serialization")
        passed += 1

    except Exception as e:
        test_fail("Serialization", str(e))
        traceback.print_exc()

    print(f"\n  Result: {passed}/{total} passed")
    return passed


def test_optional_fields() -> int:
    """测试 7: 所有新字段均为 Optional"""
    test_separator("Test 7: Optional Field Verification")
    passed = 0
    total = 4

    try:
        from catalyst_knowledge.schema.catalysis_schema_v1_extensions import (
            Limitation, OpenQuestion, Feasibility, ValidationPlan,
            LimitationType, QuestionType, FeasibilityStatus,
        )

        # Limitation: only required fields
        lim = Limitation(
            document_id="doc_001",
            content="Test",
            limitation_type=LimitationType.SCOPE,
        )
        assert lim.affects_assertion_ids == []
        assert lim.source is None
        test_pass("Limitation optional fields default correctly")
        passed += 1

        # OpenQuestion: only required fields
        q = OpenQuestion(
            document_id="doc_001",
            content="Test",
            question_type=QuestionType.MECHANISM,
        )
        assert q.motivates_hypothesis_ids == []
        assert q.source is None
        test_pass("OpenQuestion optional fields default correctly")
        passed += 1

        # Feasibility: only required fields
        f = Feasibility(
            document_id="doc_001",
            target_type="hypothesis",
            target_id="hyp_001",
            feasibility_status=FeasibilityStatus.FEASIBLE,
        )
        assert f.constraints == []
        assert f.source is None
        test_pass("Feasibility optional fields default correctly")
        passed += 1

        # ValidationPlan: only required fields
        vp = ValidationPlan(
            document_id="doc_001",
            method_description="Test method",
        )
        assert vp.control_experiments == []
        assert vp.source is None
        test_pass("ValidationPlan optional fields default correctly")
        passed += 1

    except Exception as e:
        test_fail("Optional fields", str(e))
        traceback.print_exc()

    print(f"\n  Result: {passed}/{total} passed")
    return passed


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  SINGLE-PAPER-KNOWLEDGE-001 Phase 2")
    print("  Schema Extension Backward Compatibility Tests")
    print("=" * 60)

    results = []
    results.append(("Original Models", test_original_models()))
    results.append(("New Models", test_new_models()))
    results.append(("Extended Models", test_extended_models()))
    results.append(("Enums", test_enums()))
    results.append(("Aggregation", test_aggregation_model()))
    results.append(("Serialization", test_serialization()))
    results.append(("Optional Fields", test_optional_fields()))

    # Summary
    test_separator("SUMMARY")
    total_passed = sum(r[1] for r in results)
    total_tests = 4 + 4 + 4 + 8 + 1 + 2 + 4  # sum of all test counts
    print(f"\n  Total: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n  [OK] ALL TESTS PASSED - Schema extensions are backward compatible")
        return 0
    else:
        print(f"\n  [WARN] {total_tests - total_passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
