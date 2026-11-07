"""
SINGLE-DOC-AUDIT-UI-008 Part A: 全流程产物对账
生成统一产物索引 + 专项对账报告
"""
import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE = Path("D:/Knowledge_World")
OUTPUT_DIR = BASE / "runs" / "audit_008"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path, chunk_size=8192):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def safe_json_load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ============================================================
# 1. 统一产物索引
# ============================================================
artifacts = []

# --- 1.1 原始文档 (unified_test_manifest.json) ---
manifest = safe_json_load(BASE / "data/test_corpus/unified_test_manifest.json")
if manifest:
    for doc in manifest.get("documents", []):
        artifacts.append({
            "document_id": doc["document_id"],
            "artifact_type": "source_document",
            "source_path": doc["file_path"],
            "artifact_path": doc["file_path"],
            "file_type": doc["document_type"],
            "file_size_bytes": doc["file_size_bytes"],
            "sha256": doc.get("sha256"),
            "signature_valid": doc.get("signature_valid"),
            "status": "VERIFIED" if doc.get("signature_valid") else "UNVERIFIED",
            "version": "original",
            "parent_document_id": None,
            "generation_batch": "FLOW-VERIFY-001"
        })

# --- 1.2 P01主论文 (LINK-001) ---
link01_pdf = BASE / "data/test_corpus/link01_pair/P01_main.pdf"
if link01_pdf.exists():
    artifacts.append({
        "document_id": "P01_main",
        "artifact_type": "source_document",
        "source_path": str(link01_pdf),
        "artifact_path": str(link01_pdf),
        "file_type": "research_article",
        "file_size_bytes": link01_pdf.stat().st_size,
        "sha256": sha256_file(link01_pdf),
        "signature_valid": True,
        "status": "VERIFIED",
        "version": "original",
        "parent_document_id": "P01",
        "generation_batch": "LINK-001"
    })

# --- 1.3 MinerU解析输出 (每个batch取最终版本) ---
mineru_base = BASE / "data/test_corpus/mineru_output"
mineru_final_batches = {}

# 定义每个文档的最终batch（优先取final/v2/batch，跳过test/regression/segmented）
skip_patterns = ["_test", "_regression", "_segmented", "_v2", "_manual_test"]
priority_patterns = ["_final", "_batch", "_v2"]

if mineru_base.exists():
    for batch_dir in sorted(mineru_base.iterdir()):
        if not batch_dir.is_dir():
            continue
        name = batch_dir.name
        # 跳过非最终版本
        is_final = any(p in name for p in priority_patterns)
        is_skip = any(p in name for p in skip_patterns) and not is_final
        if is_skip:
            continue

        # 找 .md 文件
        md_files = list(batch_dir.rglob("*.md"))
        if not md_files:
            continue

        md_file = md_files[0]
        # 提取文档ID
        if name.startswith("F"):
            doc_id = name.split("_")[0]
        elif name.startswith("P"):
            doc_id = name.split("_")[0]
        elif name.startswith("PAT"):
            doc_id = name.split("_")[0]
        else:
            continue

        # 如果已有记录且是final版本，覆盖
        if doc_id in mineru_final_batches:
            existing = mineru_final_batches[doc_id]
            if "final" in name and "final" not in existing["batch"]:
                mineru_final_batches[doc_id] = {"batch": name, "md": md_file}
        else:
            mineru_final_batches[doc_id] = {"batch": name, "md": md_file}

for doc_id, info in mineru_final_batches.items():
    md_file = info["md"]
    content = md_file.read_text(encoding="utf-8", errors="replace")
    line_count = len(content.splitlines())

    artifacts.append({
        "document_id": doc_id,
        "artifact_type": "mineru_parsed_markdown",
        "source_path": f"data/test_corpus/mineru_output/{info['batch']}",
        "artifact_path": str(md_file.relative_to(BASE)),
        "file_type": "markdown",
        "file_size_bytes": md_file.stat().st_size,
        "line_count": line_count,
        "sha256": sha256_file(md_file),
        "status": "PARSED",
        "version": "v1",
        "parent_document_id": doc_id,
        "generation_batch": info["batch"]
    })

# --- 1.4 图像文件统计 ---
if mineru_base.exists():
    for doc_id in list(mineru_final_batches.keys()):
        batch_name = mineru_final_batches[doc_id]["batch"]
        img_dir = mineru_base / batch_name
        images = list(img_dir.rglob("*.jpg")) + list(img_dir.rglob("*.png"))
        if images:
            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "mineru_extracted_images",
                "source_path": f"data/test_corpus/mineru_output/{batch_name}",
                "artifact_path": str(img_dir.relative_to(BASE)),
                "file_type": "image_directory",
                "image_count": len(images),
                "total_size_bytes": sum(f.stat().st_size for f in images),
                "status": "EXTRACTED",
                "version": "v1",
                "parent_document_id": doc_id,
                "generation_batch": batch_name
            })

# --- 1.5 Document IR (content_list.json) ---
if mineru_base.exists():
    for doc_id, info in mineru_final_batches.items():
        batch_name = info["batch"]
        cl_files = list((mineru_base / batch_name).rglob("*content_list.json"))
        for cl in cl_files:
            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "document_ir_content_list",
                "source_path": str(cl.relative_to(BASE)),
                "artifact_path": str(cl.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": cl.stat().st_size,
                "status": "GENERATED",
                "version": "v1",
                "parent_document_id": doc_id,
                "generation_batch": batch_name
            })

# --- 1.6 EXT-001 六维LLM抽取 ---
ext01_dir = BASE / "data/test_corpus/ext01_output"
if ext01_dir.exists():
    # Phase2 per-dimension
    phase2 = ext01_dir / "phase2_per_dimension"
    if phase2.exists():
        for dim_file in phase2.glob("*_extracted.json"):
            dim_name = dim_file.name.replace("_extracted.json", "")
            artifacts.append({
                "document_id": "P01",
                "artifact_type": "llm_dimension_extraction",
                "dimension": dim_name,
                "source_path": "data/test_corpus/ext01_output/phase2_per_dimension",
                "artifact_path": str(dim_file.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": dim_file.stat().st_size,
                "status": "EXTRACTED",
                "version": "phase2",
                "parent_document_id": "P01",
                "generation_batch": "EXT-001-Phase2"
            })

    # P01 main ext01 LLM
    for f in ["P01_main_ext01_llm.json", "P01_main_ext01_v2_corrected.json"]:
        fp = ext01_dir / f
        if fp.exists():
            artifacts.append({
                "document_id": "P01",
                "artifact_type": "llm_six_dimension_extraction",
                "source_path": "data/test_corpus/ext01_output",
                "artifact_path": str(fp.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": fp.stat().st_size,
                "status": "EXTRACTED",
                "version": "v2_corrected" if "v2" in f else "v1",
                "parent_document_id": "P01",
                "generation_batch": "EXT-001"
            })

# --- 1.7 G3 多文献结构化抽取 ---
g3_dir = BASE / "data/test_corpus/g3_output"
if g3_dir.exists():
    for doc_id in ["F02", "F07", "P01", "PAT01"]:
        doc_g3 = g3_dir / doc_id
        if not doc_g3.exists():
            continue

        # 各维度抽取
        for dim_file in sorted(doc_g3.glob("*_extracted.json")):
            dim_name = dim_file.name.replace("_extracted.json", "")
            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "g3_dimension_extraction",
                "dimension": dim_name,
                "source_path": str(doc_g3.relative_to(BASE)),
                "artifact_path": str(dim_file.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": dim_file.stat().st_size,
                "status": "EXTRACTED",
                "version": "v1",
                "parent_document_id": doc_id,
                "generation_batch": "G3-01"
            })

        # 科学对象
        so_file = doc_g3 / "scientific_objects.json"
        if so_file.exists():
            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "scientific_objects_structured",
                "source_path": str(doc_g3.relative_to(BASE)),
                "artifact_path": str(so_file.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": so_file.stat().st_size,
                "status": "STRUCTURED",
                "version": "v1",
                "parent_document_id": doc_id,
                "generation_batch": "G3-02"
            })

        # 分类
        cls_file = doc_g3 / "classification.json"
        if cls_file.exists():
            cls_data = safe_json_load(cls_file)
            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "taxonomy_classification",
                "source_path": str(doc_g3.relative_to(BASE)),
                "artifact_path": str(cls_file.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": cls_file.stat().st_size,
                "status": "CLASSIFIED" if cls_data else "FAILED",
                "version": "v1",
                "parent_document_id": doc_id,
                "generation_batch": "G3-03"
            })

        # QA验证
        qa_file = doc_g3 / "qa_verification.json"
        if qa_file.exists():
            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "qa_verification",
                "source_path": str(doc_g3.relative_to(BASE)),
                "artifact_path": str(qa_file.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": qa_file.stat().st_size,
                "status": "VERIFIED",
                "version": "v1",
                "parent_document_id": doc_id,
                "generation_batch": "G3-04"
            })

# --- 1.8 XLSX附件处理 ---
xlsx_sqlite = BASE / "data/test_corpus/xlsx_sqlite"
if xlsx_sqlite.exists():
    for db_file in xlsx_sqlite.glob("*.db"):
        doc_id = "P06" if "62293" in db_file.name else "P07" if "72061" in db_file.name else db_file.stem
        meta_file = xlsx_sqlite / f"{db_file.stem.replace('.db','')}_metadata.json"
        meta = safe_json_load(meta_file) if meta_file.exists() else {}
        artifacts.append({
            "document_id": doc_id,
            "artifact_type": "xlsx_sqlite_database",
            "source_path": f"data/test_corpus/xlsx_sqlite/{db_file.name}",
            "artifact_path": str(db_file.relative_to(BASE)),
            "file_type": "sqlite",
            "file_size_bytes": db_file.stat().st_size,
            "metadata": meta,
            "status": "LOADED",
            "version": "v1",
            "parent_document_id": doc_id,
            "generation_batch": "FLOW-VERIFY-001"
        })

# --- 1.9 ZIP附件处理 ---
zip_proc = BASE / "data/test_corpus/zip_processed"
if zip_proc.exists():
    zip_summary = safe_json_load(zip_proc / "zip_processing_summary.json")
    zip_json = zip_proc / "P01_41467_2024_50691_MOESM4_ESM.json"
    if zip_json.exists():
        artifacts.append({
            "document_id": "P01",
            "artifact_type": "zip_attachment_extracted",
            "source_path": "data/test_corpus/zip_processed",
            "artifact_path": str(zip_json.relative_to(BASE)),
            "file_type": "json",
            "file_size_bytes": zip_json.stat().st_size,
            "entry_count": zip_summary.get("total_entries") if zip_summary else None,
            "status": "EXTRACTED",
            "version": "v1",
            "parent_document_id": "P01",
            "generation_batch": "FLOW-VERIFY-001"
        })

# --- 1.10 RapidTable表格结构化 ---
evidence004 = safe_json_load(BASE / "runs/evidence_004/part_c_rapidtable_structuring.json")
if evidence004:
    artifacts.append({
        "document_id": "MULTI",
        "artifact_type": "rapidtable_structuring",
        "source_path": "runs/evidence_004/part_c_rapidtable_structuring.json",
        "artifact_path": "runs/evidence_004/part_c_rapidtable_structuring.json",
        "file_type": "json",
        "file_size_bytes": (BASE / "runs/evidence_004/part_c_rapidtable_structuring.json").stat().st_size,
        "status": "STRUCTURED",
        "version": "v1",
        "parent_document_id": None,
        "generation_batch": "EVIDENCE-004"
    })

# --- 1.11 单篇知识报告 (最终JSON+MD) ---
report_base = BASE / "runs/single_doc_reports"
if report_base.exists():
    for doc_id in ["F02", "F07", "P01", "PAT01"]:
        doc_dir = report_base / doc_id
        if not doc_dir.exists():
            continue

        json_report = doc_dir / f"{doc_id}_knowledge_report.json"
        md_report = doc_dir / f"{doc_id}_knowledge_report.md"

        if json_report.exists():
            report_data = safe_json_load(json_report)
            ko_count = 0
            rel_count = 0
            if report_data:
                ko = report_data.get("knowledge_objects", {})
                ko_count = sum(len(v) for v in ko.values()) if isinstance(ko, dict) else 0
                rel_count = len(report_data.get("relationships", []))

            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "single_doc_report_json",
                "source_path": f"data/test_corpus/g3_output/{doc_id}",
                "artifact_path": str(json_report.relative_to(BASE)),
                "file_type": "json",
                "file_size_bytes": json_report.stat().st_size,
                "knowledge_object_count": ko_count,
                "relationship_count": rel_count,
                "generator_version": report_data.get("generator_version") if report_data else None,
                "status": "GENERATED",
                "version": "v2",
                "parent_document_id": doc_id,
                "generation_batch": "SINGLE-DOC-REPORT-002"
            })

        if md_report.exists():
            artifacts.append({
                "document_id": doc_id,
                "artifact_type": "single_doc_report_markdown",
                "source_path": f"data/test_corpus/g3_output/{doc_id}",
                "artifact_path": str(md_report.relative_to(BASE)),
                "file_type": "markdown",
                "file_size_bytes": md_report.stat().st_size,
                "status": "GENERATED",
                "version": "v2",
                "parent_document_id": doc_id,
                "generation_batch": "SINGLE-DOC-REPORT-002"
            })

# --- 1.12 Canonical Store ---
cs_dir = BASE / "data/test_corpus/canonical_store"
if cs_dir.exists():
    store_index = safe_json_load(cs_dir / "store_index.json")
    for sub in ["documents", "extractions", "associations"]:
        sub_dir = cs_dir / sub
        if not sub_dir.exists():
            continue
        for f in sorted(sub_dir.iterdir()):
            if f.is_file() and f.suffix == ".json" and "backup" not in f.name:
                artifacts.append({
                    "document_id": f.stem.split("_")[0],
                    "artifact_type": f"canonical_store_{sub}",
                    "source_path": str(f.relative_to(BASE)),
                    "artifact_path": str(f.relative_to(BASE)),
                    "file_type": "json",
                    "file_size_bytes": f.stat().st_size,
                    "status": "STORED",
                    "version": "v1",
                    "parent_document_id": None,
                    "generation_batch": "CANONICAL-STORE-001"
                })

# --- 1.13 验证/审计报告产物 ---
audit_dirs = {
    "evidence_003": "SINGLE-DOC-EVIDENCE-003",
    "evidence_004": "SINGLE-DOC-EVIDENCE-004",
    "final_006": "SINGLE-DOC-FINAL-006",
    "v11_007": "SINGLE-DOC-V11-007",
    "v11_007_r1": "SINGLE-DOC-V11-007-R1",
}
for dir_name, batch_id in audit_dirs.items():
    audit_dir = BASE / "runs" / dir_name
    if not audit_dir.exists():
        continue
    for f in sorted(audit_dir.iterdir()):
        if f.is_file():
            artifacts.append({
                "document_id": "AUDIT",
                "artifact_type": "audit_report",
                "source_path": str(f.relative_to(BASE)),
                "artifact_path": str(f.relative_to(BASE)),
                "file_type": f.suffix.lstrip("."),
                "file_size_bytes": f.stat().st_size,
                "status": "COMPLETED",
                "version": "v1",
                "parent_document_id": None,
                "generation_batch": batch_id
            })

# --- 1.14 NUM-UNIT-001产物 ---
for dir_name, batch_id in [
    ("num_unit_001_final", "NUM-UNIT-001-FINAL"),
    ("num_unit_001_taskB_normalization", "NUM-UNIT-001-TaskB"),
    ("num_unit_001_taskC_integration", "NUM-UNIT-001-TaskC"),
]:
    d = BASE / "runs" / dir_name
    if not d.exists():
        continue
    for f in sorted(d.iterdir()):
        if f.is_file():
            artifacts.append({
                "document_id": "NUM-UNIT",
                "artifact_type": "numerical_unit_artifact",
                "source_path": str(f.relative_to(BASE)),
                "artifact_path": str(f.relative_to(BASE)),
                "file_type": f.suffix.lstrip("."),
                "file_size_bytes": f.stat().st_size,
                "status": "COMPLETED",
                "version": "v1",
                "parent_document_id": None,
                "generation_batch": batch_id
            })

# --- 1.15 SSPK-001 Schema产物 ---
for f in sorted(BASE.glob("runs/SSPK_001_*.md")) + sorted(BASE.glob("runs/SSPK_001_*.json")):
    if f.exists():
        artifacts.append({
            "document_id": "SCHEMA",
            "artifact_type": "schema_artifact",
            "source_path": str(f.relative_to(BASE)),
            "artifact_path": str(f.relative_to(BASE)),
            "file_type": f.suffix.lstrip("."),
            "file_size_bytes": f.stat().st_size,
            "status": "COMPLETED",
            "version": "v1",
            "parent_document_id": None,
            "generation_batch": "SSPK-001"
        })

# --- 1.16 LINK-001关联产物 ---
link01_json = BASE / "data/test_corpus/link01_pair/P01_link01_associations.json"
if link01_json.exists():
    artifacts.append({
        "document_id": "P01",
        "artifact_type": "link01_association",
        "source_path": "data/test_corpus/link01_pair",
        "artifact_path": str(link01_json.relative_to(BASE)),
        "file_type": "json",
        "file_size_bytes": link01_json.stat().st_size,
        "status": "VERIFIED",
        "version": "v1",
        "parent_document_id": "P01",
        "generation_batch": "LINK-001"
    })

# --- 1.17 G3-VERIFY/CLOSE产物 ---
for f in sorted(BASE.glob("runs/G3_*.json")) + sorted(BASE.glob("runs/G3_*.md")):
    if f.exists():
        batch = f.stem.split("_")[0] + "_" + f.stem.split("_")[1] if "_" in f.stem else f.stem
        artifacts.append({
            "document_id": "G3",
            "artifact_type": "g3_verification_artifact",
            "source_path": str(f.relative_to(BASE)),
            "artifact_path": str(f.relative_to(BASE)),
            "file_type": f.suffix.lstrip("."),
            "file_size_bytes": f.stat().st_size,
            "status": "COMPLETED",
            "version": "v1",
            "parent_document_id": None,
            "generation_batch": batch
        })

# ============================================================
# 2. 保存统一索引
# ============================================================
index = {
    "index_version": "1.0",
    "generated_at": datetime.now().isoformat(),
    "project": "Catalyst Knowledge Base V2",
    "audit_batch": "SINGLE-DOC-AUDIT-UI-008-PartA",
    "total_artifacts": len(artifacts),
    "artifacts": artifacts
}

index_path = OUTPUT_DIR / "unified_artifact_index.json"
with open(index_path, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"统一产物索引已生成: {index_path}")
print(f"总产物数: {len(artifacts)}")

# 按类型统计
by_type = defaultdict(int)
by_status = defaultdict(int)
by_batch = defaultdict(int)
by_doc = defaultdict(int)

for a in artifacts:
    by_type[a["artifact_type"]] += 1
    by_status[a["status"]] += 1
    by_batch[a["generation_batch"]] += 1
    by_doc[a["document_id"]] += 1

print("\n=== 按产物类型 ===")
for t, c in sorted(by_type.items()):
    print(f"  {t}: {c}")

print("\n=== 按状态 ===")
for s, c in sorted(by_status.items()):
    print(f"  {s}: {c}")

print("\n=== 按生成批次 ===")
for b, c in sorted(by_batch.items()):
    print(f"  {b}: {c}")

print("\n=== 按文档ID ===")
for d, c in sorted(by_doc.items(), key=lambda x: -x[1]):
    print(f"  {d}: {c}")
