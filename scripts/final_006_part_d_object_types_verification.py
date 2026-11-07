#!/usr/bin/env python3
"""
Part D: 9类知识对象完整显示验证
验证每份报告是否包含所有9类知识对象
"""
import json
from pathlib import Path
from datetime import datetime

REQUIRED_OBJECT_TYPES = [
    'facts',
    'claims', 
    'evidence',
    'hypotheses',
    'experiment_proposals',
    'limitations',
    'open_questions',
    'validation_plans',
    'feasibility_assessments'
]

TYPE_DISPLAY_NAMES = {
    'facts': 'Fact（事实）',
    'claims': 'Claim（声明）',
    'evidence': 'Evidence（证据）',
    'hypotheses': 'Hypothesis（假设）',
    'experiment_proposals': 'ExperimentProposal（实验提案）',
    'limitations': 'Limitation（限制）',
    'open_questions': 'OpenQuestion（开放问题）',
    'validation_plans': 'ValidationPlan（验证计划）',
    'feasibility_assessments': 'FeasibilityAssessment（可行性评估）'
}

def verify_object_types(doc_id):
    """验证单个文档的9类知识对象"""
    report_path = Path(f'runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json')
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    knowledge_objects = report.get('knowledge_objects', {})
    
    verification_result = {
        'doc_id': doc_id,
        'total_types_required': len(REQUIRED_OBJECT_TYPES),
        'types_present': 0,
        'types_missing': 0,
        'type_details': {}
    }
    
    for obj_type in REQUIRED_OBJECT_TYPES:
        objects = knowledge_objects.get(obj_type, [])
        count = len(objects) if isinstance(objects, list) else (1 if objects else 0)
        
        is_present = count > 0
        if is_present:
            verification_result['types_present'] += 1
        else:
            verification_result['types_missing'] += 1
        
        verification_result['type_details'][obj_type] = {
            'display_name': TYPE_DISPLAY_NAMES.get(obj_type, obj_type),
            'count': count,
            'present': is_present,
            'sample_ids': get_sample_ids(objects, obj_type) if count > 0 else []
        }
    
    verification_result['completeness_rate'] = (
        verification_result['types_present'] / verification_result['total_types_required']
    )
    
    return verification_result

def get_sample_ids(objects, obj_type):
    """获取对象的样本ID"""
    if not objects:
        return []
    
    # 如果是列表，取前3个
    if isinstance(objects, list):
        sample_objects = objects[:3]
    else:
        sample_objects = [objects]
    
    # 提取ID字段
    id_field_map = {
        'facts': 'fact_id',
        'claims': 'claim_id',
        'evidence': 'evidence_id',
        'hypotheses': 'hypothesis_id',
        'experiment_proposals': 'proposal_id',
        'limitations': 'limitation_id',
        'open_questions': 'question_id',
        'validation_plans': 'plan_id',
        'feasibility_assessments': 'feasibility_id'
    }
    
    id_field = id_field_map.get(obj_type, 'object_id')
    
    sample_ids = []
    for obj in sample_objects:
        obj_id = obj.get(id_field) or obj.get('object_id', 'NO_ID')
        sample_ids.append(obj_id)
    
    return sample_ids

def main():
    docs = ['F02', 'F07', 'P01', 'PAT01']
    all_verifications = {}
    
    print("=" * 70)
    print("Part D: 9类知识对象完整显示验证")
    print("=" * 70)
    
    for doc in docs:
        print(f"\nVerifying {doc}...")
        verification = verify_object_types(doc)
        all_verifications[doc] = verification
        
        print(f"  Types present: {verification['types_present']}/{verification['total_types_required']} "
              f"({verification['completeness_rate']*100:.1f}%)")
        
        # 显示缺失的类型
        missing_types = [
            TYPE_DISPLAY_NAMES.get(t, t) 
            for t, details in verification['type_details'].items() 
            if not details['present']
        ]
        if missing_types:
            print(f"  Missing types: {', '.join(missing_types)}")
    
    # 保存结果
    output_path = Path('runs/final_006/part_d_object_types_verification.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result = {
        'verification_timestamp': datetime.now().isoformat(),
        'required_types': REQUIRED_OBJECT_TYPES,
        'documents': all_verifications
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*70}")
    print(f"Part D complete. Results saved to {output_path}")
    
    # 生成总摘要
    print(f"\n{'='*70}")
    print("总摘要:")
    
    total_present = sum(v['types_present'] for v in all_verifications.values())
    total_required = sum(v['total_types_required'] for v in all_verifications.values())
    
    print(f"  总类型数（4文档×9类型）: {total_required}")
    print(f"  存在类型数: {total_present} ({total_present/total_required*100:.1f}%)")
    print(f"  缺失类型数: {total_required - total_present} ({(total_required-total_present)/total_required*100:.1f}%)")
    
    # 按类型统计跨文档出现情况
    type_appearance = {}
    for obj_type in REQUIRED_OBJECT_TYPES:
        type_appearance[obj_type] = {
            'display_name': TYPE_DISPLAY_NAMES.get(obj_type, obj_type),
            'docs_present': [],
            'docs_missing': [],
            'total_count': 0
        }
    
    for doc_id, verification in all_verifications.items():
        for obj_type, details in verification['type_details'].items():
            if details['present']:
                type_appearance[obj_type]['docs_present'].append(doc_id)
                type_appearance[obj_type]['total_count'] += details['count']
            else:
                type_appearance[obj_type]['docs_missing'].append(doc_id)
    
    print(f"\n按类型统计（跨文档）:")
    for obj_type in REQUIRED_OBJECT_TYPES:
        info = type_appearance[obj_type]
        present_count = len(info['docs_present'])
        print(f"  {info['display_name']}:")
        print(f"    出现文档: {present_count}/4 ({', '.join(info['docs_present']) if info['docs_present'] else 'None'})")
        print(f"    总对象数: {info['total_count']}")
        if info['docs_missing']:
            print(f"    缺失文档: {', '.join(info['docs_missing'])}")

if __name__ == '__main__':
    main()
