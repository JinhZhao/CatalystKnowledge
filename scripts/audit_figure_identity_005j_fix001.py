"""
005-J-FIX-001: Comprehensive Figure Identity Audit

Audits all 25 VLM records against FigureParser, Document IR, and actual image files.
Checks all 9 figures in F02 for consistency.
"""
import json
import os
import sys
import hashlib
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# === Paths ===
STORE_VLM_DIR = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_I\canonical_store\vlm_records")
FIGURE_PARSER_PATH = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_G\figure_parser\F02_figure_parser.json")
DOC_IR_PATH = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\document_ir\F02_document_ir.json")
VLM_CACHE_PATH = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_G_FIX_001\PIPELINE_005_G\F02_vlm_science_records.json")
MINERU_IMAGES_DIR = Path(r"D:\Knowledge_World\data\test_corpus\mineru_output\F02_regression\main\auto\images")

# === Load data ===
print("=" * 70)
print("005-J-FIX-001: Figure Identity Audit")
print("=" * 70)

# 1. Load VLM records from Store
vlm_records = []
for fn in sorted(STORE_VLM_DIR.glob("*.json")):
    with open(fn, 'r', encoding='utf-8') as f:
        vlm_records.append(json.load(f))
print(f"\nStore VLM records: {len(vlm_records)}")

# 2. Load FigureParser
with open(FIGURE_PARSER_PATH, 'r', encoding='utf-8') as f:
    fig_parser = json.load(f)
fig_lookup = {fig['figure_id']: fig for fig in fig_parser['figures']}
print(f"FigureParser figures: {fig_parser['figure_count']}")

# 3. Load Document IR
with open(DOC_IR_PATH, 'r', encoding='utf-8') as f:
    doc_ir = json.load(f)
doc_ir_images = {}
for block in doc_ir.get('blocks', []):
    if block.get('type') == 'image':
        doc_ir_images[block['element_id']] = {
            'page_idx': block['page_idx'],
            'bbox': block['source_anchor']['bbox'],
        }
print(f"Document IR image blocks: {len(doc_ir_images)}")

# 4. Load VLM cache (raw)
vlm_cache_data = None
if VLM_CACHE_PATH.exists():
    with open(VLM_CACHE_PATH, 'r', encoding='utf-8') as f:
        vlm_cache_data = json.load(f)
    cache_results = vlm_cache_data.get('results', [])
    cache_records = []
    for r in cache_results:
        cache_records.extend(r.get('records', []))
    print(f"VLM cache records: {len(cache_records)}")
else:
    print(f"VLM cache NOT FOUND: {VLM_CACHE_PATH}")
    cache_records = []

# === Part A: Audit all 25 VLM records ===
print("\n" + "=" * 70)
print("PART A: VLM Record Identity Audit (25 records)")
print("=" * 70)

record_audits = []
for rec in vlm_records:
    rid = rec['record_id']
    fid = rec['figure_id']
    sa = rec.get('source_anchor', {})
    vlm_bbox = [sa.get('bbox', {}).get('x0', 0), sa.get('bbox', {}).get('y0', 0),
                sa.get('bbox', {}).get('x1', 0), sa.get('bbox', {}).get('y1', 0)]
    vlm_sha = sa.get('image_file', {}).get('sha256', '')
    vlm_page = sa.get('page_idx', -1)
    vlm_img_path = sa.get('image_file', {}).get('path', '')

    fig = fig_lookup.get(fid)
    audit = {
        'record_id': rid,
        'figure_id': fid,
        'vlm_sha256': vlm_sha,
        'vlm_bbox': vlm_bbox,
        'vlm_page_idx': vlm_page,
        'vlm_image_path': vlm_img_path,
    }

    if fig:
        audit['fp_sha256'] = fig['image_sha256']
        audit['fp_bbox'] = fig['bbox']
        audit['fp_page_idx'] = fig['page_idx']
        audit['fp_image_path'] = fig.get('image_path', '')
        audit['fp_caption'] = fig.get('caption', '')[:80]
        audit['sha_match'] = vlm_sha == fig['image_sha256']
        audit['bbox_match'] = vlm_bbox == fig['bbox']
        audit['page_match'] = vlm_page == fig['page_idx']
        
        # Check if VLM sha matches a DIFFERENT figure
        audit['sha_matches_other_fig'] = None
        for ofid, ofig in fig_lookup.items():
            if ofid != fid and ofig['image_sha256'] == vlm_sha:
                audit['sha_matches_other_fig'] = ofid
                break
        
        # Check if VLM bbox matches a DIFFERENT figure
        audit['bbox_matches_other_fig'] = None
        for ofid, ofig in fig_lookup.items():
            if ofid != fid and ofig['bbox'] == vlm_bbox:
                audit['bbox_matches_other_fig'] = ofid
                break
        
        # Document IR check
        audit['doc_ir_element'] = None
        for eid, info in doc_ir_images.items():
            if info['page_idx'] == vlm_page and info['bbox'] == vlm_bbox:
                audit['doc_ir_element'] = eid
                break
        audit['correct_doc_ir_element'] = None
        for eid, info in doc_ir_images.items():
            if info['page_idx'] == fig['page_idx'] and info['bbox'] == fig['bbox']:
                audit['correct_doc_ir_element'] = eid
                break
        
        # Image file existence check
        audit['image_file_exists'] = os.path.exists(vlm_img_path) if vlm_img_path else False
        
        # Actual file hash check
        if audit['image_file_exists']:
            with open(vlm_img_path, 'rb') as f:
                actual_sha = hashlib.sha256(f.read()).hexdigest()
            audit['actual_file_sha256'] = actual_sha
            audit['file_sha_matches_vlm'] = actual_sha == vlm_sha
            audit['file_sha_matches_fp'] = actual_sha == fig['image_sha256']
    
    record_audits.append(audit)

# Print summary
sha_matches = sum(1 for a in record_audits if a.get('sha_match'))
bbox_matches = sum(1 for a in record_audits if a.get('bbox_match'))
page_matches = sum(1 for a in record_audits if a.get('page_match'))
sha_other = [a for a in record_audits if a.get('sha_matches_other_fig')]
bbox_other = [a for a in record_audits if a.get('bbox_matches_other_fig')]

print(f"\nSHA256 match: {sha_matches}/25")
print(f"Bbox match: {bbox_matches}/25")
print(f"Page match: {page_matches}/25")
print(f"SHA matches other figure: {len(sha_other)}/25")
print(f"Bbox matches other figure: {len(bbox_other)}/25")

if sha_other:
    print(f"\nSHA cross-match details:")
    for a in sha_other[:3]:
        print(f"  {a['record_id']}: claims {a['figure_id']}, SHA matches {a['sha_matches_other_fig']}")

if bbox_other:
    print(f"\nBbox cross-match details:")
    for a in bbox_other[:3]:
        print(f"  {a['record_id']}: claims {a['figure_id']}, bbox matches {a['bbox_matches_other_fig']}")

# === Part B: Check VLM cache records ===
print("\n" + "=" * 70)
print("PART B: VLM Cache Record Audit")
print("=" * 70)

if cache_records:
    cache_audits = []
    for rec in cache_records:
        rid = rec.get('record_id', '')
        fid = rec.get('figure_id', '')
        content = rec.get('content', {})
        
        # Check if content has image reference
        image_ref = None
        if isinstance(content, dict):
            image_ref = content.get('image_path') or content.get('image')
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'image_url':
                    image_ref = item.get('image_url', {}).get('url', '')
                    break
        
        cache_audits.append({
            'record_id': rid,
            'figure_id': fid,
            'has_image_ref': image_ref is not None,
            'image_ref_preview': str(image_ref)[:100] if image_ref else None,
        })
    
    print(f"Cache records: {len(cache_audits)}")
    for a in cache_audits[:3]:
        print(f"  {a['record_id']}: fig={a['figure_id']}, img_ref={a['has_image_ref']}")
        if a['image_ref_preview']:
            print(f"    ref: {a['image_ref_preview']}")

# === Part C: Nine Figure Identity Matrix ===
print("\n" + "=" * 70)
print("PART C: F02 Nine Figure Identity Matrix")
print("=" * 70)

figure_matrix = []
for fid in sorted(fig_lookup.keys()):
    fig = fig_lookup[fid]
    entry = {
        'figure_id': fid,
        'page_idx': fig['page_idx'],
        'image_sha256': fig['image_sha256'],
        'image_sha256_short': fig['image_sha256'][:16] + '...',
        'bbox': fig['bbox'],
        'caption': fig.get('caption', '')[:60],
        'image_path': fig.get('image_path', ''),
        'image_exists': os.path.exists(fig.get('image_path', '')),
    }
    
    # Document IR match
    entry['doc_ir_element'] = None
    for eid, info in doc_ir_images.items():
        if info['page_idx'] == fig['page_idx'] and info['bbox'] == fig['bbox']:
            entry['doc_ir_element'] = eid
            break
    
    # VLM records for this figure
    vlm_for_fig = [a for a in record_audits if a['figure_id'] == fid]
    entry['vlm_record_count'] = len(vlm_for_fig)
    entry['vlm_sha_match'] = all(a.get('sha_match', False) for a in vlm_for_fig) if vlm_for_fig else None
    entry['vlm_bbox_match'] = all(a.get('bbox_match', False) for a in vlm_for_fig) if vlm_for_fig else None
    
    # Check actual file hash
    if entry['image_exists']:
        with open(entry['image_path'], 'rb') as f:
            entry['actual_file_sha256'] = hashlib.sha256(f.read()).hexdigest()
        entry['file_sha_matches_fp'] = entry['actual_file_sha256'] == fig['image_sha256']
    
    figure_matrix.append(entry)
    
    status = "OK" if (entry.get('doc_ir_element') and entry.get('image_exists') and entry.get('file_sha_matches_fp')) else "ISSUE"
    print(f"\n  {fid}: page={fig['page_idx']} sha={entry['image_sha256_short']} bbox={fig['bbox']}")
    print(f"    caption: {entry['caption']}")
    print(f"    doc_ir: {entry.get('doc_ir_element', 'NOT_FOUND')}")
    print(f"    image_exists: {entry['image_exists']}")
    if entry.get('actual_file_sha256'):
        print(f"    file_sha_match: {entry.get('file_sha_matches_fp')}")
    print(f"    vlm_records: {entry['vlm_record_count']} (sha={entry.get('vlm_sha_match')}, bbox={entry.get('vlm_bbox_match')})")
    print(f"    status: {status}")

# === Part D: Cross-figure SHA collision check ===
print("\n" + "=" * 70)
print("PART D: SHA256 Collision Check (all 9 figures)")
print("=" * 70)

sha_to_figs = {}
for entry in figure_matrix:
    sha = entry['image_sha256']
    if sha not in sha_to_figs:
        sha_to_figs[sha] = []
    sha_to_figs[sha].append(entry['figure_id'])

collisions = {sha: figs for sha, figs in sha_to_figs.items() if len(figs) > 1}
if collisions:
    print(f"COLLISIONS FOUND: {len(collisions)}")
    for sha, figs in collisions.items():
        print(f"  SHA {sha[:16]}...: {figs}")
else:
    print("No SHA256 collisions among  9 figures — all image files are unique.")

# Check if any VLM record's SHA matches a different figure
print("\nVLM SHA cross-match (VLM record claims fig X but SHA matches fig Y):")
cross_matches = []
for a in record_audits:
    if a.get('sha_matches_other_fig'):
        cross_matches.append(a)
        print(f"  {a['record_id']}: claims {a['figure_id']}, SHA actually matches {a['sha_matches_other_fig']}")
if not cross_matches:
    print("  None — all VLM record SHAs match their claimed figure_id.")

# === Summary ===
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# What image did the VLM actually see?
print("\nQ1: What image did the 25 VLM records actually analyze?")
if cross_matches:
    target = cross_matches[0].get('sha_matches_other_fig')
    print(f"  All 25 records claim figure_id=F02_fig_07")
    print(f"  But SHA256 matches: {target}")
    print(f"  CONCLUSION: VLM actually analyzed {target}, not F02_fig_07")
else:
    print(f"  SHA256 matches claimed figure_id for all 25 records")
    print(f"  CONCLUSION: VLM analyzed the correct image")

print("\nQ2: Where did the bbox error occur?")
print(f"  VLM records have bbox from: {record_audits[0].get('bbox_matches_other_fig', 'UNKNOWN')}")
print(f"  Correct bbox for F02_fig_07: {fig_lookup['F02_fig_07']['bbox']}")
print(f"  VLM record bbox: {record_audits[0]['vlm_bbox']}")
print(f"  Root cause: VLM adapter SourceAnchor construction used wrong figure's bbox")

# Save audit data
audit_output = {
    'audit_id': 'FIX-001-AUDIT-001',
    'record_audits': record_audits,
    'figure_matrix': figure_matrix,
    'cross_matches': [{'record_id': a['record_id'], 'claims': a['figure_id'], 
                        'sha_actually_matches': a.get('sha_matches_other_fig'),
                        'bbox_actually_matches': a.get('bbox_matches_other_fig')} 
                       for a in record_audits if a.get('sha_matches_other_fig') or a.get('bbox_matches_other_fig')],
    'collisions': {sha: figs for sha, figs in sha_to_figs.items() if len(figs) > 1},
}

out_path = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_005_J_FIX_001\AUDIT_RAW_DATA.json")
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(audit_output, f, indent=2, ensure_ascii=False)
print(f"\nRaw audit data saved: {out_path}")
