"""SINGLE-DOC-REPORT-001 | 单篇完整科学知识档案与报告生成器。

从 Canonical Store 及各抽取管线输出，生成单篇文献的：
1. 机器可读 JSON（SinglePaperKnowledge）
2. 人类可读 Markdown 报告

试点文档：F02, F07, P01(+SI), PAT01
"""

from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(r"D:\Knowledge_World")
DATA_ROOT = PROJECT_ROOT / "data" / "test_corpus"
MINERU_ROOT = DATA_ROOT / "mineru_output"
G3_ROOT = DATA_ROOT / "g3_output"
EXT01_ROOT = DATA_ROOT / "ext01_output"
STORE_ROOT = DATA_ROOT / "canonical_store"
RUNS_ROOT = PROJECT_ROOT / "runs"

MANIFEST_PATH = DATA_ROOT / "unified_test_manifest.json"


# ---------------------------------------------------------------------------
# 数据加载器
# ---------------------------------------------------------------------------

class DataLoader:
    """加载单篇文档的所有可用数据。"""

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.manifest = self._load_manifest()
        self.doc_meta = self._find_doc_meta()

    def _load_manifest(self) -> dict:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest

    def _find_doc_meta(self) -> dict:
        for doc in self.manifest.get("documents", []):
            if doc["document_id"] == self.doc_id:
                return doc

        store_doc_path = STORE_ROOT / "documents" / f"{self.doc_id}_main.json"
        if store_doc_path.exists():
            with open(store_doc_path, "r", encoding="utf-8") as f:
                store_doc = json.load(f)
            return {
                "document_id": self.doc_id,
                "document_type": "research_article",
                "title": store_doc.get("title", ""),
                "doi": store_doc.get("doi"),
                "authors": store_doc.get("authors", []),
                "journal": store_doc.get("journal", ""),
                "year": store_doc.get("year"),
                "parent_document_id": None,
                "notes": store_doc.get("si_document", ""),
            }

        for doc in self.manifest.get("documents", []):
            if doc.get("parent_document_id") == self.doc_id:
                return {
                    "document_id": self.doc_id,
                    "document_type": doc.get("document_type", "unknown"),
                    "title": doc.get("title", f"Parent of {doc['document_id']}"),
                    "doi": doc.get("doi"),
                    "parent_document_id": self.doc_id,
                    "notes": doc.get("notes", ""),
                    "focus": doc.get("focus", ""),
                }
        return {}

    # --- MinerU Document IR ---
    def load_document_ir(self) -> dict:
        ir_paths = {
            "F02": MINERU_ROOT / "F02_regression/main/auto",
            "F07": MINERU_ROOT / "F07_test/main/auto",
            "P01": MINERU_ROOT / "P01_test/41467_2024_50691_MOESM1_ESM/auto",
            "PAT01": MINERU_ROOT / "PAT01_test/US20100029974A1/auto",
        }
        base = ir_paths.get(self.doc_id)
        if not base or not base.exists():
            return {"status": "NOT_FOUND", "elements": []}

        content_list_path = None
        for p in base.iterdir():
            if p.name.endswith("_content_list.json"):
                content_list_path = p
                break
        if not content_list_path:
            return {"status": "NO_CONTENT_LIST", "elements": []}

        with open(content_list_path, "r", encoding="utf-8") as f:
            content_list = json.load(f)

        elements = []
        for idx, elem in enumerate(content_list):
            element_id = f"{self.doc_id}_p{elem.get('page_idx', 0)}_b{idx}"
            elements.append({
                "element_id": element_id,
                "element_type": elem.get("type", "text"),
                "page": elem.get("page_idx", 0),
                "content_preview": (elem.get("text", "") or "")[:200],
                "text_level": elem.get("text_level"),
            })

        md_path = base / f"{content_list_path.name.replace('_content_list', '')}.md"
        markdown_text = ""
        if md_path.exists():
            markdown_text = md_path.read_text(encoding="utf-8")[:500]

        images = list((base / "images").glob("*.jpg")) if (base / "images").exists() else []

        return {
            "status": "LOADED",
            "element_count": len(elements),
            "elements": elements,
            "image_count": len(images),
            "markdown_preview": markdown_text,
            "ir_directory": str(base),
        }

    # --- 六维抽取 ---
    def load_six_dimension(self) -> dict:
        g3_dir = G3_ROOT / self.doc_id
        ext01_map = {
            "P01": EXT01_ROOT / "phase2_per_dimension",
        }

        dimensions = {}
        dim_names = [
            "catalyst_design", "characterization", "performance",
            "mechanism", "structure_activity", "reliability"
        ]

        if g3_dir and g3_dir.exists():
            for dim in dim_names:
                fpath = g3_dir / f"{dim}_extracted.json"
                if fpath.exists():
                    with open(fpath, "r", encoding="utf-8") as f:
                        dimensions[dim] = json.load(f)
        elif self.doc_id in ext01_map:
            ext_dir = ext01_map[self.doc_id]
            if ext_dir.exists():
                for dim in dim_names:
                    fpath = ext_dir / f"{dim}_extracted.json"
                    if fpath.exists():
                        with open(fpath, "r", encoding="utf-8") as f:
                            dimensions[dim] = json.load(f)

        store_ext_path = STORE_ROOT / "extractions" / f"{self.doc_id}_main_ext.json"
        if store_ext_path.exists() and not dimensions:
            with open(store_ext_path, "r", encoding="utf-8") as f:
                store_ext = json.load(f)
            view = store_ext.get("view", store_ext)
            for dim in dim_names:
                if dim in view:
                    dimensions[dim] = view[dim]

        return {
            "status": "LOADED" if dimensions else "NOT_FOUND",
            "dimensions_loaded": list(dimensions.keys()),
            "dimensions": dimensions,
        }

    # --- 科学对象 ---
    def load_scientific_objects(self) -> dict:
        for suffix in [f"{self.doc_id}_g3_objects.json", f"{self.doc_id}_main_g3_objects.json"]:
            objects_path = STORE_ROOT / "extractions" / suffix
            if objects_path.exists():
                with open(objects_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "status": "LOADED",
                    "objects": data.get("objects", {}),
                    "relationships": data.get("relationships", []),
                    "object_count": data.get("statistics", {}).get("total_objects", len(data.get("objects", {}))),
                }
        return {"status": "NOT_FOUND", "objects": {}, "relationships": []}

    # --- 数值记录 (QuantityRecord) ---
    def load_quantity_records(self) -> list[dict]:
        records = []
        for subdir in ["trusted", "pending_validation"]:
            dir_path = STORE_ROOT / subdir
            if not dir_path.exists():
                continue
            for fpath in dir_path.glob(f"{self.doc_id}_qty_*.json"):
                with open(fpath, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                if rec.get("object_type") == "CatalystSample":
                    continue
                records.append(rec)
        return records

    # --- 图表关联 ---
    def load_figure_associations(self) -> list[dict]:
        for suffix in ["_figure_associations_v2.json", "_figure_associations.json"]:
            fpath = MINERU_ROOT / f"{self.doc_id}{suffix}"
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    return json.load(f)
        return []

    # --- LINK-001 关联 ---
    def load_link_associations(self) -> dict:
        link_path = STORE_ROOT / "associations" / f"{self.doc_id}_link01.json"
        if link_path.exists():
            with open(link_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # --- 分类 ---
    def load_classification(self) -> dict:
        g3_dir = G3_ROOT / self.doc_id
        if g3_dir and g3_dir.exists():
            cls_path = g3_dir / "classification.json"
            if cls_path.exists():
                with open(cls_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        store_ext_path = STORE_ROOT / "extractions" / f"{self.doc_id}_main_ext.json"
        if store_ext_path.exists():
            with open(store_ext_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("classification", data.get("view", {}).get("classification", {}))
        return {}

    # --- QA验证 ---
    def load_qa_verification(self) -> dict:
        g3_dir = G3_ROOT / self.doc_id
        if g3_dir and g3_dir.exists():
            qa_path = g3_dir / "qa_verification.json"
            if qa_path.exists():
                with open(qa_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        return {}

    # --- 表格信息（从Document IR提取） ---
    def extract_table_info(self) -> list[dict]:
        ir = self.load_document_ir()
        tables = [e for e in ir.get("elements", []) if e["element_type"] == "table"]
        return tables

    # --- 图片信息 ---
    def extract_figure_info(self) -> list[dict]:
        ir = self.load_document_ir()
        figures = [e for e in ir.get("elements", []) if e["element_type"] == "image"]
        fig_assoc = self.load_figure_associations()
        for fig in figures:
            for assoc in fig_assoc:
                if assoc.get("target_element_id") == fig["element_id"]:
                    fig["association"] = assoc
                    break
        return figures


# ---------------------------------------------------------------------------
# 知识对象构建器
# ---------------------------------------------------------------------------

class KnowledgeBuilder:
    """从原始抽取数据构建九类知识对象。"""

    def __init__(self, doc_id: str, loader: DataLoader):
        self.doc_id = doc_id
        self.loader = loader
        self._id_counter = 0

    def _make_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{self.doc_id}_{prefix}_{self._id_counter:03d}"

    def build_all(self) -> dict:
        six_dim = self.loader.load_six_dimension()
        objects = self.loader.load_scientific_objects()
        qty_records = self.loader.load_quantity_records()
        dims = six_dim.get("dimensions", {})

        facts = self._build_facts(dims, objects)
        claims = self._build_claims(dims, objects)
        evidence_items = self._build_evidence(dims, objects, qty_records)
        limitations = self._build_limitations(dims)
        open_questions = self._build_open_questions(dims)
        hypotheses = self._build_hypotheses(dims)
        experiment_proposals = self._build_experiment_proposals(dims)
        feasibility = self._build_feasibility(dims)
        validation_plans = self._build_validation_plans(dims)

        result = {
            "facts": facts,
            "claims": claims,
            "evidence": evidence_items,
            "limitations": limitations,
            "open_questions": open_questions,
            "hypotheses": hypotheses,
            "experiment_proposals": experiment_proposals,
            "feasibility_assessments": feasibility,
            "validation_plans": validation_plans,
        }

        rel_builder = RelationshipBuilder(self.doc_id, result)
        relationships = rel_builder.build_all()
        result["_relationships"] = relationships

        self._cross_link_claims_evidence(result)

        return result

    @staticmethod
    def _cross_link_claims_evidence(knowledge: dict):
        claims = knowledge.get("claims", [])
        evidence_items = knowledge.get("evidence", [])
        relationships = knowledge.get("_relationships", [])

        claim_ev_map = {c["claim_id"]: set() for c in claims}
        ev_claim_map = {e["evidence_id"]: set() for e in evidence_items}

        for rel in relationships:
            if rel["relationship_type"] in ("SUPPORTED_BY", "CHALLENGED_BY"):
                src_id = rel["source_id"]
                tgt_id = rel["target_id"]
                if src_id in claim_ev_map and tgt_id in ev_claim_map:
                    claim_ev_map[src_id].add(tgt_id)
                    ev_claim_map[tgt_id].add(src_id)

        for claim in claims:
            cid = claim["claim_id"]
            claim["evidence_ids"] = sorted(claim_ev_map.get(cid, set()))

        for ev in evidence_items:
            eid = ev["evidence_id"]
            ev["related_claim_ids"] = sorted(ev_claim_map.get(eid, set()))

    def _build_facts(self, dims: dict, objects: dict) -> list[dict]:
        facts = []
        cat_design = dims.get("catalyst_design", {})
        if self._is_real_content(cat_design.get("catalyst_system", "")):
            facts.append({
                "fact_id": self._make_id("fact"),
                "document_id": self.doc_id,
                "content": cat_design.get("catalyst_system", ""),
                "fact_type": "CATALYST_SYSTEM",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("catalyst_design"),
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
                "raw_fields": {
                    "catalyst_type": cat_design.get("catalyst_type", ""),
                    "active_component": cat_design.get("active_component", ""),
                    "support": cat_design.get("support", ""),
                },
            })

        char = dims.get("characterization", {})
        if char.get("techniques_used"):
            facts.append({
                "fact_id": self._make_id("fact"),
                "document_id": self.doc_id,
                "content": f"Characterization techniques: {', '.join(char['techniques_used'])}",
                "fact_type": "CHARACTERIZATION",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("characterization"),
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
                "raw_fields": {
                    "techniques": char.get("techniques_used", []),
                    "key_findings": char.get("key_findings", []),
                },
            })

        objs = objects.get("objects", {})
        rxn = objs.get("Reaction", {})
        if rxn.get("reaction_type"):
            facts.append({
                "fact_id": self._make_id("fact"),
                "document_id": self.doc_id,
                "content": rxn.get("reaction_type", ""),
                "fact_type": "REACTION",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": rxn.get("source_anchor"),
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
                "raw_fields": {
                    "object_id": rxn.get("object_id", ""),
                    "proposed_pathway": rxn.get("proposed_pathway", ""),
                },
            })

        return facts

    def _build_claims(self, dims: dict, objects: dict) -> list[dict]:
        claims = []
        perf = dims.get("performance", {})
        if self._is_real_content(perf.get("key_claim", "")):
            claims.append({
                "claim_id": self._make_id("claim"),
                "document_id": self.doc_id,
                "content": perf["key_claim"],
                "claim_type": "PERFORMANCE_CLAIM",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("performance"),
                "evidence_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        mech = dims.get("mechanism", {})
        if self._is_real_content(mech.get("proposed_pathway", "")):
            claims.append({
                "claim_id": self._make_id("claim"),
                "document_id": self.doc_id,
                "content": mech["proposed_pathway"],
                "claim_type": "MECHANISM_CLAIM",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("mechanism"),
                "evidence_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        sa = dims.get("structure_activity", {})
        if sa.get("relationship_type"):
            claims.append({
                "claim_id": self._make_id("claim"),
                "document_id": self.doc_id,
                "content": f"Structure-activity: {sa['relationship_type']}",
                "claim_type": "STRUCTURE_ACTIVITY_CLAIM",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("structure_activity"),
                "evidence_ids": [],
                "raw_fields": {
                    "descriptor": sa.get("descriptor", ""),
                    "evidence_strength": sa.get("evidence_strength", ""),
                },
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        benchmark = perf.get("benchmark_comparison", "")
        if self._is_real_content(benchmark):
            claims.append({
                "claim_id": self._make_id("claim"),
                "document_id": self.doc_id,
                "content": benchmark,
                "claim_type": "BENCHMARK_CLAIM",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("performance"),
                "evidence_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        return claims

    @staticmethod
    def _is_real_content(text: str) -> bool:
        if not text or not text.strip():
            return False
        lower = text.strip().lower()
        if lower in ("not reported", "none", "n/a", ""):
            return False
        if "not reported in" in lower:
            return False
        if lower.startswith("not specified"):
            return False
        if len(text.strip()) <= 3:
            return False
        return True

    def _build_evidence(self, dims: dict, objects: dict, qty_records: list) -> list[dict]:
        evidence_items = []

        char = dims.get("characterization", {})
        for finding in char.get("key_findings", []):
            if not self._is_real_content(finding):
                continue
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": finding,
                "evidence_type": "EXPERIMENTAL",
                "data_source": "characterization",
                "polarity": "SUPPORTING",
                "strength": "moderate",
                "source_anchor": self._dim_anchor("characterization"),
                "related_claim_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        if self._is_real_content(char.get("morphological_evidence", "")):
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": char["morphological_evidence"],
                "evidence_type": "EXPERIMENTAL",
                "data_source": "characterization/morphology",
                "polarity": "SUPPORTING",
                "strength": "strong",
                "source_anchor": self._dim_anchor("characterization"),
                "related_claim_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        if self._is_real_content(char.get("electronic_evidence", "")):
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": char["electronic_evidence"],
                "evidence_type": "EXPERIMENTAL",
                "data_source": "characterization/electronic",
                "polarity": "SUPPORTING",
                "strength": "strong",
                "source_anchor": self._dim_anchor("characterization"),
                "related_claim_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        mech = dims.get("mechanism", {})
        if self._is_real_content(mech.get("computational_support", "")):
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": mech["computational_support"],
                "evidence_type": "COMPUTATIONAL",
                "data_source": "mechanism",
                "polarity": "SUPPORTING",
                "strength": "strong",
                "source_anchor": self._dim_anchor("mechanism"),
                "related_claim_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })
        if self._is_real_content(mech.get("experimental_support", "")):
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": mech["experimental_support"],
                "evidence_type": "EXPERIMENTAL",
                "data_source": "mechanism",
                "polarity": "SUPPORTING",
                "strength": "moderate",
                "source_anchor": self._dim_anchor("mechanism"),
                "related_claim_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        perf = dims.get("performance", {})
        for metric in perf.get("key_metrics", []):
            content = f"{metric.get('metric_name', '')}: {metric.get('value', '')} ({metric.get('conditions', '')})"
            if not self._is_real_content(content):
                continue
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": content,
                "evidence_type": "EXPERIMENTAL",
                "data_source": "performance/metrics",
                "polarity": "SUPPORTING",
                "strength": "strong",
                "source_anchor": self._dim_anchor("performance"),
                "related_claim_ids": [],
                "raw_fields": {
                    "metric_name": metric.get("metric_name"),
                    "value": metric.get("value"),
                    "conditions": metric.get("conditions"),
                },
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        rel = dims.get("reliability", {})
        if rel.get("time_on_stream") and str(rel["time_on_stream"]) != "0":
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": f"Stability: TOS = {rel['time_on_stream']}",
                "evidence_type": "EXPERIMENTAL",
                "data_source": "reliability",
                "polarity": "SUPPORTING",
                "strength": "strong",
                "source_anchor": self._dim_anchor("reliability"),
                "related_claim_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })
        if rel.get("deactivation_observed"):
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": f"Deactivation: {rel['deactivation_observed']}",
                "evidence_type": "EXPERIMENTAL",
                "data_source": "reliability",
                "polarity": "CHALLENGING",
                "strength": "moderate",
                "source_anchor": self._dim_anchor("reliability"),
                "related_claim_ids": [],
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        for qr in qty_records:
            if not (qr.get("source_anchor") or qr.get("element_id")):
                continue
            tl = qr.get("three_layer_values", {})
            raw = tl.get("raw", {})
            content = f"{qr.get('quantity_type', '')}: {raw.get('value', '')} {raw.get('unit', '')}"
            if not self._is_real_content(content):
                continue
            evidence_items.append({
                "evidence_id": self._make_id("ev"),
                "document_id": self.doc_id,
                "content": content,
                "evidence_type": "EXPERIMENTAL",
                "data_source": "quantity_record",
                "polarity": "SUPPORTING",
                "strength": "moderate",
                "source_anchor": qr.get("source_anchor"),
                "related_claim_ids": [],
                "raw_fields": {
                    "record_id": qr.get("record_id", ""),
                    "quantity_type": qr.get("quantity_type", ""),
                    "three_layer_values": tl,
                    "conversion_status": qr.get("unit_conversion_status", ""),
                },
                "provenance_label": "EXTRACTED",
                "status_label": "SOURCE_LINKED" if qr.get("source_anchor") else "EXTRACTED",
            })

        return evidence_items

    def _build_limitations(self, dims: dict) -> list[dict]:
        limitations = []
        rel = dims.get("reliability", {})

        if rel.get("deactivation_observed"):
            limitations.append({
                "limitation_id": self._make_id("lim"),
                "document_id": self.doc_id,
                "content": f"Catalyst deactivation observed: {rel['deactivation_observed']}",
                "limitation_type": "SCOPE",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("reliability"),
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })

        sa = dims.get("structure_activity", {})
        if sa.get("data_points") and int(sa.get("data_points", 0)) < 5:
            limitations.append({
                "limitation_id": self._make_id("lim"),
                "document_id": self.doc_id,
                "content": f"Limited data points for structure-activity relationship: {sa.get('data_points')}",
                "limitation_type": "ACCURACY",
                "source": "SYSTEM_INFERRED",
                "status": "INFERRED",
                "source_anchor": self._dim_anchor("structure_activity"),
                "provenance_label": "INFERRED",
                "status_label": "UNRESOLVED",
            })

        mech = dims.get("mechanism", {})
        if not mech.get("rate_determining_step"):
            limitations.append({
                "limitation_id": self._make_id("lim"),
                "document_id": self.doc_id,
                "content": "Rate-determining step not identified",
                "limitation_type": "METHODOLOGY",
                "source": "SYSTEM_INFERRED",
                "status": "INFERRED",
                "source_anchor": self._dim_anchor("mechanism"),
                "provenance_label": "INFERRED",
                "status_label": "UNRESOLVED",
            })

        return limitations

    def _build_open_questions(self, dims: dict) -> list[dict]:
        questions = []
        mech = dims.get("mechanism", {})
        if mech.get("intermediates") is not None and not mech.get("intermediates"):
            questions.append({
                "question_id": self._make_id("q"),
                "document_id": self.doc_id,
                "content": "Reaction intermediates not identified",
                "question_type": "MECHANISM",
                "resolution_status": "OPEN",
                "source": "SYSTEM_INFERRED",
                "source_anchor": self._dim_anchor("mechanism"),
                "provenance_label": "INFERRED",
                "status_label": "UNRESOLVED",
            })

        rel = dims.get("reliability", {})
        if not rel.get("mass_transfer_verification"):
            questions.append({
                "question_id": self._make_id("q"),
                "document_id": self.doc_id,
                "content": "Mass transfer effects not verified",
                "question_type": "METHODOLOGY",
                "resolution_status": "OPEN",
                "source": "SYSTEM_INFERRED",
                "source_anchor": self._dim_anchor("reliability"),
                "provenance_label": "INFERRED",
                "status_label": "UNRESOLVED",
            })

        return questions

    def _build_hypotheses(self, dims: dict) -> list[dict]:
        hypotheses = []
        mech = dims.get("mechanism", {})
        if self._is_real_content(mech.get("proposed_pathway", "")):
            hypotheses.append({
                "hypothesis_id": self._make_id("hyp"),
                "document_id": self.doc_id,
                "content": mech["proposed_pathway"],
                "hypothesis_type": "MECHANISM",
                "source": "AUTHOR_STATED",
                "status": "REPORTED",
                "supporting_evidence_ids": [],
                "source_anchor": self._dim_anchor("mechanism"),
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })
        return hypotheses

    def _build_experiment_proposals(self, dims: dict) -> list[dict]:
        return []

    def _build_feasibility(self, dims: dict) -> list[dict]:
        assessments = []
        design = dims.get("catalyst_design", {})
        if self._is_real_content(design.get("design_rationale", "")):
            assessments.append({
                "feasibility_id": self._make_id("feas"),
                "document_id": self.doc_id,
                "target_type": "catalyst_design",
                "target_id": design.get("catalyst_system", self.doc_id),
                "feasibility_status": "FEASIBLE",
                "rationale": design["design_rationale"],
                "assessed_by": "AUTHOR",
                "status": "REPORTED",
                "source_anchor": self._dim_anchor("catalyst_design"),
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })
        return assessments

    def _build_validation_plans(self, dims: dict) -> list[dict]:
        plans = []
        rel = dims.get("reliability", {})
        if rel.get("cycle_count") or rel.get("time_on_stream"):
            plans.append({
                "plan_id": self._make_id("vplan"),
                "document_id": self.doc_id,
                "method_description": f"Long-term stability test: TOS={rel.get('time_on_stream', 'N/A')}, cycles={rel.get('cycle_count', 'N/A')}",
                "proposed_by": "AUTHOR",
                "plan_status": "COMPLETED",
                "source_anchor": self._dim_anchor("reliability"),
                "provenance_label": "DERIVED",
                "status_label": "EXTRACTED",
            })
        return plans

    def _dim_anchor(self, dim_name: str) -> dict:
        return {
            "document_id": self.doc_id,
            "element_type": "TEXT",
            "element_id": f"{self.doc_id}_dim_{dim_name}",
            "location": dim_name,
            "confidence": 0.8,
        }


# ---------------------------------------------------------------------------
# 关系构建器
# ---------------------------------------------------------------------------

class RelationshipBuilder:
    """构建单篇内部对象关系。"""

    SUPPORTED_BY = "SUPPORTED_BY"
    CHALLENGED_BY = "CHALLENGED_BY"
    QUALIFIED_BY = "QUALIFIED_BY"
    TESTED_BY = "TESTED_BY"
    MOTIVATES = "MOTIVATES"
    VALIDATES = "VALIDATES"
    REQUIRES = "REQUIRES"

    def __init__(self, doc_id: str, knowledge: dict):
        self.doc_id = doc_id
        self.knowledge = knowledge
        self.relationships = []

    def build_all(self) -> list[dict]:
        self._link_evidence_to_claims()
        self._link_limitations_to_claims()
        self._link_questions_to_hypotheses()
        self._link_experiments_to_claims()
        self._link_feasibility_to_hypotheses()
        self._link_validation_to_claims()
        self._link_facts_to_claims()
        return self.relationships

    def _link_evidence_to_claims(self):
        """Evidence SUPPORTS Claim (Claim is SUPPORTED_BY Evidence)"""
        for ev in self.knowledge.get("evidence", []):
            polarity = ev.get("polarity", "")
            # Match evidence to claims by data_source dimension
            ev_source = ev.get("data_source", "")
            for claim in self.knowledge.get("claims", []):
                claim_dim = claim.get("source_anchor", {}).get("location", "")
                # Relaxed matching: same dimension or both non-empty
                if ev_source and claim_dim and (ev_source in claim_dim or claim_dim in ev_source):
                    if polarity == "SUPPORTING":
                        # Claim SUPPORTED_BY Evidence (correct direction)
                        self._add_rel(claim["claim_id"], ev["evidence_id"], self.SUPPORTED_BY,
                                      source_anchor=ev.get("source_anchor"))
                    elif polarity == "CHALLENGING":
                        # Claim CHALLENGED_BY Evidence
                        self._add_rel(claim["claim_id"], ev["evidence_id"], self.CHALLENGED_BY,
                                      source_anchor=ev.get("source_anchor"))
                    elif polarity == "QUALIFYING":
                        # Claim QUALIFIED_BY Evidence
                        self._add_rel(claim["claim_id"], ev["evidence_id"], self.QUALIFIED_BY,
                                      source_anchor=ev.get("source_anchor"))

    def _link_limitations_to_claims(self):
        """Claim QUALIFIED_BY Limitation"""
        for lim in self.knowledge.get("limitations", []):
            for claim in self.knowledge.get("claims", []):
                # Claim is qualified by limitation
                self._add_rel(claim["claim_id"], lim["limitation_id"], self.QUALIFIED_BY,
                              source_anchor=lim.get("source_anchor"))

    def _link_questions_to_hypotheses(self):
        for q in self.knowledge.get("open_questions", []):
            for hyp in self.knowledge.get("hypotheses", []):
                if q.get("question_type") == "MECHANISM":
                    self._add_rel(q["question_id"], hyp["hypothesis_id"], self.MOTIVATES,
                                  source_anchor=q.get("source_anchor"))

    def _link_experiments_to_claims(self):
        """Claim TESTED_BY Experiment"""
        for exp in self.knowledge.get("experiment_proposals", []):
            for claim in self.knowledge.get("claims", []):
                # Claim is tested by experiment
                self._add_rel(claim["claim_id"], exp["proposal_id"], self.TESTED_BY,
                              source_anchor=exp.get("source_anchor"))

    def _link_feasibility_to_hypotheses(self):
        """Hypothesis VALIDATED_BY Feasibility (or Feasibility VALIDATES Hypothesis)"""
        for feas in self.knowledge.get("feasibility_assessments", []):
            for hyp in self.knowledge.get("hypotheses", []):
                # Feasibility validates hypothesis (this direction is OK)
                self._add_rel(feas["feasibility_id"], hyp["hypothesis_id"], self.VALIDATES,
                              source_anchor=feas.get("source_anchor"))

    def _link_validation_to_claims(self):
        """Claim VALIDATED_BY ValidationPlan"""
        for vplan in self.knowledge.get("validation_plans", []):
            for claim in self.knowledge.get("claims", []):
                # Claim is validated by validation plan
                self._add_rel(claim["claim_id"], vplan["plan_id"], self.VALIDATES,
                              source_anchor=vplan.get("source_anchor"))

    def _link_facts_to_claims(self):
        """Claim REQUIRES Fact (or Fact SUPPORTS Claim)"""
        for fact in self.knowledge.get("facts", []):
            for claim in self.knowledge.get("claims", []):
                if fact.get("fact_type") == "CATALYST_SYSTEM" and claim.get("claim_type") == "PERFORMANCE_CLAIM":
                    # Claim requires fact (fact supports claim)
                    self._add_rel(claim["claim_id"], fact["fact_id"], self.REQUIRES,
                                  source_anchor=fact.get("source_anchor"))

    def _add_rel(self, source_id: str, target_id: str, rel_type: str, source_anchor: dict = None):
        self.relationships.append({
            "relationship_id": f"{self.doc_id}_rel_{len(self.relationships)+1:03d}",
            "document_id": self.doc_id,
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": rel_type,
            "source_anchor": source_anchor,
            "status": "EXTRACTED",
        })


# ---------------------------------------------------------------------------
# 报告生成器
# ---------------------------------------------------------------------------

class ReportGenerator:
    """生成 JSON + Markdown 报告。"""

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.loader = DataLoader(doc_id)
        self.knowledge_builder = KnowledgeBuilder(doc_id, self.loader)
        self.knowledge = self.knowledge_builder.build_all()
        self.relationships = self.knowledge.pop("_relationships", [])

    def generate_json(self) -> dict:
        ir = self.loader.load_document_ir()
        six_dim = self.loader.load_six_dimension()
        objects = self.loader.load_scientific_objects()
        qty_records = self.loader.load_quantity_records()
        fig_assoc = self.loader.load_figure_associations()
        classification = self.loader.load_classification()
        qa = self.loader.load_qa_verification()
        tables = self.loader.extract_table_info()
        figures = self.loader.extract_figure_info()

        doc_meta = self.loader.doc_meta

        report = {
            "report_id": f"{self.doc_id}_single_doc_report",
            "report_type": "SinglePaperKnowledge",
            "document_id": self.doc_id,
            "generated_at": datetime.now().isoformat(),
            "generator_version": "SINGLE-DOC-REPORT-002-v2.0",

            "document_overview": {
                "document_id": self.doc_id,
                "title": doc_meta.get("title", objects.get("objects", {}).get("Document", {}).get("title", "")),
                "document_type": doc_meta.get("document_type", "unknown"),
                "doi": doc_meta.get("doi"),
                "source_url": doc_meta.get("source_url", ""),
                "parent_document_id": doc_meta.get("parent_document_id"),
                "mineru_parse_status": ir.get("status"),
                "mineru_element_count": ir.get("element_count", 0),
                "mineru_image_count": ir.get("image_count", 0),
            },

            "attachments": {
                "si_documents": [],
                "table_files": [],
                "other_files": [],
            },

            "document_structure": {
                "total_elements": ir.get("element_count", 0),
                "text_elements": len([e for e in ir.get("elements", []) if e["element_type"] == "text"]),
                "table_elements": len(tables),
                "figure_elements": len(figures),
                "equation_elements": len([e for e in ir.get("elements", []) if e["element_type"] == "equation"]),
            },

            "tables": tables,
            "figures": figures,
            "figure_associations": fig_assoc,

            "six_dimension_extraction": {
                "status": six_dim.get("status"),
                "dimensions": six_dim.get("dimensions", {}),
                "dimension_count": len(six_dim.get("dimensions", {})),
            },

            "scientific_objects": {
                "status": objects.get("status"),
                "objects": objects.get("objects", {}),
                "object_count": objects.get("object_count", 0),
                "relationships": objects.get("relationships", []),
            },

            "quantity_records": {
                "total": len(qty_records),
                "trusted": len([r for r in qty_records if r.get("status") == "LLM_EXTRACTED"]),
                "pending_validation": len([r for r in qty_records if r.get("status") == "PENDING_VALIDATION"]),
                "records": qty_records,
            },

            "classification": classification,

            "knowledge_objects": self.knowledge,

            "knowledge_relationships": self.relationships,

            "qa_verification": qa,

            "statistics": self._compute_statistics(),

            "provenance": {
                "extraction_method": "LLM_EXTRACTED",
                "schema_version": "1.0.0",
                "report_schema": "SinglePaperKnowledge",
                "generator_version": "SINGLE-DOC-REPORT-002-v2.0",
                "data_sources": [
                    "MinerU Document IR",
                    "EXT-001 Six-Dimension Extraction",
                    "ENT-001 Scientific Objects",
                    "NUM-UNIT-001 Quantity Records",
                    "FIG-001 Figure Associations",
                    "TAX-001 Classification",
                    "QA-001 Quality Gates",
                ],
            },

            "provenance_audit": self._build_provenance_audit(),
        }

        if self.doc_id == "P01":
            report["attachments"]["si_documents"] = [
                {
                    "doc_id": "P01_SI",
                    "filename": "41467_2024_50691_MOESM1_ESM.pdf",
                    "relation": "supplementary",
                    "parse_status": "PASS",
                }
            ]

        return report

    def _compute_statistics(self) -> dict:
        k = self.knowledge
        return {
            "fact_count": len(k.get("facts", [])),
            "claim_count": len(k.get("claims", [])),
            "evidence_count": len(k.get("evidence", [])),
            "limitation_count": len(k.get("limitations", [])),
            "open_question_count": len(k.get("open_questions", [])),
            "hypothesis_count": len(k.get("hypotheses", [])),
            "experiment_proposal_count": len(k.get("experiment_proposals", [])),
            "feasibility_count": len(k.get("feasibility_assessments", [])),
            "validation_plan_count": len(k.get("validation_plans", [])),
            "relationship_count": len(self.relationships),
            "relationship_types": list(set(r["relationship_type"] for r in self.relationships)),
        }

    def _build_provenance_audit(self) -> dict:
        all_objects = []
        for obj_type in ["facts", "claims", "evidence", "limitations", "open_questions",
                         "hypotheses", "experiment_proposals", "feasibility_assessments",
                         "validation_plans"]:
            for obj in self.knowledge.get(obj_type, []):
                obj["_object_type"] = obj_type.rstrip("s")
                all_objects.append(obj)

        provenance_counts = {}
        status_counts = {}
        provenance_by_type = {}

        for obj in all_objects:
            pl = obj.get("provenance_label", "UNKNOWN")
            sl = obj.get("status_label", "UNKNOWN")
            ot = obj.get("_object_type", "unknown")

            provenance_counts[pl] = provenance_counts.get(pl, 0) + 1
            status_counts[sl] = status_counts.get(sl, 0) + 1

            if ot not in provenance_by_type:
                provenance_by_type[ot] = {}
            provenance_by_type[ot][pl] = provenance_by_type[ot].get(pl, 0) + 1

        synthetic_anchor_objects = [
            obj.get(list(obj.keys())[0], "?")
            for obj in all_objects
            if isinstance(obj.get("source_anchor"), dict)
            and "_dim_" in obj["source_anchor"].get("element_id", "")
        ]

        return {
            "total_knowledge_objects": len(all_objects),
            "provenance_counts": provenance_counts,
            "status_counts": status_counts,
            "provenance_by_object_type": provenance_by_type,
            "objects_with_synthetic_anchors": len(synthetic_anchor_objects),
            "audit_note": "DERIVED = mapped from 6-dimension extraction fields; "
                          "INFERRED = system-generated from null field detection; "
                          "EXTRACTED = from QuantityRecord or ScientificObject pipeline. "
                          "Synthetic anchors reference dimension names, not document element IDs.",
        }

    def generate_markdown(self, json_report: dict) -> str:
        lines = []
        overview = json_report["document_overview"]
        stats = json_report["statistics"]

        lines.append(f"# 单篇科学知识报告：{self.doc_id}")
        lines.append("")
        lines.append(f"> 生成时间：{json_report['generated_at']}")
        lines.append(f"> 生成器：SINGLE-DOC-REPORT-002-v2.0")
        lines.append(f"> Schema版本：{json_report['provenance']['schema_version']}")
        lines.append("")

        # --- 1. 文献概况 ---
        lines.append("## 1. 文献概况")
        lines.append("")
        lines.append(f"| 字段 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 文档ID | {overview['document_id']} |")
        lines.append(f"| 标题 | {overview.get('title', 'N/A')[:100]} |")
        lines.append(f"| 类型 | {overview.get('document_type', 'N/A')} |")
        if overview.get('doi'):
            lines.append(f"| DOI | {overview['doi']} |")
        lines.append(f"| MinerU解析 | {overview.get('mineru_parse_status', 'N/A')} |")
        lines.append(f"| IR元素数 | {overview.get('mineru_element_count', 0)} |")
        lines.append(f"| 图片数 | {overview.get('mineru_image_count', 0)} |")
        lines.append("")

        # --- 2. 附件目录 ---
        lines.append("## 2. 附件目录")
        lines.append("")
        attachments = json_report.get("attachments", {})
        si_docs = attachments.get("si_documents", [])
        if si_docs:
            lines.append("### 补充材料")
            for si in si_docs:
                lines.append(f"- **{si['doc_id']}**: {si['filename']} (解析状态: {si['parse_status']})")
        else:
            lines.append("*无补充材料*")
        lines.append("")

        structure = json_report.get("document_structure", {})
        lines.append("### 文档结构统计")
        lines.append(f"- 文本元素: {structure.get('text_elements', 0)}")
        lines.append(f"- 表格元素: {structure.get('table_elements', 0)}")
        lines.append(f"- 图片元素: {structure.get('figure_elements', 0)}")
        lines.append(f"- 公式元素: {structure.get('equation_elements', 0)}")
        lines.append("")

        # --- 3. 六维科学抽取 ---
        lines.append("## 3. 六维科学抽取")
        lines.append("")
        six_dim = json_report.get("six_dimension_extraction", {})
        lines.append(f"抽取状态: **{six_dim.get('status', 'N/A')}** | 维度数: {six_dim.get('dimension_count', 0)}/6")
        lines.append("")
        dims = six_dim.get("dimensions", {})
        for dim_name, dim_data in dims.items():
            lines.append(f"### 3.{list(dims.keys()).index(dim_name)+1} {dim_name.replace('_', ' ').title()}")
            lines.append("")
            if isinstance(dim_data, dict):
                for k, v in dim_data.items():
                    if isinstance(v, list):
                        lines.append(f"- **{k}**: {', '.join(str(i) for i in v[:5])}")
                    elif isinstance(v, str) and len(v) > 200:
                        lines.append(f"- **{k}**: {v[:200]}...")
                    else:
                        lines.append(f"- **{k}**: {v}")
            lines.append("")

        # --- 4. 图表与结构化内容 ---
        lines.append("## 4. 图表与结构化内容")
        lines.append("")
        tables = json_report.get("tables", [])
        figures = json_report.get("figures", [])
        fig_assoc = json_report.get("figure_associations", [])

        lines.append(f"### 表格 ({len(tables)}个)")
        if tables:
            for t in tables[:10]:
                lines.append(f"- `{t['element_id']}` (page {t.get('page', '?')})")
        else:
            lines.append("*未检测到表格元素*")
        lines.append("")

        lines.append(f"### 图片 ({len(figures)}个)")
        if figures:
            for f in figures[:10]:
                assoc_status = f.get("association", {}).get("status", "NO_ASSOCIATION")
                lines.append(f"- `{f['element_id']}` (page {f.get('page', '?')}) — 关联: {assoc_status}")
        else:
            lines.append("*未检测到图片元素*")
        lines.append("")

        resolved = len([a for a in fig_assoc if a.get("status") != "UNRESOLVED"])
        unresolved = len([a for a in fig_assoc if a.get("status") == "UNRESOLVED"])
        lines.append(f"**图关联统计**: 已解析 {resolved} | 未解析 {unresolved} | 总计 {len(fig_assoc)}")
        lines.append("")

        # --- 5. 科学数值 ---
        lines.append("## 5. 科学数值与单位")
        lines.append("")
        qty = json_report.get("quantity_records", {})
        lines.append(f"总计: {qty.get('total', 0)} | Trusted: {qty.get('trusted', 0)} | Pending: {qty.get('pending_validation', 0)}")
        lines.append("")
        for rec in qty.get("records", []):
            tl = rec.get("three_layer_values", {})
            raw = tl.get("raw", {})
            si = tl.get("si", {})
            domain = tl.get("domain", {})
            status = rec.get("unit_conversion_status", rec.get("status", "N/A"))
            anchor = "Yes" if rec.get("source_anchor") else "No"
            lines.append(f"- **{rec.get('quantity_type', '?')}**: "
                         f"{raw.get('value', '?')} {raw.get('unit', '?')} "
                         f"→ SI: {si.get('value', 'N/A')} {si.get('unit', 'N/A')} "
                         f"| Domain: {domain.get('value', 'N/A')} {domain.get('unit', 'N/A')} "
                         f"| 转换: {status} | 锚点: {anchor}")
        lines.append("")

        # --- 6. 知识对象 ---
        lines.append("## 6. Fact / Claim / Evidence / Limitation")
        lines.append("")

        self._md_section(lines, "6.1", "Facts", stats.get("fact_count", 0),
                         self.knowledge.get("facts", []),
                         id_field="fact_id", content_field="content",
                         extra_fields=["fact_type", "source", "status"])

        self._md_section(lines, "6.2", "Claims", stats.get("claim_count", 0),
                         self.knowledge.get("claims", []),
                         id_field="claim_id", content_field="content",
                         extra_fields=["claim_type", "source", "status"])

        self._md_section(lines, "6.3", "Evidence", stats.get("evidence_count", 0),
                         self.knowledge.get("evidence", []),
                         id_field="evidence_id", content_field="content",
                         extra_fields=["evidence_type", "polarity", "strength", "data_source"])

        self._md_section(lines, "6.4", "Limitations", stats.get("limitation_count", 0),
                         self.knowledge.get("limitations", []),
                         id_field="limitation_id", content_field="content",
                         extra_fields=["limitation_type", "source", "status"])

        # --- 7. Question / Hypothesis / Experiment / Feasibility / Validation ---
        lines.append("## 7. Question / Hypothesis / Experiment / Feasibility / Validation")
        lines.append("")

        self._md_section(lines, "7.1", "Open Questions", stats.get("open_question_count", 0),
                         self.knowledge.get("open_questions", []),
                         id_field="question_id", content_field="content",
                         extra_fields=["question_type", "resolution_status"])

        self._md_section(lines, "7.2", "Hypotheses", stats.get("hypothesis_count", 0),
                         self.knowledge.get("hypotheses", []),
                         id_field="hypothesis_id", content_field="content",
                         extra_fields=["hypothesis_type", "source"])

        self._md_section(lines, "7.3", "Experiment Proposals", stats.get("experiment_proposal_count", 0),
                         self.knowledge.get("experiment_proposals", []),
                         id_field="proposal_id", content_field="content",
                         extra_fields=["experiment_status"])

        self._md_section(lines, "7.4", "Feasibility Assessments", stats.get("feasibility_count", 0),
                         self.knowledge.get("feasibility_assessments", []),
                         id_field="feasibility_id", content_field="rationale",
                         extra_fields=["feasibility_status", "target_type"])

        self._md_section(lines, "7.5", "Validation Plans", stats.get("validation_plan_count", 0),
                         self.knowledge.get("validation_plans", []),
                         id_field="plan_id", content_field="method_description",
                         extra_fields=["plan_status", "proposed_by"])

        # --- 8. 内部关系 ---
        lines.append("## 8. 单篇内部关系")
        lines.append("")
        lines.append(f"关系总数: **{stats.get('relationship_count', 0)}**")
        lines.append(f"关系类型: {', '.join(stats.get('relationship_types', []))}")
        lines.append("")
        lines.append("| # | Source | Target | Type | Anchor |")
        lines.append("|---|--------|--------|------|--------|")
        for i, rel in enumerate(self.relationships, 1):
            anchor = "Yes" if rel.get("source_anchor") else "No"
            lines.append(f"| {i} | `{rel['source_id']}` | `{rel['target_id']}` | {rel['relationship_type']} | {anchor} |")
        lines.append("")

        # --- 9. QA结果 ---
        lines.append("## 9. QA结果")
        lines.append("")
        qa = json_report.get("qa_verification", {})
        if qa:
            verifications = qa.get("verifications", {})
            for check_name, check_data in verifications.items():
                checks = check_data.get("checks", [])
                pass_count = len([c for c in checks if c.get("status") == "PASS"])
                warn_count = len([c for c in checks if c.get("status") == "WARN"])
                fail_count = len([c for c in checks if c.get("status") == "FAIL"])
                lines.append(f"### {check_name}")
                lines.append(f"- PASS: {pass_count} | WARN: {warn_count} | FAIL: {fail_count}")
        else:
            lines.append("*QA验证数据不可用*")
        lines.append("")

        # --- 10. 原文回链 ---
        lines.append("## 10. 原文回链与溯源")
        lines.append("")
        lines.append(f"数据来源: {', '.join(json_report['provenance']['data_sources'])}")
        lines.append("")
        lines.append("### SourceAnchor覆盖统计")
        all_objects = []
        for obj_type in ["facts", "claims", "evidence", "limitations", "open_questions",
                         "hypotheses", "experiment_proposals", "feasibility_assessments", "validation_plans"]:
            all_objects.extend(self.knowledge.get(obj_type, []))
        with_anchor = len([o for o in all_objects if o.get("source_anchor")])
        lines.append(f"- 知识对象总数: {len(all_objects)}")
        lines.append(f"- 有SourceAnchor: {with_anchor}")
        lines.append(f"- 无SourceAnchor: {len(all_objects) - with_anchor}")
        lines.append("")

        # --- 11. 缺失与未实现 ---
        lines.append("## 11. 缺失值与未实现内容")
        lines.append("")
        missing = self._identify_missing(json_report)
        for item in missing:
            lines.append(f"- {item}")
        lines.append("")

        # --- 12. 统计摘要 ---
        lines.append("## 12. 统计摘要")
        lines.append("")
        lines.append("| 类别 | 数量 |")
        lines.append("|------|------|")
        lines.append(f"| Facts | {stats.get('fact_count', 0)} |")
        lines.append(f"| Claims | {stats.get('claim_count', 0)} |")
        lines.append(f"| Evidence | {stats.get('evidence_count', 0)} |")
        lines.append(f"| Limitations | {stats.get('limitation_count', 0)} |")
        lines.append(f"| Open Questions | {stats.get('open_question_count', 0)} |")
        lines.append(f"| Hypotheses | {stats.get('hypothesis_count', 0)} |")
        lines.append(f"| Experiment Proposals | {stats.get('experiment_proposal_count', 0)} |")
        lines.append(f"| Feasibility Assessments | {stats.get('feasibility_count', 0)} |")
        lines.append(f"| Validation Plans | {stats.get('validation_plan_count', 0)} |")
        lines.append(f"| Relationships | {stats.get('relationship_count', 0)} |")
        lines.append(f"| Quantity Records | {qty.get('total', 0)} |")
        lines.append(f"| Tables | {len(tables)} |")
        lines.append(f"| Figures | {len(figures)} |")
        lines.append("")

        # --- 13. 来源审计 ---
        lines.append("## 13. 数据来源审计")
        lines.append("")
        audit = json_report.get("provenance_audit", {})
        pc = audit.get("provenance_counts", {})
        sc = audit.get("status_counts", {})
        lines.append(f"知识对象总数: **{audit.get('total_knowledge_objects', 0)}**")
        lines.append("")
        lines.append("### 来源标注 (provenance_label)")
        lines.append("| 标注 | 数量 | 含义 |")
        lines.append("|------|------|------|")
        lines.append(f"| DERIVED | {pc.get('DERIVED', 0)} | 从六维抽取字段映射 |")
        lines.append(f"| EXTRACTED | {pc.get('EXTRACTED', 0)} | 从QuantityRecord/ScientificObject管线 |")
        lines.append(f"| INFERRED | {pc.get('INFERRED', 0)} | 系统从空字段推断 |")
        lines.append("")
        lines.append("### 状态标注 (status_label)")
        lines.append("| 标注 | 数量 | 含义 |")
        lines.append("|------|------|------|")
        for label in ["EXTRACTED", "SOURCE_LINKED", "EVIDENCE_VERIFIED", "NOT_REPORTED",
                       "NOT_EXTRACTED", "UNRESOLVED", "NOT_IMPLEMENTED", "EXPERT_PENDING"]:
            if sc.get(label, 0) > 0:
                meanings = {
                    "EXTRACTED": "已从文档提取",
                    "SOURCE_LINKED": "已关联到原文位置",
                    "EVIDENCE_VERIFIED": "经证据核查确认",
                    "NOT_REPORTED": "文档中未报告",
                    "NOT_EXTRACTED": "未尝试提取",
                    "UNRESOLVED": "系统推断待确认",
                    "NOT_IMPLEMENTED": "功能未实现",
                    "EXPERT_PENDING": "待专家确认",
                }
                lines.append(f"| {label} | {sc[label]} | {meanings[label]} |")
        lines.append("")
        lines.append(f"合成SourceAnchor对象数: {audit.get('objects_with_synthetic_anchors', 0)}")
        lines.append("")
        lines.append(f"> {audit.get('audit_note', '')}")
        lines.append("")

        lines.append("---")
        lines.append(f"*报告结束 — {self.doc_id} — {json_report['generated_at']}*")

        return "\n".join(lines)

    def _md_section(self, lines, num, title, count, items, id_field, content_field, extra_fields=None):
        lines.append(f"### {num} {title} ({count}个)")
        lines.append("")
        if not items:
            lines.append("*未报告 / 未抽取*")
            lines.append("")
            return
        for item in items:
            obj_id = item.get(id_field, "?")
            content = item.get(content_field, "")
            if len(content) > 300:
                content = content[:300] + "..."
            source = item.get("source", item.get("status", ""))
            status = item.get("status", "REPORTED")
            anchor = item.get("source_anchor", {})
            anchor_str = f" → `{anchor.get('element_id', '')}`" if anchor else ""

            line = f"- **{obj_id}**: {content}"
            if extra_fields:
                extras = []
                for ef in extra_fields:
                    v = item.get(ef)
                    if v:
                        extras.append(f"{ef}={v}")
                if extras:
                    line += f"  [{', '.join(extras)}]"
            pl = item.get("provenance_label", "")
            sl = item.get("status_label", "")
            label_str = f" [{pl}/{sl}]" if pl and sl else ""
            line += f"  *({status}{anchor_str}{label_str})*"
            lines.append(line)
        lines.append("")

    def _identify_missing(self, json_report: dict) -> list[str]:
        missing = []
        six_dim = json_report.get("six_dimension_extraction", {})
        loaded_dims = six_dim.get("dimension_count", 0)
        if loaded_dims < 6:
            all_dims = ["catalyst_design", "characterization", "performance",
                        "mechanism", "structure_activity", "reliability"]
            loaded = six_dim.get("dimensions_loaded", [])
            not_loaded = [d for d in all_dims if d not in loaded]
            missing.append(f"六维抽取缺失: {', '.join(not_loaded)}")

        qty = json_report.get("quantity_records", {})
        pending = qty.get("pending_validation", 0)
        if pending > 0:
            missing.append(f"{pending}条QuantityRecord仍为PENDING_VALIDATION（缺少SourceAnchor）")

        fig_assoc = json_report.get("figure_associations", [])
        unresolved = len([a for a in fig_assoc if a.get("status") == "UNRESOLVED"])
        if unresolved > 0:
            missing.append(f"{unresolved}个图关联未解析 (UNRESOLVED)")

        tables = json_report.get("tables", [])
        if not tables:
            missing.append("未检测到表格元素（Document IR中无table类型）")

        for obj_type, count_key in [
            ("limitations", "limitation_count"),
            ("open_questions", "open_question_count"),
            ("hypotheses", "hypothesis_count"),
            ("experiment_proposals", "experiment_proposal_count"),
            ("feasibility_assessments", "feasibility_count"),
            ("validation_plans", "validation_plan_count"),
        ]:
            if not self.knowledge.get(obj_type):
                missing.append(f"{obj_type.replace('_', ' ').title()}: 未报告/未抽取")

        if not missing:
            missing.append("无显著缺失项")

        return missing


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def generate_single_doc_report(doc_id: str, output_dir: Optional[Path] = None) -> tuple[dict, str]:
    """为单篇文档生成完整报告。

    Returns:
        (json_report, markdown_text)
    """
    if output_dir is None:
        output_dir = RUNS_ROOT / "single_doc_reports" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)

    gen = ReportGenerator(doc_id)
    json_report = gen.generate_json()
    markdown_text = gen.generate_markdown(json_report)

    json_path = output_dir / f"{doc_id}_knowledge_report.json"
    md_path = output_dir / f"{doc_id}_knowledge_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)

    print(f"[OK] {doc_id}: JSON → {json_path}")
    print(f"[OK] {doc_id}: MD  → {md_path}")

    return json_report, markdown_text


def generate_all_reports() -> dict:
    """为所有试点文档生成报告。"""
    doc_ids = ["F02", "F07", "P01", "PAT01"]
    results = {}

    for doc_id in doc_ids:
        print(f"\n{'='*60}")
        print(f"Generating report for {doc_id}...")
        print(f"{'='*60}")
        try:
            json_report, md_text = generate_single_doc_report(doc_id)
            stats = json_report.get("statistics", {})
            results[doc_id] = {
                "status": "SUCCESS",
                "json_path": str(RUNS_ROOT / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.json"),
                "md_path": str(RUNS_ROOT / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.md"),
                "statistics": stats,
                "quantity_records": json_report.get("quantity_records", {}).get("total", 0),
                "tables": json_report.get("document_structure", {}).get("table_elements", 0),
                "figures": json_report.get("document_structure", {}).get("figure_elements", 0),
            }
        except Exception as e:
            results[doc_id] = {"status": "FAILED", "error": str(e)}
            import traceback
            traceback.print_exc()

    return results


if __name__ == "__main__":
    results = generate_all_reports()
    print("\n" + "=" * 60)
    print("SINGLE-DOC-REPORT-001 Results:")
    print("=" * 60)
    for doc_id, result in results.items():
        status = result["status"]
        if status == "SUCCESS":
            stats = result["statistics"]
            print(f"  {doc_id}: {status} | "
                  f"Facts={stats.get('fact_count',0)} "
                  f"Claims={stats.get('claim_count',0)} "
                  f"Evidence={stats.get('evidence_count',0)} "
                  f"Rels={stats.get('relationship_count',0)} "
                  f"Qty={result['quantity_records']}")
        else:
            print(f"  {doc_id}: {status} — {result.get('error', '')}")
