#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINGLE-DOC-CLOSE-005 Part A: 数据统计与关系状态审计

审计内容：
1. 109个知识对象完整状态
2. 43 SOURCE_LINKED + 64 UNRESOLVED + 2 ? = 109
3. 按文献及类型统计真实Element ID覆盖率
4. 43个SOURCE_LINKED对象逐一检查
5. 来源定位与语义证据验证分开统计
6. 61条关系逐一判定
7. 65→61的4条过滤记录
"""

import json
from pathlib import Path
from collections import defaultdict

RUNS_ROOT = Path(r"D:\Knowledge_World\runs")
REPORTS_DIR = RUNS_ROOT / "single_doc_reports"
EVIDENCE_004_DIR = RUNS_ROOT / "evidence_004"

def load_report(doc_id: str) -> dict:
    report_path = REPORTS_DIR / doc_id / f"{doc_id}_knowledge_report.json"
    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)

def audit_knowledge_objects(doc_id: str, report: dict) -> dict:
    """审计知识对象状态"""
    knowledge = report.get("knowledge_objects", {})
    
    object_types = [
        "facts", "claims", "evidence", "limitations",
        "open_questions", "hypotheses", "experiment_proposals",
        "feasibility_assessments", "validation_plans"
    ]
    
    audit = {
        "document_id": doc_id,
        "total_objects": 0,
        "by_type": {},
        "by_source_status": defaultdict(int),
        "by_provenance": defaultdict(int),
        "source_linked_objects": [],
        "unresolved_objects": [],
        "other_objects": []
    }
    
    for obj_type in object_types:
        objects = knowledge.get(obj_type, [])
        type_audit = {
            "count": len(objects),
            "source_linked": 0,
            "unresolved": 0,
            "system_inferred": 0,
            "objects": []
        }
        
        for obj in objects:
            obj_id = obj.get(f"{obj_type.rstrip('s')}_id", 
                           obj.get("fact_id", 
                                 obj.get("claim_id", "unknown")))
            
            # 检查source_anchor
            anchor = obj.get("source_anchor", {})
            element_id = anchor.get("element_id", "")
            
            # 判断来源状态
            if element_id and f"{doc_id}_p" in element_id:
                # 真实Element ID
                status = "SOURCE_LINKED"
                type_audit["source_linked"] += 1
                audit["source_linked_objects"].append({
                    "object_id": obj_id,
                    "object_type": obj_type.rstrip("s"),
                    "element_id": element_id,
                    "page": anchor.get("location", ""),
                    "provenance": obj.get("provenance_label", "")
                })
            elif element_id and f"{doc_id}_dim_" in element_id:
                # 合成锚点（维度级别）
                status = "UNRESOLVED"
                type_audit["unresolved"] += 1
                audit["unresolved_objects"].append({
                    "object_id": obj_id,
                    "object_type": obj_type.rstrip("s"),
                    "element_id": element_id,
                    "reason": "synthetic_dimension_anchor",
                    "provenance": obj.get("provenance_label", "")
                })
            else:
                # 其他情况
                status = "OTHER"
                audit["other_objects"].append({
                    "object_id": obj_id,
                    "object_type": obj_type.rstrip("s"),
                    "element_id": element_id,
                    "reason": "no_anchor_or_unknown",
                    "provenance": obj.get("provenance_label", "")
                })
            
            audit["by_source_status"][status] += 1
            
            # 统计provenance
            provenance = obj.get("provenance_label", "UNKNOWN")
            audit["by_provenance"][provenance] += 1
            
            type_audit["objects"].append({
                "object_id": obj_id,
                "status": status,
                "provenance": provenance
            })
        
        audit["by_type"][obj_type] = type_audit
        audit["total_objects"] += len(objects)
    
    # 转换defaultdict为普通dict
    audit["by_source_status"] = dict(audit["by_source_status"])
    audit["by_provenance"] = dict(audit["by_provenance"])
    
    return audit

def audit_relationships(doc_id: str, report: dict) -> dict:
    """审计关系状态"""
    relationships = report.get("knowledge_relationships", [])
    
    audit = {
        "document_id": doc_id,
        "total_relationships": len(relationships),
        "by_type": defaultdict(int),
        "by_structure_validity": defaultdict(int),
        "by_semantic_validity": defaultdict(int),
        "relationships": []
    }
    
    # 收集所有对象ID用于验证
    knowledge = report.get("knowledge_objects", {})
    all_object_ids = set()
    for obj_type in ["facts", "claims", "evidence", "limitations", "open_questions",
                     "hypotheses", "experiment_proposals", "feasibility_assessments",
                     "validation_plans"]:
        for obj in knowledge.get(obj_type, []):
            obj_id = obj.get(f"{obj_type.rstrip('s')}_id",
                           obj.get("fact_id",
                                 obj.get("claim_id", "unknown")))
            all_object_ids.add(obj_id)
    
    for rel in relationships:
        rel_id = rel["relationship_id"]
        rel_type = rel["relationship_type"]
        src_id = rel["source_id"]
        tgt_id = rel["target_id"]
        
        audit["by_type"][rel_type] += 1
        
        # 结构有效性：ID是否存在
        structure_valid = src_id in all_object_ids and tgt_id in all_object_ids
        audit["by_structure_validity"]["VALID" if structure_valid else "INVALID"] += 1
        
        # 语义有效性：方向是否正确
        semantic_valid = False
        if rel_type in ("SUPPORTED_BY", "CHALLENGED_BY"):
            # 应该是 claim → evidence
            semantic_valid = "claim" in src_id and "ev" in tgt_id
        elif rel_type == "QUALIFIED_BY":
            # claim → limitation
            semantic_valid = "claim" in src_id and "lim" in tgt_id
        elif rel_type == "TESTED_BY":
            # claim → experiment
            semantic_valid = "claim" in src_id and "exp" in tgt_id
        elif rel_type == "VALIDATES":
            # claim → validation_plan OR feasibility → hypothesis
            semantic_valid = (("claim" in src_id and "plan" in tgt_id) or
                            ("feas" in src_id and "hyp" in tgt_id))
        elif rel_type == "REQUIRES":
            # claim → fact
            semantic_valid = "claim" in src_id and "fact" in tgt_id
        elif rel_type == "MOTIVATES":
            # question → hypothesis
            semantic_valid = "q" in src_id and "hyp" in tgt_id
        
        audit["by_semantic_validity"]["VALID" if semantic_valid else "INVALID"] += 1
        
        audit["relationships"].append({
            "rel_id": rel_id,
            "rel_type": rel_type,
            "src_id": src_id,
            "tgt_id": tgt_id,
            "structure_valid": structure_valid,
            "semantic_valid": semantic_valid
        })
    
    # 转换defaultdict
    audit["by_type"] = dict(audit["by_type"])
    audit["by_structure_validity"] = dict(audit["by_structure_validity"])
    audit["by_semantic_validity"] = dict(audit["by_semantic_validity"])
    
    return audit

def main():
    doc_ids = ["F02", "F07", "P01", "PAT01"]
    
    print("=" * 80)
    print("SINGLE-DOC-CLOSE-005 Part A: 数据统计与关系状态审计")
    print("=" * 80)
    
    all_audits = {}
    total_objects = 0
    total_source_linked = 0
    total_unresolved = 0
    total_other = 0
    total_relationships = 0
    
    for doc_id in doc_ids:
        print(f"\n{'='*80}")
        print(f"审计文档: {doc_id}")
        print(f"{'='*80}")
        
        report = load_report(doc_id)
        
        # 审计知识对象
        obj_audit = audit_knowledge_objects(doc_id, report)
        
        # 审计关系
        rel_audit = audit_relationships(doc_id, report)
        
        all_audits[doc_id] = {
            "objects": obj_audit,
            "relationships": rel_audit
        }
        
        # 打印统计
        print(f"\n知识对象统计:")
        print(f"  总数: {obj_audit['total_objects']}")
        print(f"  SOURCE_LINKED: {obj_audit['by_source_status'].get('SOURCE_LINKED', 0)}")
        print(f"  UNRESOLVED: {obj_audit['by_source_status'].get('UNRESOLVED', 0)}")
        print(f"  OTHER: {obj_audit['by_source_status'].get('OTHER', 0)}")
        
        print(f"\n  按类型:")
        for obj_type, type_audit in obj_audit['by_type'].items():
            print(f"    {obj_type}: {type_audit['count']}个 " +
                  f"(SOURCE_LINKED={type_audit['source_linked']}, " +
                  f"UNRESOLVED={type_audit['unresolved']})")
        
        print(f"\n  按provenance:")
        for prov, count in obj_audit['by_provenance'].items():
            print(f"    {prov}: {count}")
        
        print(f"\n关系统计:")
        print(f"  总数: {rel_audit['total_relationships']}")
        print(f"  按类型:")
        for rel_type, count in rel_audit['by_type'].items():
            print(f"    {rel_type}: {count}")
        print(f"  结构有效: {rel_audit['by_structure_validity'].get('VALID', 0)}/{rel_audit['total_relationships']}")
        print(f"  语义有效: {rel_audit['by_semantic_validity'].get('VALID', 0)}/{rel_audit['total_relationships']}")
        
        # 累计
        total_objects += obj_audit['total_objects']
        total_source_linked += obj_audit['by_source_status'].get('SOURCE_LINKED', 0)
        total_unresolved += obj_audit['by_source_status'].get('UNRESOLVED', 0)
        total_other += obj_audit['by_source_status'].get('OTHER', 0)
        total_relationships += rel_audit['total_relationships']
    
    # 汇总
    print(f"\n{'='*80}")
    print("汇总统计")
    print(f"{'='*80}")
    print(f"知识对象总数: {total_objects}")
    print(f"  SOURCE_LINKED: {total_source_linked} ({total_source_linked/total_objects*100:.1f}%)")
    print(f"  UNRESOLVED: {total_unresolved} ({total_unresolved/total_objects*100:.1f}%)")
    print(f"  OTHER: {total_other} ({total_other/total_objects*100:.1f}%)")
    print(f"  验证: {total_source_linked} + {total_unresolved} + {total_other} = {total_source_linked + total_unresolved + total_other}")
    print(f"关系总数: {total_relationships}")
    
    # 保存审计结果
    output_path = EVIDENCE_004_DIR / "close_005_part_a_audit.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_audits, f, ensure_ascii=False, indent=2)
    
    print(f"\n审计结果已保存: {output_path}")

if __name__ == "__main__":
    main()
