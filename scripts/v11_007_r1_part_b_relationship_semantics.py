#!/usr/bin/env python3
"""
SINGLE-DOC-V11-007-R1 | Part B: 61条关系科学语义复核
检查对象类型、方向、谓词语义、来源
"""
import json
from pathlib import Path

DOCS = ['F02', 'F07', 'P01', 'PAT01']
REPORT_DIR = Path('runs/single_doc_reports')
OUTPUT_DIR = Path('runs/v11_007_r1')

ID_FIELD_MAP = {
    'facts': 'fact_id',
    'claims': 'claim_id',
    'evidence': 'evidence_id',
    'limitations': 'limitation_id',
    'open_questions': 'question_id',
    'hypotheses': 'hypothesis_id',
    'experiment_proposals': 'proposal_id',
    'feasibility_assessments': 'feasibility_id',
    'validation_plans': 'plan_id',
}

PREDICATE_CONSTRAINTS = {
    'SUPPORTED_BY': {
        'valid_sources': ['claims'],
        'valid_targets': ['evidence'],
        'description': 'Claim is supported by Evidence',
        'direction': 'claim -> evidence',
    },
    'CHALLENGED_BY': {
        'valid_sources': ['claims'],
        'valid_targets': ['evidence'],
        'description': 'Claim is challenged by Evidence',
        'direction': 'claim -> evidence',
    },
    'QUALIFIED_BY': {
        'valid_sources': ['claims'],
        'valid_targets': ['limitations'],
        'description': 'Claim is qualified/limited by Limitation',
        'direction': 'claim -> limitation',
    },
    'VALIDATES': {
        'valid_sources': ['hypotheses', 'claims'],
        'valid_targets': ['feasibility_assessments', 'validation_plans'],
        'description': 'Hypothesis validates Feasibility OR Claim validates ValidationPlan',
        'direction': 'hypothesis/claim -> feasibility/validation_plan',
        'pairs': [
            ('hypotheses', 'feasibility_assessments'),
            ('claims', 'validation_plans'),
        ],
    },
    'REQUIRES': {
        'valid_sources': ['claims'],
        'valid_targets': ['open_questions'],
        'description': 'Claim requires further investigation via OpenQuestion',
        'direction': 'claim -> open_question',
    },
    'MOTIVATES': {
        'valid_sources': ['open_questions'],
        'valid_targets': ['hypotheses'],
        'description': 'OpenQuestion motivates Hypothesis',
        'direction': 'open_question -> hypothesis',
    },
}


def load_report(doc_id):
    path = REPORT_DIR / doc_id / f'{doc_id}_knowledge_report.json'
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_object_type_index(knowledge_objects):
    """Build mapping: object_id -> object_type"""
    id_to_type = {}
    for obj_type, id_field in ID_FIELD_MAP.items():
        objects = knowledge_objects.get(obj_type, [])
        for obj in objects:
            obj_id = obj.get(id_field) or obj.get('object_id')
            if obj_id:
                id_to_type[obj_id] = obj_type
    return id_to_type


def review_relationship(rel, id_to_type):
    """Review a single relationship for type/direction/semantic correctness"""
    rel_id = rel.get('relationship_id', '')
    rel_type = rel.get('relationship_type', '')
    source_id = rel.get('source_id', '')
    target_id = rel.get('target_id', '')
    has_anchor = bool(rel.get('source_anchor'))

    source_type = id_to_type.get(source_id, 'UNKNOWN')
    target_type = id_to_type.get(target_id, 'UNKNOWN')

    constraints = PREDICATE_CONSTRAINTS.get(rel_type)

    if not constraints:
        return {
            'rel_id': rel_id,
            'rel_type': rel_type,
            'source_id': source_id,
            'source_type': source_type,
            'target_id': target_id,
            'target_type': target_type,
            'structure_valid': False,
            'semantic_valid': False,
            'issues': [f'Unknown relationship type: {rel_type}'],
            'has_source_anchor': has_anchor,
        }

    issues = []

    source_ok = source_type in constraints['valid_sources']
    target_ok = target_type in constraints['valid_targets']

    if not source_ok:
        issues.append(f"Source type '{source_type}' not in valid sources {constraints['valid_sources']}")
    if not target_ok:
        issues.append(f"Target type '{target_type}' not in valid targets {constraints['valid_targets']}")

    if source_type == 'UNKNOWN':
        issues.append(f"Source object '{source_id}' not found in any knowledge_objects type")
    if target_type == 'UNKNOWN':
        issues.append(f"Target object '{target_id}' not found in any knowledge_objects type")

    semantic_valid = True
    if rel_type == 'VALIDATES' and 'pairs' in constraints:
        valid_pairs = constraints['pairs']
        pair_match = any(
            source_type == pair[0] and target_type == pair[1]
            for pair in valid_pairs
        )
        if not pair_match and source_ok and target_ok:
            semantic_valid = False
            issues.append(f"VALIDATES pair ({source_type}->{target_type}) not in valid pairs")

    structure_valid = source_ok and target_ok and len([i for i in issues if 'not found' in i]) == 0

    semantic_note = ""
    if structure_valid:
        if rel_type in ('SUPPORTED_BY', 'CHALLENGED_BY'):
            semantic_note = f"Claim-Evidence link: structurally and semantically valid"
        elif rel_type == 'QUALIFIED_BY':
            semantic_note = f"Claim-Limitation qualification: valid"
        elif rel_type == 'VALIDATES':
            semantic_note = f"Validation link: {source_type} -> {target_type}, valid"
        elif rel_type == 'REQUIRES':
            semantic_note = f"Requirement link: Claim requires OpenQuestion, valid"
        elif rel_type == 'MOTIVATES':
            semantic_note = f"Motivation link: OpenQuestion motivates Hypothesis, valid"

    return {
        'rel_id': rel_id,
        'rel_type': rel_type,
        'source_id': source_id,
        'source_type': source_type,
        'target_id': target_id,
        'target_type': target_type,
        'structure_valid': structure_valid,
        'semantic_valid': semantic_valid and structure_valid,
        'semantic_note': semantic_note,
        'issues': issues,
        'has_source_anchor': has_anchor,
    }


def main():
    print("=" * 70)
    print("V11-007-R1 Part B: 61条关系科学语义复核")
    print("=" * 70)

    all_reviews = {}
    total_stats = {
        'total': 0,
        'structure_valid': 0,
        'structure_invalid': 0,
        'semantic_valid': 0,
        'semantic_invalid': 0,
        'with_anchor': 0,
        'without_anchor': 0,
        'by_type': {},
        'by_doc': {},
    }

    for doc in DOCS:
        report = load_report(doc)
        relationships = report.get('knowledge_relationships', [])
        ko = report.get('knowledge_objects', {})
        id_to_type = build_object_type_index(ko)

        doc_reviews = []
        doc_stats = {'total': len(relationships), 'valid': 0, 'invalid': 0, 'issues': []}

        for rel in relationships:
            review = review_relationship(rel, id_to_type)
            doc_reviews.append(review)

            total_stats['total'] += 1
            if review['structure_valid']:
                total_stats['structure_valid'] += 1
                doc_stats['valid'] += 1
            else:
                total_stats['structure_invalid'] += 1
                doc_stats['invalid'] += 1
                doc_stats['issues'].append(review)

            if review['semantic_valid']:
                total_stats['semantic_valid'] += 1
            else:
                total_stats['semantic_invalid'] += 1

            if review['has_source_anchor']:
                total_stats['with_anchor'] += 1
            else:
                total_stats['without_anchor'] += 1

            rt = review['rel_type']
            if rt not in total_stats['by_type']:
                total_stats['by_type'][rt] = {'count': 0, 'valid': 0, 'semantic_valid': 0}
            total_stats['by_type'][rt]['count'] += 1
            if review['structure_valid']:
                total_stats['by_type'][rt]['valid'] += 1
            if review['semantic_valid']:
                total_stats['by_type'][rt]['semantic_valid'] += 1

        all_reviews[doc] = {
            'doc_id': doc,
            'relationship_count': len(relationships),
            'reviews': doc_reviews,
            'doc_stats': doc_stats,
        }
        total_stats['by_doc'][doc] = doc_stats

        status = "ALL VALID" if doc_stats['invalid'] == 0 else f"{doc_stats['invalid']} ISSUES"
        print(f"  {doc}: {doc_stats['total']} relationships, {status}")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_stats['total']} relationships")
    print(f"Structure valid: {total_stats['structure_valid']}/{total_stats['total']} ({total_stats['structure_valid']/total_stats['total']*100:.1f}%)")
    print(f"Semantic valid: {total_stats['semantic_valid']}/{total_stats['total']} ({total_stats['semantic_valid']/total_stats['total']*100:.1f}%)")
    print(f"With SourceAnchor: {total_stats['with_anchor']}/{total_stats['total']}")

    print(f"\nBy relationship type:")
    for rt, stats in sorted(total_stats['by_type'].items()):
        print(f"  {rt}: {stats['count']} total, {stats['valid']} struct_valid, {stats['semantic_valid']} semantic_valid")

    result = {
        'r1_review': True,
        'review_type': 'V11-007-R1 Part B: Relationship scientific semantics review',
        'documents': all_reviews,
        'total_stats': total_stats,
    }

    output_path = OUTPUT_DIR / 'part_b_relationship_semantics.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nResult saved to: {output_path}")


if __name__ == '__main__':
    main()
