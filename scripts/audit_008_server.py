"""
SINGLE-DOC-AUDIT-UI-008 Part B+C+D: 审计数据接口 + HTML工作台
轻量本地HTTP服务器，提供只读API和前端界面
"""
import json
import os
import sys
import hashlib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data" / "test_corpus"
RUNS_DIR = BASE / "runs"
REVIEWS_DIR = RUNS_DIR / "audit_008" / "reviews"
REVIEWS_DIR.mkdir(parents=True, exist_ok=True)

HOST = "127.0.0.1"
PORT = 8090


def safe_json_load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e), "_path": str(path)}


def sha256_short(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read(8192))
        return h.hexdigest()[:16]
    except Exception:
        return None


# ============================================================
# 数据层：只读Audit View
# ============================================================

def get_manifest():
    return safe_json_load(DATA_DIR / "unified_test_manifest.json")


def get_all_document_ids():
    """返回所有已处理的文档ID列表"""
    docs = []
    manifest = get_manifest()
    if manifest and "_error" not in manifest:
        for doc in manifest.get("documents", []):
            docs.append({
                "document_id": doc["document_id"],
                "group": doc.get("group", ""),
                "document_type": doc.get("document_type", ""),
                "file_path": doc.get("file_path", ""),
                "file_size_bytes": doc.get("file_size_bytes", 0),
                "signature_valid": doc.get("signature_valid", False),
                "has_deep_structuring": doc["document_id"] in ["F02", "F07", "P01", "PAT01"]
            })
    # P01_main
    link01_pdf = DATA_DIR / "link01_pair" / "P01_main.pdf"
    if link01_pdf.exists():
        docs.append({
            "document_id": "P01_main",
            "group": "LINK-001",
            "document_type": "research_article",
            "file_path": str(link01_pdf),
            "file_size_bytes": link01_pdf.stat().st_size,
            "signature_valid": True,
            "has_deep_structuring": True
        })
    return docs


def get_document_overview(doc_id):
    """文档概览：元数据 + 处理状态"""
    overview = {
        "document_id": doc_id,
        "mineru_output": None,
        "images": [],
        "tables": [],
        "figures": [],
        "equations": [],
        "six_dimension_extraction": None,
        "scientific_objects": None,
        "knowledge_objects": None,
        "knowledge_relationships": None,
        "quantity_records": [],
        "classification": None,
        "qa_verification": None,
        "single_doc_report": None,
        "experiment_chain": None,
        "source_anchor_stats": None,
    }

    # MinerU output
    mineru_base = DATA_DIR / "mineru_output"
    for batch_dir in sorted(mineru_base.iterdir(), reverse=True):
        if not batch_dir.is_dir():
            continue
        if doc_id.lower() in batch_dir.name.lower():
            md_files = list(batch_dir.rglob("*.md"))
            if md_files:
                md_file = md_files[0]
                content = md_file.read_text(encoding="utf-8", errors="replace")
                overview["mineru_output"] = {
                    "batch": batch_dir.name,
                    "md_path": str(md_file),
                    "md_size_bytes": md_file.stat().st_size,
                    "line_count": len(content.splitlines()),
                    "char_count": len(content),
                    "content_preview": content[:2000]
                }
                # Images
                img_dir = md_file.parent / "images"
                if img_dir.exists():
                    imgs = sorted(img_dir.iterdir())
                    overview["images"] = [
                        {"path": str(f), "size_bytes": f.stat().st_size}
                        for f in imgs if f.is_file()
                    ][:50]
                break

    # G3 output (only for F02/F07/P01/PAT01)
    g3_dir = DATA_DIR / "g3_output" / doc_id
    if g3_dir.exists():
        # Six dimension extraction
        dims = {}
        for f in g3_dir.glob("*_extracted.json"):
            dim_name = f.name.replace("_extracted.json", "")
            dims[dim_name] = safe_json_load(f)
        if dims:
            overview["six_dimension_extraction"] = dims

        # Scientific objects
        so_file = g3_dir / "scientific_objects.json"
        if so_file.exists():
            overview["scientific_objects"] = safe_json_load(so_file)

        # Classification
        cls_file = g3_dir / "classification.json"
        if cls_file.exists():
            overview["classification"] = safe_json_load(cls_file)

        # QA verification
        qa_file = g3_dir / "qa_verification.json"
        if qa_file.exists():
            overview["qa_verification"] = safe_json_load(qa_file)

    # Single doc report
    report_json = RUNS_DIR / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.json"
    if report_json.exists():
        report = safe_json_load(report_json)
        if "_error" not in report:
            overview["single_doc_report"] = {
                "report_id": report.get("report_id"),
                "generator_version": report.get("generator_version"),
                "generated_at": report.get("generated_at"),
                "document_overview": report.get("document_overview", {}),
                "document_structure": report.get("document_structure", {}),
                "tables": report.get("tables", []),
                "figures": report.get("figures", []),
                "knowledge_objects": report.get("knowledge_objects", {}),
                "knowledge_relationships": report.get("knowledge_relationships", []),
                "scientific_objects": report.get("scientific_objects", {}),
                "quantity_records": report.get("quantity_records", []),
                "classification": report.get("classification", {}),
                "qa_verification": report.get("qa_verification", {}),
                "statistics": report.get("statistics", {}),
                "provenance": report.get("provenance", {}),
            }

            # Extract report MD
            report_md = RUNS_DIR / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.md"
            if report_md.exists():
                overview["single_doc_report"]["markdown_content"] = report_md.read_text(encoding="utf-8", errors="replace")

    # EXT-001 (P01 only)
    if doc_id == "P01":
        ext01_dir = DATA_DIR / "ext01_output"
        phase2 = ext01_dir / "phase2_per_dimension"
        if phase2.exists():
            dims = {}
            for f in phase2.glob("*_extracted.json"):
                dim_name = f.name.replace("_extracted.json", "")
                dims[dim_name] = safe_json_load(f)
            overview["six_dimension_extraction"] = dims

    # Experiment chain audit
    v11_exp = safe_json_load(RUNS_DIR / "v11_007" / "part_b_experiment_chain_audit.json")
    if v11_exp and "_error" not in v11_exp and doc_id in v11_exp.get("documents", {}):
        overview["experiment_chain"] = v11_exp["documents"][doc_id]

    # Source anchor stats
    r1_anchor = safe_json_load(RUNS_DIR / "v11_007_r1" / "part_c_source_anchor_audit.json")
    if r1_anchor and "_error" not in r1_anchor:
        cats = r1_anchor.get("source_anchor_categories", {}).get(doc_id, {})
        if cats:
            overview["source_anchor_stats"] = cats

    return overview


def get_reviews(doc_id=None):
    """读取审核记录"""
    reviews = []
    for f in sorted(REVIEWS_DIR.iterdir()):
        if f.suffix == ".json":
            review = safe_json_load(f)
            if doc_id is None or review.get("document_id") == doc_id:
                reviews.append(review)
    return reviews


def save_review(review_data):
    """保存审核记录"""
    doc_id = review_data.get("document_id", "unknown")
    object_id = review_data.get("object_id", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{doc_id}_{object_id}_{timestamp}.json"
    filepath = REVIEWS_DIR / filename

    review_data["saved_at"] = datetime.now().isoformat()
    review_data["review_id"] = f"review_{timestamp}_{hashlib.md5(filename.encode()).hexdigest()[:8]}"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(review_data, f, ensure_ascii=False, indent=2)

    return review_data


# ============================================================
# HTTP Handler
# ============================================================

class AuditHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path == "/api/documents":
            self.send_json(get_all_document_ids())
        elif path.startswith("/api/document/") and path.endswith("/overview"):
            doc_id = path.split("/")[3]
            self.send_json(get_document_overview(doc_id))
        elif path.startswith("/api/document/") and path.endswith("/report"):
            doc_id = path.split("/")[3]
            report_json = RUNS_DIR / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.json"
            if report_json.exists():
                self.send_json(safe_json_load(report_json))
            else:
                self.send_json({"error": "Report not found", "doc_id": doc_id}, 404)
        elif path.startswith("/api/document/") and path.endswith("/source"):
            doc_id = path.split("/")[3]
            overview = get_document_overview(doc_id)
            if overview["mineru_output"]:
                md_path = overview["mineru_output"]["md_path"]
                if os.path.exists(md_path):
                    content = Path(md_path).read_text(encoding="utf-8", errors="replace")
                    self.send_json({"document_id": doc_id, "markdown": content, "line_count": len(content.splitlines())})
                else:
                    self.send_json({"error": "MD file not found", "path": md_path}, 404)
            else:
                self.send_json({"error": "No MinerU output", "doc_id": doc_id}, 404)
        elif path.startswith("/api/document/") and path.endswith("/relationships"):
            doc_id = path.split("/")[3]
            report_json = RUNS_DIR / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.json"
            if report_json.exists():
                report = safe_json_load(report_json)
                rels = report.get("knowledge_relationships", [])
                self.send_json({"document_id": doc_id, "relationships": rels, "count": len(rels)})
            else:
                self.send_json({"error": "Report not found"}, 404)
        elif path.startswith("/api/document/") and path.endswith("/objects"):
            doc_id = path.split("/")[3]
            report_json = RUNS_DIR / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.json"
            if report_json.exists():
                report = safe_json_load(report_json)
                ko = report.get("knowledge_objects", {})
                so = report.get("scientific_objects", {})
                self.send_json({
                    "document_id": doc_id,
                    "knowledge_objects": ko,
                    "scientific_objects": so,
                    "knowledge_object_count": sum(len(v) for v in ko.values()),
                })
            else:
                self.send_json({"error": "Report not found"}, 404)
        elif path.startswith("/api/document/") and path.endswith("/experiments"):
            doc_id = path.split("/")[3]
            v11_exp = safe_json_load(RUNS_DIR / "v11_007" / "part_b_experiment_chain_audit.json")
            if v11_exp and "_error" not in v11_exp and doc_id in v11_exp.get("documents", {}):
                self.send_json(v11_exp["documents"][doc_id])
            else:
                self.send_json({"error": "No experiment data", "doc_id": doc_id}, 404)
        elif path.startswith("/api/document/") and path.endswith("/images"):
            doc_id = path.split("/")[3]
            overview = get_document_overview(doc_id)
            self.send_json({"document_id": doc_id, "images": overview.get("images", [])})
        elif path.startswith("/api/document/") and path.endswith("/tables"):
            doc_id = path.split("/")[3]
            report_json = RUNS_DIR / "single_doc_reports" / doc_id / f"{doc_id}_knowledge_report.json"
            if report_json.exists():
                report = safe_json_load(report_json)
                tables = report.get("tables", [])
                self.send_json({"document_id": doc_id, "tables": tables, "count": len(tables)})
            else:
                self.send_json({"error": "Report not found"}, 404)
        elif path == "/api/audit/reviews":
            doc_id = params.get("doc_id", [None])[0]
            self.send_json(get_reviews(doc_id))
        elif path == "/api/audit/reconciliation":
            recon = safe_json_load(RUNS_DIR / "audit_008" / "part_a_reconciliation.json")
            self.send_json(recon)
        elif path == "/api/audit/inventory":
            inv = safe_json_load(RUNS_DIR / "audit_008" / "unified_artifact_index.json")
            self.send_json(inv)
        elif path == "/api/health":
            self.send_json({"status": "ok", "timestamp": datetime.now().isoformat()})
        elif path == "/" or path == "/index.html":
            self.send_html()
        elif path.startswith("/api/images/"):
            # Serve images from MinerU output: /api/images/{doc_id}/{filename}
            parts = path.split("/")
            if len(parts) >= 4:
                doc_id = parts[3]
                filename = "/".join(parts[4:])
                # Try different batch naming patterns
                patterns = [
                    DATA_DIR / "mineru_output" / f"{doc_id}_batch" / "main" / "auto" / "images" / filename,
                    DATA_DIR / "mineru_output" / f"{doc_id}_final" / "main" / "auto" / "images" / filename,
                    DATA_DIR / "mineru_output" / f"{doc_id}_regression" / "main" / "auto" / "images" / filename,
                    DATA_DIR / "mineru_output" / doc_id / "main" / "auto" / "images" / filename,
                ]
                for img_path in patterns:
                    if img_path.exists() and img_path.is_file():
                        # Determine content type
                        ext = img_path.suffix.lower()
                        ct = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext[1:], "application/octet-stream")
                        self.send_file(img_path, ct)
                        return
                self.send_error(404, f"Image not found: {doc_id}/{filename}")
            else:
                self.send_error(400, "Invalid image path")
        elif path.startswith("/static/"):
            # Serve static files from runs/audit_008/www/
            rel_path = path.replace("/static/", "")
            file_path = RUNS_DIR / "audit_008" / "www" / rel_path
            if file_path.exists() and file_path.is_file():
                self.send_file(file_path)
            else:
                self.send_error(404, f"File not found: {rel_path}")
        else:
            self.send_error(404, f"Unknown route: {path}")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/audit/review":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                review_data = json.loads(body.decode("utf-8"))
                result = save_review(review_data)
                self.send_json(result, 201)
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, 400)
        else:
            self.send_error(404)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self):
        html_path = RUNS_DIR / "audit_008" / "www" / "index.html"
        if html_path.exists():
            self.send_file(html_path, "text/html; charset=utf-8")
        else:
            self.send_error(404, "index.html not found")

    def send_file(self, path, content_type="application/octet-stream"):
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def main():
    # Ensure www directory exists
    www_dir = RUNS_DIR / "audit_008" / "www"
    www_dir.mkdir(parents=True, exist_ok=True)

    server = HTTPServer((HOST, PORT), AuditHandler)
    print(f"Audit Workbench Server running at http://{HOST}:{PORT}")
    print(f"Data directory: {DATA_DIR}")
    print(f"Runs directory: {RUNS_DIR}")
    print(f"Reviews directory: {REVIEWS_DIR}")
    print(f"WWW directory: {www_dir}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
