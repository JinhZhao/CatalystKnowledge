"""SourceAnchor validation for 25 VLM records against FigureParser and Document IR."""
import json
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

store_dir = 'D:/Knowledge_World/runs/pipeline_001_fix/PIPELINE_005_I/canonical_store/vlm_records'
fig_parser_path = 'D:/Knowledge_World/runs/pipeline_001_fix/PIPELINE_005_G/figure_parser/F02_figure_parser.json'
doc_ir_path = 'D:/Knowledge_World/runs/pipeline_001_fix/document_ir/F02_document_ir.json'

vlm_records = []
for fn in sorted(os.listdir(store_dir)):
    if fn.endswith('.json'):
        with open(os.path.join(store_dir, fn), 'r', encoding='utf-8') as f:
            vlm_records.append(json.load(f))

with open(fig_parser_path, 'r', encoding='utf-8') as f:
    fig_parser = json.load(f)

with open(doc_ir_path, 'r', encoding='utf-8') as f:
    doc_ir = json.load(f)

fig_lookup = {fig['figure_id']: fig for fig in fig_parser['figures']}

doc_ir_image_blocks = {}
for block in doc_ir.get('blocks', []):
    if block.get('type') == 'image':
        doc_ir_image_blocks[block['element_id']] = {
            'page_idx': block['page_idx'],
            'bbox': block['source_anchor']['bbox'],
        }

validation_results = []
summary = {'total': 0, 'ANCHOR_VALID': 0, 'ANCHOR_PARTIAL': 0, 'ANCHOR_INVALID': 0, 'ANCHOR_UNRESOLVED': 0}

for rec in vlm_records:
    rid = rec['record_id']
    fid = rec['figure_id']
    sa = rec.get('source_anchor', {})
    vlm_bbox_dict = sa.get('bbox', {})
    vlm_bbox = [vlm_bbox_dict.get('x0', 0), vlm_bbox_dict.get('y0', 0),
                vlm_bbox_dict.get('x1', 0), vlm_bbox_dict.get('y1', 0)]
    vlm_sha = sa.get('image_file', {}).get('sha256', '')
    vlm_page = sa.get('page_idx', -1)
    vlm_page_size = sa.get('page_size', {})

    checks = {}
    fig = fig_lookup.get(fid)

    # 1. Image SHA256
    if fig:
        sha_match = vlm_sha == fig['image_sha256']
        checks['image_sha256'] = {
            'status': 'PASS' if sha_match else 'FAIL',
            'vlm_value': vlm_sha,
            'figure_parser_value': fig['image_sha256'],
            'match': sha_match,
        }
    else:
        sha_match = False
        checks['image_sha256'] = {'status': 'SKIP', 'reason': 'figure_id not in FigureParser'}

    # 2. Page index
    if fig:
        page_match = vlm_page == fig['page_idx']
        checks['page_idx'] = {
            'status': 'PASS' if page_match else 'FAIL',
            'vlm_value': vlm_page,
            'figure_parser_value': fig['page_idx'],
            'match': page_match,
        }
    else:
        page_match = False
        checks['page_idx'] = {'status': 'SKIP', 'reason': 'figure_id not in FigureParser'}

    # 3. Bbox
    if fig:
        bbox_match = vlm_bbox == fig['bbox']
        matched_other = None
        for ofid, ofig in fig_lookup.items():
            if ofid != fid and ofig['bbox'] == vlm_bbox:
                matched_other = ofid
                break
        checks['bbox'] = {
            'status': 'PASS' if bbox_match else 'FAIL',
            'vlm_value': vlm_bbox,
            'figure_parser_value': fig['bbox'],
            'match': bbox_match,
            'matches_other_figure': matched_other,
        }
    else:
        bbox_match = False
        checks['bbox'] = {'status': 'SKIP', 'reason': 'figure_id not in FigureParser'}

    # 4. Page size
    if fig:
        fp_ps = fig.get('page_size', [])
        vlm_ps = [vlm_page_size.get('width', 0), vlm_page_size.get('height', 0)]
        ps_match = abs(vlm_ps[0] - fp_ps[0]) < 0.01 and abs(vlm_ps[1] - fp_ps[1]) < 0.01
        checks['page_size'] = {
            'status': 'PASS' if ps_match else 'FAIL',
            'vlm_value': vlm_ps,
            'figure_parser_value': fp_ps,
            'match': ps_match,
        }
    else:
        ps_match = False
        checks['page_size'] = {'status': 'SKIP'}

    # 5. Bbox within page bounds
    pw = vlm_page_size.get('width', 595.28)
    ph = vlm_page_size.get('height', 841.89)
    within = (vlm_bbox[0] >= 0 and vlm_bbox[1] >= 0 and vlm_bbox[2] <= pw and vlm_bbox[3] <= ph)
    checks['bbox_within_page'] = {
        'status': 'PASS' if within else 'FAIL',
        'vlm_bbox': vlm_bbox,
        'page_size': [pw, ph],
    }

    # 6. Document IR association
    vlm_doc_ir_match = None
    for eid, info in doc_ir_image_blocks.items():
        if info['page_idx'] == vlm_page and info['bbox'] == vlm_bbox:
            vlm_doc_ir_match = eid
            break
    correct_doc_ir = None
    if fig:
        for eid, info in doc_ir_image_blocks.items():
            if info['page_idx'] == fig['page_idx'] and info['bbox'] == fig['bbox']:
                correct_doc_ir = eid
                break
    checks['document_ir_association'] = {
        'status': 'PASS' if vlm_doc_ir_match == correct_doc_ir else 'FAIL',
        'vlm_matches_element': vlm_doc_ir_match,
        'correct_element': correct_doc_ir,
        'association_correct': vlm_doc_ir_match == correct_doc_ir,
    }

    # 7. Image file existence
    img_path = sa.get('image_file', {}).get('path', '')
    img_exists = os.path.exists(img_path) if img_path else False
    checks['image_file_exists'] = {
        'status': 'PASS' if img_exists else 'FAIL',
        'path': img_path,
    }

    # Classification
    has_critical_fail = any(c['status'] == 'FAIL' for k, c in checks.items() if k in ('image_sha256', 'page_idx'))
    all_pass = all(c['status'] == 'PASS' for c in checks.values())

    if all_pass:
        classification = 'ANCHOR_VALID'
    elif has_critical_fail:
        classification = 'ANCHOR_INVALID'
    elif sha_match and page_match:
        classification = 'ANCHOR_PARTIAL'
    else:
        classification = 'ANCHOR_UNRESOLVED'

    summary['total'] += 1
    summary[classification] += 1

    validation_results.append({
        'record_id': rid,
        'figure_id': fid,
        'classification': classification,
        'checks': checks,
    })

output = {
    'validation_id': 'SA-VAL-005J-001',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'document_id': 'F02',
    'total_records': len(vlm_records),
    'summary': summary,
    'validation_dimensions': [
        'image_sha256', 'page_idx', 'bbox', 'page_size',
        'bbox_within_page', 'document_ir_association', 'image_file_exists',
    ],
    'classification_criteria': {
        'ANCHOR_VALID': 'All 7 checks PASS',
        'ANCHOR_PARTIAL': 'image_sha256+page_idx match, bbox or other non-critical checks fail',
        'ANCHOR_INVALID': 'Critical checks (image_sha256 or page_idx) FAIL',
        'ANCHOR_UNRESOLVED': 'Cannot determine due to missing reference data',
    },
    'key_finding': (
        'All 25 VLM records for F02_fig_07 have bbox from F02_fig_06 '
        '([64,82,276,246] instead of [65,316,273,484]). '
        'image_sha256 is correct, proving VLM analyzed the right image '
        'but SourceAnchor bbox was incorrectly assigned during VLM adapter construction.'
    ),
    'results': validation_results,
}

out_path = 'D:/Knowledge_World/runs/pipeline_001_fix/PIPELINE_005_J/SOURCE_ANCHOR_VALIDATION_RESULTS.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f'Written: {out_path}')
print(f'Summary: {json.dumps(summary, indent=2)}')
