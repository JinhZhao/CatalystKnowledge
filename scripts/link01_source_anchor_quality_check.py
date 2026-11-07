#!/usr/bin/env python3
"""
LINK-001 & SourceAnchor 质量检查

1. 对P01的43条匹配引用进行分层抽样核验
2. 检查Fig. S40和Table S1匹配失败原因
3. 按命名空间分别统计关联准确率
4. 从结构化记录回链到PDF原文
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def load_link01_results() -> List[Dict]:
    """Load LINK-001 association results."""
    link_file = Path('data/test_corpus/link01_pair/P01_link01_associations.json')
    with open(link_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_paper_content() -> Tuple[str, List[Dict]]:
    """Load P01 main paper content."""
    cl_file = Path('data/test_corpus/mineru_output/P01_main_link01/P01_main/auto/P01_main_content_list.json')
    with open(cl_file, 'r', encoding='utf-8') as f:
        content_list = json.load(f)
    
    full_text = ''
    for item in content_list:
        if item.get('type') == 'text':
            full_text += item.get('text', '') + '\n'
    
    return full_text, content_list


def load_si_content() -> List[Dict]:
    """Load P01 SI content."""
    si_file = Path('data/test_corpus/mineru_output/P01_41467_2024_50691_MOESM1_ESM_batch/41467_2024_50691_MOESM1_ESM/auto/41467_2024_50691_MOESM1_ESM_content_list.json')
    with open(si_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_namespace_distribution(associations: List[Dict]) -> Dict:
    """Analyze associations by namespace."""
    stats = {
        'FIGURE_S': {'total': 0, 'linked': 0, 'unresolved': 0},
        'TABLE_S': {'total': 0, 'linked': 0, 'unresolved': 0},
    }
    
    for assoc in associations:
        ref_type = assoc['ref_type']
        status = assoc['status']
        
        if ref_type not in stats:
            stats[ref_type] = {'total': 0, 'linked': 0, 'unresolved': 0}
        
        stats[ref_type]['total'] += 1
        if status == 'LINKED':
            stats[ref_type]['linked'] += 1
        elif status == 'UNRESOLVED':
            stats[ref_type]['unresolved'] += 1
    
    return stats


def check_unresolved_cases(associations: List[Dict], si_content: List[Dict]) -> Dict:
    """Check why Fig. S40 and Table S1 are unresolved."""
    unresolved = [a for a in associations if a['status'] == 'UNRESOLVED']
    
    # Extract all Figure S and Table S captions from SI
    si_figure_s = []
    si_table_s = []
    
    for item in si_content:
        if item.get('type') in ('image', 'table'):
            caps = item.get('img_caption', []) or item.get('table_caption', [])
            for cap in caps:
                if re.match(r'Figure\s+S\d+', cap, re.IGNORECASE):
                    match = re.search(r'S(\d+)', cap)
                    if match:
                        si_figure_s.append(int(match.group(1)))
                elif re.match(r'Table\s+S\d+', cap, re.IGNORECASE):
                    match = re.search(r'S(\d+)', cap)
                    if match:
                        si_table_s.append(int(match.group(1)))
    
    results = {}
    for item in unresolved:
        ref_id = item['ref_id']
        ref_type = item['ref_type']
        
        if ref_type == 'FIGURE_S':
            exists_in_si = int(ref_id) in si_figure_s
            results[f'Fig. S{ref_id}'] = {
                'exists_in_si': exists_in_si,
                'si_has_figure_s': sorted(set(si_figure_s)),
                'max_figure_s': max(si_figure_s) if si_figure_s else 0,
                'reason': 'Not in SI' if not exists_in_si else 'Unknown',
            }
        elif ref_type == 'TABLE_S':
            exists_in_si = int(ref_id) in si_table_s
            results[f'Table S{ref_id}'] = {
                'exists_in_si': exists_in_si,
                'si_has_table_s': sorted(set(si_table_s)),
                'max_table_s': max(si_table_s) if si_table_s else 0,
                'reason': 'Not in SI' if not exists_in_si else 'Unknown',
            }
    
    return results


def sample_verification(associations: List[Dict], paper_text: str, si_content: List[Dict], sample_size: int = 5) -> List[Dict]:
    """Randomly sample and verify LINKED associations."""
    import random
    linked = [a for a in associations if a['status'] == 'LINKED']
    
    if len(linked) <= sample_size:
        sample = linked
    else:
        sample = random.sample(linked, sample_size)
    
    verified = []
    for assoc in sample:
        ref_text = assoc['ref_text']
        si_caption = assoc['si_caption']
        
        # Check if reference exists in paper text
        ref_in_paper = ref_text in paper_text or ref_text.replace('.', '') in paper_text
        
        # Check if caption exists in SI
        caption_in_si = False
        for item in si_content:
            caps = item.get('img_caption', []) or item.get('table_caption', [])
            for cap in caps:
                if si_caption[:50] in cap:
                    caption_in_si = True
                    break
        
        verified.append({
            'ref_text': ref_text,
            'si_caption_preview': si_caption[:80],
            'ref_in_paper': ref_in_paper,
            'caption_in_si': caption_in_si,
            'verification': 'PASS' if (ref_in_paper and caption_in_si) else 'FAIL',
        })
    
    return verified


def verify_source_anchors(extraction_file: Path, paper_text: str, content_list: List[Dict]) -> List[Dict]:
    """Verify SourceAnchors can locate original text."""
    with open(extraction_file, 'r', encoding='utf-8') as f:
        extraction = json.load(f)
    
    anchors = extraction.get('source_anchors', {})
    verified = []
    
    for dim_name, anchor in anchors.items():
        source_location = anchor.get('source_location', '')
        raw_excerpt = anchor.get('raw_text_excerpt', '')
        
        # Try to find excerpt in paper text
        excerpt_found = False
        page_found = None
        
        if raw_excerpt:
            # Search for key phrases from excerpt
            keywords = raw_excerpt.split()[:5]  # First 5 words
            for keyword in keywords:
                if len(keyword) > 5:  # Only meaningful keywords
                    idx = paper_text.lower().find(keyword.lower())
                    if idx != -1:
                        excerpt_found = True
                        # Find which page this is on
                        char_count = 0
                        for item in content_list:
                            if item.get('type') == 'text':
                                char_count += len(item.get('text', ''))
                                if char_count > idx:
                                    page_found = item.get('page_idx', 0)
                                    break
                        break
        
        verified.append({
            'dimension': dim_name,
            'source_location': source_location,
            'excerpt_preview': raw_excerpt[:80] if raw_excerpt else 'N/A',
            'excerpt_found_in_paper': excerpt_found,
            'page_location': page_found,
            'verification': 'PASS' if excerpt_found else 'FAIL',
        })
    
    return verified


def main():
    """Run comprehensive LINK and SourceAnchor quality check."""
    print("=== LINK-001 & SourceAnchor Quality Check ===\n")
    
    # Load data
    print("1. Loading data...")
    associations = load_link01_results()
    paper_text, content_list = load_paper_content()
    si_content = load_si_content()
    print(f"   Associations: {len(associations)}")
    print(f"   Paper text: {len(paper_text)} chars")
    print(f"   SI content: {len(si_content)} items\n")
    
    # 2. Namespace distribution
    print("2. Namespace distribution analysis...")
    ns_stats = analyze_namespace_distribution(associations)
    for ns, stats in ns_stats.items():
        total = stats['total']
        linked = stats['linked']
        unresolved = stats['unresolved']
        accuracy = linked / total * 100 if total > 0 else 0
        print(f"   {ns}: {linked}/{total} linked ({accuracy:.1f}%), {unresolved} unresolved")
    print()
    
    # 3. Check unresolved cases
    print("3. Checking unresolved cases...")
    unresolved_analysis = check_unresolved_cases(associations, si_content)
    for ref, analysis in unresolved_analysis.items():
        print(f"   {ref}:")
        print(f"      Exists in SI: {analysis['exists_in_si']}")
        print(f"      Reason: {analysis['reason']}")
        if 'FIGURE_S' in ref:
            print(f"      SI has Figure S1-S{analysis['max_figure_s']}")
        elif 'TABLE_S' in ref:
            print(f"      SI has Table S1-S{analysis['max_table_s']}")
    print()
    
    # 4. Sample verification
    print("4. Sample verification (5 random LINKED associations)...")
    sample_results = sample_verification(associations, paper_text, si_content, sample_size=5)
    pass_count = sum(1 for r in sample_results if r['verification'] == 'PASS')
    print(f"   Verification result: {pass_count}/{len(sample_results)} PASS")
    for r in sample_results:
        status = "[PASS]" if r['verification'] == 'PASS' else "[FAIL]"
        print(f"   {status} {r['ref_text']}: ref_in_paper={r['ref_in_paper']}, caption_in_si={r['caption_in_si']}")
    print()
    
    # 5. SourceAnchor verification
    print("5. SourceAnchor verification...")
    extraction_file = Path('data/test_corpus/ext01_output/P01_main_ext01_v2_corrected.json')
    anchor_results = verify_source_anchors(extraction_file, paper_text, content_list)
    anchor_pass = sum(1 for r in anchor_results if r['verification'] == 'PASS')
    print(f"   SourceAnchor result: {anchor_pass}/{len(anchor_results)} PASS")
    for r in anchor_results:
        status = "[PASS]" if r['verification'] == 'PASS' else "[FAIL]"
        page_info = f"page {r['page_location']}" if r['page_location'] is not None else "unknown page"
        print(f"   {status} {r['dimension']}: excerpt_found={r['excerpt_found_in_paper']}, {page_info}")
    print()
    
    # 6. Summary
    print("=== Summary ===")
    total_linked = sum(s['linked'] for s in ns_stats.values())
    total_unresolved = sum(s['unresolved'] for s in ns_stats.values())
    total = total_linked + total_unresolved
    overall_accuracy = total_linked / total * 100 if total > 0 else 0
    
    print(f"LINK-001:")
    print(f"  Total associations: {total}")
    print(f"  Linked: {total_linked} ({overall_accuracy:.1f}%)")
    print(f"  Unresolved: {total_unresolved}")
    print(f"  Sample verification: {pass_count}/{len(sample_results)} PASS")
    print()
    print(f"SourceAnchor:")
    print(f"  Total anchors: {len(anchor_results)}")
    print(f"  Verified: {anchor_pass}/{len(anchor_results)} PASS")
    print()
    
    # Save report
    from datetime import datetime
    report = {
        'timestamp': datetime.now().isoformat(),
        'link01_stats': ns_stats,
        'unresolved_analysis': unresolved_analysis,
        'sample_verification': sample_results,
        'source_anchor_verification': anchor_results,
        'summary': {
            'link01_accuracy': overall_accuracy,
            'sample_verification_rate': pass_count / len(sample_results) * 100 if sample_results else 0,
            'source_anchor_verification_rate': anchor_pass / len(anchor_results) * 100 if anchor_results else 0,
        }
    }
    
    report_file = Path('data/test_corpus/runs/LINK01_source_anchor_quality_report.json')
    report_file.parent.mkdir(exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"Report saved: {report_file}")
    
    return report

if __name__ == '__main__':
    main()
