"""
005-J-FIX-001: Rebuild VLM records with correct SourceAnchor

Root cause: PIPELINE_005_G_FIX_001/figure_parser had corrupted bbox for F02_fig_07
(used F02_fig_06's bbox [64,82,276,246] instead of correct [65,316,273,484])

Fix: Rebuild all 25 records with correct SourceAnchor from verified FigureParser.
Scientific content (statement, evidence_type, confidence, quality_state) unchanged.
"""
import json
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

# === Paths ===
STORE_VLM_DIR = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_I\canonical_store\vlm_records")
CORRECT_FIG_PARSER = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_G\figure_parser\F02_figure_parser.json")
VLM_CACHE = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_G_FIX_001\PIPELINE_005_G\F02_vlm_science_records.json")
OUTPUT_DIR = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_J_FIX_001")
CORRECTED_DIR = OUTPUT_DIR / "corrected_vlm_records"
CORRECTED_DIR.mkdir(parents=True, exist_ok=True)

# === Load correct FigureParser ===
with open(CORRECT_FIG_PARSER, 'r', encoding='utf-8') as f:
    fig_parser = json.load(f)
fig_lookup = {fig['figure_id']: fig for fig in fig_parser['figures']}

# === Load VLM cache ===
with open(VLM_CACHE, 'r', encoding='utf-8') as f:
    vlm_cache = json.load(f)

cache_records = []
for result in vlm_cache.get('results', []):
    cache_records.extend(result.get('records', []))

print(f"Original cache records: {len(cache_records)}")

# === Fix each record ===
corrected_records = []
fix_log = []

for rec in cache_records:
    rid = rec['record_id']
    fid = rec['figure_id']
    fig = fig_lookup.get(fid)
    
    if not fig:
        print(f"WARNING: {rid} — figure_id {fid} not in FigureParser, keeping original")
        corrected_records.append(rec)
        fix_log.append({
            'record_id': rid,
            'action': 'KEPT_ORIGINAL',
            'reason': f'figure_id {fid} not found in FigureParser',
        })
        continue
    
    correct_sa = fig.get('source_anchor', {})
    old_sa = rec.get('source_anchor', {})
    
    old_bbox = old_sa.get('bbox', {})
    new_bbox = correct_sa.get('bbox', {})
    
    # Build corrected record
    corrected = dict(rec)
    corrected['source_anchor'] = dict(correct_sa)
    
    # Preserve fields that should not change
    corrected['record_id'] = rec['record_id']
    corrected['figure_id'] = rec['figure_id']
    corrected['statement'] = rec['statement']
    corrected['evidence_type'] = rec['evidence_type']
    corrected['confidence'] = rec['confidence']
    corrected['quality_state'] = rec['quality_state']
    
    corrected_records.append(corrected)
    
    bbox_changed = old_bbox != new_bbox
    fix_log.append({
        'record_id': rid,
        'action': 'SOURCE_ANCHOR_FIXED',
        'figure_id': fid,
        'old_bbox': old_bbox,
        'new_bbox': new_bbox,
        'bbox_changed': bbox_changed,
        'sha256_unchanged': old_sa.get('image_file', {}).get('sha256') == correct_sa.get('image_file', {}).get('sha256'),
        'page_idx_unchanged': old_sa.get('page_idx') == correct_sa.get('page_idx'),
    })

print(f"Corrected records: {len(corrected_records)}")
bbox_fixes = sum(1 for f in fix_log if f.get('bbox_changed'))
print(f"Bbox fixes applied: {bbox_fixes}")

# === Write corrected records ===
# Individual record files (matching Store format)
for rec in corrected_records:
    out_file = CORRECTED_DIR / f"{rec['record_id']}.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)

# Combined file
combined_path = OUTPUT_DIR / "CORRECTED_F02_VLM_RECORDS.json"
combined = {
    'fix_id': 'FIX-001-SA-001',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'document_id': 'F02',
    'total_records': len(corrected_records),
    'fix_description': 'SourceAnchor bbox corrected from F02_fig_06 values to F02_fig_07 values',
    'root_cause': 'PIPELINE_005_G_FIX_001/figure_parser had corrupted bbox for F02_fig_07',
    'scientific_content_unchanged': True,
    'records': corrected_records,
    'fix_log': fix_log,
}
with open(combined_path, 'w', encoding='utf-8') as f:
    json.dump(combined, f, indent=2, ensure_ascii=False)

print(f"\nCorrected records written to: {CORRECTED_DIR}")
print(f"Combined file: {combined_path}")

# === Verify corrected records ===
print("\n=== Verification ===")
for rec in corrected_records[:3]:
    sa = rec.get('source_anchor', {})
    bbox = sa.get('bbox', {})
    print(f"  {rec['record_id']}: bbox=[{bbox.get('x0')},{bbox.get('y0')},{bbox.get('x1')},{bbox.get('y1')}] sha={sa.get('image_file',{}).get('sha256','')[:16]}...")

# Check all corrected bboxes match FigureParser
all_match = True
for rec in corrected_records:
    fid = rec['figure_id']
    fig = fig_lookup.get(fid)
    if fig:
        rec_bbox = rec['source_anchor'].get('bbox', {})
        fig_bbox = fig['source_anchor'].get('bbox', {})
        if (rec_bbox.get('x0') != fig_bbox.get('x0') or 
            rec_bbox.get('y0') != fig_bbox.get('y0') or
            rec_bbox.get('x1') != fig_bbox.get('x1') or
            rec_bbox.get('y1') != fig_bbox.get('y1')):
            print(f"  MISMATCH: {rec['record_id']} — {fid}")
            all_match = False

print(f"\nAll bboxes match FigureParser: {all_match}")
print(f"Quality states preserved: {set(r['quality_state'] for r in corrected_records)}")
