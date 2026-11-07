#!/usr/bin/env python3
"""
Part A: Claim-Evidence对象引用一致性修复
对账所有关系，定位MISSING_OBJECT根因，修复ID引用
"""
import json
from pathlib import Path
from datetime import datetime

def audit_document_relationships(doc_id):
    """审计单个文档的所有关系"""
    report_path = Path(f'runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json')
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # 提取所有知识对象（建立ID索引）
    knowledge_objects = report.get('knowledge_objects', {})
    
    # 建立对象ID到对象的映射
    object_index = {}
    
    # 索引所有类型的对象
    for obj_type in ['facts', 'claims', 'evidence', 'hypotheses', 'experiment_proposals',
                     'limitations', 'open_questions', 'validation_plans', 'feasibility_assessments']:
        objects = knowledge_objects.get(obj_type, [])
        for obj in objects:
            # 获取对象ID（不同字段名）
            obj_id = (obj.get(f'{obj_type[:-1]}_id') or 
                     obj.get('object_id') or 
                     obj.get('claim_id') or 
                     obj.get('evidence_id') or
                     obj.get('fact_id') or
                     obj.get('hypothesis_id') or
                     obj.get('proposal_id') or
                     obj.get('limitation_id') or
                     obj.get('question_id') or
                     obj.get('plan_id') or
                     obj.get('feasibility_id'))
            if obj_id:
                object_index[obj_id] = {
                    'type': obj_type,
                    'object': obj
                }
    
    # 提取关系
    relationships = report.get('knowledge_relationships', [])
    
    # 审计每条关系
    audit_results = {
        'total': len(relationships),
        'VALID_STRUCTURE': [],
        'MISSING_SOURCE': [],
        'MISSING_TARGET': [],
        'TYPE_MISMATCH': [],
        'DANGLING': []
    }
    
    for rel in relationships:
        rel_id = rel.get('relationship_id', '')
        rel_type = rel.get('relationship_type', '')
        source_id = rel.get('source_id', '')
        target_id = rel.get('target_id', '')
        
        # 检查source对象是否存在
        source_exists = source_id in object_index
        # 检查target对象是否存在
        target_exists = target_id in object_index
        
        if not source_exists and not target_exists:
            audit_results['DANGLING'].append({
                'rel_id': rel_id,
                'rel_type': rel_type,
                'source_id': source_id,
                'target_id': target_id,
                'reason': 'Both source and target objects missing'
            })
        elif not source_exists:
            audit_results['MISSING_SOURCE'].append({
                'rel_id': rel_id,
                'rel_type': rel_type,
                'source_id': source_id,
                'target_id': target_id,
                'target_type': object_index[target_id]['type'] if target_exists else 'UNKNOWN',
                'reason': f'Source object {source_id} not found'
            })
        elif not target_exists:
            audit_results['MISSING_TARGET'].append({
                'rel_id': rel_id,
                'rel_type': rel_type,
                'source_id': source_id,
                'source_type': object_index[source_id]['type'] if source_exists else 'UNKNOWN',
                'target_id': target_id,
                'reason': f'Target object {target_id} not found'
            })
        else:
            # 两个对象都存在，检查类型约束
            source_type = object_index[source_id]['type']
            target_type = object_index[target_id]['type']
            
            type_valid = check_relationship_type_constraint(rel_type, source_type, target_type)
            
            if type_valid:
                audit_results['VALID_STRUCTURE'].append({
                    'rel_id': rel_id,
                    'rel_type': rel_type,
                    'source_id': source_id,
                    'source_type': source_type,
                    'target_id': target_id,
                    'target_type': target_type
                })
            else:
                audit_results['TYPE_MISMATCH'].append({
                    'rel_id': rel_id,
                    'rel_type': rel_type,
                    'source_id': source_id,
                    'source_type': source_type,
                    'target_id': target_id,
                    'target_type': target_type,
                    'reason': f'Type constraint violated: {rel_type} requires specific source/target types'
                })
    
    return {
        'doc_id': doc_id,
        'object_count': len(object_index),
        'relationship_count': len(relationships),
        'audit': audit_results
    }

def check_relationship_type_constraint(rel_type, source_type, target_type):
    """检查关系类型约束"""
    # SUPPORTED_BY/CHALLENGED_BY: claim → evidence
    if rel_type in ('SUPPORTED_BY', 'CHALLENGED_BY'):
        return source_type == 'claims' and target_type == 'evidence'
    
    # QUALIFIED_BY: claim → limitation
    elif rel_type == 'QUALIFIED_BY':
        return source_type == 'claims' and target_type == 'limitations'
    
    # TESTED_BY: claim → experiment_proposal
    elif rel_type == 'TESTED_BY':
        return source_type == 'claims' and target_type == 'experiment_proposals'
    
    # VALIDATES: claim → validation_plan OR hypothesis → feasibility
    elif rel_type == 'VALIDATES':
        return ((source_type == 'claims' and target_type == 'validation_plans') or
                (source_type == 'hypotheses' and target_type == 'feasibility_assessments'))
    
    # REQUIRES: claim → open_question
    elif rel_type == 'REQUIRES':
        return source_type == 'claims' and target_type == 'open_questions'
    
    # RELATES_TO: fact → fact/evidence/claim
    elif rel_type == 'RELATES_TO':
        return source_type == 'facts' and target_type in ('facts', 'evidence', 'claims')
    
    # 默认允许
    else:
        return True

def main():
    docs = ['F02', 'F07', 'P01', 'PAT01']
    all_audits = {}
    
    print("=" * 70)
    print("Part A: Claim-Evidence对象引用一致性审计")
    print("=" * 70)
    
    for doc in docs:
        print(f"\nAuditing {doc}...")
        audit = audit_document_relationships(doc)
        all_audits[doc] = audit
        
        print(f"  Objects: {audit['object_count']}")
        print(f"  Relationships: {audit['relationship_count']}")
        print(f"  VALID_STRUCTURE: {len(audit['audit']['VALID_STRUCTURE'])}")
        print(f"  MISSING_SOURCE: {len(audit['audit']['MISSING_SOURCE'])}")
        print(f"  MISSING_TARGET: {len(audit['audit']['MISSING_TARGET'])}")
        print(f"  TYPE_MISMATCH: {len(audit['audit']['TYPE_MISMATCH'])}")
        print(f"  DANGLING: {len(audit['audit']['DANGLING'])}")
    
    # 保存结果
    output_path = Path('runs/v11_007/part_a_relationship_audit.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result = {
        'audit_timestamp': datetime.now().isoformat(),
        'documents': all_audits,
        'summary': {
            'total_objects': sum(a['object_count'] for a in all_audits.values()),
            'total_relationships': sum(a['relationship_count'] for a in all_audits.values()),
            'total_valid': sum(len(a['audit']['VALID_STRUCTURE']) for a in all_audits.values()),
            'total_missing_source': sum(len(a['audit']['MISSING_SOURCE']) for a in all_audits.values()),
            'total_missing_target': sum(len(a['audit']['MISSING_TARGET']) for a in all_audits.values()),
            'total_type_mismatch': sum(len(a['audit']['TYPE_MISMATCH']) for a in all_audits.values()),
            'total_dangling': sum(len(a['audit']['DANGLING']) for a in all_audits.values())
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*70}")
    print(f"Part A审计完成。结果保存到: {output_path}")
    print(f"\n总摘要:")
    print(f"  总对象数: {result['summary']['total_objects']}")
    print(f"  总关系数: {result['summary']['total_relationships']}")
    print(f"  VALID_STRUCTURE: {result['summary']['total_valid']}")
    print(f"  MISSING_SOURCE: {result['summary']['total_missing_source']}")
    print(f"  MISSING_TARGET: {result['summary']['total_missing_target']}")
    print(f"  TYPE_MISMATCH: {result['summary']['total_type_mismatch']}")
    print(f"  DANGLING: {result['summary']['total_dangling']}")

if __name__ == '__main__':
    main()
