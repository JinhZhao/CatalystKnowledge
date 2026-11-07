#!/usr/bin/env python3
"""
Part C: 九类知识对象覆盖与状态统计
统计F02/F07/P01/PAT01的9类知识对象，区分来源和状态
"""
import json
from pathlib import Path
from datetime import datetime

OBJECT_TYPES = [
    ('facts', 'Fact'),
    ('claims', 'Claim'),
    ('evidence', 'Evidence'),
    ('limitations', 'Limitation'),
    ('open_questions', 'OpenQuestion'),
    ('hypotheses', 'Hypothesis'),
    ('experiment_proposals', 'ExperimentProposal'),
    ('feasibility_assessments', 'Feasibility'),
    ('validation_plans', 'ValidationPlan')
]

def audit_object_type(doc_id, obj_type, objects):
    """审计单个对象类型的状态"""
    if not objects:
        return {
            'count': 0,
            'status': 'NOT_EXTRACTED',
            'author_stated': 0,
            'system_inferred': 0,
            'with_source_anchor': 0,
            'unresolved': 0
        }
    
    author_stated = 0
    system_inferred = 0
    with_source_anchor = 0
    unresolved = 0
    
    for obj in objects:
        # 检查来源
        source = obj.get('source', '')
        provenance = obj.get('provenance_label', '')
        
        if source == 'AUTHOR_STATED':
            author_stated += 1
        elif provenance in ('SYSTEM_INFERRED', 'DERIVED'):
            system_inferred += 1
        
        # 检查SourceAnchor
        if obj.get('source_anchor'):
            with_source_anchor += 1
        
        # 检查UNRESOLVED状态
        source_status = obj.get('source_status', '')
        if source_status == 'UNRESOLVED':
            unresolved += 1
    
    return {
        'count': len(objects),
        'status': 'EXTRACTED' if len(objects) > 0 else 'NOT_EXTRACTED',
        'author_stated': author_stated,
        'system_inferred': system_inferred,
        'with_source_anchor': with_source_anchor,
        'unresolved': unresolved
    }

def audit_document_objects(doc_id):
    """审计单个文档的所有对象类型"""
    report_path = Path(f'runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json')
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    knowledge_objects = report.get('knowledge_objects', {})
    
    audit_results = {}
    for obj_type, display_name in OBJECT_TYPES:
        objects = knowledge_objects.get(obj_type, [])
        audit_results[obj_type] = audit_object_type(doc_id, obj_type, objects)
        audit_results[obj_type]['display_name'] = display_name
    
    return {
        'doc_id': doc_id,
        'object_types': audit_results
    }

def main():
    docs = ['F02', 'F07', 'P01', 'PAT01']
    all_audits = {}
    
    print("=" * 70)
    print("Part C: 九类知识对象覆盖与状态统计")
    print("=" * 70)
    
    for doc in docs:
        print(f"\n审计 {doc}...")
        audit = audit_document_objects(doc)
        all_audits[doc] = audit
        
        for obj_type, display_name in OBJECT_TYPES:
            stats = audit['object_types'][obj_type]
            print(f"  {display_name}: {stats['count']}个 "
                  f"(作者:{stats['author_stated']}/系统:{stats['system_inferred']}/"
                  f"锚点:{stats['with_source_anchor']}/未解决:{stats['unresolved']})")
    
    # 保存结果
    output_path = Path('runs/v11_007/part_c_object_coverage_audit.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result = {
        'audit_timestamp': datetime.now().isoformat(),
        'documents': all_audits,
        'summary': {}
    }
    
    # 生成跨文档汇总
    for obj_type, display_name in OBJECT_TYPES:
        total_count = sum(a['object_types'][obj_type]['count'] for a in all_audits.values())
        total_author = sum(a['object_types'][obj_type]['author_stated'] for a in all_audits.values())
        total_system = sum(a['object_types'][obj_type]['system_inferred'] for a in all_audits.values())
        total_anchor = sum(a['object_types'][obj_type]['with_source_anchor'] for a in all_audits.values())
        total_unresolved = sum(a['object_types'][obj_type]['unresolved'] for a in all_audits.values())
        docs_with_type = sum(1 for a in all_audits.values() if a['object_types'][obj_type]['count'] > 0)
        
        result['summary'][obj_type] = {
            'display_name': display_name,
            'total_count': total_count,
            'total_author_stated': total_author,
            'total_system_inferred': total_system,
            'total_with_source_anchor': total_anchor,
            'total_unresolved': total_unresolved,
            'docs_with_type': docs_with_type,
            'coverage_rate': docs_with_type / len(docs)
        }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*70}")
    print(f"Part C审计完成。结果保存到: {output_path}")
    print(f"\n跨文档汇总:")
    
    for obj_type, display_name in OBJECT_TYPES:
        stats = result['summary'][obj_type]
        print(f"\n  {display_name}:")
        print(f"    总数: {stats['total_count']}")
        print(f"    作者陈述: {stats['total_author_stated']}")
        print(f"    系统推断: {stats['total_system_inferred']}")
        print(f"    有SourceAnchor: {stats['total_with_source_anchor']}")
        print(f"    UNRESOLVED: {stats['total_unresolved']}")
        print(f"    覆盖文档: {stats['docs_with_type']}/4 ({stats['coverage_rate']*100:.0f}%)")

if __name__ == '__main__':
    main()
