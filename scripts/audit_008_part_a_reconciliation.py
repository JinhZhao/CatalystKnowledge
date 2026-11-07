"""
SINGLE-DOC-AUDIT-UI-008 Part A: 专项对账
回答7个关键差异问题
"""
import json
import os
from pathlib import Path
from collections import defaultdict

BASE = Path("D:/Knowledge_World")
OUTPUT_DIR = BASE / "runs" / "audit_008"


def safe_json_load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e)}


reconciliation = {
    "audit_batch": "SINGLE-DOC-AUDIT-UI-008-PartA-Reconciliation",
    "questions": {}
}

# ============================================================
# Q1: 27份初始材料+1份P01主论文的资源口径
# ============================================================
manifest = safe_json_load(BASE / "data/test_corpus/unified_test_manifest.json")
q1 = {
    "manifest_total": len(manifest.get("documents", [])) if manifest else 0,
    "manifest_summary": manifest.get("summary", {}) if manifest else {},
    "by_group": defaultdict(list),
    "p01_main_link01": None,
    "discrepancies": []
}

for doc in manifest.get("documents", []):
    q1["by_group"][doc.get("group", "unknown")].append({
        "id": doc["document_id"],
        "type": doc["document_type"],
        "size_kb": round(doc["file_size_bytes"] / 1024, 1),
        "sig_valid": doc.get("signature_valid")
    })

# P01主论文在link01_pair
link01_pdf = BASE / "data/test_corpus/link01_pair/P01_main.pdf"
q1["p01_main_link01"] = {
    "exists": link01_pdf.exists(),
    "size_kb": round(link01_pdf.stat().st_size / 1024, 1) if link01_pdf.exists() else 0
}

# 检查：manifest中27份 vs 实际唯一PDF
unique_pdfs = set()
for doc in manifest.get("documents", []):
    if doc["document_type"] in ("research_article", "supplementary_pdf", "patent"):
        unique_pdfs.add(doc["document_id"])

q1["unique_pdf_count"] = len(unique_pdfs)
q1["unique_pdf_ids"] = sorted(unique_pdfs)
q1["non_pdf_items"] = [
    doc["document_id"] for doc in manifest.get("documents", [])
    if doc["document_type"] not in ("research_article", "supplementary_pdf", "patent")
]

reconciliation["questions"]["Q1_resource_inventory"] = q1

# ============================================================
# Q2: 25份唯一PDF解析状态
# ============================================================
q2 = {"parsed_pdfs": [], "unparsed_pdfs": [], "multi_version_pdfs": []}

mineru_base = BASE / "data/test_corpus/mineru_output"
parsed_docs = set()
for batch_dir in sorted(mineru_base.iterdir()):
    if not batch_dir.is_dir():
        continue
    md_files = list(batch_dir.rglob("*.md"))
    if md_files:
        doc_id = batch_dir.name.split("_")[0]
        parsed_docs.add(doc_id)
        q2["parsed_pdfs"].append({
            "batch": batch_dir.name,
            "doc_id": doc_id,
            "md_count": len(md_files),
            "md_size_kb": round(md_files[0].stat().st_size / 1024, 1)
        })

# 检查25份唯一PDF是否全部解析
all_expected = set()
for doc in manifest.get("documents", []):
    if doc["document_type"] in ("research_article", "supplementary_pdf", "patent"):
        all_expected.add(doc["document_id"])
all_expected.add("P01_main")  # LINK-001

unparsed = all_expected - parsed_docs
q2["expected_count"] = len(all_expected)
q2["parsed_count"] = len(parsed_docs)
q2["unparsed"] = sorted(unparsed)

reconciliation["questions"]["Q2_pdf_parse_status"] = q2

# ============================================================
# Q3: 38个Experiment与最终4个Experiment的对象层级差异
# ============================================================
q3 = {
    "description": "对比不同阶段的Experiment对象统计口径",
    "stages": {}
}

# 从4份最终报告中提取Experiment
for doc_id in ["F02", "F07", "P01", "PAT01"]:
    report = safe_json_load(BASE / f"runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json")
    if report and "_error" not in report:
        ko = report.get("knowledge_objects", {})
        experiments = ko.get("experiments", [])
        observations = ko.get("observations", [])
        quantity_records = ko.get("quantity_records", [])

        q3["stages"][f"final_report_{doc_id}"] = {
            "experiment_count": len(experiments),
            "observation_count": len(observations),
            "quantity_record_count": len(quantity_records),
            "experiment_ids": [e.get("experiment_id", "?") for e in experiments],
            "experiment_details": [
                {
                    "id": e.get("experiment_id"),
                    "catalyst": e.get("catalyst_sample_id"),
                    "reaction": e.get("reaction_id"),
                    "has_observation": e.get("observation_id") is not None,
                    "quantity_count": len(e.get("quantity_records", []))
                }
                for e in experiments
            ]
        }

# 从V11-007审计中提取
v11_exp = safe_json_load(BASE / "runs/v11_007/part_b_experiment_chain_audit.json")
if v11_exp and "_error" not in v11_exp:
    q3["stages"]["v11_007_audit"] = {
        "total_experiments": v11_exp.get("summary", {}).get("total_experiments"),
        "complete_chains": v11_exp.get("summary", {}).get("complete_chains"),
        "partial_chains": v11_exp.get("summary", {}).get("partial_chains"),
    }

# 从V11-007-R1审计中
r1_exp = safe_json_load(BASE / "runs/v11_007_r1/part_d_experiment_chain_audit.json")
if r1_exp and "_error" not in r1_exp:
    q3["stages"]["v11_007_r1_audit"] = {
        "total_experiments": r1_exp.get("summary", {}).get("total_experiments"),
        "experiment_details": r1_exp.get("experiments", [])
    }

# 从FINAL-006审计中
final_exp = safe_json_load(BASE / "runs/final_006/part_a_experiment_integration.json")
if final_exp and "_error" not in final_exp:
    q3["stages"]["final_006_audit"] = {
        "summary": final_exp.get("summary", {}),
    }

reconciliation["questions"]["Q3_experiment_hierarchy"] = q3

# ============================================================
# Q4: 43个SOURCE_LINKED与3个真实Element ID的差异
# ============================================================
q4 = {
    "description": "对比不同验证阶段的SourceAnchor统计口径",
    "stages": {}
}

# evidence_004的统计
ev004 = safe_json_load(BASE / "runs/evidence_004/part_b_evidence_alignment.json")
if ev004 and "_error" not in ev004:
    status_counts = defaultdict(int)
    for doc_id in ["F02", "F07", "P01", "PAT01"]:
        doc_data = ev004.get(doc_id, {})
        for align in doc_data.get("alignments", []):
            status_counts[align.get("source_status", "UNKNOWN")] += 1
    q4["stages"]["evidence_004"] = {
        "status_distribution": dict(status_counts),
        "total_objects": sum(status_counts.values())
    }

# v11_007_r1的统计
r1_anchor = safe_json_load(BASE / "runs/v11_007_r1/part_c_source_anchor_audit.json")
if r1_anchor and "_error" not in r1_anchor:
    q4["stages"]["v11_007_r1"] = {
        "summary": r1_anchor.get("summary", {}),
        "anchor_categories": r1_anchor.get("anchor_categories", {})
    }

# evidence_003的统计
ev003_summary = safe_json_load(BASE / "runs/evidence_003/phase1_audit_summary.json")
if ev003_summary and "_error" not in ev003_summary:
    q4["stages"]["evidence_003"] = {
        "summary": ev003_summary.get("summary", {})
    }

reconciliation["questions"]["Q4_source_anchor_discrepancy"] = q4

# ============================================================
# Q5: 61条关系与不同验证阶段的统计口径
# ============================================================
q5 = {
    "description": "追踪61条关系在不同验证阶段的状态变化",
    "stages": {}
}

# V11-007 Part A审计
v11_audit = safe_json_load(BASE / "runs/v11_007/part_a_relationship_audit.json")
if v11_audit and "_error" not in v11_audit:
    summary = v11_audit.get("summary", {})
    q5["stages"]["v11_007_part_a"] = {
        "total": summary.get("total_relationships"),
        "valid_structure": summary.get("total_valid"),
        "missing_source": summary.get("total_missing_source"),
        "missing_target": summary.get("total_missing_target"),
        "type_mismatch": summary.get("total_type_mismatch"),
        "dangling": summary.get("total_dangling")
    }

# V11-007-R1 Part B语义复核
r1_sem = safe_json_load(BASE / "runs/v11_007_r1/part_b_relationship_semantics.json")
if r1_sem and "_error" not in r1_sem:
    q5["stages"]["v11_007_r1_part_b"] = {
        "total": r1_sem.get("summary", {}).get("total"),
        "structure_valid": r1_sem.get("summary", {}).get("structure_valid"),
        "semantic_valid": r1_sem.get("summary", {}).get("semantic_valid"),
        "predicate_distribution": r1_sem.get("summary", {}).get("predicate_distribution", {})
    }

# evidence_004关系验证
ev004_rel = safe_json_load(BASE / "runs/evidence_004/part_a_relationship_validation.json")
if ev004_rel and "_error" not in ev004_rel:
    q5["stages"]["evidence_004"] = {
        "summary": ev004_rel.get("summary", {})
    }

# 最终报告中的关系统计
for doc_id in ["F02", "F07", "P01", "PAT01"]:
    report = safe_json_load(BASE / f"runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json")
    if report and "_error" not in report:
        rels = report.get("relationships", [])
        type_dist = defaultdict(int)
        for r in rels:
            type_dist[r.get("relationship_type", "?")] += 1
        q5["stages"][f"report_{doc_id}"] = {
            "total": len(rels),
            "type_distribution": dict(type_dist)
        }

reconciliation["questions"]["Q5_relationship_statistics"] = q5

# ============================================================
# Q6: Canonical Store中的对象与最终报告是否一致
# ============================================================
q6 = {
    "description": "对比Canonical Store与最终报告的知识对象一致性",
    "comparisons": {}
}

cs_dir = BASE / "data/test_corpus/canonical_store"
store_index = safe_json_load(cs_dir / "store_index.json")

# 从canonical store的extractions中读取
for doc_id in ["F02", "F07", "P01", "PAT01"]:
    # 找对应的store文件
    store_file = None
    for f in (cs_dir / "extractions").iterdir():
        if doc_id.lower() in f.name.lower() and "backup" not in f.name and f.suffix == ".json":
            store_file = f
            break

    report_file = BASE / f"runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json"

    if store_file and store_file.exists():
        store_data = safe_json_load(store_file)
        report_data = safe_json_load(report_file)

        store_ko = store_data.get("knowledge_objects", {}) if store_data else {}
        report_ko = report_data.get("knowledge_objects", {}) if report_data else {}

        store_counts = {k: len(v) for k, v in store_ko.items()}
        report_counts = {k: len(v) for k, v in report_ko.items()}

        q6["comparisons"][doc_id] = {
            "store_file": str(store_file.relative_to(BASE)),
            "store_object_counts": store_counts,
            "report_object_count": report_counts,
            "store_total": sum(store_counts.values()),
            "report_total": sum(report_counts.values()),
            "match": store_counts == report_counts
        }
    else:
        q6["comparisons"][doc_id] = {
            "store_file": None,
            "note": "No canonical store file found"
        }

reconciliation["questions"]["Q6_store_vs_report_consistency"] = q6

# ============================================================
# Q7: F02/PAT01分类失败的实际状态
# ============================================================
q7 = {
    "description": "检查F02和PAT01的TAX-001分类实际状态",
    "classification_status": {}
}

g3_dir = BASE / "data/test_corpus/g3_output"
cls_summary = safe_json_load(g3_dir / "classification_summary.json")
cls_v2_summary = safe_json_load(g3_dir / "classification_v2_summary.json")

if cls_summary and "_error" not in cls_summary:
    q7["classification_summary_v1"] = cls_summary

if cls_v2_summary and "_error" not in cls_v2_summary:
    q7["classification_summary_v2"] = cls_v2_summary

for doc_id in ["F02", "F07", "P01", "PAT01"]:
    cls_file = g3_dir / doc_id / "classification.json"
    if cls_file.exists():
        cls_data = safe_json_load(cls_file)
        q7["classification_status"][doc_id] = {
            "file_exists": True,
            "status": cls_data.get("status") if cls_data else None,
            "confidence": cls_data.get("overall_confidence") if cls_data else None,
            "pending_review": cls_data.get("pending_review") if cls_data else None,
            "error": cls_data.get("_error") if cls_data else None
        }
    else:
        q7["classification_status"][doc_id] = {"file_exists": False}

reconciliation["questions"]["Q7_classification_failure_status"] = q7

# ============================================================
# 保存对账报告
# ============================================================
output_path = OUTPUT_DIR / "part_a_reconciliation.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(reconciliation, f, ensure_ascii=False, indent=2, default=str)

print(f"专项对账报告已生成: {output_path}")
print()

# 打印摘要
for q_name, q_data in reconciliation["questions"].items():
    print(f"=== {q_name} ===")
    if "description" in q_data:
        print(f"  {q_data['description']}")
    # 简要输出关键数字
    for k, v in q_data.items():
        if k == "description":
            continue
        if isinstance(v, (str, int, float, bool)):
            print(f"  {k}: {v}")
        elif isinstance(v, dict) and len(v) < 10:
            print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:200]}")
        elif isinstance(v, list):
            print(f"  {k}: [{len(v)} items]")
        elif isinstance(v, dict):
            print(f"  {k}: {{{len(v)} keys}}")
    print()
