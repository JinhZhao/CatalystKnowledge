#!/usr/bin/env python3
"""
Part C: UNRESOLVED对象分析与处理
分析64个UNRESOLVED状态对象的来源和处理策略
数据来源：runs/evidence_004/part_b_evidence_alignment.json
"""
import json
from pathlib import Path
from datetime import datetime

def analyze_unresolved_objects():
    """分析所有文档的UNRESOLVED对象（从evidence alignment数据）"""
    alignment_path = Path('runs/evidence_004/part_b_evidence_alignment.json')
    with open(alignment_path, 'r', encoding='utf-8') as f:
        alignment_data = json.load(f)
    
    all_analyses = {}
    total_unresolved = 0
    total_objects = 0
    
    for doc_id, doc_data in alignment_data.items():
        print(f"Analyzing UNRESOLVED objects for {doc_id}...")
        
        alignments = doc_data.get('alignments', [])
        status_dist = doc_data.get('status_distribution', {})
        
        doc_total = doc_data.get('total_objects', len(alignments))
        doc_unresolved = status_dist.get('UNRESOLVED', 0)
        
        total_objects += doc_total
        total_unresolved += doc_unresolved
        
        # 分析UNRESOLVED对象
        unresolved_by_type = {}
        unresolved_reasons = {}
        
        for align in alignments:
            if align.get('source_status') != 'UNRESOLVED':
                continue
            
            obj_type = align.get('object_type', 'unknown')
            if obj_type not in unresolved_by_type:
                unresolved_by_type[obj_type] = []
            
            # 确定原因
            reason = determine_unresolved_reason(align)
            if reason not in unresolved_reasons:
                unresolved_reasons[reason] = 0
            unresolved_reasons[reason] += 1
            
            unresolved_by_type[obj_type].append({
                'object_id': align.get('object_id'),
                'reason': reason,
                'llm_judgment': align.get('llm_judgment', ''),
                'verification_status': align.get('verification_status', '')
            })
        
        all_analyses[doc_id] = {
            'doc_id': doc_id,
            'total_objects': doc_total,
            'total_unresolved': doc_unresolved,
            'unresolved_rate': doc_unresolved / doc_total if doc_total > 0 else 0,
            'status_distribution': status_dist,
            'unresolved_by_type': {k: len(v) for k, v in unresolved_by_type.items()},
            'unresolved_details': unresolved_by_type,
            'unresolved_reasons': unresolved_reasons
        }
        
        print(f"  Total: {doc_total}, UNRESOLVED: {doc_unresolved} ({doc_unresolved/doc_total*100:.1f}%)")
    
    return {
        'total_objects': total_objects,
        'total_unresolved': total_unresolved,
        'documents': all_analyses
    }

def determine_unresolved_reason(align):
    """确定对象UNRESOLVED的原因"""
    llm_judgment = align.get('llm_judgment', '')
    verification_status = align.get('verification_status', '')
    match_details = align.get('match_details', {})
    
    # 根据llm_judgment判断原因
    if '无法提取查询术语' in llm_judgment:
        return 'NO_QUERY_TERMS'
    elif 'FAILED' in verification_status:
        matched = match_details.get('matched_terms', [])
        query = match_details.get('query_terms', [])
        if len(matched) < len(query):
            return 'PARTIAL_MATCH_FAILED'
        return 'VERIFICATION_FAILED'
    elif 'NOT_ATTEMPTED' in verification_status:
        return 'NOT_ATTEMPTED'
    elif not align.get('element_id'):
        return 'NO_ELEMENT_ID'
    else:
        return 'UNKNOWN'

def main():
    print("=" * 60)
    print("Part C: UNRESOLVED对象分析")
    print("数据来源: runs/evidence_004/part_b_evidence_alignment.json")
    print("=" * 60)
    
    result = analyze_unresolved_objects()
    
    # 保存结果
    output_path = Path('runs/final_006/part_c_unresolved_analysis.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        'analysis_timestamp': datetime.now().isoformat(),
        'data_source': 'evidence_004/part_b_evidence_alignment.json',
        'summary': {
            'total_objects': result['total_objects'],
            'total_unresolved': result['total_unresolved'],
            'unresolved_rate': result['total_unresolved'] / result['total_objects'] if result['total_objects'] > 0 else 0
        },
        'documents': result['documents']
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nPart C complete. Results saved to {output_path}")
    
    # 生成总摘要
    print(f"\n{'='*60}")
    print(f"总摘要:")
    print(f"  总对象数: {result['total_objects']}")
    print(f"  UNRESOLVED总数: {result['total_unresolved']} ({result['total_unresolved']/result['total_objects']*100:.1f}%)")
    
    # 按文档统计
    print(f"\n按文档统计:")
    for doc_id, doc_data in result['documents'].items():
        print(f"  {doc_id}: {doc_data['total_unresolved']}/{doc_data['total_objects']} ({doc_data['unresolved_rate']*100:.1f}%)")
    
    # 按原因统计
    all_reasons = {}
    for doc_data in result['documents'].values():
        for reason, count in doc_data.get('unresolved_reasons', {}).items():
            if reason not in all_reasons:
                all_reasons[reason] = 0
            all_reasons[reason] += count
    
    print(f"\n按原因统计:")
    for reason, count in sorted(all_reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  {reason}: {count} ({count/result['total_unresolved']*100:.1f}%)")
    
    # 按类型统计
    all_types = {}
    for doc_data in result['documents'].values():
        for obj_type, count in doc_data.get('unresolved_by_type', {}).items():
            if obj_type not in all_types:
                all_types[obj_type] = 0
            all_types[obj_type] += count
    
    print(f"\n按对象类型统计:")
    for obj_type, count in sorted(all_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {obj_type}: {count} ({count/result['total_unresolved']*100:.1f}%)")

if __name__ == '__main__':
    main()
