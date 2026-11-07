"""Generate F02 Knowledge Report v3 - Readability-focused interactive HTML.

Reads all 014 pipeline outputs and produces a single-file HTML with:
- Left sidebar navigation
- Literature overview with key metadata
- Six dimensions as proper tables (not raw JSON)
- Figure gallery with embedded images and VLM observations
- Table explorer (honest about missing data)
- Evidence status labels and source anchors
- QA verification results
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RUN_DIR = Path(__file__).parent.parent / "examples" / "F02" / "data"
REPORT_JSON = RUN_DIR / "F02_knowledge_report.json"
VLM_RECORDS = RUN_DIR / "F02_vlm_science_records.json"
FIGURE_PARSER = RUN_DIR / "F02_figure_parser.json"
TABLE_PARSER = RUN_DIR / "F02_table_parser.json"
TABLE_SCIENCE = RUN_DIR / "F02_table_science_records.json"
EXTRACTION_V2_DIR = RUN_DIR / "extraction_v2"
IMAGES_DIR = Path(__file__).parent.parent / "examples" / "F02" / "images"
OUTPUT_HTML = Path(__file__).parent.parent / "examples" / "F02" / "F02_knowledge_report_v3.html"

DIMENSIONS = ["catalyst_design", "characterization", "performance", "mechanism", "structure_activity", "reliability"]
DIMENSION_LABELS = {
    "catalyst_design": "Catalyst Design",
    "characterization": "Characterization",
    "performance": "Performance",
    "mechanism": "Mechanism",
    "structure_activity": "Structure-Activity",
    "reliability": "Reliability",
}

STATUS_COLORS = {
    "REPORTED": "#22c55e",
    "NOT_REPORTED": "#94a3b8",
    "NOT_EXTRACTED": "#f59e0b",
    "UNRESOLVED": "#ef4444",
    "PASS": "#22c55e",
    "FAIL": "#ef4444",
    "WARN": "#f59e0b",
    "NOT_EXTRACTED": "#94a3b8",
}

ORIGIN_COLORS = {
    "ORIGINAL_EXPERIMENT": "#3b82f6",
    "LITERATURE_REFERENCE": "#8b5cf6",
    "SYSTEM_INFERRED": "#f59e0b",
    "UNKNOWN_ORIGIN": "#94a3b8",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        logger.warning("File not found: %s", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_dimension(dim: str) -> dict:
    path = EXTRACTION_V2_DIR / f"{dim}_v2_extracted.json"
    return load_json(path)


def image_to_base64(img_path: Path) -> Optional[str]:
    if not img_path.exists():
        return None
    with open(img_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    ext = img_path.suffix.lower().lstrip(".")
    if ext == "jpg":
        ext = "jpeg"
    return f"data:image/{ext};base64,{data}"


def escape_html(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#94a3b8")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;">{escape_html(status)}</span>'


def origin_badge(origin: str) -> str:
    color = ORIGIN_COLORS.get(origin, "#94a3b8")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{escape_html(origin)}</span>'


def format_field_value(value: Any, status: str = "") -> str:
    if value is None:
        return '<span style="color:#94a3b8;font-style:italic;">Not available</span>'
    if isinstance(value, str):
        if value in ("NOT_REPORTED", "NOT_EXTRACTED", "UNRESOLVED"):
            return f'<span style="color:#94a3b8;font-style:italic;">{escape_html(value)}</span>'
        return escape_html(value)
    if isinstance(value, (int, float)):
        return f"<strong>{value}</strong>"
    if isinstance(value, list):
        if len(value) == 0:
            return '<span style="color:#94a3b8;font-style:italic;">No data</span>'
        return format_array_as_table(value)
    if isinstance(value, dict):
        return format_dict_as_list(value)
    return escape_html(str(value))


def format_array_as_table(arr: list) -> str:
    if not arr:
        return '<span style="color:#94a3b8;">Empty</span>'
    if isinstance(arr[0], dict):
        headers = list(arr[0].keys())
        headers = [h for h in headers if h not in ("status", "origin", "source_quote")]
        rows_html = []
        for item in arr:
            cells = []
            for h in headers:
                val = item.get(h, "")
                cells.append(f"<td>{format_field_value(val)}</td>")
            rows_html.append("<tr>" + "".join(cells) + "</tr>")
        header_html = "".join(f"<th>{escape_html(h)}</th>" for h in headers)
        return f'<table class="nested-table"><thead><tr>{header_html}</tr></thead><tbody>{"".join(rows_html)}</tbody></table>'
    else:
        items = "".join(f"<li>{format_field_value(v)}</li>" for v in arr)
        return f"<ul>{items}</ul>"


def format_dict_as_list(d: dict) -> str:
    items = []
    for k, v in d.items():
        if k in ("status", "origin", "source_quote", "notes"):
            continue
        items.append(f"<li><strong>{escape_html(k)}:</strong> {format_field_value(v)}</li>")
    return f"<ul>{''.join(items)}</ul>"


def generate_overview_section(report: dict) -> str:
    overview = report.get("document_overview", {})
    classification = report.get("classification", {})
    stats = report.get("statistics", {})

    title = overview.get("title", "Unknown")
    doi = overview.get("doi", "")
    doc_type = overview.get("document_type", "")

    six_dim = report.get("six_dimension_extraction", {}).get("dimensions", {})
    catalyst_design = six_dim.get("catalyst_design", {})
    catalyst_system = catalyst_design.get("catalyst_system", "")
    reaction_type = catalyst_design.get("reaction_type", "")

    claims = report.get("knowledge_objects", {}).get("claims", [])
    key_claim = claims[0].get("content", "") if claims else ""

    reaction_labels = classification.get("reaction_type", {}).get("labels", [])
    catalyst_labels = classification.get("catalyst_type", {}).get("labels", [])

    html = f"""
    <div class="section-card">
        <h2>Literature Overview</h2>
        <table class="info-table">
            <tr><th>Title</th><td>{escape_html(title)}</td></tr>
            <tr><th>DOI</th><td>{escape_html(doi)}</td></tr>
            <tr><th>Type</th><td>{escape_html(doc_type)}</td></tr>
            <tr><th>Catalyst System</th><td>{escape_html(catalyst_system)}</td></tr>
            <tr><th>Reaction Type</th><td>{escape_html(reaction_type)}</td></tr>
            <tr><th>Classification</th><td>Reaction: {escape_html(', '.join(reaction_labels))} | Catalyst: {escape_html(', '.join(catalyst_labels))}</td></tr>
            <tr><th>Key Claim</th><td>{escape_html(key_claim)}</td></tr>
            <tr><th>Statistics</th><td>{stats.get('total_objects', 0)} objects, {stats.get('total_relationships', 0)} relationships</td></tr>
        </table>
    </div>
    """
    return html


def generate_dimension_section(dim: str, dim_data: dict) -> str:
    fields = dim_data.get("fields", {})
    label = DIMENSION_LABELS.get(dim, dim)

    rows_html = []
    for field_name, field_data in fields.items():
        if not isinstance(field_data, dict):
            continue
        status = field_data.get("status", "")
        origin = field_data.get("origin", "")
        value = field_data.get("value")
        source_quote = field_data.get("source_quote", "")

        value_html = format_field_value(value, status)
        status_html = status_badge(status)
        origin_html = origin_badge(origin) if origin else ""

        quote_html = ""
        if source_quote:
            quote_html = f'<div class="source-quote">{escape_html(source_quote[:200])}{"..." if len(source_quote) > 200 else ""}</div>'

        rows_html.append(f"""
        <tr>
            <td><strong>{escape_html(field_name)}</strong></td>
            <td>{value_html}</td>
            <td>{status_html} {origin_html}</td>
        </tr>
        """)

    warnings = dim_data.get("validation_warnings", [])
    warnings_html = ""
    if warnings:
        warnings_html = '<div class="warnings"><strong>Warnings:</strong><ul>' + "".join(f"<li>{escape_html(str(w))}</li>" for w in warnings) + "</ul></div>"

    merge_notes = dim_data.get("merge_notes", "")
    merge_html = f'<div class="merge-notes">Merge: {escape_html(merge_notes)}</div>' if merge_notes else ""

    html = f"""
    <div class="section-card" id="dim-{dim}">
        <h2>{escape_html(label)}</h2>
        <table class="data-table">
            <thead><tr><th>Field</th><th>Value</th><th>Status / Origin</th></tr></thead>
            <tbody>{"".join(rows_html)}</tbody>
        </table>
        {warnings_html}
        {merge_html}
    </div>
    """
    return html


def generate_figure_gallery(report: dict, vlm_data: dict, figure_parser: dict) -> str:
    figures = report.get("figures", [])
    vlm_records = vlm_data.get("results", [])
    figure_images = figure_parser.get("figures", [])

    img_map = {}
    for fig in figure_images:
        fig_id = fig.get("figure_id", "")
        img_path = fig.get("image_path", "")
        caption = fig.get("caption", "")
        img_map[fig_id] = {"path": img_path, "caption": caption}

    vlm_by_figure = {}
    for result in vlm_records:
        fig_id = result.get("figure_id", "")
        records = result.get("records", [])
        if fig_id not in vlm_by_figure:
            vlm_by_figure[fig_id] = []
        vlm_by_figure[fig_id].extend(records)

    cards_html = []
    for i, fig in enumerate(figures, 1):
        fig_id = f"F02_fig_{i:02d}"
        img_info = img_map.get(fig_id, {})
        img_path = img_info.get("path", "")
        caption = img_info.get("caption", "")

        img_b64 = None
        if img_path:
            full_path = Path(img_path)
            img_b64 = image_to_base64(full_path)

        img_html = f'<img src="{img_b64}" alt="Figure {i}" style="max-width:100%;border:1px solid #e2e8f0;border-radius:8px;">' if img_b64 else '<div style="padding:40px;background:#f1f5f9;border-radius:8px;text-align:center;color:#94a3b8;">Image not available</div>'

        vlm_recs = vlm_by_figure.get(fig_id, [])
        vlm_count = len(vlm_recs)

        vlm_items_html = ""
        for rec in vlm_recs:
            statement = rec.get("statement", "")
            evidence_type = rec.get("evidence_type", "")
            confidence = rec.get("confidence", "")
            quality_state = rec.get("quality_state", "")
            vlm_items_html += f"""
            <div class="vlm-record">
                <div class="vlm-statement">{escape_html(statement)}</div>
                <div class="vlm-meta">
                    {origin_badge(evidence_type)} {status_badge(quality_state)} Confidence: {escape_html(str(confidence))}
                </div>
            </div>
            """

        vlm_section = f"""
        <details>
            <summary>VLM Scientific Observations ({vlm_count} records)</summary>
            <div class="vlm-container">{vlm_items_html}</div>
        </details>
        """ if vlm_count > 0 else '<div style="color:#94a3b8;padding:10px;">No VLM records</div>'

        cards_html.append(f"""
        <div class="figure-card" id="fig-{i}">
            <h3>Figure {i}</h3>
            <div class="figure-image">{img_html}</div>
            <div class="figure-caption">{escape_html(caption)}</div>
            {vlm_section}
        </div>
        """)

    html = f"""
    <div class="section-card">
        <h2>Figure Gallery</h2>
        <div class="figure-grid">{"".join(cards_html)}</div>
    </div>
    """
    return html


def generate_table_explorer(table_parser: dict, table_science: dict) -> str:
    tables = table_parser.get("tables", [])

    if not tables:
        return """
        <div class="section-card">
            <h2>Table Explorer</h2>
            <div style="padding:40px;background:#fef3c7;border-radius:8px;text-align:center;color:#92400e;">
                No table data available from Table Parser
            </div>
        </div>
        """

    cards_html = []
    for tbl in tables:
        table_id = tbl.get("table_id", "Unknown")
        table_label = tbl.get("table_label", "")
        caption = tbl.get("caption", "")
        page = tbl.get("page_idx", "")
        rows = tbl.get("rows", [])
        headers = tbl.get("headers", [])
        extraction_status = tbl.get("extraction_status", "")
        extraction_source = tbl.get("extraction_source", "")
        source_anchor = tbl.get("source_anchor", {})
        bbox = source_anchor.get("bbox", [])
        image_path = source_anchor.get("image_path", "")

        # Build metadata display
        meta_items = [
            f"<strong>Table ID:</strong> {escape_html(table_id)}",
            f"<strong>Label:</strong> {escape_html(table_label)}",
            f"<strong>Page:</strong> {page}",
            f"<strong>Extraction Status:</strong> {status_badge(extraction_status)}",
            f"<strong>Source:</strong> {escape_html(extraction_source)}",
        ]
        if bbox:
            meta_items.append(f"<strong>BBox:</strong> [{', '.join(str(b) for b in bbox)}]")

        meta_html = "<div class='table-meta'>" + " | ".join(meta_items) + "</div>"

        # Check if we have actual table content
        if not rows and not headers:
            # No structured data - show honest message with details
            table_html = f"""
            <div style="padding:30px;background:#fef3c7;border-radius:8px;border-left:4px solid #f59e0b;">
                <div style="font-weight:bold;color:#92400e;margin-bottom:10px;">Table Structure Not Extracted</div>
                <div style="color:#78350f;font-size:14px;line-height:1.8;">
                    <strong>Detection:</strong> Table image detected on page {page}<br>
                    <strong>OCR Status:</strong> {escape_html(extraction_status)} — structural extraction not performed<br>
                    <strong>Headers:</strong> 0 columns<br>
                    <strong>Rows:</strong> 0 rows<br>
                    <strong>Cells:</strong> 0 total<br>
                    <br>
                    <small style="color:#92400e;">Note: Table content exists as image but was not parsed into structured data during the 014 pipeline run.</small>
                </div>
            </div>
            """
        else:
            # We have structured data - display it
            header_html = "".join(f"<th>{escape_html(h)}</th>" for h in headers)
            rows_html = ""
            for row in rows:
                cells = "".join(f"<td>{escape_html(str(c))}</td>" for c in row)
                rows_html += f"<tr>{cells}</tr>"
            table_html = f'<table class="data-table"><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>'

        # Add caption
        caption_html = f'<div class="table-caption" style="margin-top:15px;font-style:italic;color:#64748b;">{escape_html(caption)}</div>' if caption else ""

        cards_html.append(f"""
        <div class="table-card">
            <h3>{escape_html(table_label or table_id)}</h3>
            {meta_html}
            {caption_html}
            {table_html}
        </div>
        """)

    # Add summary section
    summary_html = f"""
    <div style="background:#f0f9ff;border-left:4px solid #0ea5e9;padding:20px;border-radius:8px;margin-bottom:20px;">
        <h3 style="margin-top:0;color:#0c4a6e;">Table Data Source Audit</h3>
        <div style="font-size:14px;color:#334155;line-height:1.8;">
            <strong>Pipeline Stage:</strong> table_parser (014 run)<br>
            <strong>Tables Detected:</strong> {len(tables)}<br>
            <strong>Tables with Structured Data:</strong> {sum(1 for t in tables if t.get('rows'))}<br>
            <strong>Table Science Records:</strong> {table_science.get('total_records', 0)}<br>
            <strong>Gap:</strong> Table OCR/structure extraction not executed (status: OCR_PENDING)<br>
            <br>
            <small style="color:#64748b;">This report honestly displays the absence of table row/column data. The table images were detected but not parsed into structured format during the 014 pipeline execution.</small>
        </div>
    </div>
    """

    html = f"""
    <div class="section-card">
        <h2>Table Explorer</h2>
        {summary_html}
        {"".join(cards_html)}
    </div>
    """
    return html


def generate_qa_section(report: dict) -> str:
    qa = report.get("qa_verification", {})
    summary = qa.get("summary", {})
    verifications = qa.get("verifications", {})

    total = summary.get("total_checks", 0)
    passed = summary.get("pass", 0)
    failed = summary.get("fail", 0)
    warned = summary.get("warn", 0)
    overall = summary.get("overall_status", "")

    checks_html = ""
    for category, data in verifications.items():
        if not isinstance(data, dict):
            continue
        category_checks = data.get("checks", [])
        for check in category_checks:
            check_name = check.get("check", "")
            status = check.get("status", "")
            note = check.get("note", "")
            metric = check.get("metric", "")
            value = check.get("value", "")

            detail = ""
            if metric:
                detail = f"{escape_html(metric)}: {escape_html(str(value))}"
            if note:
                detail += f" - {escape_html(note)}"

            checks_html += f"""
            <tr>
                <td>{escape_html(category)}</td>
                <td>{escape_html(check_name)}</td>
                <td>{status_badge(status)}</td>
                <td>{detail}</td>
            </tr>
            """

    html = f"""
    <div class="section-card">
        <h2>QA Verification</h2>
        <div class="qa-summary">
            <div class="qa-stat"><strong>Total Checks:</strong> {total}</div>
            <div class="qa-stat"><strong>Passed:</strong> <span style="color:#22c55e;">{passed}</span></div>
            <div class="qa-stat"><strong>Failed:</strong> <span style="color:#ef4444;">{failed}</span></div>
            <div class="qa-stat"><strong>Warnings:</strong> <span style="color:#f59e0b;">{warned}</span></div>
            <div class="qa-stat"><strong>Overall:</strong> {status_badge(overall)}</div>
        </div>
        <table class="data-table">
            <thead><tr><th>Category</th><th>Check</th><th>Status</th><th>Details</th></tr></thead>
            <tbody>{checks_html}</tbody>
        </table>
    </div>
    """
    return html


def generate_knowledge_objects_section(report: dict) -> str:
    objects = report.get("knowledge_objects", {})
    relationships = report.get("knowledge_relationships", [])

    cards_html = ""
    for obj_type, obj_list in objects.items():
        if not isinstance(obj_list, list):
            continue
        count = len(obj_list)
        items_html = ""
        for obj in obj_list[:10]:
            obj_id = obj.get(f"{obj_type[:-1]}_id", obj.get("id", ""))
            content = obj.get("content", obj.get("description", ""))
            source = obj.get("source", "")
            status = obj.get("status", "")

            items_html += f"""
            <div class="knowledge-item">
                <strong>{escape_html(obj_id)}</strong> {status_badge(status)} {origin_badge(source)}
                <div>{escape_html(content[:200])}{"..." if len(content) > 200 else ""}</div>
            </div>
            """

        if count > 10:
            items_html += f'<div style="color:#64748b;padding:10px;">... and {count - 10} more</div>'

        cards_html += f"""
        <div class="knowledge-card">
            <h3>{escape_html(obj_type.replace('_', ' ').title())} ({count})</h3>
            {items_html}
        </div>
        """

    rel_html = ""
    for rel in relationships[:20]:
        rel_id = rel.get("relationship_id", "")
        rel_type = rel.get("relationship_type", "")
        source_id = rel.get("source_id", "")
        target_id = rel.get("target_id", "")
        rel_html += f"<li><strong>{escape_html(rel_type)}</strong>: {escape_html(source_id)} → {escape_html(target_id)}</li>"

    if len(relationships) > 20:
        rel_html += f"<li>... and {len(relationships) - 20} more</li>"

    html = f"""
    <div class="section-card">
        <h2>Knowledge Objects</h2>
        <div class="knowledge-grid">{cards_html}</div>
        <h3>Relationships ({len(relationships)})</h3>
        <ul>{rel_html}</ul>
    </div>
    """
    return html


def generate_evidence_section(report: dict) -> str:
    provenance = report.get("provenance", {})
    provenance_audit = report.get("provenance_audit", {})

    data_sources = provenance.get("data_sources", [])
    sources_html = "".join(f"<li>{escape_html(src)}</li>" for src in data_sources)

    prov_counts = provenance_audit.get("provenance_counts", {})
    status_counts = provenance_audit.get("status_counts", {})

    html = f"""
    <div class="section-card">
        <h2>Evidence & Provenance</h2>
        <h3>Data Sources</h3>
        <ul>{sources_html}</ul>

        <h3>Provenance Distribution</h3>
        <table class="info-table">
            <tr><th>DERIVED</th><td>{prov_counts.get('DERIVED', 0)}</td></tr>
            <tr><th>EXTRACTED</th><td>{prov_counts.get('EXTRACTED', 0)}</td></tr>
            <tr><th>INFERRED</th><td>{prov_counts.get('INFERRED', 0)}</td></tr>
        </table>

        <h3>Status Distribution</h3>
        <table class="info-table">
            <tr><th>EXTRACTED</th><td>{status_counts.get('EXTRACTED', 0)}</td></tr>
            <tr><th>SOURCE_LINKED</th><td>{status_counts.get('SOURCE_LINKED', 0)}</td></tr>
            <tr><th>UNRESOLVED</th><td>{status_counts.get('UNRESOLVED', 0)}</td></tr>
        </table>

        <div class="provenance-note">
            <strong>Audit Note:</strong> {escape_html(provenance_audit.get('audit_note', ''))}
        </div>
    </div>
    """
    return html


def generate_html(report: dict, vlm_data: dict, figure_parser: dict, table_parser: dict, table_science: dict) -> str:
    overview_html = generate_overview_section(report)

    dimensions_html = ""
    for dim in DIMENSIONS:
        dim_data = load_dimension(dim)
        dimensions_html += generate_dimension_section(dim, dim_data)

    figure_gallery_html = generate_figure_gallery(report, vlm_data, figure_parser)
    table_explorer_html = generate_table_explorer(table_parser, table_science)
    qa_html = generate_qa_section(report)
    knowledge_html = generate_knowledge_objects_section(report)
    evidence_html = generate_evidence_section(report)

    nav_items = """
    <li><a href="#overview">Overview</a></li>
    <li><a href="#dimensions">Six Dimensions</a></li>
    """
    for dim in DIMENSIONS:
        label = DIMENSION_LABELS[dim]
        nav_items += f'    <li style="padding-left:20px;"><a href="#dim-{dim}">{label}</a></li>\n'
    nav_items += """
    <li><a href="#figures">Figures</a></li>
    <li><a href="#tables">Tables</a></li>
    <li><a href="#qa">QA Verification</a></li>
    <li><a href="#knowledge">Knowledge Objects</a></li>
    <li><a href="#evidence">Evidence</a></li>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>F02 Knowledge Report v3 - {escape_html(report.get('document_overview', {}).get('title', ''))}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f8fafc;
            color: #1e293b;
            line-height: 1.6;
        }}
        .container {{ display: flex; min-height: 100vh; }}
        .sidebar {{
            width: 250px;
            background: #1e293b;
            color: white;
            padding: 20px;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
        }}
        .sidebar h1 {{ font-size: 18px; margin-bottom: 20px; color: #f1f5f9; }}
        .sidebar ul {{ list-style: none; }}
        .sidebar li {{ margin: 8px 0; }}
        .sidebar a {{ color: #cbd5e1; text-decoration: none; font-size: 14px; }}
        .sidebar a:hover {{ color: white; }}
        .main-content {{
            margin-left: 250px;
            padding: 40px;
            flex: 1;
            max-width: 1200px;
        }}
        .section-card {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .section-card h2 {{
            font-size: 24px;
            margin-bottom: 20px;
            color: #0f172a;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
        }}
        .section-card h3 {{
            font-size: 18px;
            margin: 20px 0 10px;
            color: #334155;
        }}
        .info-table, .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        .info-table th, .data-table th {{
            background: #f1f5f9;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border: 1px solid #e2e8f0;
        }}
        .info-table td, .data-table td {{
            padding: 12px;
            border: 1px solid #e2e8f0;
            vertical-align: top;
        }}
        .nested-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 13px;
        }}
        .nested-table th, .nested-table td {{
            padding: 8px;
            border: 1px solid #cbd5e1;
            text-align: left;
        }}
        .nested-table th {{ background: #f8fafc; }}
        .source-quote {{
            background: #fef3c7;
            border-left: 3px solid #f59e0b;
            padding: 8px 12px;
            margin-top: 8px;
            font-size: 12px;
            color: #78350f;
            font-style: italic;
        }}
        .warnings {{
            background: #fef2f2;
            border-left: 3px solid #ef4444;
            padding: 12px;
            margin-top: 15px;
            font-size: 13px;
        }}
        .merge-notes {{
            background: #f0f9ff;
            border-left: 3px solid #0ea5e9;
            padding: 8px 12px;
            margin-top: 10px;
            font-size: 12px;
            color: #0c4a6e;
        }}
        .figure-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .figure-card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 20px;
        }}
        .figure-card h3 {{ margin-top: 0; }}
        .figure-image {{ margin: 15px 0; }}
        .figure-caption {{ font-size: 13px; color: #64748b; margin: 10px 0; }}
        details {{
            margin-top: 15px;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 10px;
        }}
        summary {{
            cursor: pointer;
            font-weight: 600;
            color: #334155;
        }}
        .vlm-container {{
            margin-top: 15px;
            max-height: 400px;
            overflow-y: auto;
        }}
        .vlm-record {{
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
        }}
        .vlm-statement {{ font-size: 14px; margin-bottom: 8px; }}
        .vlm-meta {{ font-size: 12px; color: #64748b; }}
        .table-card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
        }}
        .table-meta {{ font-size: 13px; color: #64748b; margin: 10px 0; }}
        .table-caption {{ font-size: 14px; margin: 10px 0; }}
        .qa-summary {{
            display: flex;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .qa-stat {{
            background: #f1f5f9;
            padding: 15px 20px;
            border-radius: 8px;
            font-size: 14px;
        }}
        .knowledge-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .knowledge-card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 20px;
        }}
        .knowledge-item {{
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
            font-size: 13px;
        }}
        .provenance-note {{
            background: #f0f9ff;
            border-left: 3px solid #0ea5e9;
            padding: 15px;
            margin-top: 20px;
            font-size: 13px;
        }}
        ul {{ padding-left: 20px; }}
        li {{ margin: 5px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="sidebar">
            <h1>F02 Knowledge Report</h1>
            <ul>
                {nav_items}
            </ul>
        </nav>
        <main class="main-content">
            <div id="overview">{overview_html}</div>
            <div id="dimensions">{dimensions_html}</div>
            <div id="figures">{figure_gallery_html}</div>
            <div id="tables">{table_explorer_html}</div>
            <div id="qa">{qa_html}</div>
            <div id="knowledge">{knowledge_html}</div>
            <div id="evidence">{evidence_html}</div>
        </main>
    </div>
</body>
</html>
"""
    return html


def main():
    logger.info("Loading data sources...")
    report = load_json(REPORT_JSON)
    vlm_data = load_json(VLM_RECORDS)
    figure_parser = load_json(FIGURE_PARSER)
    table_parser = load_json(TABLE_PARSER)
    table_science = load_json(TABLE_SCIENCE)

    logger.info("Generating HTML...")
    html = generate_html(report, vlm_data, figure_parser, table_parser, table_science)

    logger.info("Writing to %s", OUTPUT_HTML)
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("[DONE] Generated %s (%d bytes)", OUTPUT_HTML.name, len(html))


if __name__ == "__main__":
    main()
