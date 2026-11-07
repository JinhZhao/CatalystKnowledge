#!/usr/bin/env python3
"""
FIG-001 F4: 最小图文关联实现
- 提取正文中的Figure引用
- 与图片元素匹配
- 生成关联记录（SourceAnchor + 置信度 + 状态）
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass


@dataclass
class FigureTextAssociation:
    """图文关联记录"""
    source_element_id: str  # 正文引用位置的Element ID
    target_element_id: str  # 图片元素的Element ID
    figure_id: str  # Figure编号（如"Figure 1", "Fig. S1"）
    association_type: str  # explicit_reference / caption_match / proximity
    confidence: float  # 0.0-1.0
    status: str  # CONFIRMED / CANDIDATE / UNRESOLVED / AMBIGUOUS
    evidence: str  # 匹配证据
    source_anchor: Dict  # SourceAnchor对象


def extract_figure_references(text: str) -> List[Tuple[str, int, int]]:
    """
    提取正文中的Figure引用
    
    Returns:
        List of (figure_id, start_pos, end_pos)
    """
    # 匹配模式：Figure 1, Fig. 1, Figure S1, FIGURE 1, etc.
    patterns = [
        r'Figure\s+(\d+[a-z]?)',  # Figure 1, Figure 1a
        r'Fig\.?\s+(\d+[a-z]?)',  # Fig. 1, Fig 1
        r'FIGURE\s+(\d+[a-z]?)',  # FIGURE 1
        r'Figure\s+S(\d+)',  # Figure S1 (SI)
        r'Fig\.?\s+S(\d+)',  # Fig. S1
    ]
    
    references = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            fig_id = match.group(0)
            start = match.start()
            end = match.end()
            references.append((fig_id, start, end))
    
    # 去重并按位置排序
    references = list(set(references))
    references.sort(key=lambda x: x[1])
    
    return references


def extract_figure_elements(content_list: List[Dict]) -> List[Dict]:
    """
    从content_list中提取图片元素
    
    Returns:
        List of figure elements with id, caption, page_idx
    """
    figures = []
    for idx, item in enumerate(content_list):
        if item.get('type') == 'image':
            # 生成Element ID
            page_idx = item.get('page_idx', 0)
            element_id = f"p{page_idx}_img{idx}"
            
            # 提取caption
            captions = item.get('img_caption', [])
            caption_text = ' '.join(captions) if captions else ''
            
            figures.append({
                'element_id': element_id,
                'page_idx': page_idx,
                'caption': caption_text,
                'img_path': item.get('img_path', ''),
                'bbox': item.get('bbox', []),
            })
    
    return figures


def match_figure_to_references(
    text_content: str,
    figures: List[Dict],
    doc_id: str
) -> List[FigureTextAssociation]:
    """
    将图片与正文引用匹配
    
    Args:
        text_content: 正文文本
        figures: 图片元素列表
        doc_id: 文档ID
    
    Returns:
        关联记录列表
    """
    associations = []
    
    # 提取正文中的Figure引用
    references = extract_figure_references(text_content)
    
    # 为每个图片查找匹配
    for fig in figures:
        caption = fig['caption'].upper()
        
        # 尝试从caption中提取Figure编号
        fig_number = None
        for pattern in [r'FIGURE\s+(\d+)', r'FIG\.?\s+(\d+)', r'TABLE\s+(\d+)']:
            match = re.search(pattern, caption)
            if match:
                fig_number = match.group(1)
                break
        
        # 在正文引用中查找匹配
        matched_ref = None
        for ref_text, start, end in references:
            if fig_number and fig_number in ref_text:
                matched_ref = (ref_text, start, end)
                break
        
        if matched_ref:
            # 显式引用匹配
            ref_text, start, end = matched_ref
            source_element_id = f"{doc_id}_p{fig['page_idx']}_text_ref_{start}"
            
            association = FigureTextAssociation(
                source_element_id=source_element_id,
                target_element_id=fig['element_id'],
                figure_id=ref_text,
                association_type='explicit_reference',
                confidence=0.9,
                status='CONFIRMED',
                evidence=f"正文引用'{ref_text}'与图片caption'{fig['caption'][:50]}'匹配",
                source_anchor={
                    'document_id': doc_id,
                    'element_type': 'text',
                    'element_id': source_element_id,
                    'page': fig['page_idx'],
                    'location': f'char_offset={start}-{end}',
                    'confidence': 0.9,
                }
            )
            associations.append(association)
        else:
            # 未匹配的图片
            association = FigureTextAssociation(
                source_element_id='',
                target_element_id=fig['element_id'],
                figure_id=fig['caption'][:30] if fig['caption'] else 'Unknown',
                association_type='unmatched',
                confidence=0.0,
                status='UNRESOLVED',
                evidence='未在正文中找到对应引用',
                source_anchor={
                    'document_id': doc_id,
                    'element_type': 'figure',
                    'element_id': fig['element_id'],
                    'page': fig['page_idx'],
                    'confidence': 0.0,
                }
            )
            associations.append(association)
    
    return associations


def process_document_for_figure_associations(
    doc_id: str,
    output_dir: Path
) -> List[FigureTextAssociation]:
    """
    处理单个文档的图文关联
    
    Args:
        doc_id: 文档ID
        output_dir: MinerU输出目录
    
    Returns:
        关联记录列表
    """
    # 查找main_content_list.json
    content_list_path = None
    for json_file in output_dir.rglob('main_content_list.json'):
        content_list_path = json_file
        break
    
    if not content_list_path:
        # 尝试其他可能的文件名
        for json_file in output_dir.rglob('*content_list.json'):
            content_list_path = json_file
            break
    
    if not content_list_path:
        print(f"[WARN] {doc_id}: content_list.json not found")
        return []
    
    # 加载content_list
    with open(content_list_path, 'r', encoding='utf-8') as f:
        content_list = json.load(f)
    
    # 提取图片元素
    figures = extract_figure_elements(content_list)
    
    # 提取正文文本
    text_parts = []
    for item in content_list:
        if item.get('type') == 'text':
            text_parts.append(item.get('text', ''))
    text_content = '\n'.join(text_parts)
    
    # 匹配图文关联
    associations = match_figure_to_references(text_content, figures, doc_id)
    
    return associations


def main():
    """主函数：处理F07/P01/PAT01的图文关联"""
    output_base = Path('D:/Knowledge_World/data/test_corpus/mineru_output')
    
    test_docs = [
        ('F07', output_base / 'F07_batch'),
        ('P01', output_base / 'P01_41467_2024_50691_MOESM1_ESM_batch'),
        ('PAT01', output_base / 'PAT01_table_test'),
    ]
    
    all_results = {}
    
    for doc_id, output_dir in test_docs:
        print(f"\n=== Processing {doc_id} ===")
        
        if not output_dir.exists():
            print(f"[SKIP] {doc_id}: output directory not found")
            continue
        
        associations = process_document_for_figure_associations(doc_id, output_dir)
        
        # 统计
        confirmed = sum(1 for a in associations if a.status == 'CONFIRMED')
        unresolved = sum(1 for a in associations if a.status == 'UNRESOLVED')
        
        print(f"  Total figures: {len(associations)}")
        print(f"  Confirmed: {confirmed}")
        print(f"  Unresolved: {unresolved}")
        
        # 保存结果
        result_file = output_base / f'{doc_id}_figure_associations.json'
        result_data = [
            {
                'source_element_id': a.source_element_id,
                'target_element_id': a.target_element_id,
                'figure_id': a.figure_id,
                'association_type': a.association_type,
                'confidence': a.confidence,
                'status': a.status,
                'evidence': a.evidence,
                'source_anchor': a.source_anchor,
            }
            for a in associations
        ]
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        
        print(f"  Results saved to: {result_file}")
        
        all_results[doc_id] = {
            'total': len(associations),
            'confirmed': confirmed,
            'unresolved': unresolved,
            'result_file': str(result_file),
        }
    
    # 保存汇总
    summary_file = output_base / 'figure_associations_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n=== Summary ===")
    print(f"Total documents: {len(all_results)}")
    total_figures = sum(r['total'] for r in all_results.values())
    total_confirmed = sum(r['confirmed'] for r in all_results.values())
    print(f"Total figures: {total_figures}")
    print(f"Total confirmed: {total_confirmed}")
    print(f"Summary saved to: {summary_file}")


if __name__ == '__main__':
    main()
