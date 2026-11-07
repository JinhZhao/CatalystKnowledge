#!/usr/bin/env python3
"""
Document IR增强 v2：Schema-compliant Element ID和SourceAnchor生成
- Element ID: 基于文档ID+页码+块/行/span层级的稳定标识符
- SourceAnchor: 符合catalysis_schema_v1.py定义，包含document_id/element_type/element_id/page/bbox
"""

import json
import hashlib
from typing import Dict, List, Optional
from pathlib import Path


def generate_element_id(
    doc_id: str,
    page_idx: int,
    block_idx: Optional[int] = None,
    line_idx: Optional[int] = None,
    span_idx: Optional[int] = None,
) -> str:
    """
    生成稳定的Element ID
    
    Returns:
        格式化的Element ID字符串
    
    Examples:
        - 块级: "F07_p0_b3"
        - 行级: "F07_p0_b3_l2"
        - Span级: "F07_p0_b3_l2_s1"
    """
    parts = [doc_id, f"p{page_idx}"]
    if block_idx is not None:
        parts.append(f"b{block_idx}")
    if line_idx is not None:
        parts.append(f"l{line_idx}")
    if span_idx is not None:
        parts.append(f"s{span_idx}")
    return "_".join(parts)


def map_to_element_type(ir_type: str) -> str:
    """
    将Document IR类型映射到Schema ElementType枚举
    
    Args:
        ir_type: Document IR中的类型（text_block/text_line/span/image/table/equation等）
    
    Returns:
        Schema ElementType枚举值（TEXT/TABLE/FIGURE/SCHEME/EQUATION/CODE/REFERENCE）
    
    Mapping:
        - text_block/text_line/span/title/caption → TEXT
        - image → FIGURE
        - table → TABLE
        - equation → EQUATION
        - scheme → SCHEME
        - code → CODE
        - reference → REFERENCE
    """
    mapping = {
        'text_block': 'text',
        'text_line': 'text',
        'span': 'text',
        'title': 'text',
        'caption': 'text',
        'text': 'text',
        'image': 'figure',
        'figure': 'figure',
        'table': 'table',
        'equation': 'equation',
        'scheme': 'scheme',
        'code': 'code',
        'reference': 'reference',
    }
    
    return mapping.get(ir_type.lower(), 'text')  # 默认映射到TEXT


def create_source_anchor(
    document_id: str,
    element_id: str,
    element_type: str,
    page_idx: int,
    bbox: List[float],
    confidence: Optional[float] = None,
    location: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> Dict:
    """
    创建符合Schema的SourceAnchor对象
    
    Args:
        document_id: 来源文档ID
        element_id: 元素ID（由generate_element_id生成）
        element_type: 元素类型（text/image/table/title等）
        page_idx: 页码（0-based）
        bbox: 边界框 [x0, y0, x1, y1]
        confidence: 置信度（可选）
        location: 位置描述（可选，默认生成bbox字符串）
        raw_text: 原始文本片段（可选）
    
    Returns:
        SourceAnchor字典（符合catalysis_schema_v1.py）
    """
    # 如果没有提供location，使用bbox生成
    if location is None:
        if len(bbox) >= 4:
            location = f"bbox=[{bbox[0]:.0f},{bbox[1]:.0f},{bbox[2]:.0f},{bbox[3]:.0f}]"
        else:
            location = "bbox=[invalid]"
    
    anchor = {
        "document_id": document_id,
        "element_id": element_id,
        "element_type": element_type,
        "page": page_idx,
        "location": location,
        "bbox": bbox,  # 扩展字段，Schema中未定义但PDF解析需要
        "coordinate_system": "pdf_points",  # 扩展字段
    }
    
    if confidence is not None:
        anchor["confidence"] = confidence
    if raw_text is not None:
        anchor["raw_text"] = raw_text
    
    return anchor


def extract_blocks_with_ids(
    middle_json_path: Path,
    doc_id: str
) -> List[Dict]:
    """
    从middle.json提取所有块并赋予稳定Element ID和Schema-compliant SourceAnchor
    """
    with open(middle_json_path, "r", encoding="utf-8") as f:
        middle = json.load(f)
    
    blocks_with_ids = []
    
    for page_idx, page_info in enumerate(middle.get("pdf_info", [])):
        for block_idx, block in enumerate(page_info.get("preproc_blocks", [])):
            block_id = generate_element_id(doc_id, page_idx, block_idx)
            block_type = block.get("type", "text")
            
            block_data = {
                "element_id": block_id,
                "type": block_type,
                "page_idx": page_idx,
                "source_anchor": create_source_anchor(
                    document_id=doc_id,
                    element_id=block_id,
                    element_type=block_type,
                    page_idx=page_idx,
                    bbox=block.get("bbox", [0, 0, 0, 0]),
                ),
                "lines": [],
            }
            
            for line_idx, line in enumerate(block.get("lines", [])):
                line_id = generate_element_id(doc_id, page_idx, block_idx, line_idx)
                
                line_data = {
                    "element_id": line_id,
                    "source_anchor": create_source_anchor(
                        document_id=doc_id,
                        element_id=line_id,
                        element_type="line",
                        page_idx=page_idx,
                        bbox=line.get("bbox", [0, 0, 0, 0]),
                    ),
                    "spans": [],
                }
                
                for span_idx, span in enumerate(line.get("spans", [])):
                    span_id = generate_element_id(
                        doc_id, page_idx, block_idx, line_idx, span_idx
                    )
                    span_type = span.get("type", "text")
                    span_content = span.get("content", "")
                    
                    span_data = {
                        "element_id": span_id,
                        "content": span_content,
                        "type": span_type,
                        "source_anchor": create_source_anchor(
                            document_id=doc_id,
                            element_id=span_id,
                            element_type=span_type,
                            page_idx=page_idx,
                            bbox=span.get("bbox", [0, 0, 0, 0]),
                            confidence=span.get("score"),
                            raw_text=span_content,
                        ),
                    }
                    
                    line_data["spans"].append(span_data)
                
                block_data["lines"].append(line_data)
            
            blocks_with_ids.append(block_data)
    
    return blocks_with_ids


def map_content_list_to_blocks(
    content_list_path: Path,
    blocks_with_ids: List[Dict],
    doc_id: str
) -> List[Dict]:
    """
    将content_list条目映射到带ID的块结构，添加Schema-compliant element_id
    
    FIX-001: 使用全局entry_idx确保每个content_list条目有唯一的element_id
    """
    with open(content_list_path, "r", encoding="utf-8") as f:
        content_list = json.load(f)
    
    # 按页码组织块
    blocks_by_page = {}
    for block in blocks_with_ids:
        page_idx = block["page_idx"]
        if page_idx not in blocks_by_page:
            blocks_by_page[page_idx] = []
        blocks_by_page[page_idx].append(block)
    
    # 为每个content_list条目生成唯一element_id
    enhanced_content = []
    for entry_idx, entry in enumerate(content_list):
        page_idx = entry.get("page_idx", 0)
        entry_type = entry.get("type")
        
        # 使用全局entry_idx生成唯一ID
        entry_id = f"{doc_id}_p{page_idx}_e{entry_idx}"
        
        # 尝试匹配对应的块类型（仅用于element_type）
        matched_block_type = None
        page_blocks = blocks_by_page.get(page_idx, [])
        
        # 按类型匹配
        type_map = {"text": "text", "image": "image", "table": "table"}
        target_type = type_map.get(entry_type)
        
        for block in page_blocks:
            if block["type"] == target_type:
                matched_block_type = block["type"]
                break
        
        enhanced_entry = entry.copy()
        enhanced_entry["element_id"] = entry_id
        enhanced_entry["element_type"] = matched_block_type or entry_type or "unknown"
        
        enhanced_content.append(enhanced_entry)
    
    return enhanced_content


if __name__ == "__main__":
    import sys
    
    doc_id = "F07_test"
    output_base = Path(r"D:\Knowledge_World\data\test_corpus\mineru_output\F07_test\main\auto")
    
    middle_path = output_base / "main_middle.json"
    content_list_path = output_base / "main_content_list.json"
    
    print(f"Processing {doc_id} with Schema-compliant SourceAnchor...")
    
    # 提取带ID的块
    blocks = extract_blocks_with_ids(middle_path, doc_id)
    print(f"Extracted {len(blocks)} blocks with Element IDs")
    
    # 保存带ID的块结构
    blocks_output = output_base / "blocks_with_ids.json"
    with open(blocks_output, "w", encoding="utf-8") as f:
        json.dump(blocks, f, ensure_ascii=False, indent=2)
    print(f"Saved: {blocks_output}")
    
    # 映射content_list
    enhanced_content = map_content_list_to_blocks(content_list_path, blocks, doc_id)
    print(f"Enhanced {len(enhanced_content)} content_list entries")
    
    # 保存增强后的content_list
    content_output = output_base / "content_list_enhanced.json"
    with open(content_output, "w", encoding="utf-8") as f:
        json.dump(enhanced_content, f, ensure_ascii=False, indent=2)
    print(f"Saved: {content_output}")
    
    # 验证Schema合规性
    print(f"\n=== Schema Compliance Check ===")
    sample_block = blocks[0]
    anchor = sample_block['source_anchor']
    required_fields = ['document_id', 'element_id', 'element_type', 'page', 'location']
    missing = [f for f in required_fields if f not in anchor]
    if missing:
        print(f"[FAIL] Missing required fields: {missing}")
    else:
        print(f"[PASS] All required fields present")
        print(f"  document_id: {anchor['document_id']}")
        print(f"  element_id: {anchor['element_id']}")
        print(f"  element_type: {anchor['element_type']}")
        print(f"  page: {anchor['page']}")
        print(f"  location: {anchor['location']}")
        print(f"  bbox: {anchor.get('bbox')}")
    
    # 统计
    print(f"\n=== Statistics ===")
    print(f"Total blocks: {len(blocks)}")
    print(f"Total lines: {sum(len(b['lines']) for b in blocks)}")
    print(f"Total spans: {sum(len(l['spans']) for b in blocks for l in b['lines'])}")
    print(f"Content entries with element_id: {sum(1 for e in enhanced_content if 'element_id' in e)}")
