#!/usr/bin/env python3
"""
Document IR增强：稳定Element ID和SourceAnchor生成
- Element ID: 基于文档ID+页码+块/行/span层级的稳定标识符
- SourceAnchor: 保留原始PDF坐标和置信度信息
"""

import json
import hashlib
from typing import Dict, List, Optional, Tuple
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
    
    Args:
        doc_id: 文档标识符（如 F07_test）
        page_idx: 页码（0-based）
        block_idx: 块索引（0-based，可选）
        line_idx: 行索引（0-based，可选）
        span_idx: span索引（0-based，可选）
    
    Returns:
        格式化的Element ID字符串
    
    Examples:
        - 页面级: "F07_p0"
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


def create_source_anchor(
    page_idx: int,
    bbox: List[float],
    score: Optional[float] = None,
    coordinate_system: str = "pdf_points"
) -> Dict:
    """
    创建SourceAnchor对象，保留原始PDF坐标信息
    
    Args:
        page_idx: 页码（0-based）
        bbox: 边界框 [x0, y0, x1, y1]
        score: 置信度分数（可选）
        coordinate_system: 坐标系（默认pdf_points，即72 DPI）
    
    Returns:
        SourceAnchor字典
    """
    anchor = {
        "page_idx": page_idx,
        "bbox": bbox,
        "coordinate_system": coordinate_system,
    }
    if score is not None:
        anchor["confidence"] = score
    return anchor


def extract_blocks_with_ids(
    middle_json_path: Path,
    doc_id: str
) -> List[Dict]:
    """
    从middle.json提取所有块并赋予稳定Element ID
    
    Args:
        middle_json_path: middle.json文件路径
        doc_id: 文档标识符
    
    Returns:
        包含Element ID和SourceAnchor的块列表
    """
    with open(middle_json_path, "r", encoding="utf-8") as f:
        middle = json.load(f)
    
    blocks_with_ids = []
    
    for page_idx, page_info in enumerate(middle.get("pdf_info", [])):
        for block_idx, block in enumerate(page_info.get("preproc_blocks", [])):
            block_id = generate_element_id(doc_id, page_idx, block_idx)
            
            block_data = {
                "element_id": block_id,
                "type": block.get("type"),
                "page_idx": page_idx,
                "source_anchor": create_source_anchor(
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
                        page_idx=page_idx,
                        bbox=line.get("bbox", [0, 0, 0, 0]),
                    ),
                    "spans": [],
                }
                
                for span_idx, span in enumerate(line.get("spans", [])):
                    span_id = generate_element_id(
                        doc_id, page_idx, block_idx, line_idx, span_idx
                    )
                    
                    span_data = {
                        "element_id": span_id,
                        "content": span.get("content", ""),
                        "type": span.get("type", "text"),
                        "source_anchor": create_source_anchor(
                            page_idx=page_idx,
                            bbox=span.get("bbox", [0, 0, 0, 0]),
                            score=span.get("score"),
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
    将content_list条目映射到带ID的块结构
    
    通过页码和类型匹配，为content_list条目添加element_id引用
    
    Args:
        content_list_path: content_list.json文件路径
        blocks_with_ids: 从extract_blocks_with_ids生成的块列表
        doc_id: 文档标识符
    
    Returns:
        增强后的content_list（包含element_id引用）
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
    
    # 为每个content_list条目匹配element_id
    enhanced_content = []
    for entry_idx, entry in enumerate(content_list):
        page_idx = entry.get("page_idx", 0)
        entry_type = entry.get("type")
        
        # 尝试匹配对应的块
        matched_block_id = None
        page_blocks = blocks_by_page.get(page_idx, [])
        
        # 按类型匹配
        type_map = {"text": "text", "image": "image", "table": "table"}
        target_type = type_map.get(entry_type)
        
        for block in page_blocks:
            if block["type"] == target_type:
                matched_block_id = block["element_id"]
                break
        
        enhanced_entry = entry.copy()
        if matched_block_id:
            enhanced_entry["element_id"] = matched_block_id
        else:
            # 如果没有匹配的块，使用条目索引生成ID
            enhanced_entry["element_id"] = f"{doc_id}_p{page_idx}_e{entry_idx}"
        
        enhanced_content.append(enhanced_entry)
    
    return enhanced_content


def generate_content_hash(content: str) -> str:
    """
    生成内容的SHA256哈希（用于去重和验证）
    
    Args:
        content: 文本内容
    
    Returns:
        16进制哈希字符串（前16位）
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    # 测试：为F07_test生成带ID的Document IR
    import sys
    
    doc_id = "F07_test"
    output_base = Path(r"D:\Knowledge_World\data\test_corpus\mineru_output\F07_test\main\auto")
    
    middle_path = output_base / "main_middle.json"
    content_list_path = output_base / "main_content_list.json"
    
    print(f"Processing {doc_id}...")
    
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
    
    # 统计
    print(f"\n=== Statistics ===")
    print(f"Total blocks: {len(blocks)}")
    print(f"Total lines: {sum(len(b['lines']) for b in blocks)}")
    print(f"Total spans: {sum(len(l['spans']) for b in blocks for l in b['lines'])}")
    print(f"Content entries with element_id: {sum(1 for e in enhanced_content if 'element_id' in e)}")
