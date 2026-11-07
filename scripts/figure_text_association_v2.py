#!/usr/bin/env python3
"""
FIG-001 F4 v2: namespace-aware figure-text association

Fixes v1 issues:
- Figure 1 no longer matches TABLE 1 caption (namespace separation)
- Supports Figure/Fig./FIGURE/Figure S/sub-figure variants
- Status values: CANDIDATE / VERIFIED / REJECTED / UNRESOLVED
- Separates auto-matching from human confirmation
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict


NAMESPACE_FIGURE = 'FIGURE'
NAMESPACE_TABLE = 'TABLE'
NAMESPACE_SCHEME = 'SCHEME'
NAMESPACE_UNKNOWN = 'UNKNOWN'

STATUS_CANDIDATE = 'CANDIDATE'
STATUS_VERIFIED = 'VERIFIED'
STATUS_REJECTED = 'REJECTED'
STATUS_UNRESOLVED = 'UNRESOLVED'


def detect_caption_namespace(caption: str) -> Tuple[str, Optional[str]]:
    """
    Detect the namespace and ID from a caption string.

    Returns:
        (namespace, id_str) e.g. ('FIGURE', '3'), ('TABLE', '1'), ('UNKNOWN', None)
    """
    if not caption:
        return NAMESPACE_UNKNOWN, None

    cap_upper = caption.strip().upper()

    patterns = [
        (r'^FIGURE\s+(\d+[a-z]?(?:\.\d+)?)', NAMESPACE_FIGURE),
        (r'^FIG\.\s*(\d+[a-z]?(?:\.\d+)?)', NAMESPACE_FIGURE),
        (r'^SCHEME\s+(\d+[a-z]?)', NAMESPACE_SCHEME),
        (r'^TABLE\s+(\d+[a-z]?)', NAMESPACE_TABLE),
        (r'^Tab\.\s*(\d+[a-z]?)', NAMESPACE_TABLE),
    ]

    for pattern, ns in patterns:
        m = re.match(pattern, cap_upper)
        if m:
            return ns, m.group(1)

    return NAMESPACE_UNKNOWN, None


def extract_text_references(text: str) -> List[Dict]:
    """
    Extract all Figure/Table/Scheme references from body text.

    Returns list of dicts:
        {ref_text, namespace, id_str, panel, start, end, is_si}
    """
    refs = []

    patterns = [
        (r'Figure\s+S(\d+)([a-z])?', NAMESPACE_FIGURE, True),
        (r'Fig\.\s*S(\d+)([a-z])?', NAMESPACE_FIGURE, True),
        (r'FIGURE\s+S(\d+)([a-z])?', NAMESPACE_FIGURE, True),
        (r'Figure\s+(\d+)([a-z])?', NAMESPACE_FIGURE, False),
        (r'Fig\.\s*(\d+)([a-z])?', NAMESPACE_FIGURE, False),
        (r'FIGURE\s+(\d+)([a-z])?', NAMESPACE_FIGURE, False),
        (r'Table\s+S(\d+)([a-z])?', NAMESPACE_TABLE, True),
        (r'TABLE\s+S(\d+)([a-z])?', NAMESPACE_TABLE, True),
        (r'Table\s+(\d+)([a-z])?', NAMESPACE_TABLE, False),
        (r'TABLE\s+(\d+)([a-z])?', NAMESPACE_TABLE, False),
        (r'Scheme\s+S(\d+)([a-z])?', NAMESPACE_SCHEME, True),
        (r'SCHEME\s+S(\d+)([a-z])?', NAMESPACE_SCHEME, True),
        (r'Scheme\s+(\d+)([a-z])?', NAMESPACE_SCHEME, False),
        (r'SCHEME\s+(\d+)([a-z])?', NAMESPACE_SCHEME, False),
    ]

    seen_spans = set()
    for pat, ns, is_si in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)

            id_str = m.group(1)
            panel = m.group(2) if m.group(2) else None

            prefix = 'S' if is_si else ''
            ref_text = m.group(0)

            refs.append({
                'ref_text': ref_text,
                'namespace': ns,
                'id_str': id_str,
                'panel': panel,
                'is_si': is_si,
                'start': m.start(),
                'end': m.end(),
            })

    refs.sort(key=lambda r: r['start'])
    return refs


def extract_figure_elements(content_list: List[Dict]) -> List[Dict]:
    """
    Extract image/table elements from MinerU content_list.

    Returns list of element dicts with:
        element_id, page_idx, caption, namespace, caption_id, img_path, bbox, type
    """
    elements = []
    img_count = 0
    table_count = 0

    for idx, item in enumerate(content_list):
        item_type = item.get('type', '')

        if item_type == 'image':
            page_idx = item.get('page_idx', 0)
            element_id = f"p{page_idx}_img{idx}"
            captions = item.get('img_caption', [])
            caption_text = ' '.join(captions).strip() if captions else ''
            ns, cap_id = detect_caption_namespace(caption_text)

            elements.append({
                'element_id': element_id,
                'page_idx': page_idx,
                'caption': caption_text,
                'namespace': ns,
                'caption_id': cap_id,
                'img_path': item.get('img_path', ''),
                'bbox': item.get('bbox', []),
                'content_type': 'image',
            })
            img_count += 1

        elif item_type == 'table':
            page_idx = item.get('page_idx', idx)
            element_id = f"p{page_idx}_tbl{idx}"
            captions = item.get('table_caption', [])
            caption_text = ' '.join(captions).strip() if captions else ''
            ns, cap_id = detect_caption_namespace(caption_text)

            elements.append({
                'element_id': element_id,
                'page_idx': page_idx,
                'caption': caption_text,
                'namespace': ns,
                'caption_id': cap_id,
                'img_path': '',
                'bbox': item.get('bbox', []),
                'content_type': 'table',
            })
            table_count += 1

    return elements


def match_elements_to_references(
    elements: List[Dict],
    text_refs: List[Dict],
    doc_id: str,
) -> List[Dict]:
    """
    Namespace-aware matching: only match within same namespace+id.

    Returns list of association record dicts.
    """
    associations = []

    for elem in elements:
        elem_ns = elem['namespace']
        elem_id = elem['caption_id']

        if elem_ns == NAMESPACE_UNKNOWN or elem_id is None:
            associations.append(_make_unresolved(elem, doc_id, 'no_caption_namespace'))
            continue

        best_match = None
        best_confidence = 0.0

        for ref in text_refs:
            if ref['namespace'] != elem_ns:
                continue
            if ref['id_str'] != elem_id:
                continue

            confidence = 0.95
            if ref.get('panel'):
                confidence = 0.85
            if ref.get('is_si') and not elem.get('is_si_caption'):
                confidence = 0.7

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = ref

        if best_match:
            source_elem_id = f"{doc_id}_p{best_match['start']}_ref"
            associations.append({
                'source_element_id': source_elem_id,
                'target_element_id': elem['element_id'],
                'figure_id': best_match['ref_text'],
                'namespace': elem_ns,
                'association_type': 'explicit_reference',
                'confidence': best_confidence,
                'status': STATUS_CANDIDATE,
                'evidence': (
                    f"Text ref '{best_match['ref_text']}' (ns={elem_ns}, id={elem_id}) "
                    f"matches caption '{elem['caption'][:60]}'"
                ),
                'source_anchor': {
                    'document_id': doc_id,
                    'element_type': 'TEXT',
                    'element_id': source_elem_id,
                    'page': best_match['start'],
                    'location': f"char_offset={best_match['start']}-{best_match['end']}",
                    'confidence': best_confidence,
                    'raw_text': best_match['ref_text'],
                },
                'human_review': None,
            })
        else:
            reason = f'no_text_ref_for_{elem_ns}_{elem_id}'
            associations.append(_make_unresolved(elem, doc_id, reason))

    return associations


def _make_unresolved(elem: Dict, doc_id: str, reason: str) -> Dict:
    return {
        'source_element_id': '',
        'target_element_id': elem['element_id'],
        'figure_id': elem['caption'][:30] if elem['caption'] else 'Unknown',
        'namespace': elem['namespace'],
        'association_type': 'unmatched',
        'confidence': 0.0,
        'status': STATUS_UNRESOLVED,
        'evidence': f'Unresolved: {reason}',
        'source_anchor': {
            'document_id': doc_id,
            'element_type': 'FIGURE',
            'element_id': elem['element_id'],
            'page': elem['page_idx'],
            'confidence': 0.0,
        },
        'human_review': None,
    }


def apply_human_review(
    associations: List[Dict],
    review_decisions: Dict[str, str],
) -> List[Dict]:
    """
    Apply human review decisions to CANDIDATE associations.

    review_decisions: {target_element_id: 'VERIFIED' | 'REJECTED'}
    Updates status in-place and returns the list.
    """
    for assoc in associations:
        tid = assoc['target_element_id']
        if tid in review_decisions:
            decision = review_decisions[tid]
            if decision in (STATUS_VERIFIED, STATUS_REJECTED):
                assoc['status'] = decision
                assoc['human_review'] = {
                    'decision': decision,
                    'reviewer': 'human',
                }
    return associations


def process_document(doc_id: str, output_dir: Path) -> List[Dict]:
    """Process a single document: load content_list, extract, match."""
    content_list_path = None
    for pattern in ['main/auto/main_content_list.json', '*content_list.json']:
        matches = list(output_dir.rglob(pattern))
        if matches:
            content_list_path = matches[0]
            break

    if not content_list_path:
        print(f"  [WARN] {doc_id}: content_list.json not found under {output_dir}")
        return []

    with open(content_list_path, 'r', encoding='utf-8') as f:
        content_list = json.load(f)

    elements = extract_figure_elements(content_list)

    text_parts = []
    for item in content_list:
        if item.get('type') == 'text':
            text_parts.append(item.get('text', ''))
    text_content = '\n'.join(text_parts)

    text_refs = extract_text_references(text_content)

    associations = match_elements_to_references(elements, text_refs, doc_id)

    return associations


def run_f07_regression_test(output_base: Path) -> bool:
    """
    Regression test: F07 must NOT match Figure 1 to TABLE 1.
    Returns True if test passes.
    """
    print("\n=== F07 Regression Test ===")
    f07_dir = output_base / 'F07_batch'
    if not f07_dir.exists():
        print("  [SKIP] F07_batch not found")
        return True

    associations = process_document('F07', f07_dir)

    passed = True

    fig_to_table = [a for a in associations
                    if a['namespace'] == NAMESPACE_TABLE
                    and a['figure_id'].startswith('Figure')]
    if fig_to_table:
        print(f"  [FAIL] {len(fig_to_table)} Figure refs incorrectly matched to TABLE captions")
        passed = False
    else:
        print("  [PASS] No Figure-to-Table namespace confusion")

    fig3_match = [a for a in associations
                  if a['target_element_id'] == 'p6_img56'
                  and a['status'] == STATUS_CANDIDATE
                  and a['namespace'] == NAMESPACE_FIGURE]
    if fig3_match:
        print("  [PASS] p6_img56 correctly CANDIDATE (Figure 3 -> FIGURE 3 caption)")
    else:
        print("  [FAIL] p6_img56 (FIGURE 3 caption) should be CANDIDATE with FIGURE namespace")
        passed = False

    p3_img45 = [a for a in associations if a['target_element_id'] == 'p3_img45']
    if p3_img45:
        a = p3_img45[0]
        if a['figure_id'] == 'Table 1' and a['namespace'] == NAMESPACE_TABLE:
            print("  [PASS] p3_img45 (TABLE 1 caption) matched to Table 1, NOT Figure 1")
        elif a['figure_id'].startswith('Figure'):
            print(f"  [FAIL] p3_img45 matched to '{a['figure_id']}' (Figure->Table confusion)")
            passed = False
        else:
            print(f"  [PASS] p3_img45 status={a['status']} (no Figure mismatch)")

    fig1_match = [a for a in associations
                  if a['figure_id'] == 'Figure 1' and a['status'] == STATUS_CANDIDATE]
    if fig1_match:
        print(f"  [FAIL] Figure 1 incorrectly matched to {fig1_match[0]['target_element_id']}")
        passed = False
    else:
        print("  [PASS] Figure 1 has no CANDIDATE match (no FIGURE 1 caption exists)")

    cand = sum(1 for a in associations if a['status'] == STATUS_CANDIDATE)
    unres = sum(1 for a in associations if a['status'] == STATUS_UNRESOLVED)
    print(f"  Summary: {len(associations)} elements, {cand} CANDIDATE, {unres} UNRESOLVED")

    return passed


def main():
    output_base = Path('D:/Knowledge_World/data/test_corpus/mineru_output')

    regression_ok = run_f07_regression_test(output_base)

    test_docs = [
        ('F07', output_base / 'F07_batch'),
        ('P01', output_base / 'P01_41467_2024_50691_MOESM1_ESM_batch'),
        ('PAT01', output_base / 'PAT01_table_test'),
    ]

    all_results = {}

    for doc_id, output_dir in test_docs:
        print(f"\n=== Processing {doc_id} ===")

        if not output_dir.exists():
            print(f"  [SKIP] {output_dir} not found")
            continue

        associations = process_document(doc_id, output_dir)

        candidate = sum(1 for a in associations if a['status'] == STATUS_CANDIDATE)
        unresolved = sum(1 for a in associations if a['status'] == STATUS_UNRESOLVED)
        verified = sum(1 for a in associations if a['status'] == STATUS_VERIFIED)
        rejected = sum(1 for a in associations if a['status'] == STATUS_REJECTED)

        ns_counts = {}
        for a in associations:
            ns = a.get('namespace', 'UNKNOWN')
            ns_counts[ns] = ns_counts.get(ns, 0) + 1

        print(f"  Total elements: {len(associations)}")
        print(f"  CANDIDATE: {candidate}, VERIFIED: {verified}, "
              f"REJECTED: {rejected}, UNRESOLVED: {unresolved}")
        print(f"  Namespaces: {ns_counts}")

        result_file = output_base / f'{doc_id}_figure_associations_v2.json'
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(associations, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {result_file}")

        all_results[doc_id] = {
            'total': len(associations),
            'candidate': candidate,
            'verified': verified,
            'rejected': rejected,
            'unresolved': unresolved,
            'namespaces': ns_counts,
            'result_file': str(result_file),
        }

    summary_file = output_base / 'figure_associations_v2_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n=== Overall Summary ===")
    print(f"Documents: {len(all_results)}")
    total = sum(r['total'] for r in all_results.values())
    total_cand = sum(r['candidate'] for r in all_results.values())
    total_unres = sum(r['unresolved'] for r in all_results.values())
    print(f"Total elements: {total}, CANDIDATE: {total_cand}, UNRESOLVED: {total_unres}")
    print(f"Regression test: {'PASS' if regression_ok else 'FAIL'}")
    print(f"Summary saved: {summary_file}")


if __name__ == '__main__':
    main()
