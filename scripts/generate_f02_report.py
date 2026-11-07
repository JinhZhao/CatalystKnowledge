#!/usr/bin/env python3
"""Generate standalone HTML audit report for F02"""
import json
from pathlib import Path
from datetime import datetime

# Load data
base = Path('D:/Knowledge_World/runs/audit_008')
overview = json.loads((base / 'f02_overview.json').read_text('utf-8'))
source = json.loads((base / 'f02_source.json').read_text('utf-8'))
experiments = json.loads((base / 'f02_experiments.json').read_text('utf-8'))

# Escape HTML
def esc(s):
    if s is None:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

# Build HTML
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>F02 Audit Report - Catalyst Knowledge Base V2</title>
<style>
:root {{
  --bg: #0d1117;
  --surface: #161b22;
  --surface2: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --accent: #58a6ff;
  --green: #3fb950;
  --yellow: #d29922;
  --red: #f85149;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 20px; max-width: 1400px; margin: 0 auto; }}
h1 {{ color: var(--accent); margin-bottom: 8px; }}
h2 {{ color: var(--accent); margin: 24px 0 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
h3 {{ color: var(--text); margin: 16px 0 8px; font-size: 16px; }}
.subtitle {{ color: var(--text2); font-size: 14px; margin-bottom: 24px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; margin-right: 4px; }}
.badge-green {{ background: rgba(63,185,80,0.15); color: var(--green); border: 1px solid rgba(63,185,80,0.3); }}
.badge-yellow {{ background: rgba(210,153,34,0.15); color: var(--yellow); border: 1px solid rgba(210,153,34,0.3); }}
.badge-red {{ background: rgba(248,81,73,0.15); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }}
.badge-blue {{ background: rgba(88,166,255,0.15); color: var(--accent); border: 1px solid rgba(88,166,255,0.3); }}
.badge-gray {{ background: rgba(139,148,158,0.15); color: var(--text2); border: 1px solid rgba(139,148,158,0.3); }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 12px 0; }}
.stat-box {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; text-align: center; }}
.stat-value {{ font-size: 28px; font-weight: 700; color: var(--accent); }}
.stat-label {{ font-size: 12px; color: var(--text2); margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 12px 0; }}
th {{ text-align: left; padding: 10px; background: var(--surface2); color: var(--text2); font-weight: 600; border-bottom: 2px solid var(--border); }}
td {{ padding: 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
tr:hover td {{ background: rgba(88,166,255,0.04); }}
.dim-card {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 12px; }}
.dim-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
.dim-title {{ font-weight: 600; font-size: 14px; }}
.object-card {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 10px; }}
.object-id {{ font-weight: 600; color: var(--accent); font-size: 13px; }}
.object-content {{ font-size: 13px; color: var(--text); margin: 8px 0; line-height: 1.6; }}
.anchor-tag {{ font-size: 11px; padding: 3px 8px; border-radius: 4px; display: inline-block; margin-top: 4px; }}
.synthetic {{ color: var(--yellow); background: rgba(210,153,34,0.1); }}
.real {{ color: var(--green); background: rgba(63,185,80,0.1); }}
.exp-flow {{ display: flex; flex-direction: column; gap: 0; margin: 16px 0; }}
.exp-step {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; }}
.exp-step + .exp-step {{ margin-top: -1px; }}
.exp-step-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.exp-step-icon {{ font-size: 20px; }}
.exp-step-title {{ font-weight: 600; font-size: 14px; }}
.exp-step-content {{ font-size: 12px; color: var(--text2); padding-left: 28px; line-height: 1.6; }}
.exp-arrow {{ text-align: center; color: var(--text2); font-size: 18px; padding: 4px 0; }}
.source-text {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 4px; padding: 12px; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; color: var(--text2); }}
.section {{ margin-bottom: 32px; }}
.toc {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
.toc a {{ color: var(--accent); text-decoration: none; display: block; padding: 4px 0; }}
.toc a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>

<h1>📊 F02 Audit Report</h1>
<div class="subtitle">Catalyst Knowledge Base V2 | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>

<div class="toc">
<h3 style="margin-top:0;">📑 Table of Contents</h3>
<a href="#overview">1. Overview & Statistics</a>
<a href="#classification">2. Taxonomy Classification (TAX-001)</a>
<a href="#extraction">3. Six-Dimension LLM Extraction</a>
<a href="#experiments">4. Experiment Chain</a>
<a href="#objects">5. Knowledge Objects</a>
<a href="#relationships">6. Relationships</a>
<a href="#source">7. Source Document</a>
</div>

<div class="section" id="overview">
<h2>1. Overview & Statistics</h2>
<div class="card">
<h3>Processing Status</h3>
<div class="stats-grid">
<div class="stat-box"><div class="stat-value">✅</div><div class="stat-label">MinerU Parsed</div></div>
<div class="stat-box"><div class="stat-value">{len(overview.get('images', []))}</div><div class="stat-label">Images</div></div>
<div class="stat-box"><div class="stat-value">✅</div><div class="stat-label">6-Dim Extraction</div></div>
<div class="stat-box"><div class="stat-value">✅</div><div class="stat-label">Full Report</div></div>
</div>
</div>

<div class="card">
<h3>SourceAnchor Statistics</h3>
'''

sa_stats = overview.get('source_anchor_stats', {})
cats = sa_stats.get('categories', {})
html += f'''<div class="stats-grid">
<div class="stat-box"><div class="stat-value">{cats.get('real_document_ir_element_id', 0)}</div><div class="stat-label">Real Element ID</div></div>
<div class="stat-box"><div class="stat-value" style="color:var(--yellow);">{cats.get('synthetic_dimension_level', 0)}</div><div class="stat-label">Synthetic Dimension</div></div>
<div class="stat-box"><div class="stat-value">{cats.get('with_citation_verified', 0)}</div><div class="stat-label">Citation Verified</div></div>
<div class="stat-box"><div class="stat-value">{sa_stats.get('total_objects', 0)}</div><div class="stat-label">Total Objects</div></div>
</div>'''

if cats.get('synthetic_dimension_level', 0) > 0:
    html += f'<div style="margin-top:12px;padding:10px;background:rgba(210,153,34,0.1);border:1px solid rgba(210,153,34,0.3);border-radius:4px;color:var(--yellow);font-size:12px;">⚠️ WARNING: {cats.get("synthetic_dimension_level", 0)} objects have SYNTHETIC dimension anchors (not real document locations)</div>'

html += '</div></div>'

# Classification
html += '<div class="section" id="classification"><h2>2. Taxonomy Classification (TAX-001)</h2>'
cls = overview.get('classification', {})
if cls:
    html += f'<div class="card"><p>Status: <span class="badge {"badge-green" if cls.get("status") == "ACCEPTED" else "badge-red"}">{cls.get("status", "UNKNOWN")}</span>'
    if cls.get('overall_confidence'):
        html += f' <span style="margin-left:12px;color:var(--text2);">Overall Confidence: {cls.get("overall_confidence")}</span>'
    html += '</p>'
    
    dim_labels = {
        'reaction_type': ('🧪', 'Reaction Type'),
        'catalyst_type': ('⚗️', 'Catalyst Type'),
        'application_domain': ('🏭', 'Application Domain'),
        'document_type': ('📄', 'Document Type')
    }
    
    for dim, (icon, label) in dim_labels.items():
        data = cls.get(dim, {})
        if data:
            html += f'<div class="dim-card"><div class="dim-header"><span class="dim-title">{icon} {label}</span>'
            if data.get('confidence'):
                conf = data['confidence']
                conf_class = 'badge-green' if conf >= 0.9 else 'badge-yellow' if conf >= 0.7 else 'badge-red'
                html += f'<span class="badge {conf_class}">{conf}</span>'
            html += '</div>'
            
            if data.get('labels'):
                html += '<div style="margin:6px 0;">'
                for lbl in data['labels']:
                    html += f'<span class="badge badge-blue">{esc(lbl.replace("_", " "))}</span>'
                html += '</div>'
            
            if data.get('evidence'):
                html += f'<div style="font-size:12px;color:var(--text2);font-style:italic;margin-top:6px;">{esc(data["evidence"][:200])}{"..." if len(data.get("evidence", "")) > 200 else ""}</div>'
            
            html += '</div>'
    
    if cls.get('metadata'):
        meta = cls['metadata']
        html += f'<div style="margin-top:12px;font-size:11px;color:var(--text2);">Model: {meta.get("model", "?")} | Vocabulary: v{meta.get("vocabulary_version", "?")} ({meta.get("vocabulary_status", "?")})</div>'
    
    html += '</div>'
html += '</div>'

# Six-Dimension Extraction
html += '<div class="section" id="extraction"><h2>3. Six-Dimension LLM Extraction</h2>'
ext = overview.get('six_dimension_extraction', {})
if ext:
    dim_meta = {
        'catalyst_design': ('🎯', 'Catalyst Design'),
        'characterization': ('🔬', 'Characterization'),
        'mechanism': ('⚙️', 'Mechanism'),
        'performance': ('📊', 'Performance'),
        'reliability': ('🛡️', 'Reliability'),
        'structure_activity': ('🔗', 'Structure-Activity')
    }
    
    for dim, (icon, label) in dim_meta.items():
        data = ext.get(dim)
        if data:
            html += f'<div class="card"><h3>{icon} {label}</h3>'
            if isinstance(data, dict):
                for key, value in data.items():
                    if value not in [None, '', {}]:
                        key_label = key.replace('_', ' ').title()
                        html += f'<div style="margin:6px 0;"><strong style="color:var(--text2);min-width:120px;display:inline-block;">{esc(key_label)}:</strong> '
                        if isinstance(value, (dict, list)):
                            html += f'<span>{esc(json.dumps(value, ensure_ascii=False))}</span>'
                        else:
                            html += f'<span>{esc(str(value))}</span>'
                        html += '</div>'
            html += '</div>'
html += '</div>'

# Experiments
html += '<div class="section" id="experiments"><h2>4. Experiment Chain</h2>'
if experiments:
    integration_status = experiments.get('integration_status', 'UNKNOWN')
    html += f'<div class="card"><p>Integration Status: <span class="badge {"badge-green" if integration_status == "COMPLETE" else "badge-yellow"}">{integration_status}</span></p>'
    
    completeness = experiments.get('chain_completeness', {})
    if completeness:
        html += '<h3 style="margin-top:16px;">Chain Completeness</h3><div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;">'
        for step, done in completeness.items():
            html += f'<span class="badge {"badge-green" if done else "badge-gray"}">{"✅" if done else "⬜"} {step}</span>'
        html += '</div>'
    
    html += '</div>'
    
    # Experiment flow
    sample = experiments.get('sample_details')
    reaction = experiments.get('reaction_details')
    audit = experiments.get('experiment_audit', {})
    
    html += '<div class="card"><h3>Experiment Flow</h3><div class="exp-flow">'
    
    if sample:
        html += f'<div class="exp-step"><div class="exp-step-header"><span class="exp-step-icon">⚗️</span><span class="exp-step-title">Catalyst Sample</span><span class="badge badge-blue">{esc(sample.get("object_id", "N/A"))}</span></div>'
        if sample.get('name'):
            html += f'<div class="exp-step-content" style="font-weight:500;">{esc(sample["name"][:150])}{"..." if len(sample.get("name", "")) > 150 else ""}</div>'
        if sample.get('roles'):
            roles = sample['roles']
            if roles.get('active_component'):
                html += f'<div class="exp-step-content"><strong>Active:</strong> {esc(roles["active_component"])}</div>'
            if roles.get('support'):
                html += f'<div class="exp-step-content"><strong>Support:</strong> {esc(roles["support"])}</div>'
        html += '</div><div class="exp-arrow">↓</div>'
    
    if reaction:
        html += f'<div class="exp-step"><div class="exp-step-header"><span class="exp-step-icon">🔄</span><span class="exp-step-title">Reaction</span><span class="badge badge-blue">{esc(reaction.get("object_id", "N/A"))}</span></div>'
        if reaction.get('reaction_type'):
            html += f'<div class="exp-step-content">{esc(reaction["reaction_type"])}</div>'
        html += '</div><div class="exp-arrow">↓</div>'
    
    has_obs = audit.get('has_observation', False)
    html += f'<div class="exp-step {"exp-step-missing" if not has_obs else ""}"><div class="exp-step-header"><span class="exp-step-icon">{"👁️" if has_obs else "❌"}</span><span class="exp-step-title">Observation</span><span class="badge {"badge-green" if has_obs else "badge-gray"}">{"PRESENT (" + str(audit.get("observation_count", 0)) + ")" if has_obs else "NOT_EXTRACTED"}</span></div></div><div class="exp-arrow">↓</div>'
    
    has_qr = audit.get('has_quantity_records', False) or audit.get('quantity_record_count', 0) > 0
    html += f'<div class="exp-step {"exp-step-missing" if not has_qr else ""}"><div class="exp-step-header"><span class="exp-step-icon">{"🔬" if has_qr else "❌"}</span><span class="exp-step-title">Evidence / Quantity Records</span><span class="badge {"badge-green" if has_qr else "badge-gray"}">{str(audit.get("quantity_record_count", 0)) + " records" if has_qr else "NOT_EXTRACTED"}</span></div></div>'
    
    html += '</div></div>'
    
    # Experiment details
    exp_details = experiments.get('experiment_details')
    if exp_details:
        html += '<div class="card"><h3>Experiment Details</h3>'
        html += f'<div style="font-size:13px;line-height:1.8;"><div><strong>ID:</strong> {esc(exp_details.get("object_id", "N/A"))}</div>'
        if exp_details.get('reaction_conditions'):
            html += f'<div style="margin-top:8px;"><strong>Reaction Conditions:</strong></div><div style="color:var(--text2);padding-left:12px;">{esc(exp_details["reaction_conditions"])}</div>'
        if exp_details.get('metrics'):
            html += '<div style="margin-top:12px;"><strong>Key Metrics:</strong></div><table><tr><th>Metric</th><th>Value</th><th>Conditions</th></tr>'
            for m in exp_details['metrics']:
                html += f'<tr><td>{esc(m.get("metric_name", ""))}</td><td style="color:var(--accent);font-weight:600;">{esc(m.get("value", ""))}</td><td style="color:var(--text2);font-size:12px;">{esc((m.get("conditions", "") or "")[:100])}</td></tr>'
            html += '</table>'
        if exp_details.get('time_on_stream_note'):
            html += f'<div style="margin-top:8px;color:var(--text2);font-style:italic;">{esc(exp_details["time_on_stream_note"])}</div>'
        html += '</div></div>'

html += '</div>'

# Knowledge Objects
html += '<div class="section" id="objects"><h2>5. Knowledge Objects</h2>'
report = overview.get('single_doc_report', {})
ko = report.get('knowledge_objects', {})
if ko:
    type_meta = {
        'facts': ('📊', 'Facts'),
        'claims': ('💡', 'Claims'),
        'evidence': ('🔬', 'Evidence'),
        'limitations': ('⚠️', 'Limitations'),
        'open_questions': ('❓', 'Open Questions'),
        'hypotheses': ('🧪', 'Hypotheses'),
        'experiment_proposals': ('📋', 'Experiment Proposals'),
        'feasibility_assessments': ('✅', 'Feasibility Assessments'),
        'validation_plans': ('📝', 'Validation Plans')
    }
    
    for type_key, (icon, label) in type_meta.items():
        items = ko.get(type_key, [])
        html += f'<div class="card"><h3>{icon} {label} ({len(items)})</h3>'
        if not items:
            html += '<p style="color:var(--text2);font-size:13px;">NOT_EXTRACTED</p>'
        else:
            for item in items:
                item_id = item.get('fact_id') or item.get('claim_id') or item.get('evidence_id') or item.get('limitation_id') or item.get('question_id') or item.get('hypothesis_id') or item.get('proposal_id') or item.get('feasibility_id') or item.get('plan_id') or item.get('object_id') or '?'
                content = item.get('content') or item.get('description') or item.get('rationale') or item.get('method_description') or ''
                status = item.get('extraction_status') or item.get('status') or ''
                
                html += f'<div class="object-card"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;"><span class="object-id">{icon} {esc(item_id)}</span>'
                if status:
                    status_class = 'badge-green' if any(s in status.upper() for s in ['COMPLETE', 'ACCEPTED', 'VERIFIED', 'CONFIRMED']) else 'badge-yellow' if any(s in status.upper() for s in ['PARTIAL', 'PENDING']) else 'badge-red' if any(s in status.upper() for s in ['FAIL', 'ERROR', 'UNRESOLVED']) else 'badge-gray'
                    html += f'<span class="badge {status_class}">{status}</span>'
                html += '</div>'
                
                if content:
                    html += f'<div class="object-content">{esc(content[:300])}{"..." if len(content) > 300 else ""}</div>'
                
                sa = item.get('source_anchor', {})
                if sa:
                    is_synthetic = sa.get('authenticity') == 'SYNTHETIC_ANCHOR' or (sa.get('element_id') and '_dim_' in sa.get('element_id', ''))
                    if is_synthetic:
                        html += f'<div class="anchor-tag synthetic">⚠️ SYNTHETIC: {esc(sa.get("element_id", "dimension-level"))}</div>'
                    elif sa.get('element_id'):
                        html += f'<div class="anchor-tag real">✅ REAL: {esc(sa.get("element_id"))} (p.{sa.get("page", "?")})</div>'
                
                html += '</div>'
        html += '</div>'
html += '</div>'

# Relationships
html += '<div class="section" id="relationships"><h2>6. Relationships</h2>'
rels = report.get('knowledge_relationships', [])
if rels:
    html += f'<div class="card"><h3>Knowledge Relationships ({len(rels)})</h3>'
    by_type = {}
    for rel in rels:
        t = rel.get('relationship_type', 'UNKNOWN')
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(rel)
    
    for rel_type, type_rels in by_type.items():
        html += f'<h4 style="margin-top:16px;">{rel_type} ({len(type_rels)})</h4><table><tr><th>Source</th><th></th><th>Target</th><th>Status</th></tr>'
        for rel in type_rels:
            html += f'<tr><td style="color:var(--accent);">{esc(rel.get("source_id", "?"))}</td><td style="color:var(--text2);">→</td><td style="color:var(--accent);">{esc(rel.get("target_id", "?"))}</td>'
            ev_status = rel.get('evidence_status', '')
            if ev_status:
                html += f'<td><span class="badge {"badge-green" if ev_status == "VERIFIED" else "badge-yellow"}">{ev_status}</span></td>'
            else:
                html += '<td></td>'
            html += '</tr>'
        html += '</table>'
    html += '</div>'
html += '</div>'

# Source Document
html += '<div class="section" id="source"><h2>7. Source Document</h2>'
if source:
    html += f'<div class="card"><h3>Original MinerU Markdown ({source.get("line_count", 0)} lines)</h3>'
    html += f'<div class="source-text">{esc(source.get("markdown", ""))}</div>'
    html += '</div>'
html += '</div>'

html += f'''
<div style="margin-top:40px;padding:20px;background:var(--surface);border:1px solid var(--border);border-radius:8px;text-align:center;color:var(--text2);font-size:12px;">
<p><strong>Catalyst Knowledge Base V2 - Audit Report</strong></p>
<p>Document: F02 | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p>This is a standalone audit report. For interactive exploration, use the Audit Workbench at http://127.0.0.1:8090</p>
</div>

</body>
</html>
'''

# Write output
output_path = Path('D:/Knowledge_World/runs/audit_008/F02_audit_report.html')
output_path.write_text(html, encoding='utf-8')
print(f'[OK] Generated: {output_path}')
print(f'     Size: {output_path.stat().st_size:,} bytes')
