#!/usr/bin/env python3
"""
LINK-001: 正文与SI关联测试

验证主论文中的Figure S/Table S引用与SI文档中对应caption的匹配关系。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def extract_si_references(text: str) -> List[Dict]:
    """Extract Figure S and Table S references from main text."""
    refs = []

    patterns = [
        (r'(Figure|Fig\.?)\s+S(\d+)([a-z])?', 'FIGURE_S', True),
        (r'(Table|TABLE)\s+S(\d+)', 'TABLE_S', False),
    ]

    seen = set()
    for pat, ref_type, has_panel in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            panel = m.group(3) if has_panel and len(m.groups()) >= 3 else None
            key = (ref_type, m.group(2), panel or '')
            if key in seen:
                continue
            seen.add(key)

            refs.append({
                'type': ref_type,
                'id': m.group(2),
                'panel': panel,
                'ref_text': m.group(0),
                'start': m.start(),
                'end': m.end(),
            })

    return refs


def extract_si_captions(content_list: List[Dict]) -> List[Dict]:
    """Extract Figure S and Table S captions from SI content_list."""
    captions = []

    for item in content_list:
        if item.get('type') in ('image', 'table'):
            caps = item.get('img_caption', []) or item.get('table_caption', [])
            for cap_text in caps:
                # Check if caption starts with Figure S or Table S
                m = re.match(r'(Figure|FIGURE|Fig\.?)\s+S(\d+)', cap_text, re.IGNORECASE)
                if m:
                    captions.append({
                        'type': 'FIGURE_S',
                        'id': m.group(2),
                        'caption': cap_text.strip(),
                        'page_idx': item.get('page_idx', 0),
                        'element_id': f"si_p{item.get('page_idx',0)}_img{len(captions)}",
                    })
                    continue

                m = re.match(r'(Table|TABLE)\s+S(\d+)', cap_text, re.IGNORECASE)
                if m:
                    captions.append({
                        'type': 'TABLE_S',
                        'id': m.group(2),
                        'caption': cap_text.strip(),
                        'page_idx': item.get('page_idx', 0),
                        'element_id': f"si_p{item.get('page_idx',0)}_tbl{len(captions)}",
                    })

    return captions


def match_refs_to_captions(
    refs: List[Dict],
    captions: List[Dict],
    main_doc_id: str,
    si_doc_id: str,
) -> List[Dict]:
    """Match main text references to SI captions by type+id."""
    associations = []

    for ref in refs:
        ref_type = ref['type']
        ref_id = ref['id']

        # Find matching caption
        matched_cap = None
        for cap in captions:
            if cap['type'] == ref_type and cap['id'] == ref_id:
                matched_cap = cap
                break

        if matched_cap:
            associations.append({
                'main_doc_id': main_doc_id,
                'si_doc_id': si_doc_id,
                'ref_type': ref_type,
                'ref_id': ref_id,
                'ref_text': ref['ref_text'],
                'main_text_location': f"char_offset={ref['start']}-{ref['end']}",
                'si_caption': matched_cap['caption'][:100],
                'si_page': matched_cap['page_idx'],
                'si_element_id': matched_cap['element_id'],
                'status': 'LINKED',
                'confidence': 0.95,
            })
        else:
            associations.append({
                'main_doc_id': main_doc_id,
                'si_doc_id': si_doc_id,
                'ref_type': ref_type,
                'ref_id': ref_id,
                'ref_text': ref['ref_text'],
                'main_text_location': f"char_offset={ref['start']}-{ref['end']}",
                'si_caption': None,
                'si_page': None,
                'si_element_id': None,
                'status': 'UNRESOLVED',
                'confidence': 0.0,
                'reason': f'No {ref_type} S{ref_id} caption found in SI',
            })

    return associations


def test_p01_link01():
    """Test LINK-001 on P01 main + SI pair."""
    print("=== LINK-001 Test: P01 Main + SI ===\n")

    main_dir = Path('data/test_corpus/mineru_output/P01_main_link01/P01_main/auto')
    si_dir = Path('data/test_corpus/mineru_output/P01_41467_2024_50691_MOESM1_ESM_batch/41467_2024_50691_MOESM1_ESM/auto')

    # Load main text
    main_cl_path = main_dir / 'P01_main_content_list.json'
    with open(main_cl_path, 'r', encoding='utf-8') as f:
        main_cl = json.load(f)

    main_text = ''
    for item in main_cl:
        if item.get('type') == 'text':
            main_text += item.get('text', '') + '\n'

    # Load SI
    si_cl_path = si_dir / '41467_2024_50691_MOESM1_ESM_content_list.json'
    with open(si_cl_path, 'r', encoding='utf-8') as f:
        si_cl = json.load(f)

    # Extract references and captions
    refs = extract_si_references(main_text)
    captions = extract_si_captions(si_cl)

    print(f"Main text: {len(main_text)} chars")
    print(f"  Figure S refs: {sum(1 for r in refs if r['type']=='FIGURE_S')}")
    print(f"  Table S refs: {sum(1 for r in refs if r['type']=='TABLE_S')}")
    print(f"\nSI document:")
    print(f"  Figure S captions: {sum(1 for c in captions if c['type']=='FIGURE_S')}")
    print(f"  Table S captions: {sum(1 for c in captions if c['type']=='TABLE_S')}")

    # Match
    associations = match_refs_to_captions(refs, captions, 'P01_main', 'P01_SI')

    linked = [a for a in associations if a['status'] == 'LINKED']
    unresolved = [a for a in associations if a['status'] == 'UNRESOLVED']

    print(f"\n=== Association Results ===")
    print(f"LINKED: {len(linked)}")
    print(f"UNRESOLVED: {len(unresolved)}")

    if linked:
        print(f"\nSample LINKED associations:")
        for a in linked[:5]:
            print(f"  {a['ref_text']} -> SI p{a['si_page']} {a['si_caption'][:60]}")

    if unresolved:
        print(f"\nSample UNRESOLVED:")
        for a in unresolved[:3]:
            print(f"  {a['ref_text']}: {a.get('reason','')}")

    # Save results
    output_path = Path('data/test_corpus/link01_pair/P01_link01_associations.json')
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(associations, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved: {output_path}")

    # Compute metrics
    total = len(associations)
    link_rate = len(linked) / total if total > 0 else 0
    print(f"\nLINK-001 Success Rate: {len(linked)}/{total} = {link_rate:.1%}")

    return associations


if __name__ == '__main__':
    test_p01_link01()
