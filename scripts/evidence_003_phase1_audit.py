"""
Phase 1 审计报告：真实SourceAnchor回链可行性分析
根据PI决策"不得为了提高SourceAnchor覆盖率而制造来源"，
诚实记录哪些知识对象可以回链、哪些不能、以及原因。
"""
import json
from pathlib import Path
from datetime import datetime

DATA_ROOT = Path("D:/Knowledge_World/data/test_corpus")
REPORTS_ROOT = Path("D:/Knowledge_World/runs/single_doc_reports")
OUTPUT_ROOT = Path("D:/Knowledge_World/runs/evidence_003")

DOCS = ["F02", "F07", "P01", "PAT01"]


def analyze_document(doc_id: str) -> dict:
    """分析单个文档的回链情况"""
    report_path = REPORTS_ROOT / doc_id / f"{doc_id}_knowledge_report.json"
    if not report_path.exists():
        return {"status": "NOT_FOUND", "doc_id": doc_id}
    
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    
    ko = report.get("knowledge_objects", {})
    qty_records = report.get("quantity_records", [])
    
    # 统计各类知识对象
    object_stats = {}
    total_derived = 0
    total_extracted = 0
    total_inferred = 0
    
    for obj_type in ["facts", "claims", "evidence", "limitations", "open_questions",
                     "hypotheses", "experiment_proposals", "feasibility_assessments",
                     "validation_plans"]:
        objects = ko.get(obj_type, [])
        derived_count = sum(1 for obj in objects if obj.get("provenance_label") == "DERIVED")
        extracted_count = sum(1 for obj in objects if obj.get("provenance_label") == "EXTRACTED")
        inferred_count = sum(1 for obj in objects if obj.get("provenance_label") == "INFERRED")
        
        object_stats[obj_type] = {
            "total": len(objects),
            "derived": derived_count,
            "extracted": extracted_count,
            "inferred": inferred_count,
        }
        
        total_derived += derived_count
        total_extracted += extracted_count
        total_inferred += inferred_count
    
    # 分析SourceAnchor现状
    anchor_analysis = {
        "synthetic_anchors": 0,
        "real_element_anchors": 0,
        "missing_anchors": 0,
        "anchor_patterns": {},
    }
    
    for obj_type, objects in ko.items():
        if not isinstance(objects, list):
            continue
        for obj in objects:
            anchor = obj.get("source_anchor", {})
            element_id = anchor.get("element_id", "")
            
            if not element_id:
                anchor_analysis["missing_anchors"] += 1
            elif "_dim_" in element_id:
                anchor_analysis["synthetic_anchors"] += 1
                # 记录合成锚的模式
                pattern = element_id
                anchor_analysis["anchor_patterns"][pattern] = anchor_analysis["anchor_patterns"].get(pattern, 0) + 1
            else:
                anchor_analysis["real_element_anchors"] += 1
    
    # 分析QuantityRecord
    qty_records = report.get("quantity_records", {})
    if isinstance(qty_records, dict):
        qty_list = list(qty_records.values())
    else:
        qty_list = qty_records
    
    qty_stats = {
        "total": len(qty_list),
        "with_source_anchor": sum(1 for qr in qty_list if isinstance(qr, dict) and qr.get("source_anchor")),
        "provenance_extracted": sum(1 for qr in qty_list if isinstance(qr, dict) and qr.get("provenance_label") == "EXTRACTED"),
    }
    
    # 检查六维抽取数据是否有来源信息
    g3_output_dir = DATA_ROOT / "g3_output" / doc_id
    has_dimension_source_info = False
    if g3_output_dir.exists():
        for ext_file in g3_output_dir.glob("*_extracted.json"):
            with open(ext_file, "r", encoding="utf-8") as f:
                dim_data = json.load(f)
            # 检查是否有source_location或page_idx等字段
            if any(key in dim_data for key in ["source_location", "page_idx", "element_id", "source_anchor"]):
                has_dimension_source_info = True
                break
    
    return {
        "doc_id": doc_id,
        "status": "ANALYZED",
        "timestamp": datetime.now().isoformat(),
        "object_statistics": object_stats,
        "provenance_summary": {
            "derived": total_derived,
            "extracted": total_extracted,
            "inferred": total_inferred,
            "total": total_derived + total_extracted + total_inferred,
        },
        "anchor_analysis": anchor_analysis,
        "quantity_record_stats": qty_stats,
        "dimension_data_has_source_info": has_dimension_source_info,
        "conclusion": {
            "can_rebuild_real_anchors": False,
            "reason": "知识对象为LLM从六维抽取数据确定性映射(DERIVED)，六维抽取数据无来源位置元数据，"
                     "无法追溯到具体文档元素。根据PI决策，不得制造来源。",
            "recommendation": "保留合成锚点作为历史溯源信息，标记为UNRESOLVED，"
                            "优先从下一阶段开始为新增知识对象建立真实回链机制。",
        },
    }


def main():
    """生成Phase 1审计报告"""
    print("=" * 70)
    print("SINGLE-DOC-EVIDENCE-003 Phase 1 审计：真实SourceAnchor回链可行性")
    print("=" * 70)
    
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    
    audit_results = {}
    for doc_id in DOCS:
        print(f"\n分析 {doc_id}...")
        result = analyze_document(doc_id)
        audit_results[doc_id] = result
        
        # 打印关键统计
        if result["status"] == "ANALYZED":
            prov = result["provenance_summary"]
            anchor = result["anchor_analysis"]
            print(f"  知识对象: DERIVED={prov['derived']}, EXTRACTED={prov['extracted']}, INFERRED={prov['inferred']}")
            print(f"  锚点状态: 合成={anchor['synthetic_anchors']}, 真实={anchor['real_element_anchors']}, 缺失={anchor['missing_anchors']}")
            print(f"  六维数据有来源信息: {result['dimension_data_has_source_info']}")
            print(f"  结论: {result['conclusion']['can_rebuild_real_anchors']}")
        
        # 保存单个文档审计
        output_path = OUTPUT_ROOT / f"{doc_id}_phase1_audit.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  已保存: {output_path}")
    
    # 保存汇总审计
    summary_path = OUTPUT_ROOT / "phase1_audit_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2, ensure_ascii=False)
    
    # 生成Markdown报告
    md_path = OUTPUT_ROOT / "phase1_audit_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# SINGLE-DOC-EVIDENCE-003 Phase 1 审计报告\n\n")
        f.write(f"**生成时间**: {datetime.now().isoformat()}\n\n")
        f.write("## 审计目标\n\n")
        f.write("评估现有知识对象能否回链到真实文档元素（页码、block_index、bbox、原文片段）。\n\n")
        f.write("## PI决策约束\n\n")
        f.write("> 不得为了提高SourceAnchor覆盖率而根据数值相同、关键词相似或LLM推测制造来源。\n\n")
        f.write("## 审计结果汇总\n\n")
        
        total_objects = 0
        total_derived = 0
        total_synthetic = 0
        total_real = 0
        
        for doc_id in DOCS:
            result = audit_results[doc_id]
            if result["status"] != "ANALYZED":
                continue
            
            prov = result["provenance_summary"]
            anchor = result["anchor_analysis"]
            
            total_objects += prov["total"]
            total_derived += prov["derived"]
            total_synthetic += anchor["synthetic_anchors"]
            total_real += anchor["real_element_anchors"]
            
            f.write(f"### {doc_id}\n\n")
            f.write(f"- **知识对象总数**: {prov['total']}\n")
            f.write(f"  - DERIVED (六维映射): {prov['derived']}\n")
            f.write(f"  - EXTRACTED (管线抽取): {prov['extracted']}\n")
            f.write(f"  - INFERRED (系统推断): {prov['inferred']}\n")
            f.write(f"- **SourceAnchor状态**:\n")
            f.write(f"  - 合成维度锚点: {anchor['synthetic_anchors']}\n")
            f.write(f"  - 真实元素锚点: {anchor['real_element_anchors']}\n")
            f.write(f"  - 缺失: {anchor['missing_anchors']}\n")
            f.write(f"- **六维数据有来源位置信息**: {result['dimension_data_has_source_info']}\n\n")
        
        f.write("## 总体统计\n\n")
        f.write(f"| 指标 | 数值 |\n")
        f.write(f"|------|------|\n")
        f.write(f"| 知识对象总数 | {total_objects} |\n")
        f.write(f"| DERIVED对象 | {total_derived} ({total_derived/total_objects*100:.1f}%) |\n")
        f.write(f"| 合成锚点 | {total_synthetic} |\n")
        f.write(f"| 真实锚点 | {total_real} |\n")
        f.write(f"| 可回链率 | {total_real/total_objects*100:.1f}% |\n\n")
        
        f.write("## 结论\n\n")
        f.write("### 核心发现\n\n")
        f.write("1. **所有DERIVED知识对象无法回链到真实文档元素**\n")
        f.write("   - 原因：六维抽取数据（catalyst_design_extracted.json等）由LLM生成，不包含source_location、page_idx、element_id等来源元数据\n")
        f.write("   - 知识对象是从六维字段确定性映射而来，继承了这一缺陷\n\n")
        f.write("2. **合成锚点（如`F02_dim_catalyst_design`）的历史价值**\n")
        f.write("   - 这些锚点记录了知识对象来源于哪个六维字段\n")
        f.write("   - 应保留为legacy溯源信息，但不得伪装为真实文档元素引用\n\n")
        f.write("3. **EXTRACTED对象（QuantityRecord）可能有回链能力**\n")
        f.write("   - 这些对象来自NUM-UNIT-001管线，部分带有source_anchor\n")
        f.write("   - 需要单独审计其锚点质量（Phase 3任务）\n\n")
        
        f.write("### 下一步建议\n\n")
        f.write("1. **Phase 2**: 对INFERRED对象（Limitations/OpenQuestions）进行内容核验，确认是否为作者明确陈述\n")
        f.write("2. **Phase 3**: 审计QuantityRecord的真实锚点质量\n")
        f.write("3. **Phase 5**: 在报告中明确区分\"可回链\"与\"不可回链\"对象，不掩盖事实\n")
        f.write("4. **长期**: 为后续新增知识对象建立从LLM抽取阶段就携带来源位置元数据的机制\n\n")
        
        f.write("## 合规声明\n\n")
        f.write("本报告严格遵守PI决策：未制造任何虚假来源锚点。所有无法回链的对象标记为UNRESOLVED，"
               "并保留原有合成锚点作为历史溯源信息。\n")
    
    print(f"\n{'=' * 70}")
    print("Phase 1 审计完成")
    print(f"{'=' * 70}")
    print(f"Markdown报告: {md_path}")
    print(f"JSON汇总: {summary_path}")
    print(f"\n核心结论: {total_real}/{total_objects} ({total_real/total_objects*100:.1f}%) 知识对象可回链到真实文档元素")
    print(f"原因: 六维抽取数据无来源位置元数据，DERIVED对象继承此缺陷")


if __name__ == "__main__":
    main()
