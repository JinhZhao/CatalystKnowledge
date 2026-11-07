"""验证测试夹具能否通过 Schema V1 解析。"""

import json
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def validate_paper_fixture():
    """验证论文夹具。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        Document, DocumentType, TaxonomyAssignment,
        Experiment, Observation, Reaction, ChemicalEntity, CatalystSample,
        ValueWithSource, DataStatus, Assertion, SourceAnchor, ElementType,
        SchemaMetadata,
    )

    fixture_path = Path(__file__).parent / "fixtures" / "sample_paper_extraction.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 验证 Document
    doc_data = data["document"]
    doc = Document(
        document_id=doc_data["document_id"],
        doi=doc_data["doi"],
        title=doc_data["title"],
        authors=doc_data["authors"],
        publication_year=doc_data["publication_year"],
        journal=doc_data["journal"],
        document_type=DocumentType(doc_data["document_type"]),
        abstract=doc_data["abstract"],
    )
    assert doc.document_id == "test_doc_001"
    print("[OK] Document validation")

    # 验证 TaxonomyAssignment
    tax_data = data["taxonomy"]
    tax = TaxonomyAssignment(
        document_id=tax_data["document_id"],
        layer=tax_data["layer"],
        reaction_types=tax_data["reaction_types"],
        catalyst_types=tax_data["catalyst_types"],
        material_classes=tax_data["material_classes"],
        confidence=tax_data["confidence"],
    )
    assert len(tax.reaction_types) == 2
    print("[OK] TaxonomyAssignment validation")

    # 验证 Experiment
    exp_data = data["experiments"][0]
    reaction = Reaction(
        reaction_type=exp_data["reaction"]["reaction_type"],
        name=exp_data["reaction"]["name"],
        substrates=[
            ChemicalEntity(name=s["name"], role=s["role"])
            for s in exp_data["reaction"]["substrates"]
        ],
        products=[
            ChemicalEntity(name=p["name"], role=p["role"])
            for p in exp_data["reaction"]["products"]
        ],
    )

    temp_data = exp_data["temperature"]
    temp = ValueWithSource(
        raw_value=temp_data["raw_value"],
        normalized_value=temp_data["normalized_value"],
        normalized_unit=temp_data["normalized_unit"],
        status=DataStatus(temp_data["status"]),
    )

    exp = Experiment(
        experiment_id=exp_data["experiment_id"],
        reaction=reaction,
        temperature=temp,
    )
    assert exp.experiment_id == "exp_001"
    print("[OK] Experiment validation")

    # 验证 Observation
    for obs_data in data["observations"]:
        val_data = obs_data["value"]
        val = ValueWithSource(
            raw_value=val_data["raw_value"],
            normalized_value=val_data["normalized_value"],
            normalized_unit=val_data["normalized_unit"],
            status=DataStatus(val_data["status"]),
        )
        obs = Observation(
            observation_id=obs_data["observation_id"],
            experiment_id=obs_data["experiment_id"],
            metric_name=obs_data["metric_name"],
            value=val,
        )
        assert obs.experiment_id == "exp_001"
    print(f"[OK] Observation validation ({len(data['observations'])} observations)")

    # 验证 Assertion
    for assert_data in data["assertions"]:
        assertion = Assertion(
            assertion_id=assert_data["assertion_id"],
            content=assert_data["content"],
            assertion_type=assert_data["assertion_type"],
            experiment_ids=assert_data["experiment_ids"],
            observation_ids=assert_data["observation_ids"],
            document_id=assert_data["document_id"],
            confidence=assert_data["confidence"],
        )
    print(f"[OK] Assertion validation ({len(data['assertions'])} assertions)")

    # 验证 SourceAnchor
    for anchor_data in data["source_anchors"]:
        anchor = SourceAnchor(
            document_id=anchor_data["document_id"],
            element_type=ElementType(anchor_data["element_type"]),
            element_id=anchor_data["element_id"],
            location=anchor_data["location"],
            page=anchor_data["page"],
            raw_text=anchor_data["raw_text"],
            confidence=anchor_data["confidence"],
        )
    print(f"[OK] SourceAnchor validation ({len(data['source_anchors'])} anchors)")

    # 验证 SchemaMetadata
    meta_data = data["schema_metadata"]
    meta = SchemaMetadata(
        schema_name=meta_data["schema_name"],
        schema_version=meta_data["schema_version"],
        extractor_name=meta_data["extractor_name"],
        extractor_version=meta_data["extractor_version"],
    )
    print("[OK] SchemaMetadata validation")

    return True


def validate_patent_fixture():
    """验证专利夹具。"""
    from catalyst_knowledge.schema.catalysis_schema_v1 import (
        Document, DocumentType, PatentClaim, PatentExample,
        Experiment, Reaction, ChemicalEntity, CatalystSample,
        Observation, ValueWithSource, DataStatus,
        SourceAnchor, ElementType, SchemaMetadata,
    )

    fixture_path = Path(__file__).parent / "fixtures" / "sample_patent_extraction.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 验证 Document (patent)
    doc_data = data["document"]
    doc = Document(
        document_id=doc_data["document_id"],
        title=doc_data["title"],
        document_type=DocumentType(doc_data["document_type"]),
        patent_number=doc_data["patent_number"],
        patent_family=doc_data["patent_family"],
    )
    assert doc.document_type == DocumentType.PATENT
    print("[OK] Patent Document validation")

    # 验证 PatentClaim
    for claim_data in data["patent_claims"]:
        claim = PatentClaim(
            claim_id=claim_data["claim_id"],
            patent_document_id=claim_data["patent_document_id"],
            claim_number=claim_data["claim_number"],
            claim_type=claim_data["claim_type"],
            text=claim_data["text"],
            covers_examples=claim_data["covers_examples"],
            scope_note=claim_data["scope_note"],
        )
    print(f"[OK] PatentClaim validation ({len(data['patent_claims'])} claims)")

    # 验证 PatentExample
    for example_data in data["patent_examples"]:
        # 构建 Experiment
        exp_data = example_data.get("experiment", {})
        reaction_data = exp_data.get("reaction", {})

        if reaction_data:
            reaction = Reaction(
                reaction_type=reaction_data["reaction_type"],
                substrates=[
                    ChemicalEntity(name=s["name"], role=s["role"])
                    for s in reaction_data.get("substrates", [])
                ],
            )
            experiment = Experiment(
                reaction=reaction,
                procedure=exp_data.get("procedure", ""),
            )
        else:
            experiment = None

        # 构建 Observations
        observations = []
        for obs_data in example_data.get("results", []):
            val_data = obs_data["value"]
            val = ValueWithSource(
                raw_value=val_data["raw_value"],
                normalized_value=val_data["normalized_value"],
                normalized_unit=val_data["normalized_unit"],
                status=DataStatus(val_data["status"]),
            )
            obs = Observation(
                observation_id=obs_data["observation_id"],
                experiment_id=obs_data["experiment_id"],
                metric_name=obs_data["metric_name"],
                value=val,
            )
            observations.append(obs)

        example = PatentExample(
            example_id=example_data["example_id"],
            patent_document_id=example_data["patent_document_id"],
            example_number=example_data["example_number"],
            example_type=example_data["example_type"],
            experiment=experiment,
            results=observations,
        )
    print(f"[OK] PatentExample validation ({len(data['patent_examples'])} examples)")

    return True


def run_fixture_validation():
    """运行夹具验证。"""
    print("=" * 60)
    print("Schema V1 Fixture Validation")
    print("=" * 60)

    try:
        print("\n--- Paper Fixture ---")
        validate_paper_fixture()

        print("\n--- Patent Fixture ---")
        validate_patent_fixture()

        print("\n" + "=" * 60)
        print("PASSED: All fixtures validated successfully")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_fixture_validation()
    sys.exit(0 if success else 1)
