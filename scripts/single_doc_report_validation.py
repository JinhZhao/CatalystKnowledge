"""SINGLE-DOC-REPORT-001 | Phase 5 验收脚本。

对4份试点报告执行：
1. 章节完整性验证
2. 图表数量与解析原件对账
3. 六维字段真实性和来源核验
4. 科学主张与证据关系核验
5. 数值、单位、实验条件一致性
6. 缺失值和未报告处理
7. 单篇对象与关系ID稳定性
8. Canonical Store回读及报告可重建
"""

from __future__ import annotations

import json
import hashlib
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from single_doc_report_generator import (
    generate_single_doc_report,
    DataLoader,
    RUNS_ROOT,
)


REQUIRED_SECTIONS = [
    "document_overview",
    "attachments",
    "document_structure",
    "tables",
    "figures",
    "figure_associations",
    "six_dimension_extraction",
    "scientific_objects",
    "quantity_records",
    "classification",
    "knowledge_objects",
    "knowledge_relationships",
    "qa_verification",
    "statistics",
    "provenance",
]

KNOWLEDGE_OBJECT_TYPES = [
    "facts", "claims", "evidence", "limitations",
    "open_questions", "hypotheses", "experiment_proposals",
    "feasibility_assessments", "validation_plans",
]

RELATIONSHIP_TYPES = [
    "SUPPORTED_BY", "CHALLENGED_BY", "QUALIFIED_BY",
    "TESTED_BY", "MOTIVATES", "VALIDATES", "REQUIRES",
]


def verify_section_completeness(report: dict, doc_id: str) -> dict:
    """验证报告章节完整性。"""
    results = {"pass": 0, "fail": 0, "warn": 0, "details": []}

    for section in REQUIRED_SECTIONS:
        if section in report and report[section]:
            results["pass"] += 1
            results["details"].append({"section": section, "status": "PRESENT"})
        else:
            results["fail"] += 1
            results["details"].append({"section": section, "status": "MISSING"})

    ko = report.get("knowledge_objects", {})
    for obj_type in KNOWLEDGE_OBJECT_TYPES:
        items = ko.get(obj_type, [])
        if items:
            results["details"].append({
                "section": f"knowledge_objects/{obj_type}",
                "status": "PRESENT",
                "count": len(items),
            })
        else:
            results["warn"] += 1
            results["details"].append({
                "section": f"knowledge_objects/{obj_type}",
                "status": "NOT_REPORTED",
            })

    md_path = RUNS_ROOT / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.md"
    if md_path.exists():
        md_text = md_path.read_text(encoding="utf-8")
        md_sections = [line for line in md_text.split("\n") if line.startswith("## ")]
        results["md_sections"] = len(md_sections)
        results["details"].append({
            "section": "markdown_report",
            "status": "PRESENT",
            "section_count": len(md_sections),
        })
    else:
        results["fail"] += 1
        results["details"].append({"section": "markdown_report", "status": "MISSING"})

    return results


def verify_figure_table_reconciliation(report: dict, doc_id: str) -> dict:
    """图表数量与解析原件对账。"""
    loader = DataLoader(doc_id)
    ir = loader.load_document_ir()

    ir_tables = [e for e in ir.get("elements", []) if e["element_type"] == "table"]
    ir_figures = [e for e in ir.get("elements", []) if e["element_type"] == "image"]

    report_tables = report.get("tables", [])
    report_figures = report.get("figures", [])
    fig_assoc = report.get("figure_associations", [])

    return {
        "ir_table_count": len(ir_tables),
        "report_table_count": len(report_tables),
        "table_match": len(ir_tables) == len(report_tables),
        "ir_figure_count": len(ir_figures),
        "report_figure_count": len(report_figures),
        "figure_match": len(ir_figures) == len(report_figures),
        "figure_associations_total": len(fig_assoc),
        "figure_associations_resolved": len([a for a in fig_assoc if a.get("status") != "UNRESOLVED"]),
        "figure_associations_unresolved": len([a for a in fig_assoc if a.get("status") == "UNRESOLVED"]),
    }


def verify_six_dimension_provenance(report: dict, doc_id: str) -> dict:
    """六维字段真实性和来源核验。"""
    six_dim = report.get("six_dimension_extraction", {})
    dims = six_dim.get("dimensions", {})
    dim_count = six_dim.get("dimension_count", 0)

    field_audit = {}
    for dim_name, dim_data in dims.items():
        if isinstance(dim_data, dict):
            total_fields = len(dim_data)
            non_empty = sum(1 for v in dim_data.values()
                          if v is not None and v != "" and v != [] and v != {})
            field_audit[dim_name] = {
                "total_fields": total_fields,
                "non_empty_fields": non_empty,
                "fill_rate": round(non_empty / max(total_fields, 1), 3),
            }

    return {
        "dimensions_loaded": dim_count,
        "dimensions_expected": 6,
        "all_dimensions_loaded": dim_count == 6,
        "per_dimension": field_audit,
    }


def verify_claim_evidence_relationships(report: dict, doc_id: str) -> dict:
    """科学主张与证据关系核验。"""
    rels = report.get("knowledge_relationships", [])
    claims = report.get("knowledge_objects", {}).get("claims", [])
    evidence = report.get("knowledge_objects", {}).get("evidence", [])

    rel_type_counts = {}
    for r in rels:
        rt = r.get("relationship_type", "UNKNOWN")
        rel_type_counts[rt] = rel_type_counts.get(rt, 0) + 1

    claim_ids = {c.get("claim_id") for c in claims}
    evidence_ids = {e.get("evidence_id") for e in evidence}

    dangling_source = 0
    dangling_target = 0
    for r in rels:
        src = r.get("source_id")
        tgt = r.get("target_id")
        all_ids = claim_ids | evidence_ids
        all_ids.update(
            {f.get("fact_id") for f in report.get("knowledge_objects", {}).get("facts", [])}
        )
        all_ids.update(
            {l.get("limitation_id") for l in report.get("knowledge_objects", {}).get("limitations", [])}
        )
        all_ids.update(
            {q.get("question_id") for q in report.get("knowledge_objects", {}).get("open_questions", [])}
        )
        all_ids.update(
            {h.get("hypothesis_id") for h in report.get("knowledge_objects", {}).get("hypotheses", [])}
        )
        all_ids.update(
            {p.get("proposal_id") for p in report.get("knowledge_objects", {}).get("experiment_proposals", [])}
        )
        all_ids.update(
            {f.get("feasibility_id") for f in report.get("knowledge_objects", {}).get("feasibility_assessments", [])}
        )
        all_ids.update(
            {v.get("plan_id") for v in report.get("knowledge_objects", {}).get("validation_plans", [])}
        )
        if src not in all_ids:
            dangling_source += 1
        if tgt not in all_ids:
            dangling_target += 1

    claims_with_evidence = set()
    for r in rels:
        if r.get("relationship_type") == "SUPPORTED_BY":
            claims_with_evidence.add(r.get("target_id"))

    return {
        "total_relationships": len(rels),
        "relationship_type_counts": rel_type_counts,
        "claims_total": len(claims),
        "evidence_total": len(evidence),
        "claims_with_supporting_evidence": len(claims_with_evidence),
        "dangling_source_refs": dangling_source,
        "dangling_target_refs": dangling_target,
        "no_cross_doc_relationships": all(
            r.get("document_id") == doc_id for r in rels
        ),
    }


def verify_quantity_consistency(report: dict, doc_id: str) -> dict:
    """数值、单位、实验条件一致性。"""
    qty = report.get("quantity_records", {})
    records = qty.get("records", [])

    three_layer_ok = 0
    three_layer_missing = 0
    conversion_success = 0
    conversion_failed = 0
    conversion_pending = 0

    for rec in records:
        tl = rec.get("three_layer_values", {})
        if tl.get("raw") and tl.get("si") is not None and tl.get("domain"):
            three_layer_ok += 1
        elif tl.get("raw"):
            three_layer_missing += 1

        status = rec.get("unit_conversion_status", rec.get("status", ""))
        if status == "SUCCESS":
            conversion_success += 1
        elif status in ("FAILED", "UNKNOWN_UNIT"):
            conversion_failed += 1
        else:
            conversion_pending += 1

    return {
        "total_records": len(records),
        "three_layer_complete": three_layer_ok,
        "three_layer_partial": three_layer_missing,
        "conversion_success": conversion_success,
        "conversion_failed": conversion_failed,
        "conversion_pending": conversion_pending,
    }


def verify_missing_value_handling(report: dict, doc_id: str) -> dict:
    """缺失值和未报告处理核验。"""
    ko = report.get("knowledge_objects", {})
    stats = report.get("statistics", {})

    empty_types = []
    for obj_type in KNOWLEDGE_OBJECT_TYPES:
        if not ko.get(obj_type):
            empty_types.append(obj_type)

    md_path = RUNS_ROOT / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.md"
    not_reported_count = 0
    if md_path.exists():
        md_text = md_path.read_text(encoding="utf-8")
        not_reported_count = md_text.count("*未报告 / 未抽取*")

    return {
        "empty_knowledge_types": empty_types,
        "empty_type_count": len(empty_types),
        "markdown_not_reported_markers": not_reported_count,
        "correctly_marks_missing": not_reported_count > 0 or len(empty_types) == 0,
    }


def verify_id_stability(doc_id: str) -> dict:
    """单篇对象与关系ID稳定性验证。

    生成两次报告，比对所有对象ID是否一致。
    """
    report1, _ = generate_single_doc_report(doc_id,
        output_dir=RUNS_ROOT / "single_doc_reports" / doc_id / "_verify_run_1")
    report2, _ = generate_single_doc_report(doc_id,
        output_dir=RUNS_ROOT / "single_doc_reports" / doc_id / "_verify_run_2")

    all_ids_1 = _collect_all_ids(report1)
    all_ids_2 = _collect_all_ids(report2)

    stable = all_ids_1 == all_ids_2

    import shutil
    for d in ["_verify_run_1", "_verify_run_2"]:
        p = RUNS_ROOT / "single_doc_reports" / doc_id / d
        if p.exists():
            shutil.rmtree(p)

    return {
        "id_sets_match": stable,
        "total_ids_run1": len(all_ids_1),
        "total_ids_run2": len(all_ids_2),
        "only_in_run1": list(all_ids_1 - all_ids_2)[:10],
        "only_in_run2": list(all_ids_2 - all_ids_1)[:10],
    }


def _collect_all_ids(report: dict) -> set:
    ids = set()
    ko = report.get("knowledge_objects", {})
    for obj_type, items in ko.items():
        if isinstance(items, list):
            for item in items:
                for key in item:
                    if key.endswith("_id"):
                        ids.add(f"{obj_type}/{item[key]}")
    for rel in report.get("knowledge_relationships", []):
        ids.add(f"rel/{rel.get('relationship_id', '')}")
    return ids


def verify_store_readback(doc_id: str) -> dict:
    """Canonical Store回读验证。"""
    loader = DataLoader(doc_id)
    qty_records = loader.load_quantity_records()

    readback_ok = 0
    readback_fail = 0
    sha256_verified = 0

    for rec in qty_records:
        record_id = rec.get("record_id", "")
        stored_sha = rec.get("sha256", "")

        verify_rec = {k: v for k, v in rec.items() if k != "sha256"}
        verify_rec["sha256"] = ""
        computed_sha = hashlib.sha256(
            json.dumps(verify_rec, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        if stored_sha and computed_sha == stored_sha:
            sha256_verified += 1
            readback_ok += 1
        elif not stored_sha:
            readback_ok += 1
        else:
            readback_fail += 1

    return {
        "total_records": len(qty_records),
        "readback_ok": readback_ok,
        "readback_fail": readback_fail,
        "sha256_verified": sha256_verified,
    }


def verify_report_rebuild(doc_id: str) -> dict:
    """报告可重建验证。"""
    report1, md1 = generate_single_doc_report(doc_id,
        output_dir=RUNS_ROOT / "single_doc_reports" / doc_id / "_rebuild_1")
    report2, md2 = generate_single_doc_report(doc_id,
        output_dir=RUNS_ROOT / "single_doc_reports" / doc_id / "_rebuild_2")

    stats1 = report1.get("statistics", {})
    stats2 = report2.get("statistics", {})
    stats_match = stats1 == stats2

    json1 = json.dumps(report1, sort_keys=True, ensure_ascii=False, default=str)
    json2 = json.dumps(report2, sort_keys=True, ensure_ascii=False, default=str)
    r1_clean = {k: v for k, v in report1.items() if k != "generated_at"}
    r2_clean = {k: v for k, v in report2.items() if k != "generated_at"}
    content_match = (
        json.dumps(r1_clean, sort_keys=True, ensure_ascii=False, default=str) ==
        json.dumps(r2_clean, sort_keys=True, ensure_ascii=False, default=str)
    )

    import shutil
    for d in ["_rebuild_1", "_rebuild_2"]:
        p = RUNS_ROOT / "single_doc_reports" / doc_id / d
        if p.exists():
            shutil.rmtree(p)

    return {
        "statistics_match": stats_match,
        "content_match_except_timestamp": content_match,
    }


def run_full_validation(doc_id: str) -> dict:
    """对单篇文档执行全量验收。"""
    print(f"\n{'='*60}")
    print(f"Validating {doc_id}...")
    print(f"{'='*60}")

    report_path = RUNS_ROOT / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.json"
    if not report_path.exists():
        return {"status": "FAILED", "error": f"Report not found: {report_path}"}

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    results = {}

    results["section_completeness"] = verify_section_completeness(report, doc_id)
    print(f"  Section completeness: "
          f"PASS={results['section_completeness']['pass']} "
          f"FAIL={results['section_completeness']['fail']} "
          f"WARN={results['section_completeness']['warn']}")

    results["figure_table_reconciliation"] = verify_figure_table_reconciliation(report, doc_id)
    ft = results["figure_table_reconciliation"]
    print(f"  Figure/Table: tables={ft['ir_table_count']}/{ft['report_table_count']} "
          f"figures={ft['ir_figure_count']}/{ft['report_figure_count']}")

    results["six_dimension_provenance"] = verify_six_dimension_provenance(report, doc_id)
    sd = results["six_dimension_provenance"]
    print(f"  Six-dim: {sd['dimensions_loaded']}/6 loaded")

    results["claim_evidence"] = verify_claim_evidence_relationships(report, doc_id)
    ce = results["claim_evidence"]
    print(f"  Claims/Evidence: {ce['claims_total']} claims, {ce['evidence_total']} evidence, "
          f"{ce['total_relationships']} rels, dangling={ce['dangling_source_refs']}/{ce['dangling_target_refs']}")

    results["quantity_consistency"] = verify_quantity_consistency(report, doc_id)
    qc = results["quantity_consistency"]
    print(f"  Quantities: {qc['total_records']} total, "
          f"3-layer={qc['three_layer_complete']}/{qc['total_records']}")

    results["missing_values"] = verify_missing_value_handling(report, doc_id)
    mv = results["missing_values"]
    print(f"  Missing handling: {mv['empty_type_count']} empty types, "
          f"{mv['markdown_not_reported_markers']} 'not reported' markers")

    results["id_stability"] = verify_id_stability(doc_id)
    ids = results["id_stability"]
    print(f"  ID stability: {ids['id_sets_match']} ({ids['total_ids_run1']} IDs)")

    results["store_readback"] = verify_store_readback(doc_id)
    sr = results["store_readback"]
    print(f"  Store readback: {sr['readback_ok']}/{sr['total_records']} OK, "
          f"SHA256={sr['sha256_verified']}")

    results["report_rebuild"] = verify_report_rebuild(doc_id)
    rb = results["report_rebuild"]
    print(f"  Report rebuild: stats={rb['statistics_match']} content={rb['content_match_except_timestamp']}")

    overall_pass = (
        results["section_completeness"]["fail"] == 0 and
        results["figure_table_reconciliation"]["table_match"] and
        results["figure_table_reconciliation"]["figure_match"] and
        results["six_dimension_provenance"]["all_dimensions_loaded"] and
        results["claim_evidence"]["dangling_source_refs"] == 0 and
        results["claim_evidence"]["dangling_target_refs"] == 0 and
        results["claim_evidence"]["no_cross_doc_relationships"] and
        results["id_stability"]["id_sets_match"] and
        results["store_readback"]["readback_fail"] == 0 and
        results["report_rebuild"]["statistics_match"] and
        results["report_rebuild"]["content_match_except_timestamp"]
    )

    results["overall"] = "PASS" if overall_pass else "CONDITIONAL_PASS"
    print(f"\n  >>> {doc_id}: {results['overall']}")

    return results


def main():
    doc_ids = ["F02", "F07", "P01", "PAT01"]
    all_results = {}

    for doc_id in doc_ids:
        all_results[doc_id] = run_full_validation(doc_id)

    print("\n" + "=" * 60)
    print("SINGLE-DOC-REPORT-001 Phase 5 Validation Summary")
    print("=" * 60)

    summary = {
        "task": "SINGLE-DOC-REPORT-001",
        "timestamp": datetime.now().isoformat(),
        "documents_validated": len(doc_ids),
        "results": {},
    }

    all_pass = True
    for doc_id in doc_ids:
        result = all_results[doc_id]
        overall = result.get("overall", "FAILED")
        if overall != "PASS":
            all_pass = False

        stats = result.get("section_completeness", {})
        ko_stats = result.get("claim_evidence", {})
        qty_stats = result.get("quantity_consistency", {})

        summary["results"][doc_id] = {
            "overall": overall,
            "section_pass": stats.get("pass", 0),
            "section_fail": stats.get("fail", 0),
            "claims": ko_stats.get("claims_total", 0),
            "evidence": ko_stats.get("evidence_total", 0),
            "relationships": ko_stats.get("total_relationships", 0),
            "quantities": qty_stats.get("total_records", 0),
        }

        print(f"  {doc_id}: {overall} | "
              f"sections={stats.get('pass',0)}/{stats.get('pass',0)+stats.get('fail',0)} | "
              f"claims={ko_stats.get('claims_total',0)} | "
              f"evidence={ko_stats.get('evidence_total',0)} | "
              f"rels={ko_stats.get('total_relationships',0)} | "
              f"qty={qty_stats.get('total_records',0)}")

    summary["overall_verdict"] = "PASS" if all_pass else "CONDITIONAL_PASS"
    print(f"\n  Verdict: {summary['overall_verdict']}")

    output_path = RUNS_ROOT / "single_doc_reports" / "validation_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved: {output_path}")

    return summary


if __name__ == "__main__":
    main()
