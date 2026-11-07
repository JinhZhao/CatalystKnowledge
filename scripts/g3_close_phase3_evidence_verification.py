"""
G3-CLOSE-003 Phase 3: Scientific Object and Relationship Evidence Verification

Tasks:
1. Load all scientific objects for F02, F07, PAT01
2. 4-level verification:
   - L1: Structural integrity (required fields present)
   - L2: Source anchor validity (document_id, element_type, location)
   - L3: Evidence quality (confidence, supporting data)
   - L4: Relationship endpoint consistency
3. Generate comprehensive verification report
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple


REQUIRED_FIELDS = {
    'Document': ['object_id', 'document_type'],
    'CatalystSample': ['object_id', 'document_id', 'name', 'roles'],
    'Reaction': ['object_id', 'document_id', 'reaction_type'],
    'Experiment': ['object_id', 'document_id', 'reaction_conditions', 'metrics'],
    'Observation': ['object_id', 'document_id', 'observation_type'],
    'Evidence': ['object_id', 'document_id', 'evidence_type', 'supports_object_id']
}


def load_scientific_objects(doc_id: str) -> dict:
    """Load scientific objects for a document."""
    f = Path(f'data/test_corpus/g3_output/{doc_id}/scientific_objects.json')
    if f.exists():
        with open(f, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    return {}


def verify_structure(obj: dict, obj_type: str) -> Tuple[bool, List[str]]:
    """L1: Verify structural integrity."""
    issues = []
    required = REQUIRED_FIELDS.get(obj_type, ['object_id'])
    
    for field in required:
        if field not in obj:
            issues.append(f"Missing required field: {field}")
        elif obj[field] is None or obj[field] == '':
            issues.append(f"Empty required field: {field}")
    
    return len(issues) == 0, issues


def verify_source_anchor(obj: dict) -> Tuple[bool, List[str]]:
    """L2: Verify source anchor validity."""
    issues = []
    
    if 'source_anchor' not in obj:
        return False, ["Missing source_anchor"]
    
    anchor = obj['source_anchor']
    
    if not anchor.get('document_id'):
        issues.append("source_anchor missing document_id")
    
    if not anchor.get('element_type'):
        issues.append("source_anchor missing element_type")
    
    if anchor.get('element_type') not in ['TEXT', 'TABLE', 'FIGURE', 'FORMULA', None]:
        issues.append(f"Invalid element_type: {anchor.get('element_type')}")
    
    if not anchor.get('location'):
        issues.append("source_anchor missing location")
    
    return len(issues) == 0, issues


def verify_evidence_quality(obj: dict, obj_type: str) -> Tuple[bool, List[str]]:
    """L3: Verify evidence quality."""
    issues = []
    
    # Check confidence field
    if 'confidence' not in obj:
        issues.append("Missing confidence field")
    elif obj['confidence'] not in ['candidate', 'verified', 'rejected']:
        issues.append(f"Invalid confidence value: {obj['confidence']}")
    
    # Type-specific evidence checks
    if obj_type == 'CatalystSample':
        if 'characterization_evidence' not in obj:
            issues.append("CatalystSample missing characterization_evidence")
        elif not obj['characterization_evidence']:
            issues.append("Empty characterization_evidence")
    
    elif obj_type == 'Reaction':
        if 'proposed_pathway' not in obj and 'intermediates' not in obj:
            issues.append("Reaction missing pathway or intermediates")
    
    elif obj_type == 'Experiment':
        if 'metrics' not in obj:
            issues.append("Experiment missing metrics")
        elif not obj['metrics']:
            issues.append("Empty metrics list")
    
    elif obj_type == 'Evidence':
        if 'supports_object_id' not in obj:
            issues.append("Evidence missing supports_object_id")
    
    return len(issues) == 0, issues


def collect_all_object_ids(objects: dict) -> List[str]:
    """Collect all object IDs including list-type objects."""
    ids = []
    for obj_type, obj_data in objects.items():
        obj_list = obj_data if isinstance(obj_data, list) else [obj_data]
        for obj in obj_list:
            if isinstance(obj, dict) and 'object_id' in obj:
                ids.append(obj['object_id'])
    return ids


def verify_relationships(relationships: List[dict], object_ids: List[str]) -> Tuple[int, int, List[str]]:
    """L4: Verify relationship endpoint consistency."""
    valid_count = 0
    issues = []
    
    for i, rel in enumerate(relationships):
        source_id = rel.get('source_id')
        target_id = rel.get('target_id')
        
        if not source_id:
            issues.append(f"Relationship {i}: missing source_id")
            continue
        
        if not target_id:
            issues.append(f"Relationship {i}: missing target_id")
            continue
        
        if source_id not in object_ids:
            issues.append(f"Relationship {i}: source_id '{source_id}' not found")
            continue
        
        if target_id not in object_ids:
            issues.append(f"Relationship {i}: target_id '{target_id}' not found")
            continue
        
        valid_count += 1
    
    return valid_count, len(relationships), issues


def verify_document(doc_id: str) -> Dict[str, Any]:
    """Run all 4 verification levels for a document."""
    print(f"\n{'='*60}")
    print(f"Verifying: {doc_id}")
    print(f"{'='*60}")
    
    data = load_scientific_objects(doc_id)
    if not data:
        return {'doc_id': doc_id, 'error': 'No data found'}
    
    objects = data.get('objects', {})
    relationships = data.get('relationships', [])
    
    result = {
        'doc_id': doc_id,
        'object_count': 0,
        'relationship_count': len(relationships),
        'verification': {
            'L1_structure': {'pass': 0, 'fail': 0, 'issues': []},
            'L2_source_anchor': {'pass': 0, 'fail': 0, 'issues': []},
            'L3_evidence_quality': {'pass': 0, 'fail': 0, 'issues': []},
            'L4_relationships': {'valid': 0, 'total': len(relationships), 'issues': []}
        },
        'objects': []
    }
    
    # Collect all object IDs for relationship verification
    all_object_ids = collect_all_object_ids(objects)
    
    # Verify each object
    for obj_type, obj_data in objects.items():
        obj_list = obj_data if isinstance(obj_data, list) else [obj_data]
        
        for obj in obj_list:
            if not isinstance(obj, dict):
                continue
            
            result['object_count'] += 1
            obj_id = obj.get('object_id', f'{doc_id}_{obj_type}_unknown')
            
            obj_result = {
                'object_id': obj_id,
                'object_type': obj_type,
                'L1_pass': False,
                'L2_pass': False,
                'L3_pass': False
            }
            
            # L1: Structure
            l1_pass, l1_issues = verify_structure(obj, obj_type)
            obj_result['L1_pass'] = l1_pass
            if l1_pass:
                result['verification']['L1_structure']['pass'] += 1
            else:
                result['verification']['L1_structure']['fail'] += 1
                result['verification']['L1_structure']['issues'].append(f"{obj_id}: {l1_issues}")
            
            # L2: Source anchor
            l2_pass, l2_issues = verify_source_anchor(obj)
            obj_result['L2_pass'] = l2_pass
            if l2_pass:
                result['verification']['L2_source_anchor']['pass'] += 1
            else:
                result['verification']['L2_source_anchor']['fail'] += 1
                result['verification']['L2_source_anchor']['issues'].append(f"{obj_id}: {l2_issues}")
            
            # L3: Evidence quality
            l3_pass, l3_issues = verify_evidence_quality(obj, obj_type)
            obj_result['L3_pass'] = l3_pass
            if l3_pass:
                result['verification']['L3_evidence_quality']['pass'] += 1
            else:
                result['verification']['L3_evidence_quality']['fail'] += 1
                result['verification']['L3_evidence_quality']['issues'].append(f"{obj_id}: {l3_issues}")
            
            result['objects'].append(obj_result)
    
    # L4: Relationships
    l4_valid, l4_total, l4_issues = verify_relationships(relationships, all_object_ids)
    result['verification']['L4_relationships']['valid'] = l4_valid
    result['verification']['L4_relationships']['total'] = l4_total
    result['verification']['L4_relationships']['issues'] = l4_issues
    
    # Print summary
    print(f"  Objects: {result['object_count']}")
    print(f"  L1 Structure: {result['verification']['L1_structure']['pass']}/{result['object_count']} PASS")
    print(f"  L2 Source Anchor: {result['verification']['L2_source_anchor']['pass']}/{result['object_count']} PASS")
    print(f"  L3 Evidence Quality: {result['verification']['L3_evidence_quality']['pass']}/{result['object_count']} PASS")
    print(f"  L4 Relationships: {result['verification']['L4_relationships']['valid']}/{result['verification']['L4_relationships']['total']} valid")
    
    return result


def main():
    """Run 4-level evidence verification for all documents."""
    print("="*60)
    print("G3-CLOSE-003 Phase 3: Evidence Verification")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    doc_ids = ['F02', 'F07', 'PAT01']
    results = []
    
    # Aggregate statistics
    total_objects = 0
    total_l1_pass = 0
    total_l2_pass = 0
    total_l3_pass = 0
    total_rels = 0
    total_valid_rels = 0
    
    for doc_id in doc_ids:
        result = verify_document(doc_id)
        results.append(result)
        
        total_objects += result['object_count']
        total_l1_pass += result['verification']['L1_structure']['pass']
        total_l2_pass += result['verification']['L2_source_anchor']['pass']
        total_l3_pass += result['verification']['L3_evidence_quality']['pass']
        total_rels += result['verification']['L4_relationships']['total']
        total_valid_rels += result['verification']['L4_relationships']['valid']
    
    # Overall summary
    print(f"\n{'='*60}")
    print("OVERALL VERIFICATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total objects: {total_objects}")
    print(f"  L1 Structure: {total_l1_pass}/{total_objects} PASS ({100*total_l1_pass/total_objects:.1f}%)")
    print(f"  L2 Source Anchor: {total_l2_pass}/{total_objects} PASS ({100*total_l2_pass/total_objects:.1f}%)")
    print(f"  L3 Evidence Quality: {total_l3_pass}/{total_objects} PASS ({100*total_l3_pass/total_objects:.1f}%)")
    print(f"Total relationships: {total_rels}")
    print(f"  L4 Valid endpoints: {total_valid_rels}/{total_rels} ({100*total_valid_rels/total_rels:.1f}%)")
    
    # Save results
    output_dir = Path('runs')
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / 'G3_CLOSE003_phase3_evidence_verification.json'
    
    output = {
        'task': 'G3-CLOSE-003 Phase 3: Scientific Object and Relationship Evidence Verification',
        'timestamp': datetime.now().isoformat(),
        'documents': results,
        'overall_summary': {
            'total_objects': total_objects,
            'L1_structure_pass': total_l1_pass,
            'L1_structure_rate': f"{100*total_l1_pass/total_objects:.1f}%",
            'L2_source_anchor_pass': total_l2_pass,
            'L2_source_anchor_rate': f"{100*total_l2_pass/total_objects:.1f}%",
            'L3_evidence_quality_pass': total_l3_pass,
            'L3_evidence_quality_rate': f"{100*total_l3_pass/total_objects:.1f}%",
            'total_relationships': total_rels,
            'L4_valid_relationships': total_valid_rels,
            'L4_valid_rate': f"{100*total_valid_rels/total_rels:.1f}%"
        },
        'conclusion': f"All {total_objects} objects verified at 4 levels. L1-L3: {total_l1_pass}/{total_l2_pass}/{total_l3_pass} pass. L4: {total_valid_rels}/{total_rels} relationships valid."
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved: {output_file}")
    
    return results


if __name__ == '__main__':
    main()
