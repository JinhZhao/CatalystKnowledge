#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINGLE-DOC-EVIDENCE-004 Part A: Claim-Evidence关系验证脚本

验证目标：
1. 关系方向正确性（claim→evidence for SUPPORTED_BY/CHALLENGED_BY）
2. ID存在性检查（无dangling references）
3. 关系分类：VALID_STRUCTURE/VALID_EVIDENCE/UNRESOLVED/INVALID/DANGLING
"""

import json
from pathlib import Path
from collections import defaultdict

RUNS_ROOT = Path(r"D:\Knowledge_World\runs")
REPORTS_DIR = RUNS_ROOT / "single_doc_reports"

def load_report(doc_id: str) -> dict:
    report_path = REPORTS_DIR / doc_id / f"{doc_id}_knowledge_report.json"
    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_relationships(doc_id: str, report: dict) -> dict:
    """验证单个文档的关系质量"""
    
    # 收集所有对象ID - knowledge_objects包含所有知识对象
    knowledge_objects = report.get("knowledge_objects", {})
    
    all_object_ids = set()
    claim_ids = set()
    evidence_ids = set()
    
    for claim in knowledge_objects.get("claims", []):
        cid = claim["claim_id"]
        claim_ids.add(cid)
        all_object_ids.add(cid)
    
    for ev in knowledge_objects.get("evidence", []):
        eid = ev["evidence_id"]
        evidence_ids.add(eid)
        all_object_ids.add(eid)
    
    for fact in knowledge_objects.get("facts", []):
        all_object_ids.add(fact["fact_id"])
    
    for lim in knowledge_objects.get("limitations", []):
        all_object_ids.add(lim["limitation_id"])
    
    for q in knowledge_objects.get("open_questions", []):
        all_object_ids.add(q["question_id"])
    
    for hyp in knowledge_objects.get("hypotheses", []):
        all_object_ids.add(hyp["hypothesis_id"])
    
    for exp in knowledge_objects.get("experiment_proposals", []):
        all_object_ids.add(exp["proposal_id"])
    
    for feas in knowledge_objects.get("feasibility_assessments", []):
        all_object_ids.add(feas["feasibility_id"])
    
    for vplan in knowledge_objects.get("validation_plans", []):
        all_object_ids.add(vplan["plan_id"])
    
    # 验证每条关系 - knowledge_relationships在顶层
    relationships = report.get("knowledge_relationships", [])
    validation_results = {
        "total": len(relationships),
        "VALID_STRUCTURE": [],
        "VALID_EVIDENCE": [],
        "UNRESOLVED": [],
        "INVALID": [],
        "DANGLING": [],
    }
    
    direction_errors = []
    
    for rel in relationships:
        rel_id = rel["relationship_id"]
        src_id = rel["source_id"]
        tgt_id = rel["target_id"]
        rel_type = rel["relationship_type"]
        
        # 检查ID是否存在
        if src_id not in all_object_ids:
            validation_results["DANGLING"].append({
                "rel_id": rel_id,
                "reason": f"source_id {src_id} not found",
                "rel": rel
            })
            continue
        
        if tgt_id not in all_object_ids:
            validation_results["DANGLING"].append({
                "rel_id": rel_id,
                "reason": f"target_id {tgt_id} not found",
                "rel": rel
            })
            continue
        
        # 检查关系方向语义
        if rel_type in ("SUPPORTED_BY", "CHALLENGED_BY", "QUALIFIED_BY", "TESTED_BY", "VALIDATES", "REQUIRES"):
            # 这些关系应该是 claim → evidence/limitation/experiment/validation/fact
            # 即 source 应该是 claim，target 应该是支持对象
            
            if rel_type in ("SUPPORTED_BY", "CHALLENGED_BY"):
                # 必须是 claim → evidence
                if src_id not in claim_ids:
                    direction_errors.append({
                        "rel_id": rel_id,
                        "rel_type": rel_type,
                        "src_id": src_id,
                        "tgt_id": tgt_id,
                        "reason": f"source should be claim, got {src_id}"
                    })
                    validation_results["INVALID"].append({
                        "rel_id": rel_id,
                        "reason": "direction error: source not claim",
                        "rel": rel
                    })
                    continue
                
                if tgt_id not in evidence_ids:
                    direction_errors.append({
                        "rel_id": rel_id,
                        "rel_type": rel_type,
                        "src_id": src_id,
                        "tgt_id": tgt_id,
                        "reason": f"target should be evidence, got {tgt_id}"
                    })
                    validation_results["INVALID"].append({
                        "rel_id": rel_id,
                        "reason": "direction error: target not evidence",
                        "rel": rel
                    })
                    continue
                
                # 方向正确，检查证据内容是否真实
                ev_obj = next((e for e in knowledge_objects.get("evidence", []) if e["evidence_id"] == tgt_id), None)
                if ev_obj:
                    provenance = ev_obj.get("provenance_label", "")
                    if provenance in ("EXTRACTED", "EVIDENCE_VERIFIED"):
                        validation_results["VALID_EVIDENCE"].append({
                            "rel_id": rel_id,
                            "reason": f"claim→evidence, provenance={provenance}",
                            "rel": rel
                        })
                    elif provenance == "DERIVED":
                        validation_results["VALID_STRUCTURE"].append({
                            "rel_id": rel_id,
                            "reason": f"claim→evidence, provenance=DERIVED (structure valid)",
                            "rel": rel
                        })
                    else:
                        validation_results["UNRESOLVED"].append({
                            "rel_id": rel_id,
                            "reason": f"claim→evidence, provenance={provenance}",
                            "rel": rel
                        })
            
            elif rel_type == "QUALIFIED_BY":
                # claim → limitation
                if src_id in claim_ids and tgt_id in [lim["limitation_id"] for lim in knowledge_objects.get("limitations", [])]:
                    validation_results["VALID_STRUCTURE"].append({
                        "rel_id": rel_id,
                        "reason": "claim→limitation direction correct",
                        "rel": rel
                    })
                else:
                    validation_results["UNRESOLVED"].append({
                        "rel_id": rel_id,
                        "reason": "QUALIFIED_BY but target not limitation",
                        "rel": rel
                    })
            
            elif rel_type == "TESTED_BY":
                # claim → experiment
                if src_id in claim_ids and tgt_id in [exp["proposal_id"] for exp in knowledge_objects.get("experiment_proposals", [])]:
                    validation_results["VALID_STRUCTURE"].append({
                        "rel_id": rel_id,
                        "reason": "claim→experiment direction correct",
                        "rel": rel
                    })
                else:
                    validation_results["UNRESOLVED"].append({
                        "rel_id": rel_id,
                        "reason": "TESTED_BY but target not experiment",
                        "rel": rel
                    })
            
            elif rel_type == "VALIDATES":
                # Two valid patterns:
                # 1. claim → validation_plan (passive: claim is validated by plan)
                # 2. feasibility → hypothesis (active: feasibility validates hypothesis)
                if src_id in claim_ids and tgt_id in [vp["plan_id"] for vp in knowledge_objects.get("validation_plans", [])]:
                    validation_results["VALID_STRUCTURE"].append({
                        "rel_id": rel_id,
                        "reason": "claim→validation_plan direction correct",
                        "rel": rel
                    })
                elif src_id in [feas["feasibility_id"] for feas in knowledge_objects.get("feasibility_assessments", [])] and tgt_id in [hyp["hypothesis_id"] for hyp in knowledge_objects.get("hypotheses", [])]:
                    validation_results["VALID_STRUCTURE"].append({
                        "rel_id": rel_id,
                        "reason": "feasibility→hypothesis direction correct (active validation)",
                        "rel": rel
                    })
                else:
                    validation_results["UNRESOLVED"].append({
                        "rel_id": rel_id,
                        "reason": "VALIDATES but unexpected source/target type",
                        "rel": rel
                    })
            
            elif rel_type == "REQUIRES":
                # claim → fact
                if src_id in claim_ids and tgt_id in [fact["fact_id"] for fact in knowledge_objects.get("facts", [])]:
                    validation_results["VALID_STRUCTURE"].append({
                        "rel_id": rel_id,
                        "reason": "claim→fact direction correct",
                        "rel": rel
                    })
                else:
                    validation_results["UNRESOLVED"].append({
                        "rel_id": rel_id,
                        "reason": "REQUIRES but target not fact",
                        "rel": rel
                    })
        
        elif rel_type == "MOTIVATES":
            # question → hypothesis
            if src_id in [q["question_id"] for q in knowledge_objects.get("open_questions", [])] and tgt_id in [hyp["hypothesis_id"] for hyp in knowledge_objects.get("hypotheses", [])]:
                validation_results["VALID_STRUCTURE"].append({
                    "rel_id": rel_id,
                    "reason": "question→hypothesis direction correct",
                    "rel": rel
                })
            else:
                validation_results["UNRESOLVED"].append({
                    "rel_id": rel_id,
                    "reason": "MOTIVATES but unexpected source/target type",
                    "rel": rel
                })
        
        else:
            validation_results["UNRESOLVED"].append({
                "rel_id": rel_id,
                "reason": f"unknown relationship type {rel_type}",
                "rel": rel
            })
    
    return {
        "validation_results": validation_results,
        "direction_errors": direction_errors,
        "claim_count": len(claim_ids),
        "evidence_count": len(evidence_ids),
    }

def main():
    doc_ids = ["F02", "F07", "P01", "PAT01"]
    
    print("=" * 80)
    print("SINGLE-DOC-EVIDENCE-004 Part A: Claim-Evidence关系验证")
    print("=" * 80)
    
    all_results = {}
    total_valid_structure = 0
    total_valid_evidence = 0
    total_unresolved = 0
    total_invalid = 0
    total_dangling = 0
    total_direction_errors = 0
    
    for doc_id in doc_ids:
        print(f"\n{'='*80}")
        print(f"验证文档: {doc_id}")
        print(f"{'='*80}")
        
        report = load_report(doc_id)
        result = validate_relationships(doc_id, report)
        all_results[doc_id] = result
        
        vr = result["validation_results"]
        de = result["direction_errors"]
        
        print(f"\n对象统计:")
        print(f"  Claims: {result['claim_count']}")
        print(f"  Evidence: {result['evidence_count']}")
        
        print(f"\n关系验证结果:")
        print(f"  总关系数: {vr['total']}")
        print(f"  VALID_STRUCTURE: {len(vr['VALID_STRUCTURE'])}")
        print(f"  VALID_EVIDENCE: {len(vr['VALID_EVIDENCE'])}")
        print(f"  UNRESOLVED: {len(vr['UNRESOLVED'])}")
        print(f"  INVALID: {len(vr['INVALID'])}")
        print(f"  DANGLING: {len(vr['DANGLING'])}")
        
        print(f"\n方向错误: {len(de)}")
        if de:
            for err in de[:3]:  # 只显示前3个
                print(f"  - {err['rel_id']}: {err['reason']}")
        
        total_valid_structure += len(vr['VALID_STRUCTURE'])
        total_valid_evidence += len(vr['VALID_EVIDENCE'])
        total_unresolved += len(vr['UNRESOLVED'])
        total_invalid += len(vr['INVALID'])
        total_dangling += len(vr['DANGLING'])
        total_direction_errors += len(de)
    
    print(f"\n{'='*80}")
    print("汇总统计")
    print(f"{'='*80}")
    print(f"VALID_STRUCTURE: {total_valid_structure}")
    print(f"VALID_EVIDENCE: {total_valid_evidence}")
    print(f"UNRESOLVED: {total_unresolved}")
    print(f"INVALID: {total_invalid}")
    print(f"DANGLING: {total_dangling}")
    print(f"方向错误总数: {total_direction_errors}")
    
    if total_invalid == 0 and total_dangling == 0 and total_direction_errors == 0:
        print(f"\n[PASS] Part A: INVALID=0, DANGLING=0, direction_errors=0")
    else:
        print(f"\n[FAIL] Part A: invalid={total_invalid}, dangling={total_dangling}, direction_errors={total_direction_errors}")
    
    # 保存详细结果
    output_path = RUNS_ROOT / "evidence_004" / "part_a_relationship_validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存: {output_path}")

if __name__ == "__main__":
    main()
