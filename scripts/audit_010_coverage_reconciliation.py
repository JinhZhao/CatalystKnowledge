"""
010 Independent Audit: Coverage Denominator Reconciliation
===========================================================
Verify the 68 paragraphs / 18 sections claim and exclusion rationale.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

BASE = Path("D:/Knowledge_World")
CONTENT_LIST = BASE / "data/test_corpus/mineru_output/F02_regression/main/auto/main_content_list.json"

sys.path.insert(0, str(BASE / "src"))
from catalyst_knowledge.pipeline.section_aware_extractor import SectionAwareContentLoader


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main():
    print("="*70)
    print("010 INDEPENDENT AUDIT: COVERAGE DENOMINATOR RECONCILIATION")
    print("="*70)
    
    # Load raw content list
    content_list = load_json(CONTENT_LIST)
    print(f"\nRaw content_list.json:")
    print(f"  Total items: {len(content_list)}")
    
    # Count by type
    type_counts = defaultdict(int)
    for item in content_list:
        type_counts[item.get("type", "unknown")] += 1
    print(f"  Type distribution: {dict(type_counts)}")
    
    # Extract text items
    text_items = [item for item in content_list if item.get("type") == "text"]
    print(f"  Text items: {len(text_items)}")
    
    # Load via SectionAwareContentLoader
    loader = SectionAwareContentLoader(CONTENT_LIST)
    loader.load()
    
    print(f"\nSectionAwareContentLoader analysis:")
    print(f"  Total elements: {len(loader.elements)}")
    print(f"  Total sections: {len(loader.sections)}")
    print(f"  Full text chars: {len(loader.full_text)}")
    
    # Section-by-section analysis
    print(f"\n{'='*70}")
    print("SECTION INVENTORY (18 sections claimed)")
    print(f"{'='*70}")
    
    total_chars = 0
    excluded_chars = 0
    excluded_sections = []
    included_sections = []
    
    for i, section in enumerate(loader.sections):
        is_excluded = loader._is_excluded_section(section.title)
        status = "EXCLUDED" if is_excluded else "INCLUDED"
        
        print(f"\n[{i:2d}] {section.title[:60]}")
        print(f"     Section ID: {section.section_id}")
        print(f"     Level: {section.level}, Pages: {section.page_start}-{section.page_end}")
        print(f"     Chars: {section.char_count}")
        print(f"     Status: {status}")
        
        total_chars += section.char_count
        
        if is_excluded:
            excluded_chars += section.char_count
            excluded_sections.append({
                "index": i,
                "title": section.title,
                "section_id": section.section_id,
                "char_count": section.char_count,
                "page_range": [section.page_start, section.page_end],
            })
        else:
            included_sections.append({
                "index": i,
                "title": section.title,
                "section_id": section.section_id,
                "char_count": section.char_count,
                "page_range": [section.page_start, section.page_end],
            })
    
    print(f"\n{'='*70}")
    print("COVERAGE DENOMINATOR RECONCILIATION")
    print(f"{'='*70}")
    
    print(f"\nTotal sections: {len(loader.sections)}")
    print(f"  Included: {len(included_sections)}")
    print(f"  Excluded: {len(excluded_sections)}")
    
    print(f"\nTotal chars: {total_chars}")
    print(f"  Included chars: {total_chars - excluded_chars}")
    print(f"  Excluded chars: {excluded_chars}")
    print(f"  Inclusion ratio: {(total_chars - excluded_chars) / total_chars * 100:.1f}%")
    
    print(f"\n{'='*70}")
    print("EXCLUDED SECTIONS DETAIL")
    print(f"{'='*70}")
    
    for sec in excluded_sections:
        print(f"\n[{sec['index']:2d}] {sec['title']}")
        print(f"     Section ID: {sec['section_id']}")
        print(f"     Chars: {sec['char_count']}")
        print(f"     Pages: {sec['page_range']}")
        
        # Check if this is truly non-scientific
        title_lower = sec['title'].lower()
        is_metadata = any(kw in title_lower for kw in [
            'reference', 'bibliography', 'acknowledgment', 'acknowledgement',
            'funding', 'author contribution', 'conflict of interest',
            'data availability', 'supporting information', 'supplementary',
            'publisher\'s note', 'publisher note'
        ])
        
        if is_metadata:
            print(f"     Classification: METADATA (non-scientific)")
        else:
            print(f"     Classification: ⚠️ UNCLEAR - may contain scientific content")
    
    print(f"\n{'='*70}")
    print("CRITICAL AUDIT QUESTIONS")
    print(f"{'='*70}")
    
    # Q1: Are all 68 text paragraphs accounted for?
    print(f"\nQ1: Text paragraph count")
    print(f"  Claimed: 68")
    print(f"  Actual (from content_list): {len(text_items)}")
    print(f"  Actual (from loader.elements): {len([e for e in loader.elements if e.element_type == 'text'])}")
    
    if len(text_items) != 68:
        print(f"  ⚠️ MISMATCH: Expected 68, got {len(text_items)}")
    else:
        print(f"  ✅ MATCH")
    
    # Q2: Are all 18 sections accounted for?
    print(f"\nQ2: Section count")
    print(f"  Claimed: 18")
    print(f"  Actual: {len(loader.sections)}")
    
    if len(loader.sections) != 18:
        print(f"  ⚠️ MISMATCH: Expected 18, got {len(loader.sections)}")
    else:
        print(f"  ✅ MATCH")
    
    # Q3: What is the true coverage denominator?
    print(f"\nQ3: Coverage denominator")
    print(f"  Total chars (all sections): {total_chars}")
    print(f"  Included chars (non-excluded): {total_chars - excluded_chars}")
    print(f"  Excluded chars: {excluded_chars}")
    print(f"  Coverage claim: 68.6% = {total_chars - excluded_chars} / {total_chars}")
    
    calculated_coverage = (total_chars - excluded_chars) / total_chars * 100
    print(f"  Calculated: {calculated_coverage:.1f}%")
    
    if abs(calculated_coverage - 68.6) < 0.1:
        print(f"  ✅ MATCH")
    else:
        print(f"  ⚠️ MISMATCH: Expected 68.6%, got {calculated_coverage:.1f}%")
    
    # Q4: Does "100% scientific content" hold?
    print(f"\nQ4: '100% scientific content' claim validation")
    print(f"  Claim: All non-excluded sections are scientific content")
    print(f"  Excluded sections: {len(excluded_sections)}")
    
    # Check if any excluded section might contain scientific content
    scientific_keywords = ['introduction', 'experimental', 'results', 'discussion', 
                          'conclusion', 'method', 'analysis', 'synthesis', 'characterization']
    
    potentially_scientific_excluded = []
    for sec in excluded_sections:
        title_lower = sec['title'].lower()
        if any(kw in title_lower for kw in scientific_keywords):
            potentially_scientific_excluded.append(sec['title'])
    
    if potentially_scientific_excluded:
        print(f"  ⚠️ WARNING: Excluded sections with scientific keywords:")
        for title in potentially_scientific_excluded:
            print(f"     - {title}")
    else:
        print(f"  ✅ No excluded sections appear to contain scientific content")
    
    # Q5: full_text mode coverage
    print(f"\nQ5: full_text mode actual coverage")
    full_text_sections = loader.get_relevant_sections("catalyst_design", mode="full_text")
    full_text_chars = sum(s.char_count for s in full_text_sections)
    
    print(f"  Sections in full_text mode: {len(full_text_sections)}")
    print(f"  Chars in full_text mode: {full_text_chars}")
    print(f"  Coverage: {full_text_chars / total_chars * 100:.1f}%")
    
    if len(full_text_sections) == len(included_sections):
        print(f"  ✅ full_text mode includes all non-excluded sections")
    else:
        print(f"  ⚠️ MISMATCH: full_text has {len(full_text_sections)} sections, expected {len(included_sections)}")
    
    # Generate reconciliation report
    print(f"\n{'='*70}")
    print("RECONCILIATION SUMMARY")
    print(f"{'='*70}")
    
    reconciliation = {
        "audit_id": "010_COVERAGE_DENOMINATOR_RECONCILIATION",
        "document_id": "F02",
        "audit_timestamp": "2026-11-06T23:00:00Z",
        
        "raw_data": {
            "content_list_items": len(content_list),
            "text_items": len(text_items),
            "loader_elements": len(loader.elements),
            "loader_sections": len(loader.sections),
            "full_text_chars": len(loader.full_text),
        },
        
        "claimed_vs_actual": {
            "text_paragraphs": {
                "claimed": 68,
                "actual": len(text_items),
                "match": len(text_items) == 68,
            },
            "sections": {
                "claimed": 18,
                "actual": len(loader.sections),
                "match": len(loader.sections) == 18,
            },
            "coverage_pct": {
                "claimed": 68.6,
                "calculated": round(calculated_coverage, 1),
                "match": abs(calculated_coverage - 68.6) < 0.1,
            },
        },
        
        "coverage_denominator": {
            "total_chars": total_chars,
            "included_chars": total_chars - excluded_chars,
            "excluded_chars": excluded_chars,
            "inclusion_ratio_pct": round((total_chars - excluded_chars) / total_chars * 100, 1),
        },
        
        "excluded_sections": excluded_sections,
        "included_sections": included_sections,
        
        "scientific_content_validation": {
            "all_non_excluded_are_scientific": len(potentially_scientific_excluded) == 0,
            "potentially_scientific_excluded": potentially_scientific_excluded,
        },
        
        "full_text_mode_validation": {
            "sections_in_full_text": len(full_text_sections),
            "chars_in_full_text": full_text_chars,
            "coverage_pct": round(full_text_chars / total_chars * 100, 1),
            "matches_included_sections": len(full_text_sections) == len(included_sections),
        },
        
        "audit_findings": [],
    }
    
    # Generate findings
    if len(text_items) != 68:
        reconciliation["audit_findings"].append({
            "finding_id": "FINDING-COV-001",
            "severity": "MAJOR",
            "description": f"Text paragraph count mismatch: claimed 68, actual {len(text_items)}",
        })
    
    if len(loader.sections) != 18:
        reconciliation["audit_findings"].append({
            "finding_id": "FINDING-COV-002",
            "severity": "MAJOR",
            "description": f"Section count mismatch: claimed 18, actual {len(loader.sections)}",
        })
    
    if abs(calculated_coverage - 68.6) >= 0.1:
        reconciliation["audit_findings"].append({
            "finding_id": "FINDING-COV-003",
            "severity": "MODERATE",
            "description": f"Coverage percentage mismatch: claimed 68.6%, calculated {calculated_coverage:.1f}%",
        })
    
    if potentially_scientific_excluded:
        reconciliation["audit_findings"].append({
            "finding_id": "FINDING-COV-004",
            "severity": "CRITICAL",
            "description": f"Excluded sections may contain scientific content: {potentially_scientific_excluded}",
        })
    
    if len(full_text_sections) != len(included_sections):
        reconciliation["audit_findings"].append({
            "finding_id": "FINDING-COV-005",
            "severity": "MAJOR",
            "description": f"full_text mode section count mismatch: {len(full_text_sections)} vs {len(included_sections)}",
        })
    
    # Overall verdict
    critical_findings = [f for f in reconciliation["audit_findings"] if f["severity"] == "CRITICAL"]
    major_findings = [f for f in reconciliation["audit_findings"] if f["severity"] == "MAJOR"]
    
    if critical_findings:
        reconciliation["overall_verdict"] = "FAIL"
        reconciliation["verdict_rationale"] = f"CRITICAL findings: {len(critical_findings)}"
    elif major_findings:
        reconciliation["overall_verdict"] = "CONDITIONAL_PASS"
        reconciliation["verdict_rationale"] = f"MAJOR findings: {len(major_findings)}, no CRITICAL"
    else:
        reconciliation["overall_verdict"] = "PASS"
        reconciliation["verdict_rationale"] = "All claims verified, no findings"
    
    print(f"\nOverall verdict: {reconciliation['overall_verdict']}")
    print(f"Rationale: {reconciliation['verdict_rationale']}")
    print(f"Findings: {len(reconciliation['audit_findings'])}")
    
    # Save reconciliation report
    output_dir = BASE / "runs/engineering_closeout_010"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "COVERAGE_DENOMINATOR_RECONCILIATION.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(reconciliation, f, indent=2, ensure_ascii=False)
    
    print(f"\nReconciliation report saved to: {output_file}")
    
    return reconciliation


if __name__ == "__main__":
    reconciliation = main()
    
    if reconciliation["overall_verdict"] == "FAIL":
        sys.exit(1)
    elif reconciliation["overall_verdict"] == "CONDITIONAL_PASS":
        sys.exit(2)
    else:
        sys.exit(0)
