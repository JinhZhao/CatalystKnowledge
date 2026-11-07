"""HTML Report Generator — minimal standalone HTML export.

Reads the existing F02_knowledge_report.json (or equivalent) produced by
single_doc_report_generator.py and renders a self-contained HTML file that
can be opened in any modern browser.

Design constraints (PI directive 012-C):
  - Standalone HTML (no external CSS/JS dependencies)
  - 9 required content sections
  - DataStatus badges: VERIFIED / CANDIDATE / UNVERIFIABLE / others
  - Candidate knowledge MUST NOT be auto-upgraded to verified facts
  - Do NOT modify Schema or Prompt to accommodate HTML
"""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# DataStatus badge colors — explicit visual distinction required by PI.
# Grouped by semantic meaning: green=verified, blue=normalized, orange=candidate,
# purple=inferred, red=unverifiable/failed, gray=absent/not-attempted.
_STATUS_COLORS = {
    # Verified / reported
    "VERIFIED":       ("#1e7a3a", "#e6f4ea"),
    "REPORTED":       ("#1e7a3a", "#e6f4ea"),
    "SUCCESS":        ("#1e7a3a", "#e6f4ea"),
    "PASS":           ("#1e7a3a", "#e6f4ea"),
    # Normalized / processed
    "NORMALIZED":     ("#0b5ed7", "#e7f1ff"),
    "LOADED":         ("#0b5ed7", "#e7f1ff"),
    "COMPLETE":       ("#0b5ed7", "#e7f1ff"),
    # Extracted (LLM/rule) — intermediate confidence
    "LLM_EXTRACTED":  ("#0b5ed7", "#e7f1ff"),
    "RULE_EXTRACTED": ("#0b5ed7", "#e7f1ff"),
    "EXTRACTED":      ("#0b5ed7", "#e7f1ff"),
    "PARTIAL":        ("#0b5ed7", "#e7f1ff"),
    # Inferred / needs context
    "INFERRED":       ("#7952b3", "#f1eafb"),
    "REQUIRES_CONTEXT": ("#7952b3", "#f1eafb"),
    "SYNTHESIS":      ("#7952b3", "#f1eafb"),
    # Candidate / predicted — not yet verified
    "CANDIDATE":      ("#c06a00", "#fff4e5"),
    "PREDICTED":      ("#c06a00", "#fff4e5"),
    "NOT_VERIFIED":   ("#c06a00", "#fff4e5"),
    "PENDING":        ("#c06a00", "#fff4e5"),
    # Unverifiable / failed / conflicted
    "UNVERIFIABLE":   ("#8a3a3a", "#f9e5e5"),
    "CONFLICTED":     ("#a61c00", "#fde7e7"),
    "FAILED":         ("#a61c00", "#fde7e7"),
    "ERROR":          ("#a61c00", "#fde7e7"),
    "INVALID":        ("#a61c00", "#fde7e7"),
    # Absent / not attempted
    "NOT_REPORTED":   ("#6c757d", "#f1f3f5"),
    "NOT_EXTRACTED":  ("#6c757d", "#f1f3f5"),
    "NOT_APPLICABLE": ("#6c757d", "#f1f3f5"),
    "NOT_AVAILABLE":  ("#6c757d", "#f1f3f5"),
    "SKIPPED":        ("#6c757d", "#f1f3f5"),
    "DISABLED":       ("#6c757d", "#f1f3f5"),
    "UNRESOLVED":     ("#845a33", "#f4eadb"),
    "UNKNOWN":        ("#6c757d", "#f1f3f5"),
}


def _status_badge(status: str | None) -> str:
    """Render a DataStatus badge as inline HTML."""
    if not status:
        status = "UNKNOWN"
    s_upper = str(status).upper()
    fg, bg = _STATUS_COLORS.get(s_upper, ("#333", "#f5f5f5"))
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'font-size:11px;font-weight:600;color:{fg};background:{bg};'
        f'border:1px solid {fg};">{html.escape(s_upper)}</span>'
    )


def _escape(value: Any) -> str:
    if value is None:
        return '<span style="color:#888;">—</span>'
    return html.escape(str(value))


def _render_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render a simple HTML table."""
    if not rows:
        return '<p style="color:#888;font-style:italic;">(no records)</p>'
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body_rows = []
    for r in rows:
        cells = ""
        for c in r:
            if isinstance(c, str) and c.startswith("<"):
                cells += f"<td>{c}</td>"
            else:
                cells += f"<td>{_escape(c)}</td>"
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        '<table style="border-collapse:collapse;width:100%;font-size:13px;">'
        f"<thead><tr>{th}</tr></thead>"
        f'<tbody>{"".join(body_rows)}</tbody>'
        "</table>"
    )


def _render_kv(pairs: list[tuple[str, Any]]) -> str:
    rows = "".join(
        f"<tr><th style='text-align:left;padding:4px 12px 4px 0;color:#555;'>"
        f"{html.escape(k)}</th>"
        f"<td style='padding:4px 0;'>{_escape(v)}</td></tr>"
        for k, v in pairs
    )
    return f"<table>{rows}</table>"


# ---------------------------------------------------------------------------
# Section renderers — one per required content area
# ---------------------------------------------------------------------------

def _section_overview(data: dict) -> str:
    ov = data.get("document_overview", {}) or {}
    pairs = [
        ("Document ID", data.get("document_id")),
        ("Report ID", data.get("report_id")),
        ("Generated at", data.get("generated_at")),
        ("Generator version", data.get("generator_version")),
        ("Title", ov.get("title")),
        ("Authors", ov.get("authors")),
        ("Journal", ov.get("journal")),
        ("DOI", ov.get("doi")),
        ("Publication year", ov.get("publication_year")),
        ("Document type", ov.get("document_type")),
        ("Pages", ov.get("page_count")),
    ]
    return _render_kv([(k, v) for k, v in pairs if v is not None])


def _section_six_dimensions(data: dict) -> str:
    """Section 2: 催化科学知识六维结构."""
    six = data.get("six_dimension_extraction", {}) or {}
    if not six:
        return '<p style="color:#888;">No six-dimension extraction data.</p>'
    
    # Handle both structures:
    # Old: {"catalyst_design": {"fields": {...}}}
    # New: {"status": "...", "dimensions": {"catalyst_design": {...}}}
    dims = six.get("dimensions", {}) or six
    
    parts = []
    for dim_name, dim_data in dims.items():
        if not isinstance(dim_data, dict):
            continue
        # Skip metadata keys
        if dim_name in ("status", "dimension_count"):
            continue
        
        # Check if this is the old structure with "fields" key
        fields = dim_data.get("fields", {}) or dim_data
        if not fields:
            continue
        
        rows = []
        for field_name, field_value in fields.items():
            if field_name == "fields":
                continue
            if isinstance(field_value, dict):
                # Old structure: {status, value, origin}
                status = field_value.get("status", "")
                value = field_value.get("value")
                origin = field_value.get("origin", "")
                rows.append([
                    field_name,
                    _status_badge(status),
                    _escape(value) if value is not None else "—",
                    _escape(origin),
                ])
            else:
                # New flat structure: just a string value, no per-field status.
                # Use LLM_EXTRACTED (not REPORTED) because we lack original
                # verification metadata — these are LLM outputs, not confirmed facts.
                if field_value is None or (isinstance(field_value, str) and not field_value.strip()):
                    status = "NOT_REPORTED"
                    display_value = "—"
                elif isinstance(field_value, list):
                    status = "LLM_EXTRACTED" if field_value else "NOT_REPORTED"
                    display_value = _escape(str(field_value))
                else:
                    status = "LLM_EXTRACTED"
                    display_value = _escape(field_value)
                rows.append([field_name, _status_badge(status), display_value, ""])
        
        if rows:
            table = _render_table(["Field", "Status", "Value", "Origin"], rows)
            parts.append(
                f"<h4 style='margin-top:16px;color:#333;'>{html.escape(dim_name)}</h4>"
                f"{table}"
            )
    return "\n".join(parts) if parts else '<p style="color:#888;">No dimensions.</p>'


def _section_catalyst_conditions(data: dict) -> str:
    """Section 3: 催化剂与反应条件."""
    six = data.get("six_dimension_extraction", {}) or {}
    dims = six.get("dimensions", {}) or six
    cat_design = dims.get("catalyst_design", {}) or {}
    
    # Handle both structures
    fields = cat_design.get("fields", {}) or cat_design
    if not fields:
        return _render_table(["Parameter", "Status", "Value"], [])
    
    rows = []
    for k, v in fields.items():
        if k == "fields":
            continue
        if isinstance(v, dict):
            rows.append([k, _status_badge(v.get("status")), _escape(v.get("value"))])
        else:
            # Flat structure: no per-field status metadata.
            # Use LLM_EXTRACTED (not REPORTED) — unverified LLM output.
            if v is None or (isinstance(v, str) and not v.strip()):
                status = "NOT_REPORTED"
                display_value = "—"
            else:
                status = "LLM_EXTRACTED"
                display_value = _escape(v)
            rows.append([k, _status_badge(status), display_value])
    return _render_table(["Parameter", "Status", "Value"], rows)


def _section_performance_characterization(data: dict) -> str:
    """Section 4: 性能和表征结果."""
    six = data.get("six_dimension_extraction", {}) or {}
    dims = six.get("dimensions", {}) or six
    
    parts = []
    for dim in ("performance", "characterization"):
        dim_data = dims.get(dim, {}) or {}
        # Handle both structures
        fields = dim_data.get("fields", {}) or dim_data
        if not fields:
            continue
        
        rows = []
        for k, v in fields.items():
            if k == "fields":
                continue
            if isinstance(v, dict):
                rows.append([
                    k, _status_badge(v.get("status")),
                    _escape(v.get("value")),
                    _escape(v.get("origin", "")),
                ])
            else:
                # Flat structure: no per-field status metadata.
                # Use LLM_EXTRACTED (not REPORTED) — unverified LLM output.
                if v is None or (isinstance(v, str) and not v.strip()):
                    status = "NOT_REPORTED"
                    display_value = "—"
                else:
                    status = "LLM_EXTRACTED"
                    display_value = _escape(v)
                rows.append([k, _status_badge(status), display_value, ""])
        
        if rows:
            parts.append(
                f"<h4>{html.escape(dim.title())}</h4>"
                + _render_table(["Metric", "Status", "Value", "Origin"], rows)
            )
    return "\n".join(parts) if parts else '<p style="color:#888;">No data.</p>'


def _section_mechanism_claims(data: dict) -> str:
    """Section 5: 反应机制与科学主张."""
    six = data.get("six_dimension_extraction", {}) or {}
    dims = six.get("dimensions", {}) or six
    mechanism = dims.get("mechanism", {}) or {}
    
    # Handle both structures
    fields = mechanism.get("fields", {}) or mechanism
    if not fields:
        return '<p style="color:#888;">No mechanism data.</p>'
    
    rows = []
    for k, v in fields.items():
        if k == "fields":
            continue
        if isinstance(v, dict):
            rows.append([
                k, _status_badge(v.get("status")),
                _escape(v.get("value")),
                _escape(v.get("notes", "")),
            ])
        else:
            # Flat structure: no per-field status metadata.
            # Use LLM_EXTRACTED (not REPORTED) — unverified LLM output.
            if v is None or (isinstance(v, str) and not v.strip()):
                status = "NOT_REPORTED"
                display_value = "—"
            else:
                status = "LLM_EXTRACTED"
                display_value = _escape(v)
            rows.append([k, _status_badge(status), display_value, ""])
    
    if rows:
        return _render_table(["Aspect", "Status", "Value", "Notes"], rows)
    return '<p style="color:#888;">No mechanism data.</p>'


def _section_figures_tables(data: dict) -> str:
    """Section 6: Figure/Table 及对应证据."""
    parts = []

    figures = data.get("figures", []) or []
    if figures:
        rows = []
        for fig in figures:
            if isinstance(fig, dict):
                # Handle both old and new structure
                fig_id = fig.get("figure_id") or fig.get("element_id", "")
                fig_type = fig.get("figure_type") or fig.get("element_type", "")
                page = fig.get("page", "")
                caption = fig.get("caption") or fig.get("content_preview", "")
                record_count = fig.get("record_count", "")
                rows.append([
                    fig_id,
                    fig_type,
                    page,
                    str(caption)[:120] if caption else "",
                    record_count,
                ])
        parts.append(
            "<h4>Figures</h4>"
            + _render_table(["ID", "Type", "Page", "Caption (truncated)", "Records"], rows)
        )

    tables = data.get("tables", []) or []
    if tables:
        rows = []
        for tab in tables:
            if isinstance(tab, dict):
                # Handle both old and new structure
                tab_id = tab.get("table_id") or tab.get("element_id", "")
                page = tab.get("page", "")
                caption = tab.get("caption") or tab.get("content_preview", "")
                rows_count = tab.get("rows_count", "")
                cols_count = tab.get("columns_count", "")
                rows.append([
                    tab_id,
                    page,
                    str(caption)[:120] if caption else "",
                    rows_count,
                    cols_count,
                ])
        parts.append(
            "<h4>Tables</h4>"
            + _render_table(["ID", "Page", "Caption (truncated)", "Rows", "Cols"], rows)
        )

    assoc = data.get("figure_associations", []) or []
    if assoc:
        rows = []
        for a in assoc[:50]:
            if isinstance(a, dict):
                rows.append([
                    a.get("association_id", ""),
                    a.get("figure_ref", ""),
                    a.get("dimension", ""),
                    _status_badge(a.get("status")),
                ])
        parts.append(
            "<h4>Figure Associations</h4>"
            + _render_table(["ID", "Figure", "Dimension", "Status"], rows)
        )

    return "\n".join(parts) if parts else '<p style="color:#888;">No Figure/Table data.</p>'


def _section_limitations(data: dict) -> str:
    """Section 7: 局限性和不确定性."""
    qa = data.get("qa_verification", {}) or {}
    stats = data.get("statistics", {}) or {}
    parts = []

    if qa:
        rows = []
        for k, v in qa.items():
            if isinstance(v, dict):
                rows.append([k, _status_badge(v.get("status") or v.get("verdict")),
                             _escape(v.get("detail", ""))])
            else:
                rows.append([k, "", _escape(v)])
        parts.append("<h4>QA Verification</h4>" + _render_table(["Check", "Status", "Detail"], rows))

    if stats:
        rows = [[k, _escape(v)] for k, v in stats.items()]
        parts.append("<h4>Statistics</h4>" + _render_table(["Metric", "Value"], rows))

    return "\n".join(parts) if parts else '<p style="color:#888;">No limitation data.</p>'


def _section_source_anchor(data: dict) -> str:
    """Section 8: SourceAnchor 与原文定位."""
    prov = data.get("provenance", {}) or {}
    prov_audit = data.get("provenance_audit", {}) or {}
    parts = []

    if prov:
        rows = []
        for k, v in prov.items():
            if isinstance(v, list):
                rows.append([k, f"{len(v)} record(s)"])
            elif isinstance(v, dict):
                rows.append([k, f"{len(v)} field(s)"])
            else:
                rows.append([k, _escape(v)])
        parts.append("<h4>Provenance Summary</h4>" + _render_table(["Category", "Count"], rows))

    if prov_audit:
        rows = [[k, _escape(v)] for k, v in prov_audit.items()
                if not isinstance(v, (list, dict))]
        if rows:
            parts.append("<h4>Provenance Audit</h4>" + _render_table(["Field", "Value"], rows))

    return "\n".join(parts) if parts else '<p style="color:#888;">No SourceAnchor data.</p>'


def _section_versions(data: dict) -> str:
    """Section 9: Schema, Prompt, LLM, 运行版本."""
    pairs = [
        ("Schema version", data.get("schema_version", "1.0.0")),
        ("Prompt version", data.get("prompt_version", "1.0.0")),
        ("LLM model", data.get("llm_model", "deepseek-chat")),
        ("LLM temperature", data.get("llm_temperature", 0.1)),
        ("LLM max_tokens", data.get("llm_max_tokens", 4096)),
        ("Report generator", data.get("generator_version", "unknown")),
        ("Report generated at", data.get("generated_at", "")),
        ("Extraction version", data.get("extraction_version", "v2")),
        ("Token estimation", "heuristic (chars/3.5); NOT exact tokenizer count"),
    ]
    return _render_kv(pairs)


# ---------------------------------------------------------------------------
# Top-level renderer
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
       margin: 0; padding: 24px; color: #222; background: #fafafa; line-height: 1.5; }
.container { max-width: 1100px; margin: 0 auto; background: white;
             padding: 32px 40px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);
             border-radius: 6px; }
h1 { color: #0b5ed7; border-bottom: 2px solid #0b5ed7; padding-bottom: 8px; }
h2 { color: #333; margin-top: 32px; border-left: 4px solid #0b5ed7; padding-left: 12px; }
h3 { color: #555; margin-top: 20px; }
h4 { color: #666; margin-top: 14px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 13px; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f5f7fa; font-weight: 600; color: #333; }
tr:nth-child(even) td { background: #fcfcfd; }
.meta-banner { background: #fff8e1; border-left: 4px solid #f0ad4e; padding: 10px 14px;
               margin: 16px 0; font-size: 13px; color: #6a4a00; }
.footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd;
          font-size: 12px; color: #888; }
"""


def generate_html_report(
    report_data: dict,
    output_path: str | Path,
    title: str | None = None,
) -> Path:
    """Render a knowledge report dict to a standalone HTML file.

    Args:
        report_data: dict loaded from *_knowledge_report.json
        output_path: destination HTML file path
        title: optional HTML title (defaults to document_id)

    Returns:
        Path to the written HTML file.
    """
    doc_id = report_data.get("document_id", "unknown")
    html_title = title or f"Catalyst Knowledge Report — {doc_id}"

    sections = [
        ("1. 论文基本信息", _section_overview(report_data)),
        ("2. 催化科学知识六维结构", _section_six_dimensions(report_data)),
        ("3. 催化剂与反应条件", _section_catalyst_conditions(report_data)),
        ("4. 性能和表征结果", _section_performance_characterization(report_data)),
        ("5. 反应机制与科学主张", _section_mechanism_claims(report_data)),
        ("6. Figure/Table 及对应证据", _section_figures_tables(report_data)),
        ("7. 局限性和不确定性", _section_limitations(report_data)),
        ("8. SourceAnchor 与原文定位", _section_source_anchor(report_data)),
        ("9. Schema / Prompt / LLM 版本", _section_versions(report_data)),
    ]

    section_html = "\n".join(
        f"<h2>{html.escape(name)}</h2>\n{body}" for name, body in sections
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    qa_status = report_data.get("qa_status", report_data.get("report_status", ""))
    if qa_status in ("FAILED", "ERROR"):
        status_banner = (
            '<div class="meta-banner" style="background:#fde7e7;border:2px solid #a61c00;">'
            '<strong>Pipeline FAILED:</strong> 本运行未通过质量门控，报告中的数据'
            '<strong>不可用于科学结论</strong>。QA状态: '
            f'{html.escape(str(qa_status))}'
            '</div>'
        )
    elif qa_status in ("CONDITIONAL_PASS", "PARTIAL"):
        status_banner = (
            '<div class="meta-banner" style="background:#fff4e5;border:2px solid #c06a00;">'
            '<strong>CONDITIONAL PASS:</strong> 本运行存在未满足的质量条件，'
            '报告数据为<strong>部分验证</strong>。QA状态: '
            f'{html.escape(str(qa_status))}'
            '</div>'
        )
    else:
        status_banner = ""

    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{html.escape(html_title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">

<h1>{html.escape(html_title)}</h1>

<div class="meta-banner">
<strong>重要说明：</strong>本报告中的科学知识按 DataStatus 分级显示。
只有 <span style="color:#1e7a3a;font-weight:600;">VERIFIED</span> /
<span style="color:#1e7a3a;font-weight:600;">REPORTED</span> 状态的数据直接来自文献原文；
<span style="color:#c06a00;font-weight:600;">CANDIDATE</span> /
<span style="color:#7952b3;font-weight:600;">INFERRED</span> /
<span style="color:#c06a00;font-weight:600;">PREDICTED</span>
状态的数据为模型推断或候选观察，<strong>不得视为已验证事实</strong>。
<span style="color:#8a3a3a;font-weight:600;">UNVERIFIABLE</span>
状态的数据无法通过当前证据核实。
</div>

{status_banner}

{section_html}

<div class="footer">
Generated at {html.escape(generated_at)} by catalyst_knowledge HTML report generator v0.12.0.
Document ID: {html.escape(doc_id)}.
</div>

</div>
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    logger.info("HTML report written: %s (%d bytes)", out, len(document))
    return out


def generate_html_from_json(json_path: str | Path, output_path: str | Path) -> Path:
    """Convenience: load a JSON report and render to HTML."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return generate_html_report(data, output_path)
