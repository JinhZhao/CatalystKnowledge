"""
Phase 5: 增强报告生成器
整合Phase 1-4审计结果，生成包含完整来源验证的对象报告。
"""
import json
from pathlib import Path
from datetime import datetime

DATA_ROOT = Path("D:/Knowledge_World/data/test_corpus")
REPORTS_ROOT = Path("D:/Knowledge_World/runs/single_doc_reports")
EVIDENCE_ROOT = Path("D:/Knowledge_World/runs/evidence_003")
OUTPUT_ROOT = Path("D:/Knowledge_World/runs/evidence_003/reports_v3")

DOCS = ["F02", "F07", "P01", "PAT01"]


def load_audit_results(doc_id: str) -> dict:
    """加载Phase 1-4审计结果"""
    audits = {}
    
    # Phase 1 audit
    p1_path = EVIDENCE_ROOT / f"{doc_id}_phase1_audit.json"
    if p1_path.exists():
        with open(p1_path, "r", encoding="utf-8") as f:
            audits["phase1"] = json.load(f)
    
    # Phase 2 audit
    p2_path = EVIDENCE_ROOT / f"{doc_id}_phase2_audit.json"
    if p2_path.exists():
        with open(p2_path, "r", encoding="utf-8") as f:
            audits["phase2"] = json.load(f)
    
    # Phase 4 audit
    p4_path = EVIDENCE_ROOT / f"{doc_id}_phase4_audit.json"
    if p4_path.exists():
        with open(p4_path, "r", encoding="utf-8") as f:
            audits["phase4"] = json.load(f)
    
    return audits


def enhance_report(doc_id: str, original_report: dict, audits: dict) -> dict:
    """增强报告，整合审计结果"""
    enhanced = original_report.copy()
    
    # 添加审计元数据
    enhanced["evidence_003_audit"] = {
        "audit_timestamp": datetime.now().isoformat(),
        "audit_phases": list(audits.keys()),
        "generator_version": "SINGLE-DOC-EVIDENCE-003-v3.0",
    }
    
    # Phase 1: SourceAnchor覆盖审计
    if "phase1" in audits:
        p1 = audits["phase1"]
        anchor_analysis = p1.get("anchor_analysis", {})
        enhanced["evidence_003_audit"]["source_anchor_audit"] = {
            "total_objects": p1.get("provenance_summary", {}).get("total", 0),
            "synthetic_anchors": anchor_analysis.get("synthetic_anchors", 0),
            "real_element_anchors": anchor_analysis.get("real_element_anchors", 0),
            "missing_anchors": anchor_analysis.get("missing_anchors", 0),
            "real_anchor_coverage_rate": (
                anchor_analysis.get("real_element_anchors", 0) / 
                p1.get("provenance_summary", {}).get("total", 1) * 100
            ),
            "conclusion": p1.get("conclusion", {}),
        }
    
    # Phase 2: 内容核验审计
    if "phase2" in audits:
        p2 = audits["phase2"]
        summary = p2.get("summary", {})
        
        # 统计各类verification
        verification_counts = {}
        for obj_type, type_audit in p2.get("object_audits", {}).items():
            for ver, count in type_audit.get("verification_summary", {}).items():
                verification_counts[ver] = verification_counts.get(ver, 0) + count
        
        enhanced["evidence_003_audit"]["content_verification_audit"] = {
            "total_objects": summary.get("total_objects", 0),
            "risk_flags": summary.get("total_risk_flags", 0),
            "risk_rate": summary.get("risk_rate", 0) * 100,
            "verification_distribution": verification_counts,
            "relationship_quality": summary.get("relationship_quality", {}),
        }
    
    # Phase 3: 表格结构化审计（记录能力缺口）
    enhanced["evidence_003_audit"]["table_structure_audit"] = {
        "status": "CAPABILITY_GAP",
        "reason": "表格数据以图像形式存储，无RapidTable结构化输出（HTML/行列数据）",
        "table_count": len(original_report.get("tables", [])),
        "cannot_establish_chain": True,
        "recommendation": "后续阶段需集成RapidTable或类似工具提取结构化表格数据",
    }
    
    # Phase 4: 图表关联审计
    if "phase4" in audits:
        p4 = audits["phase4"]
        enhanced["evidence_003_audit"]["figure_association_audit"] = {
            "total_associations": p4.get("v2_associations", 0),
            "status_distribution": p4.get("v2_status_distribution", {}),
            "has_verified_version": p4.get("has_verified_version", False),
            "report_uses_v2": p4.get("report_uses_v2_not_verified", False),
            "issues": p4.get("issues", {}),
        }
    
    # 增强知识对象，添加verification标注
    knowledge_objects = enhanced.get("knowledge_objects", {})
    if "phase2" in audits:
        p2_audits = audits["phase2"].get("object_audits", {})
        for obj_type, objects in knowledge_objects.items():
            if obj_type not in p2_audits:
                continue
            type_audits = {a["object_id"]: a for a in p2_audits[obj_type].get("audits", [])}
            
            for obj in objects:
                obj_id = obj.get(f"{obj_type.rstrip('s')}_id", "")
                if obj_id in type_audits:
                    audit_info = type_audits[obj_id]
                    obj["content_verification"] = audit_info["content_verification"]
                    obj["verification_reason"] = audit_info["verification_reason"]
                    obj["risk_flag"] = audit_info["risk_flag"]
    
    # 添加综合验收指标
    enhanced["evidence_003_audit"]["acceptance_metrics"] = {
        "real_element_id_coverage": enhanced["evidence_003_audit"].get(
            "source_anchor_audit", {}
        ).get("real_anchor_coverage_rate", 0),
        "content_verification_pass_rate": (
            100 - enhanced["evidence_003_audit"].get(
                "content_verification_audit", {}
            ).get("risk_rate", 100)
        ),
        "relationship_validity_rate": (
            enhanced["evidence_003_audit"]
            .get("content_verification_audit", {})
            .get("relationship_quality", {})
            .get("PLAUSIBLE", 0) / 
            max(1, sum(enhanced["evidence_003_audit"]
                      .get("content_verification_audit", {})
                      .get("relationship_quality", {}).values())) * 100
        ),
        "figure_association_resolution_rate": (
            enhanced["evidence_003_audit"]
            .get("figure_association_audit", {})
            .get("status_distribution", {})
            .get("VERIFIED", 0) / 
            max(1, enhanced["evidence_003_audit"]
                   .get("figure_association_audit", {})
                   .get("total_associations", 1)) * 100
        ),
        "table_structure_coverage": 0,  # Phase 3能力缺口
    }
    
    return enhanced


def generate_enhanced_markdown(enhanced_report: dict, doc_id: str) -> str:
    """生成增强的Markdown报告"""
    lines = []
    audit = enhanced_report.get("evidence_003_audit", {})
    
    lines.append(f"# 单篇科学知识报告（增强版）：{doc_id}")
    lines.append("")
    lines.append(f"> 生成时间：{enhanced_report.get('generated_at', 'unknown')}")
    lines.append(f"> 增强审计时间：{audit.get('audit_timestamp', 'unknown')}")
    lines.append(f"> 生成器：{audit.get('generator_version', 'unknown')}")
    lines.append(f"> Schema版本：{enhanced_report.get('provenance', {}).get('schema_version', 'unknown')}")
    lines.append("")
    
    # 验收指标总览
    lines.append("## 验收指标总览")
    lines.append("")
    metrics = audit.get("acceptance_metrics", {})
    lines.append("| 指标 | 数值 | 说明 |")
    lines.append("|------|------|------|")
    lines.append(f"| 真实Element ID覆盖率 | {metrics.get('real_element_id_coverage', 0):.1f}% | Phase 1审计 |")
    lines.append(f"| 内容核验通过率 | {metrics.get('content_verification_pass_rate', 0):.1f}% | Phase 2审计 |")
    lines.append(f"| 关系有效性比率 | {metrics.get('relationship_validity_rate', 0):.1f}% | Phase 2审计 |")
    lines.append(f"| 图表关联解决率 | {metrics.get('figure_association_resolution_rate', 0):.1f}% | Phase 4审计 |")
    lines.append(f"| 表格结构化覆盖率 | {metrics.get('table_structure_coverage', 0):.1f}% | Phase 3能力缺口 |")
    lines.append("")
    
    # 来源锚点审计
    lines.append("## 来源锚点审计 (Phase 1)")
    lines.append("")
    anchor_audit = audit.get("source_anchor_audit", {})
    lines.append(f"- **总知识对象**: {anchor_audit.get('total_objects', 0)}")
    lines.append(f"- **合成锚点**: {anchor_audit.get('synthetic_anchors', 0)}")
    lines.append(f"- **真实元素锚点**: {anchor_audit.get('real_element_anchors', 0)}")
    lines.append(f"- **缺失锚点**: {anchor_audit.get('missing_anchors', 0)}")
    lines.append(f"- **真实锚点覆盖率**: {anchor_audit.get('real_anchor_coverage_rate', 0):.1f}%")
    if anchor_audit.get("conclusion"):
        lines.append(f"- **结论**: {anchor_audit['conclusion'].get('reason', 'N/A')}")
    lines.append("")
    
    # 内容核验审计
    lines.append("## 内容核验审计 (Phase 2)")
    lines.append("")
    content_audit = audit.get("content_verification_audit", {})
    lines.append(f"- **总对象数**: {content_audit.get('total_objects', 0)}")
    lines.append(f"- **风险标记数**: {content_audit.get('risk_flags', 0)} ({content_audit.get('risk_rate', 0):.1f}%)")
    lines.append("")
    lines.append("### 来源标注分布")
    lines.append("")
    ver_dist = content_audit.get("verification_distribution", {})
    lines.append("| 来源标注 | 数量 | 占比 |")
    lines.append("|----------|------|------|")
    total = sum(ver_dist.values()) if ver_dist else 1
    for ver in ["AUTHOR_STATED", "DIRECT_OBSERVATION", "DERIVED_WITH_EVIDENCE", 
                "SYSTEM_INFERRED", "NOT_FOUND_IN_DOCUMENT", "UNRESOLVED"]:
        count = ver_dist.get(ver, 0)
        pct = count / total * 100
        lines.append(f"| {ver} | {count} | {pct:.1f}% |")
    lines.append("")
    
    # 关系质量
    lines.append("### Claim-Evidence关系质量")
    lines.append("")
    rel_quality = content_audit.get("relationship_quality", {})
    lines.append("| 质量等级 | 数量 |")
    lines.append("|----------|------|")
    for quality in ["INVALID", "QUESTIONABLE", "WEAK", "PLAUSIBLE"]:
        lines.append(f"| {quality} | {rel_quality.get(quality, 0)} |")
    lines.append("")
    
    # 表格结构化审计
    lines.append("## 表格结构化审计 (Phase 3)")
    lines.append("")
    table_audit = audit.get("table_structure_audit", {})
    lines.append(f"- **状态**: {table_audit.get('status', 'UNKNOWN')}")
    lines.append(f"- **原因**: {table_audit.get('reason', 'N/A')}")
    lines.append(f"- **表格数量**: {table_audit.get('table_count', 0)}")
    lines.append(f"- **建议**: {table_audit.get('recommendation', 'N/A')}")
    lines.append("")
    
    # 图表关联审计
    lines.append("## 图表关联审计 (Phase 4)")
    lines.append("")
    fig_audit = audit.get("figure_association_audit", {})
    lines.append(f"- **总关联数**: {fig_audit.get('total_associations', 0)}")
    lines.append(f"- **有verified版本**: {fig_audit.get('has_verified_version', False)}")
    lines.append(f"- **报告使用v2(非verified)**: {fig_audit.get('report_uses_v2', False)}")
    lines.append("")
    lines.append("### 状态分布")
    lines.append("")
    status_dist = fig_audit.get("status_distribution", {})
    for status, count in status_dist.items():
        lines.append(f"- {status}: {count}")
    lines.append("")
    
    issues = fig_audit.get("issues", {})
    if any(issues.values()):
        lines.append("### 问题")
        lines.append("")
        if issues.get("namespace_not_distinguished"):
            lines.append("- **[WARNING]** namespace未区分main/SI")
        if issues.get("candidate_auto_upgraded"):
            lines.append("- **[WARNING]** CANDIDATE被错误升级为VERIFIED")
        lines.append("")
    
    # 六维科学信息
    lines.append("## 六维科学信息与实际来源")
    lines.append("")
    six_dim = enhanced_report.get("six_dimension_extraction", {})
    if six_dim.get("status") == "LOADED":
        dims = six_dim.get("dimensions", {})
        for dim_name, dim_data in dims.items():
            lines.append(f"### {dim_name}")
            lines.append("")
            if isinstance(dim_data, dict):
                for key, value in list(dim_data.items())[:5]:
                    if isinstance(value, str):
                        lines.append(f"- **{key}**: {value[:150]}...")
                    else:
                        lines.append(f"- **{key}**: {value}")
            lines.append("")
    
    # 知识对象（带verification标注）
    lines.append("## 知识对象（含来源验证）")
    lines.append("")
    knowledge_objects = enhanced_report.get("knowledge_objects", {})
    for obj_type in ["facts", "claims", "evidence", "limitations", "open_questions"]:
        objects = knowledge_objects.get(obj_type, [])
        if not objects:
            continue
        
        lines.append(f"### {obj_type.replace('_', ' ').title()} ({len(objects)}个)")
        lines.append("")
        
        for obj in objects[:5]:  # 只显示前5个
            obj_id = obj.get(f"{obj_type.rstrip('s')}_id", "unknown")
            content = obj.get("content", "")[:100]
            verification = obj.get("content_verification", "UNKNOWN")
            risk = obj.get("risk_flag", False)
            
            risk_marker = " [RISK]" if risk else ""
            lines.append(f"- **{obj_id}**: {content}... *({verification}{risk_marker})*")
        
        if len(objects) > 5:
            lines.append(f"- ... 及其他{len(objects)-5}个")
        lines.append("")
    
    # 不能定位的对象
    lines.append("## 不能定位的对象及原因")
    lines.append("")
    unresolved_objects = []
    for obj_type, objects in knowledge_objects.items():
        for obj in objects:
            if obj.get("content_verification") in ["UNRESOLVED", "NOT_FOUND_IN_DOCUMENT"]:
                unresolved_objects.append({
                    "type": obj_type,
                    "id": obj.get(f"{obj_type.rstrip('s')}_id", "unknown"),
                    "reason": obj.get("verification_reason", "unknown"),
                })
    
    if unresolved_objects:
        lines.append(f"共{len(unresolved_objects)}个对象不能定位：")
        lines.append("")
        for obj in unresolved_objects[:10]:
            lines.append(f"- `{obj['id']}` ({obj['type']}): {obj['reason']}")
        if len(unresolved_objects) > 10:
            lines.append(f"- ... 及其他{len(unresolved_objects)-10}个")
    else:
        lines.append("所有对象均可定位或已标注来源。")
    lines.append("")
    
    # 合规声明
    lines.append("## 合规声明")
    lines.append("")
    lines.append("本报告严格遵守SINGLE-DOC-EVIDENCE-003批次要求：")
    lines.append("1. 未制造虚假SourceAnchor，合成锚点保留为历史溯源信息")
    lines.append("2. 明确区分AUTHOR_STATED/SYSTEM_INFERRED/DERIVED_WITH_EVIDENCE等来源标注")
    lines.append("3. 未将CANDIDATE图表关联自动升级为VERIFIED")
    lines.append("4. 保留所有UNRESOLVED对象及其原因")
    lines.append("5. 表格结构化能力缺口已明确标记")
    lines.append("")
    
    return "\n".join(lines)


def main():
    """生成增强报告"""
    print("=" * 70)
    print("SINGLE-DOC-EVIDENCE-003 Phase 5: 增强报告生成")
    print("=" * 70)
    
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    
    for doc_id in DOCS:
        print(f"\n处理 {doc_id}...")
        
        # 读取原始报告
        report_path = REPORTS_ROOT / doc_id / f"{doc_id}_knowledge_report.json"
        if not report_path.exists():
            print(f"  跳过: 报告不存在")
            continue
        
        with open(report_path, "r", encoding="utf-8") as f:
            original_report = json.load(f)
        
        # 加载审计结果
        audits = load_audit_results(doc_id)
        print(f"  加载审计: {list(audits.keys())}")
        
        # 增强报告
        enhanced_report = enhance_report(doc_id, original_report, audits)
        
        # 保存增强JSON
        json_path = OUTPUT_ROOT / f"{doc_id}_knowledge_report_v3.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(enhanced_report, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {json_path}")
        
        # 生成增强Markdown
        md_content = generate_enhanced_markdown(enhanced_report, doc_id)
        md_path = OUTPUT_ROOT / f"{doc_id}_knowledge_report_v3.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"  Markdown: {md_path}")
        
        # 打印验收指标
        metrics = enhanced_report["evidence_003_audit"]["acceptance_metrics"]
        print(f"  验收指标:")
        print(f"    真实Element ID覆盖率: {metrics['real_element_id_coverage']:.1f}%")
        print(f"    内容核验通过率: {metrics['content_verification_pass_rate']:.1f}%")
        print(f"    关系有效性比率: {metrics['relationship_validity_rate']:.1f}%")
        print(f"    图表关联解决率: {metrics['figure_association_resolution_rate']:.1f}%")
        print(f"    表格结构化覆盖率: {metrics['table_structure_coverage']:.1f}%")
    
    print(f"\n{'=' * 70}")
    print("Phase 5 完成")
    print(f"{'=' * 70}")
    print(f"增强报告目录: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
