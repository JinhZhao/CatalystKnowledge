"""Schema V1 可执行校验测试。

验证 Catalysis Schema V1 的所有模型可以正确实例化和验证。
"""

import sys
from datetime import datetime
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def test_source_anchor():
    """测试 SourceAnchor 模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        SourceAnchor,
        ElementType,
    )

    anchor = SourceAnchor(
        document_id="doc_001",
        element_type=ElementType.TABLE,
        element_id="table_3",
        location="Row 2, Column 3",
        page=5,
        raw_text="TOF = 500 h-1",
        confidence=0.95,
    )
    assert anchor.document_id == "doc_001"
    assert anchor.confidence == 0.95
    print("[OK] SourceAnchor")


def test_value_with_source():
    """测试 ValueWithSource 模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        ValueWithSource,
        DataStatus,
        SourceAnchor,
        ElementType,
    )

    # 基本值
    value = ValueWithSource(
        raw_value="150 deg C",
        normalized_value=150.0,
        normalized_unit="degC",
        status=DataStatus.NORMALIZED,
    )
    assert value.normalized_value == 150.0
    print("[OK] ValueWithSource (basic)")

    # 带来源的值
    anchor = SourceAnchor(
        document_id="doc_001",
        element_type=ElementType.TABLE,
        element_id="table_1",
    )
    value_with_source = ValueWithSource(
        raw_value="95%",
        normalized_value=0.95,
        normalized_unit="fraction",
        status=DataStatus.REPORTED,
        source=anchor,
    )
    assert value_with_source.source is not None
    print("[OK] ValueWithSource (with source)")


def test_document():
    """测试 Document 模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        Document,
        DocumentType,
        Attachment,
    )

    doc = Document(
        doi="10.1000/xyz123",
        title="Test Paper on Catalysis",
        authors=["Author A", "Author B"],
        publication_year=2024,
        journal="Journal of Catalysis",
        document_type=DocumentType.RESEARCH,
        abstract="This is a test abstract.",
    )
    assert doc.document_type == DocumentType.RESEARCH
    assert len(doc.authors) == 2
    print("[OK] Document")

    # 测试附件
    attachment = Attachment(
        filename="si.pdf",
        file_type="pdf",
        relation="supplementary",
    )
    doc_with_attachment = Document(
        title="Paper with SI",
        attachments=[attachment],
    )
    assert len(doc_with_attachment.attachments) == 1
    print("[OK] Document with Attachment")


def test_chemical_entity():
    """测试 ChemicalEntity 模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        ChemicalEntity,
        OntologyMapping,
    )

    entity = ChemicalEntity(
        name="Platinum",
        role="catalyst",
        smiles="[Pt]",
        chebi_id="CHEBI:33364",
        formula="Pt",
        molecular_weight=195.084,
    )
    assert entity.role == "catalyst"
    print("[OK] ChemicalEntity")

    # 测试本体映射
    entity_with_ontology = ChemicalEntity(
        name="Pd/C",
        role="catalyst",
        ontology=OntologyMapping(
            local_name="Pd/C",
            standard_id="CHEBI:33364",
            ontology_source="ChEBI",
            mapping_confidence=0.8,
            is_resolved=False,
        ),
    )
    assert entity_with_ontology.ontology is not None
    print("[OK] ChemicalEntity with OntologyMapping")


def test_experiment_observation():
    """测试 Experiment 和 Observation 模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        Experiment,
        Observation,
        Reaction,
        ChemicalEntity,
        ValueWithSource,
        DataStatus,
    )

    # 创建反应
    reaction = Reaction(
        reaction_type="hydrogenation",
        name="Olefin Hydrogenation",
        substrates=[ChemicalEntity(name="Ethylene", role="substrate")],
        products=[ChemicalEntity(name="Ethane", role="product")],
    )

    # 创建实验
    experiment = Experiment(
        reaction=reaction,
        temperature=ValueWithSource(
            raw_value="100 deg C",
            normalized_value=100.0,
            normalized_unit="degC",
            status=DataStatus.REPORTED,
        ),
        pressure=ValueWithSource(
            raw_value="10 bar",
            normalized_value=10.0,
            normalized_unit="bar",
            status=DataStatus.REPORTED,
        ),
        procedure="Added catalyst to reactor...",
    )
    assert experiment.experiment_id
    print("[OK] Experiment")

    # 创建观测
    observation = Observation(
        experiment_id=experiment.experiment_id,
        metric_name="conversion",
        value=ValueWithSource(
            raw_value=">99%",
            normalized_value=0.99,
            normalized_unit="fraction",
            status=DataStatus.REPORTED,
        ),
    )
    assert observation.metric_name == "conversion"
    print("[OK] Observation")


def test_patent_models():
    """测试专利相关模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        PatentClaim,
        PatentExample,
        Document,
        DocumentType,
    )

    # 创建专利文档
    patent = Document(
        title="Catalytic Process Patent",
        document_type=DocumentType.PATENT,
        patent_number="US12345678",
        patent_family="US12345678-A1",
    )

    # 创建权利要求
    claim = PatentClaim(
        patent_document_id=patent.document_id,
        claim_number=1,
        claim_type="independent",
        text="A process for catalyzing...",
        covers_examples=True,
    )
    assert claim.claim_type == "independent"
    print("[OK] PatentClaim")

    # 创建实施例
    example = PatentExample(
        patent_document_id=patent.document_id,
        example_number="E1",
        example_type="example",
    )
    assert example.example_type == "example"
    print("[OK] PatentExample")


def test_taxonomy_assignment():
    """测试 TaxonomyAssignment 模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        TaxonomyAssignment,
        SourceAnchor,
        ElementType,
    )

    assignment = TaxonomyAssignment(
        document_id="doc_001",
        layer="metadata",
        reaction_types=["hydrogenation", "oxidation"],
        catalyst_types=["supported_metal"],
        confidence={"hydrogenation": 0.9, "oxidation": 0.7},
    )
    assert len(assignment.reaction_types) == 2
    print("[OK] TaxonomyAssignment")


def test_schema_metadata():
    """测试 SchemaMetadata 模型。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        SchemaMetadata,
        SCHEMA_VERSION,
    )

    metadata = SchemaMetadata(
        extractor_name="test_extractor",
        extractor_version="1.0.0",
        prompt_version="v1",
    )
    assert metadata.schema_version == SCHEMA_VERSION
    print("[OK] SchemaMetadata")


def test_data_status_enum():
    """测试 DataStatus 枚举完整性。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import DataStatus

    expected = [
        "REPORTED", "NORMALIZED", "INFERRED", "PREDICTED",
        "NOT_REPORTED", "NOT_EXTRACTED", "NOT_APPLICABLE", "CONFLICTED",
    ]
    actual = [s.value for s in DataStatus]
    assert set(expected) == set(actual), f"Missing: {set(expected) - set(actual)}"
    print("[OK] DataStatus enum complete")


def test_value_with_source_validation():
    """测试 ValueWithSource 的验证规则。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import ValueWithSource
    from pydantic import ValidationError

    # 正常情况
    v = ValueWithSource(
        raw_value="100",
        normalized_value=100.0,
        normalized_unit="degC",
    )
    assert v.normalized_unit == "degC"
    print("[OK] ValueWithSource validation (normal)")

    # 异常情况：有值无单位
    try:
        v = ValueWithSource(
            raw_value="100",
            normalized_value=100.0,
            normalized_unit=None,  # 应该报错
        )
        print("[FAIL] ValueWithSource should reject value without unit")
        return False
    except ValidationError:
        print("[OK] ValueWithSource validation (rejects value without unit)")
        return True


def run_all_tests():
    """运行所有测试。"""
    tests = [
        test_source_anchor,
        test_value_with_source,
        test_document,
        test_chemical_entity,
        test_experiment_observation,
        test_patent_models,
        test_taxonomy_assignment,
        test_schema_metadata,
        test_data_status_enum,
        test_value_with_source_validation,
    ]

    passed = 0
    failed = 0

    print("=" * 60)
    print("Catalysis Schema V1 Validation Tests")
    print("=" * 60)

    for test in tests:
        try:
            result = test()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
