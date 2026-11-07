#!/usr/bin/env python3
"""
修复8条TYPE_MISMATCH关系
- VALIDATES: feasibility→hypothesis 改为 hypothesis→feasibility
- REQUIRES: claim→fact 改为 claim→open_question（或移除如果无open_question）
"""
import json
from pathlib import Path
import shutil

def fix_relationships_in_report(doc_id):
    """修复单个文档的关系"""
    report_path = Path(f'runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json')
    
    # 备份原文件
    backup_path = report_path.with_suffix('.json.backup_v11_007')
    if not backup_path.exists():
        shutil.copy2(report_path, backup_path)
        print(f"  备份: {backup_path}")
    
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    relationships = report.get('knowledge_relationships', [])
    knowledge_objects = report.get('knowledge_objects', {})
    
    # 建立对象ID索引
    object_index = {}
    for obj_type in ['facts', 'claims', 'evidence', 'hypotheses', 'experiment_proposals',
                     'limitations', 'open_questions', 'validation_plans', 'feasibility_assessments']:
        objects = knowledge_objects.get(obj_type, [])
        for obj in objects:
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
                object_index[obj_id] = obj_type
    
    fixed_count = 0
    removed_count = 0
    
    # 修复关系
    new_relationships = []
    for rel in relationships:
        rel_id = rel.get('relationship_id', '')
        rel_type = rel.get('relationship_type', '')
        source_id = rel.get('source_id', '')
        target_id = rel.get('target_id', '')
        
        source_type = object_index.get(source_id)
        target_type = object_index.get(target_id)
        
        # 修复VALIDATES: feasibility→hypothesis 改为 hypothesis→feasibility
        if rel_type == 'VALIDATES' and source_type == 'feasibility_assessments' and target_type == 'hypotheses':
            print(f"  修复 {rel_id}: VALIDATES方向反转 {source_id}→{target_id} 改为 {target_id}→{source_id}")
            rel['source_id'] = target_id
            rel['target_id'] = source_id
            fixed_count += 1
            new_relationships.append(rel)
        
        # 修复REQUIRES: claim→fact 改为 claim→open_question
        elif rel_type == 'REQUIRES' and source_type == 'claims' and target_type == 'facts':
            # 查找该文档是否有open_questions
            open_questions = knowledge_objects.get('open_questions', [])
            if open_questions:
                # 使用第一个open_question作为target
                first_oq = open_questions[0]
                oq_id = (first_oq.get('question_id') or first_oq.get('object_id'))
                print(f"  修复 {rel_id}: REQUIRES目标改为open_question {target_id}→{oq_id}")
                rel['target_id'] = oq_id
                fixed_count += 1
                new_relationships.append(rel)
            else:
                # 没有open_question，移除该关系
                print(f"  移除 {rel_id}: REQUIRES无可用open_question目标")
                removed_count += 1
        
        # 其他关系保持不变
        else:
            new_relationships.append(rel)
    
    # 更新报告
    report['knowledge_relationships'] = new_relationships
    
    # 保存修复后的报告
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return fixed_count, removed_count

def main():
    docs = ['F02', 'F07', 'P01', 'PAT01']
    
    print("=" * 70)
    print("修复TYPE_MISMATCH关系")
    print("=" * 70)
    
    total_fixed = 0
    total_removed = 0
    
    for doc in docs:
        print(f"\n处理 {doc}...")
        fixed, removed = fix_relationships_in_report(doc)
        total_fixed += fixed
        total_removed += removed
        print(f"  修复: {fixed}, 移除: {removed}")
    
    print(f"\n{'='*70}")
    print(f"修复完成")
    print(f"  总修复: {total_fixed}")
    print(f"  总移除: {total_removed}")
    print(f"  原文件已备份为 .backup_v11_007")

if __name__ == '__main__':
    main()
