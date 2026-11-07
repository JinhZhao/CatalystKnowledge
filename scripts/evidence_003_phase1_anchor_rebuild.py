"""
Phase 1: 真实SourceAnchor重建
从MinerU content_list.json和middle.json建立真实文档元素索引，
将知识对象回链到具体页码、block_index、bbox和原文片段。
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 配置
DATA_ROOT = Path("D:/Knowledge_World/data/test_corpus")
MINERU_ROOT = DATA_ROOT / "mineru_output"
REPORTS_ROOT = Path("D:/Knowledge_World/runs/single_doc_reports")
OUTPUT_ROOT = Path("D:/Knowledge_World/runs/evidence_003")

# 文档配置：doc_id -> (mineru_dir, document_id_in_store)
DOC_CONFIG = {
    "F02": {
        "mineru_dir": "F02_regression/main/auto",
        "doc_id": "F02",
        "content_list": "main_content_list.json",
        "middle": "main_middle.json",
    },
    "F07": {
        "mineru_dir": "F07_batch/main/auto",
        "doc_id": "F07",
        "content_list": "main_content_list.json",
        "middle": "main_middle.json",
    },
    "P01_main": {
        "mineru_dir": "P01_main_link01/P01_main/auto",
        "doc_id": "P01_main",
        "content_list": "P01_main_content_list.json",
        "middle": "P01_main_middle.json",
    },
    "PAT01": {
        "mineru_dir": "PAT01_batch/US20100029974A1/auto",
        "doc_id": "PAT01",
        "content_list": "US20100029974A1_content_list.json",
        "middle": "US20100029974A1_middle.json",
    },
}


class DocumentElementIndex:
    """文档元素索引，存储所有可回链的元素"""
    
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.elements: List[Dict] = []
        self.text_to_elements: Dict[str, List[int]] = {}  # 文本片段 -> element indices
    
    def add_element(self, element: Dict):
        """添加元素"""
        idx = len(self.elements)
        self.elements.append(element)
        
        # 建立文本索引（使用关键片段）
        text = element.get("text", "")
        if text:
            # 使用前100字符作为索引键
            key = text[:100].strip().lower()
            if key not in self.text_to_elements:
                self.text_to_elements[key] = []
            self.text_to_elements[key].append(idx)
    
    def find_matching_elements(self, query_text: str, min_overlap: int = 20) -> List[Tuple[int, float]]:
        """查找匹配的元素，返回(element_idx, confidence)"""
        if not query_text or len(query_text) < min_overlap:
            return []
        
        query_lower = query_text.strip().lower()
        matches = []
        
        # 精确匹配
        if query_lower[:100] in self.text_to_elements:
            for idx in self.text_to_elements[query_lower[:100]]:
                matches.append((idx, 1.0))
            return matches
        
        # 模糊匹配：检查query是否包含在元素文本中
        for idx, elem in enumerate(self.elements):
            elem_text = elem.get("text", "").lower()
            if not elem_text:
                continue
            
            # 计算重叠
            if query_lower in elem_text or elem_text in query_lower:
                overlap = min(len(query_lower), len(elem_text))
                confidence = overlap / max(len(query_lower), len(elem_text))
                if confidence > 0.5:
                    matches.append((idx, confidence))
        
        return matches


def build_element_index(doc_id: str, config: Dict) -> DocumentElementIndex:
    """从MinerU输出构建元素索引"""
    mineru_dir = MINERU_ROOT / config["mineru_dir"]
    content_list_path = mineru_dir / config["content_list"]
    middle_path = mineru_dir / config["middle"]
    
    index = DocumentElementIndex(doc_id)
    
    # 读取content_list.json
    if not content_list_path.exists():
        print(f"  WARNING: {content_list_path} not found, skipping")
        return index
    
    with open(content_list_path, "r", encoding="utf-8") as f:
        content_list = json.load(f)
    
    # 读取middle.json获取bbox信息
    middle_data = None
    if middle_path.exists():
        with open(middle_path, "r", encoding="utf-8") as f:
            middle_data = json.load(f)
    
    # 解析content_list，建立元素索引
    block_index = 0
    for item in content_list:
        item_type = item.get("type", "unknown")
        page_idx = item.get("page_idx", 0)
        
        if item_type == "text":
            text = item.get("text", "").strip()
            if not text:
                continue
            
            # 尝试从middle_data获取bbox
            bbox = None
            if middle_data and page_idx < len(middle_data.get("pdf_info", [])):
                page_info = middle_data["pdf_info"][page_idx]
                # 查找匹配的block
                for block in page_info.get("preproc_blocks", []):
                    if block.get("type") == "text":
                        block_text = " ".join([
                            span.get("content", "")
                            for line in block.get("lines", [])
                            for span in line.get("spans", [])
                        ]).strip()
                        if block_text and text[:50] in block_text:
                            bbox = block.get("bbox")
                            break
            
            element = {
                "element_id": f"{doc_id}_p{page_idx}_b{block_index}",
                "element_type": "TEXT",
                "page_idx": page_idx,
                "block_index": block_index,
                "text": text,
                "text_preview": text[:200],
                "bbox": bbox,
                "source_file": config["content_list"],
                "parse_version": "MinerU_v1.0",
            }
            index.add_element(element)
            block_index += 1
        
        elif item_type == "image":
            img_path = item.get("img_path", "")
            img_caption = item.get("img_caption", [])
            
            element = {
                "element_id": f"{doc_id}_p{page_idx}_b{block_index}",
                "element_type": "IMAGE",
                "page_idx": page_idx,
                "block_index": block_index,
                "img_path": img_path,
                "img_caption": img_caption,
                "text": " ".join(img_caption) if img_caption else "",
                "source_file": config["content_list"],
                "parse_version": "MinerU_v1.0",
            }
            index.add_element(element)
            block_index += 1
        
        elif item_type == "table":
            table_content = item.get("table_content", "")
            table_caption = item.get("table_caption", [])
            
            element = {
                "element_id": f"{doc_id}_p{page_idx}_b{block_index}",
                "element_type": "TABLE",
                "page_idx": page_idx,
                "block_index": block_index,
                "table_content": table_content,
                "table_caption": table_caption,
                "text": " ".join(table_caption) if table_caption else table_content[:200],
                "source_file": config["content_list"],
                "parse_version": "MinerU_v1.0",
            }
            index.add_element(element)
            block_index += 1
    
    print(f"  Indexed {len(index.elements)} elements from {content_list_path.name}")
    return index


def match_knowledge_to_elements(
    knowledge_obj: Dict,
    index: DocumentElementIndex,
    doc_id: str
) -> Optional[Dict]:
    """将知识对象匹配到文档元素"""
    content = knowledge_obj.get("content", "")
    if not content:
        return None
    
    # 查找匹配元素
    matches = index.find_matching_elements(content)
    if not matches:
        return None
    
    # 选择最佳匹配
    best_idx, best_conf = matches[0]
    element = index.elements[best_idx]
    
    # 构建真实SourceAnchor
    real_anchor = {
        "document_id": doc_id,
        "element_id": element["element_id"],
        "element_type": element["element_type"],
        "page_idx": element["page_idx"],
        "block_index": element["block_index"],
        "bbox": element.get("bbox"),
        "original_text": element.get("text_preview", ""),
        "source_file": element.get("source_file", ""),
        "parse_version": element.get("parse_version", ""),
        "match_confidence": best_conf,
        "match_method": "text_overlap",
    }
    
    return real_anchor


def process_document(doc_key: str, config: Dict) -> Dict:
    """处理单个文档，生成真实SourceAnchor映射"""
    doc_id = config["doc_id"]
    print(f"\nProcessing {doc_key} (doc_id={doc_id})...")
    
    # 构建元素索引
    index = build_element_index(doc_id, config)
    if not index.elements:
        print(f"  No elements indexed, skipping")
        return {"status": "SKIPPED", "reason": "no_elements"}
    
    # 读取报告
    report_path = REPORTS_ROOT / doc_key.split("_")[0] / f"{doc_key.split('_')[0]}_knowledge_report.json"
    if not report_path.exists():
        print(f"  Report not found: {report_path}")
        return {"status": "SKIPPED", "reason": "no_report"}
    
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    
    knowledge_objects = report.get("knowledge_objects", {})
    
    # 处理每类知识对象
    anchor_mapping = {
        "document_id": doc_id,
        "element_index_size": len(index.elements),
        "objects_processed": 0,
        "objects_matched": 0,
        "objects_unresolved": 0,
        "anchors": [],
    }
    
    for obj_type in ["facts", "claims", "evidence", "limitations", "open_questions",
                     "hypotheses", "experiment_proposals", "feasibility_assessments",
                     "validation_plans"]:
        objects = knowledge_objects.get(obj_type, [])
        for obj in objects:
            anchor_mapping["objects_processed"] += 1
            
            # 保留旧锚点
            old_anchor = obj.get("source_anchor", {})
            
            # 尝试匹配新锚点
            new_anchor = match_knowledge_to_elements(obj, index, doc_id)
            
            if new_anchor:
                anchor_mapping["objects_matched"] += 1
                anchor_record = {
                    "object_type": obj_type.rstrip("s"),
                    "object_id": obj.get(f"{obj_type.rstrip('s')}_id", f"{obj_type}_{len(anchor_mapping['anchors'])}"),
                    "content_preview": obj.get("content", "")[:100],
                    "old_anchor": old_anchor,
                    "new_anchor": new_anchor,
                    "provenance_label": obj.get("provenance_label", "UNKNOWN"),
                    "status_label": obj.get("status_label", "UNKNOWN"),
                }
                anchor_mapping["anchors"].append(anchor_record)
            else:
                anchor_mapping["objects_unresolved"] += 1
    
    print(f"  Processed: {anchor_mapping['objects_processed']}, "
          f"Matched: {anchor_mapping['objects_matched']}, "
          f"Unresolved: {anchor_mapping['objects_unresolved']}")
    
    return anchor_mapping


def main():
    """主函数"""
    print("=" * 60)
    print("SINGLE-DOC-EVIDENCE-003 Phase 1: 真实SourceAnchor重建")
    print("=" * 60)
    
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    
    results = {}
    for doc_key, config in DOC_CONFIG.items():
        result = process_document(doc_key, config)
        results[doc_key] = result
        
        # 保存单个文档结果
        output_path = OUTPUT_ROOT / f"{doc_key}_anchor_mapping.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {output_path}")
    
    # 保存汇总结果
    summary_path = OUTPUT_ROOT / "phase1_anchor_mapping_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("Phase 1 完成")
    print("=" * 60)
    
    # 打印统计
    total_processed = sum(r.get("objects_processed", 0) for r in results.values() if isinstance(r, dict))
    total_matched = sum(r.get("objects_matched", 0) for r in results.values() if isinstance(r, dict))
    total_unresolved = sum(r.get("objects_unresolved", 0) for r in results.values() if isinstance(r, dict))
    
    print(f"总知识对象: {total_processed}")
    print(f"成功回链: {total_matched}")
    print(f"未解决: {total_unresolved}")
    if total_processed > 0:
        print(f"回链率: {total_matched / total_processed * 100:.1f}%")


if __name__ == "__main__":
    main()
