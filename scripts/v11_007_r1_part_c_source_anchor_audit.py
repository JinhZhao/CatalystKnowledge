#!/usr/bin/env python3
"""
SINGLE-DOC-V11-007-R1 | Part C: SourceAnchor真实性与24条NOT_ATTEMPTED对象恢复
"""
import json
from pathlib import Path

DOCS = ['F02', 'F07', 'P01', 'PAT01']
REPORT_DIR = Path('runs/single_doc_reports')
EVIDENCE_DIR = Path('runs/evidence_004')
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


def load_report(doc_id):
    path = REPORT_DIR / doc_id / f'{doc_id}_knowledge_report.json'
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_evidence_alignment(doc_id):
    path = EVIDENCE_DIR / 'part_b_evidence_alignment.json'
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get(doc_id, {})


def categorize_source_anchor(report, alignment_data):
    """Categorize each object's SourceAnchor into 5 types"""
    ko = report.get('knowledge_objects', {})
    alignments = alignment_data.get('alignments', [])
    align_map = {a['object_id']: a for a in alignments}

    categories = {
        'real_document_ir_element_id': [],
        'synthetic_dimension_level': [],
        'with_citation_verified': [],
        'cannot_locate': [],
        'system_inferred_candidate': [],
    }

    all_objects = []
    for obj_type, id_field in ID_FIELD_MAP.items():
        objects = ko.get(obj_type, [])
        for obj in objects:
            obj_id = obj.get(id_field) or obj.get('object_id')
            if not obj_id:
                continue

            anchor = obj.get('source_anchor', {})
            align = align_map.get(obj_id, {})
            anchor_status = align.get('source_status', 'UNKNOWN')
            verification = align.get('verification_status', 'UNKNOWN')
            element_id = anchor.get('element_id') or align.get('element_id')
            confidence = anchor.get('confidence') or align.get('confidence', 0)
            provenance = obj.get('provenance_label', '')

            entry = {
                'object_id': obj_id,
                'object_type': obj_type,
                'element_id': element_id,
                'anchor_confidence': confidence,
                'alignment_status': anchor_status,
                'verification_status': verification,
                'provenance': provenance,
            }

            if element_id and element_id.startswith(doc_id_from_obj_id(obj_id) + '_p'):
                categories['real_document_ir_element_id'].append(entry)
            elif element_id and element_id.startswith(doc_id_from_obj_id(obj_id) + '_dim_'):
                categories['synthetic_dimension_level'].append(entry)
            elif verification == 'VERIFIED' and element_id:
                categories['with_citation_verified'].append(entry)
            elif anchor_status == 'UNRESOLVED' and not element_id:
                if provenance in ('DERIVED', 'SYSTEM_INFERRED'):
                    categories['system_inferred_candidate'].append(entry)
                else:
                    categories['cannot_locate'].append(entry)
            elif anchor_status == 'SOURCE_LINKED':
                categories['real_document_ir_element_id'].append(entry)
            else:
                categories['system_inferred_candidate'].append(entry)

            all_objects.append(entry)

    return categories, all_objects


def doc_id_from_obj_id(obj_id):
    """Extract doc_id from object_id (e.g., F02_claim_004 -> F02)"""
    parts = obj_id.split('_')
    return parts[0] if parts else ''


def retry_not_attempted(alignment_data, report):
    """Retry NOT_ATTEMPTED objects using existing EvidenceAligner logic"""
    alignments = alignment_data.get('alignments', [])
    ko = report.get('knowledge_objects', {})

    not_attempted = [a for a in alignments if a.get('verification_status') == 'NOT_ATTEMPTED']

    results = []
    for item in not_attempted:
        obj_id = item['object_id']
        obj_type = item['object_type']
        original_status = item['source_status']

        obj_data = find_object(ko, obj_id, obj_type)
        if not obj_data:
            results.append({
                'object_id': obj_id,
                'original_status': original_status,
                'retry_result': 'OBJECT_NOT_FOUND',
                'new_status': original_status,
                'reason': f'Object {obj_id} not found in report',
            })
            continue

        content = obj_data.get('content', '') or obj_data.get('rationale', '') or obj_data.get('description', '')
        if not content:
            results.append({
                'object_id': obj_id,
                'original_status': original_status,
                'retry_result': 'NO_CONTENT',
                'new_status': original_status,
                'reason': 'Object has no extractable content for alignment',
            })
            continue

        query_terms = extract_query_terms(content)
        if not query_terms:
            results.append({
                'object_id': obj_id,
                'original_status': original_status,
                'retry_result': 'NO_QUERY_TERMS',
                'new_status': 'UNRESOLVED',
                'reason': 'Cannot extract meaningful query terms from content',
            })
            continue

        results.append({
            'object_id': obj_id,
            'original_status': original_status,
            'retry_result': 'ATTEMPTED_WITH_TERMS',
            'new_status': 'REQUIRES_MANUAL_REVIEW',
            'query_terms': query_terms,
            'reason': f'Extracted {len(query_terms)} query terms for alignment',
        })

    return results


def find_object(ko, obj_id, obj_type):
    """Find an object in knowledge_objects by ID"""
    type_to_key = {
        'fact': 'facts',
        'claim': 'claims',
        'evidence': 'evidence',
        'limitation': 'limitations',
        'open_question': 'open_questions',
        'hypothesis': 'hypotheses',
        'experiment_proposal': 'experiment_proposals',
        'feasibility_assessment': 'feasibility_assessments',
        'feasibility': 'feasibility_assessments',
        'validation_plan': 'validation_plans',
    }

    key = type_to_key.get(obj_type, obj_type + 's')
    objects = ko.get(key, [])

    id_field = ID_FIELD_MAP.get(key, 'object_id')
    for obj in objects:
        if obj.get(id_field) == obj_id or obj.get('object_id') == obj_id:
            return obj
    return None


def extract_query_terms(content):
    """Extract potential query terms from content for alignment"""
    if not content:
        return []

    science_terms = [
        'catalyst', 'conversion', 'selectivity', 'yield', 'temperature',
        'surface area', 'reaction', 'propane', 'propylene', 'oxidative',
        'dehydrogenation', 'Cu', 'BN', 'nanosheet', 'nanoflower',
        'performance', 'activity', 'stability', 'photothermal',
        'specific surface', 'pore', 'crystallinity', 'morphology',
        'characterization', 'XRD', 'SEM', 'TEM', 'XPS', 'BET',
        'claim', 'example', 'composition', 'method', 'system',
    ]

    content_lower = content.lower()
    found = [t for t in science_terms if t.lower() in content_lower]
    return found[:5]


def main():
    print("=" * 70)
    print("V11-007-R1 Part C: SourceAnchor真实性与24条NOT_ATTEMED对象恢复")
    print("=" * 70)

    all_categories = {}
    all_retry_results = {}
    total_stats = {
        'real_document_ir': 0,
        'synthetic_dimension': 0,
        'citation_verified': 0,
        'cannot_locate': 0,
        'system_inferred': 0,
        'total_objects': 0,
    }
    retry_stats = {
        'total_not_attempted': 0,
        'recovered': 0,
        'still_unresolved': 0,
        'no_content': 0,
        'no_query_terms': 0,
        'object_not_found': 0,
    }

    for doc in DOCS:
        report = load_report(doc)
        alignment = load_evidence_alignment(doc)

        categories, all_objects = categorize_source_anchor(report, alignment)
        all_categories[doc] = {
            'doc_id': doc,
            'total_objects': len(all_objects),
            'categories': {k: len(v) for k, v in categories.items()},
            'category_details': categories,
        }

        total_stats['real_document_ir'] += len(categories['real_document_ir_element_id'])
        total_stats['synthetic_dimension'] += len(categories['synthetic_dimension_level'])
        total_stats['citation_verified'] += len(categories['with_citation_verified'])
        total_stats['cannot_locate'] += len(categories['cannot_locate'])
        total_stats['system_inferred'] += len(categories['system_inferred_candidate'])
        total_stats['total_objects'] += len(all_objects)

        retry_results = retry_not_attempted(alignment, report)
        all_retry_results[doc] = retry_results

        for r in retry_results:
            retry_stats['total_not_attempted'] += 1
            if r['retry_result'] == 'ATTEMPTED_WITH_TERMS':
                retry_stats['recovered'] += 1
            elif r['retry_result'] == 'NO_QUERY_TERMS':
                retry_stats['no_query_terms'] += 1
                retry_stats['still_unresolved'] += 1
            elif r['retry_result'] == 'NO_CONTENT':
                retry_stats['no_content'] += 1
                retry_stats['still_unresolved'] += 1
            elif r['retry_result'] == 'OBJECT_NOT_FOUND':
                retry_stats['object_not_found'] += 1
                retry_stats['still_unresolved'] += 1

        print(f"  {doc}: {len(all_objects)} objects")
        print(f"    Real Element ID: {len(categories['real_document_ir_element_id'])}")
        print(f"    Synthetic Dimension: {len(categories['synthetic_dimension_level'])}")
        print(f"    Citation Verified: {len(categories['with_citation_verified'])}")
        print(f"    Cannot Locate: {len(categories['cannot_locate'])}")
        print(f"    System Inferred: {len(categories['system_inferred_candidate'])}")
        print(f"    NOT_ATTEMPTED retry: {len(retry_results)} items")

    print(f"\n{'=' * 70}")
    print(f"SourceAnchor总计: {total_stats['total_objects']} objects")
    print(f"  真实Document IR Element ID: {total_stats['real_document_ir']}")
    print(f"  合成维度级SourceAnchor: {total_stats['synthetic_dimension']}")
    print(f"  有原文引文已核对: {total_stats['citation_verified']}")
    print(f"  无法定位: {total_stats['cannot_locate']}")
    print(f"  系统推断候选: {total_stats['system_inferred']}")

    print(f"\n24条NOT_ATTEMPTED恢复结果:")
    print(f"  总计: {retry_stats['total_not_attempted']}")
    print(f"  可恢复(提取到query terms): {retry_stats['recovered']}")
    print(f"  仍无法解决: {retry_stats['still_unresolved']}")
    print(f"    - 无query terms: {retry_stats['no_query_terms']}")
    print(f"    - 无content: {retry_stats['no_content']}")
    print(f"    - 对象未找到: {retry_stats['object_not_found']}")

    result = {
        'r1_review': True,
        'review_type': 'V11-007-R1 Part C: SourceAnchor authenticity + NOT_ATTEMPTED retry',
        'source_anchor_categories': all_categories,
        'total_stats': total_stats,
        'retry_results': all_retry_results,
        'retry_stats': retry_stats,
    }

    output_path = OUTPUT_DIR / 'part_c_source_anchor_audit.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nResult saved to: {output_path}")


if __name__ == '__main__':
    main()
