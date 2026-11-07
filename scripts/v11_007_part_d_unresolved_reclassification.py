#!/usr/bin/env python3
"""
Part D: EvidenceAligner剩余对象处理
重新分类64条UNRESOLVED对象，修复工程遗漏
"""
import json
from pathlib import Path
from datetime import datetime

def reclassify_unresolved_objects():
    """重新分类UNRESOLVED对象"""
    alignment_path = Path('runs/evidence_004/part_b_evidence_alignment.json')
    with open(alignment_path, 'r', encoding='utf-8') as f:
        alignment_data = json.load(f)
    
    reclassification = {
        'total_unresolved': 0,
        'by_doc': {},
        'by_cause': {},
        'by_type': {},
        'fixable': [],
        'keep_unresolved': [],
        'reclassified': []
    }
    
    for doc_id, doc_data in alignment_data.items():
        doc_unresolved = 0
        alignments = doc_data.get('alignments', [])
        
        for align in alignments:
            if align.get('source_status') != 'UNRESOLVED':
                continue
            
            doc_unresolved += 1
            reclassification['total_unresolved'] += 1
            
            obj_id = align.get('object_id', '')
            obj_type = align.get('object_type', 'unknown')
            llm_judgment = align.get('llm_judgment', '')
            verification_status = align.get('verification_status', '')
            match_details = align.get('match_details', {})
            
            # 统计按类型
            if obj_type not in reclassification['by_type']:
                reclassification['by_type'][obj_type] = 0
            reclassification['by_type'][obj_type] += 1
            
            # 判断原因和可修复性
            cause = determine_cause(llm_judgment, verification_status, match_details)
            
            if cause not in reclassification['by_cause']:
                reclassification['by_cause'][cause] = []
            reclassification['by_cause'][cause].append({
                'doc_id': doc_id,
                'obj_id': obj_id,
                'obj_type': obj_type,
                'llm_judgment': llm_judgment,
                'verification_status': verification_status
            })
            
            # 判断是否可修复
            if cause in ('NO_QUERY_TERMS', 'NOT_ATTEMPTED'):
                # 检查是否真的是工程遗漏
                if is_likely_engineering_omission(align, cause):
                    reclassification['fixable'].append({
                        'doc_id': doc_id,
                        'obj_id': obj_id,
                        'obj_type': obj_type,
                        'cause': cause,
                        'reason': 'Likely engineering omission - has content but alignment failed'
                    })
                else:
                    reclassification['keep_unresolved'].append({
                        'doc_id': doc_id,
                        'obj_id': obj_id,
                        'obj_type': obj_type,
                        'cause': cause,
                        'reason': 'Truly unevidenced - no extractable source text'
                    })
            else:
                reclassification['keep_unresolved'].append({
                    'doc_id': doc_id,
                    'obj_id': obj_id,
                    'obj_type': obj_type,
                    'cause': cause,
                    'reason': f'Alignment failed: {cause}'
                })
        
        reclassification['by_doc'][doc_id] = doc_unresolved
    
    return reclassification

def determine_cause(llm_judgment, verification_status, match_details):
    """确定UNRESOLVED的原因"""
    if '无法提取查询术语' in llm_judgment:
        return 'NO_QUERY_TERMS'
    elif 'NOT_ATTEMPTED' in verification_status:
        return 'NOT_ATTEMPTED'
    elif 'FAILED' in verification_status:
        matched = match_details.get('matched_terms', [])
        query = match_details.get('query_terms', [])
        if len(matched) < len(query):
            return 'PARTIAL_MATCH_FAILED'
        return 'VERIFICATION_FAILED'
    else:
        return 'UNKNOWN'

def is_likely_engineering_omission(align, cause):
    """判断是否可能是工程遗漏"""
    # 如果有match_details但失败了，可能是工程问题
    match_details = align.get('match_details', {})
    if match_details and match_details.get('query_terms'):
        # 有查询术语但匹配失败，可能是算法问题
        if cause == 'NO_QUERY_TERMS':
            # 检查是否真的有内容
            llm_judgment = align.get('llm_judgment', '')
            if '无法提取' in llm_judgment:
                # 可能是内容太抽象，不是工程遗漏
                return False
        return True
    return False

def main():
    print("=" * 70)
    print("Part D: EvidenceAligner剩余对象处理")
    print("=" * 70)
    
    reclassification = reclassify_unresolved_objects()
    
    # 保存结果
    output_path = Path('runs/v11_007/part_d_unresolved_reclassification.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result = {
        'reclassification_timestamp': datetime.now().isoformat(),
        'data_source': 'evidence_004/part_b_evidence_alignment.json',
        'reclassification': reclassification
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\nPart D分析完成。结果保存到: {output_path}")
    
    print(f"\n总摘要:")
    print(f"  UNRESOLVED总数: {reclassification['total_unresolved']}")
    
    print(f"\n按文档统计:")
    for doc_id, count in reclassification['by_doc'].items():
        print(f"  {doc_id}: {count}")
    
    print(f"\n按原因统计:")
    for cause, items in sorted(reclassification['by_cause'].items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {cause}: {len(items)} ({len(items)/reclassification['total_unresolved']*100:.1f}%)")
    
    print(f"\n按对象类型统计:")
    for obj_type, count in sorted(reclassification['by_type'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {obj_type}: {count} ({count/reclassification['total_unresolved']*100:.1f}%)")
    
    print(f"\n处理建议:")
    print(f"  可修复（工程遗漏）: {len(reclassification['fixable'])}")
    print(f"  保持UNRESOLVED（真实无证据）: {len(reclassification['keep_unresolved'])}")
    
    if reclassification['fixable']:
        print(f"\n可修复对象详情（前5个）:")
        for item in reclassification['fixable'][:5]:
            print(f"  {item['doc_id']}/{item['obj_id']} ({item['obj_type']}): {item['cause']}")

if __name__ == '__main__':
    main()
