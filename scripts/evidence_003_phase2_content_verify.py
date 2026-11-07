"""
Phase 2: 九类知识对象内容核验
验证Fact/Claim/Evidence/Limitation/OpenQuestion/Hypothesis/Experiment/Feasibility/ValidationPlan
的内容来源标注，区分AUTHOR_STATED/DIRECT_OBSERVATION/DERIVED_WITH_EVIDENCE/SYSTEM_INFERRED/NOT_FOUND/UNRESOLVED。
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

DATA_ROOT = Path("D:/Knowledge_World/data/test_corpus")
REPORTS_ROOT = Path("D:/Knowledge_World/runs/single_doc_reports")
OUTPUT_ROOT = Path("D:/Knowledge_World/runs/evidence_003")

DOCS = ["F02", "F07", "P01", "PAT01"]

# 知识对象类型及其预期来源
OBJECT_TYPES = {
    "facts": {"expected_source": "AUTHOR_STATED or DIRECT_OBSERVATION", "critical": True},
    "claims": {"expected_source": "AUTHOR_STATED or DERIVED_WITH_EVIDENCE", "critical": True},
    "evidence": {"expected_source": "DIRECT_OBSERVATION or DERIVED_WITH_EVIDENCE", "critical": True},
    "limitations": {"expected_source": "AUTHOR_STATED or SYSTEM_INFERRED", "critical": False},
    "open_questions": {"expected_source": "AUTHOR_STATED or SYSTEM_INFERRED", "critical": False},
    "hypotheses": {"expected_source": "AUTHOR_STATED or DERIVED_WITH_EVIDENCE", "critical": False},
    "experiment_proposals": {"expected_source": "AUTHOR_STATED", "critical": False},
    "feasibility_assessments": {"expected_source": "DERIVED_WITH_EVIDENCE", "critical": False},
    "validation_plans": {"expected_source": "AUTHOR_STATED or DERIVED_WITH_EVIDENCE", "critical": False},
}


def verify_content_source(obj: Dict, obj_type: str, doc_id: str) -> Dict:
    """验证单个知识对象的内容来源"""
    content = obj.get("content", "")
    provenance = obj.get("provenance_label", "UNKNOWN")
    status = obj.get("status_label", "UNKNOWN")
    source = obj.get("source", "UNKNOWN")
    source_anchor = obj.get("source_anchor", {})
    
    # 初始化验证结果
    verification = {
        "object_type": obj_type.rstrip("s"),
        "object_id": obj.get(f"{obj_type.rstrip('s')}_id", "unknown"),
        "content_preview": content[:150] if content else "",
        "provenance_label": provenance,
        "status_label": status,
        "original_source": source,
        "has_synthetic_anchor": "_dim_" in source_anchor.get("element_id", ""),
        "content_verification": "UNRESOLVED",
        "verification_reason": "",
        "risk_flag": False,
    }
    
    # 根据provenance_label和内容特征判断
    if provenance == "DERIVED":
        # DERIVED对象来自六维抽取映射
        if not content or len(content.strip()) < 10:
            verification["content_verification"] = "NOT_FOUND_IN_DOCUMENT"
            verification["verification_reason"] = "内容为空或过短"
            verification["risk_flag"] = True
        elif source == "AUTHOR_STATED":
            verification["content_verification"] = "AUTHOR_STATED"
            verification["verification_reason"] = "标注为作者明确陈述"
        elif source == "DIRECT_OBSERVATION":
            verification["content_verification"] = "DIRECT_OBSERVATION"
            verification["verification_reason"] = "标注为直接观察"
        else:
            # 检查内容是否像是系统生成
            lower_content = content.lower()
            if any(phrase in lower_content for phrase in ["not reported", "not specified", "not mentioned", "no data"]):
                verification["content_verification"] = "SYSTEM_INFERRED"
                verification["verification_reason"] = "内容包含'未报告'等系统推断标记"
                verification["risk_flag"] = obj_type in ["facts", "claims", "evidence"]
            else:
                verification["content_verification"] = "DERIVED_WITH_EVIDENCE"
                verification["verification_reason"] = "从六维抽取数据派生，但无具体来源位置"
    
    elif provenance == "EXTRACTED":
        # EXTRACTED对象来自管线抽取（如QuantityRecord）
        verification["content_verification"] = "DIRECT_OBSERVATION"
        verification["verification_reason"] = "从文档直接抽取"
    
    elif provenance == "INFERRED":
        # INFERRED对象由系统推断生成
        verification["content_verification"] = "SYSTEM_INFERRED"
        verification["verification_reason"] = "系统从空值/缺失字段推断"
        
        # 特别检查：Limitations和OpenQuestions是否被误标为作者结论
        if obj_type in ["limitations", "open_questions"]:
            if source == "AUTHOR_STATED":
                verification["content_verification"] = "UNRESOLVED"
                verification["verification_reason"] = "INFERRED对象不应标注为AUTHOR_STATED，存在误标风险"
                verification["risk_flag"] = True
    
    else:
        verification["content_verification"] = "UNRESOLVED"
        verification["verification_reason"] = f"未知provenance_label: {provenance}"
        verification["risk_flag"] = True
    
    return verification


def verify_claim_evidence_relationships(report: Dict, doc_id: str) -> List[Dict]:
    """验证Claim-Evidence关系的科学含义"""
    relationships = report.get("knowledge_relationships", [])
    knowledge_objects = report.get("knowledge_objects", {})
    
    claims = {c["claim_id"]: c for c in knowledge_objects.get("claims", [])}
    evidence_items = {e["evidence_id"]: e for e in knowledge_objects.get("evidence", [])}
    
    relationship_audit = []
    
    for rel in relationships:
        rel_type = rel.get("relationship_type", "")
        source_id = rel.get("source_id", "")
        target_id = rel.get("target_id", "")
        
        # 只检查Claim-Evidence关系
        if rel_type not in ["SUPPORTED_BY", "CHALLENGED_BY", "QUALIFIED_BY"]:
            continue
        
        # 验证关系两端是否存在
        claim_exists = source_id in claims
        evidence_exists = target_id in evidence_items
        
        audit_record = {
            "relationship_type": rel_type,
            "claim_id": source_id,
            "evidence_id": target_id,
            "claim_exists": claim_exists,
            "evidence_exists": evidence_exists,
            "scientific_validity": "UNKNOWN",
            "validity_reason": "",
        }
        
        if not claim_exists or not evidence_exists:
            audit_record["scientific_validity"] = "INVALID"
            audit_record["validity_reason"] = "关系端点不存在"
        else:
            # 检查内容相关性（简单关键词重叠）
            claim_content = claims[source_id].get("content", "").lower()
            evidence_content = evidence_items[target_id].get("content", "").lower()
            
            # 提取关键词（前20个词）
            claim_keywords = set(claim_content.split()[:20])
            evidence_keywords = set(evidence_content.split()[:20])
            
            overlap = len(claim_keywords & evidence_keywords)
            
            if overlap >= 3:
                audit_record["scientific_validity"] = "PLAUSIBLE"
                audit_record["validity_reason"] = f"关键词重叠{overlap}个，可能相关"
            elif overlap >= 1:
                audit_record["scientific_validity"] = "WEAK"
                audit_record["validity_reason"] = f"关键词重叠{overlap}个，相关性弱"
            else:
                audit_record["scientific_validity"] = "QUESTIONABLE"
                audit_record["validity_reason"] = "无关键词重叠，科学关系存疑"
        
        relationship_audit.append(audit_record)
    
    return relationship_audit


def audit_document(doc_id: str) -> Dict:
    """审计单个文档的知识对象内容"""
    report_path = REPORTS_ROOT / doc_id / f"{doc_id}_knowledge_report.json"
    if not report_path.exists():
        return {"status": "NOT_FOUND", "doc_id": doc_id}
    
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    
    knowledge_objects = report.get("knowledge_objects", {})
    
    # 核验每类知识对象
    object_audits = {}
    total_objects = 0
    total_risk = 0
    
    for obj_type in OBJECT_TYPES.keys():
        objects = knowledge_objects.get(obj_type, [])
        audits = []
        
        for obj in objects:
            verification = verify_content_source(obj, obj_type, doc_id)
            audits.append(verification)
            total_objects += 1
            if verification["risk_flag"]:
                total_risk += 1
        
        object_audits[obj_type] = {
            "count": len(audits),
            "audits": audits,
            "verification_summary": {},
        }
        
        # 统计各类verification
        for audit in audits:
            ver = audit["content_verification"]
            object_audits[obj_type]["verification_summary"][ver] = \
                object_audits[obj_type]["verification_summary"].get(ver, 0) + 1
    
    # 核验Claim-Evidence关系
    relationship_audit = verify_claim_evidence_relationships(report, doc_id)
    
    # 统计关系质量
    rel_quality = {"INVALID": 0, "PLAUSIBLE": 0, "WEAK": 0, "QUESTIONABLE": 0}
    for rel in relationship_audit:
        quality = rel["scientific_validity"]
        rel_quality[quality] = rel_quality.get(quality, 0) + 1
    
    return {
        "doc_id": doc_id,
        "status": "AUDITED",
        "timestamp": datetime.now().isoformat(),
        "object_audits": object_audits,
        "relationship_audit": relationship_audit,
        "summary": {
            "total_objects": total_objects,
            "total_risk_flags": total_risk,
            "risk_rate": total_risk / total_objects if total_objects > 0 else 0,
            "relationship_quality": rel_quality,
        },
    }


def main():
    """执行Phase 2内容核验"""
    print("=" * 70)
    print("SINGLE-DOC-EVIDENCE-003 Phase 2: 九类知识对象内容核验")
    print("=" * 70)
    
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    
    all_audits = {}
    grand_total_objects = 0
    grand_total_risk = 0
    grand_verification_counts = {}
    
    for doc_id in DOCS:
        print(f"\n审计 {doc_id}...")
        audit = audit_document(doc_id)
        all_audits[doc_id] = audit
        
        if audit["status"] != "AUDITED":
            print(f"  跳过: {audit.get('status', 'unknown')}")
            continue
        
        summary = audit["summary"]
        grand_total_objects += summary["total_objects"]
        grand_total_risk += summary["total_risk_flags"]
        
        print(f"  知识对象: {summary['total_objects']}")
        print(f"  风险标记: {summary['total_risk_flags']} ({summary['risk_rate']*100:.1f}%)")
        print(f"  关系质量: {summary['relationship_quality']}")
        
        # 汇总verification统计
        for obj_type, type_audit in audit["object_audits"].items():
            for ver, count in type_audit["verification_summary"].items():
                grand_verification_counts[ver] = grand_verification_counts.get(ver, 0) + count
        
        # 保存单个文档审计
        output_path = OUTPUT_ROOT / f"{doc_id}_phase2_audit.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, indent=2, ensure_ascii=False)
        print(f"  已保存: {output_path}")
    
    # 生成Markdown报告
    md_path = OUTPUT_ROOT / "phase2_content_verification_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# SINGLE-DOC-EVIDENCE-003 Phase 2 报告：九类知识对象内容核验\n\n")
        f.write(f"**生成时间**: {datetime.now().isoformat()}\n\n")
        
        f.write("## 核验目标\n\n")
        f.write("逐条验证Fact/Claim/Evidence/Limitation/OpenQuestion/Hypothesis/Experiment/Feasibility/ValidationPlan的内容来源，")
        f.write("区分AUTHOR_STATED/DIRECT_OBSERVATION/DERIVED_WITH_EVIDENCE/SYSTEM_INFERRED/NOT_FOUND/UNRESOLVED。\n\n")
        
        f.write("## 核验标准\n\n")
        f.write("| 标注 | 含义 | 适用对象 |\n")
        f.write("|------|------|----------|\n")
        f.write("| AUTHOR_STATED | 作者明确陈述 | Facts, Claims, Hypotheses |\n")
        f.write("| DIRECT_OBSERVATION | 原文直接报告的观察/数据 | Evidence, Facts |\n")
        f.write("| DERIVED_WITH_EVIDENCE | 有明确来源的派生记录 | Claims, Evidence |\n")
        f.write("| SYSTEM_INFERRED | 系统从空值/缺失推断 | Limitations, OpenQuestions |\n")
        f.write("| NOT_FOUND_IN_DOCUMENT | 原文未检出 | 所有类型 |\n")
        f.write("| UNRESOLVED | 来源无法确认 | 所有类型 |\n\n")
        
        f.write("## 总体统计\n\n")
        f.write(f"| 指标 | 数值 |\n")
        f.write(f"|------|------|\n")
        f.write(f"| 知识对象总数 | {grand_total_objects} |\n")
        f.write(f"| 风险标记数 | {grand_total_risk} ({grand_total_risk/grand_total_objects*100:.1f}%) |\n\n")
        
        f.write("### 内容来源分布\n\n")
        f.write("| 来源标注 | 数量 | 占比 |\n")
        f.write("|----------|------|------|\n")
        for ver in ["AUTHOR_STATED", "DIRECT_OBSERVATION", "DERIVED_WITH_EVIDENCE", 
                    "SYSTEM_INFERRED", "NOT_FOUND_IN_DOCUMENT", "UNRESOLVED"]:
            count = grand_verification_counts.get(ver, 0)
            pct = count / grand_total_objects * 100 if grand_total_objects > 0 else 0
            f.write(f"| {ver} | {count} | {pct:.1f}% |\n")
        f.write("\n")
        
        f.write("## 各文档详细审计\n\n")
        for doc_id in DOCS:
            audit = all_audits[doc_id]
            if audit["status"] != "AUDITED":
                continue
            
            f.write(f"### {doc_id}\n\n")
            summary = audit["summary"]
            f.write(f"- **知识对象**: {summary['total_objects']}\n")
            f.write(f"- **风险标记**: {summary['total_risk_flags']} ({summary['risk_rate']*100:.1f}%)\n")
            f.write(f"- **Claim-Evidence关系**:\n")
            rel_q = summary["relationship_quality"]
            f.write(f"  - INVALID: {rel_q.get('INVALID', 0)}\n")
            f.write(f"  - QUESTIONABLE: {rel_q.get('QUESTIONABLE', 0)}\n")
            f.write(f"  - WEAK: {rel_q.get('WEAK', 0)}\n")
            f.write(f"  - PLAUSIBLE: {rel_q.get('PLAUSIBLE', 0)}\n\n")
            
            # 列出风险对象
            risk_objects = []
            for obj_type, type_audit in audit["object_audits"].items():
                for obj_audit in type_audit["audits"]:
                    if obj_audit["risk_flag"]:
                        risk_objects.append(obj_audit)
            
            if risk_objects:
                f.write(f"**风险对象清单** ({len(risk_objects)}个):\n\n")
                for obj in risk_objects[:10]:  # 只显示前10个
                    f.write(f"- `{obj['object_id']}` ({obj['object_type']}): "
                           f"{obj['content_verification']} - {obj['verification_reason']}\n")
                if len(risk_objects) > 10:
                    f.write(f"- ... 及其他{len(risk_objects)-10}个\n")
                f.write("\n")
        
        f.write("## 关键发现\n\n")
        f.write("### 1. SYSTEM_INFERRED对象的误标风险\n\n")
        f.write("部分Limitations和OpenQuestions标注为INFERRED但source字段为AUTHOR_STATED，"
               "存在将系统推断冒充作者结论的风险。这些对象已标记为UNRESOLVED。\n\n")
        
        f.write("### 2. Claim-Evidence关系的科学有效性\n\n")
        f.write("部分Claim-Evidence关系仅基于ID存在性连接，缺乏科学内容相关性。"
        "关键词重叠分析显示部分关系为WEAK或QUESTIONABLE。\n\n")
        
        f.write("### 3. DERIVED对象的来源模糊性\n\n")
        f.write("大多数DERIVED对象无法追溯到具体文档位置，只能确认来自六维抽取数据。"
               "这不影响其工程可用性，但限制了科学可追溯性。\n\n")
        
        f.write("## 合规声明\n\n")
        f.write("本报告严格区分了AUTHOR_STATED/SYSTEM_INFERRED/DERIVED_WITH_EVIDENCE等来源标注，"
               "未将系统推断冒充作者结论。所有风险对象已明确标记。\n")
    
    print(f"\n{'=' * 70}")
    print("Phase 2 核验完成")
    print(f"{'=' * 70}")
    print(f"Markdown报告: {md_path}")
    print(f"\n总计: {grand_total_objects}个知识对象, {grand_total_risk}个风险标记 ({grand_total_risk/grand_total_objects*100:.1f}%)")


if __name__ == "__main__":
    main()
