#!/usr/bin/env python3
"""
EXT-001 Phase 2: 真实LLM六维自动抽取

使用配置的LLM API执行P01主论文的完整六维抽取
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Set LLM API credentials
os.environ['LLM_API_BASE'] = 'https://chemestack.dicp.ac.cn:8443/v1'
if not os.environ.get('LLM_API_KEY'):
    import warnings; warnings.warn("LLM_API_KEY not set in environment", stacklevel=2)
os.environ['LLM_MODEL'] = 'DeepSeek-Flash'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.core.six_dimension_summarizer import SixDimensionSummarizer
from catalyst_knowledge.core.six_dimension_schema import SixDimensionView


def load_paper_content(paper_dir: Path) -> dict:
    """Load paper content from MinerU output."""
    cl_path = None
    for f in paper_dir.rglob('*content_list.json'):
        cl_path = f
        break

    if not cl_path:
        raise FileNotFoundError(f"No content_list.json found in {paper_dir}")

    with open(cl_path, 'r', encoding='utf-8') as f:
        content_list = json.load(f)

    title = ''
    for item in content_list[:10]:
        if item.get('type') == 'text':
            text = item.get('text', '')
            if len(text) > 20 and len(text) < 300:
                title = text.strip()
                break

    abstract = ''
    full_text = ''
    for item in content_list:
        if item.get('type') == 'text':
            text = item.get('text', '')
            full_text += text + '\n'
            if 'abstract' in text.lower() and len(text) < 2000:
                abstract = text

    if not abstract:
        abstract = full_text[:1000]

    return {
        'title': title,
        'abstract': abstract,
        'key_content': full_text[:8000],
    }


def create_source_anchors(view: SixDimensionView, doc_id: str, paper_content: dict) -> dict:
    """Create SourceAnchor objects for each dimension with real locations."""
    anchors = {}
    
    # Search for dimension keywords in paper content
    full_text = paper_content['key_content']
    
    dimension_keywords = {
        'catalyst_design': ['catalyst', 'Ru NPs/TiN', 'supported', 'design'],
        'characterization': ['XPS', 'XAS', 'SEM', 'TEM', 'characterization', 'analysis'],
        'performance': ['activity', 'overpotential', 'current density', 'performance', 'stability'],
        'mechanism': ['mechanism', 'pathway', 'DFT', 'calculation', 'adsorption'],
        'structure_activity': ['structure-activity', 'descriptor', 'relationship', 'adhesion'],
        'reliability': ['stability', 'time on stream', 'TOS', '1000 h', 'durability', 'degradation'],
    }
    
    for dim_name, keywords in dimension_keywords.items():
        dim_data = getattr(view, dim_name, None)
        if dim_data is None:
            continue
            
        # Check if dimension has data
        has_data = False
        if dim_name == 'catalyst_design' and dim_data.catalyst_system:
            has_data = True
        elif dim_name == 'characterization' and dim_data.techniques_used:
            has_data = True
        elif dim_name == 'performance' and (dim_data.key_claim or dim_data.key_metrics):
            has_data = True
        elif dim_name == 'mechanism' and dim_data.proposed_pathway:
            has_data = True
        elif dim_name == 'structure_activity' and dim_data.descriptor:
            has_data = True
        elif dim_name == 'reliability' and (dim_data.time_on_stream > 0 or dim_data.deactivation_observed):
            has_data = True
        
        if has_data:
            # Find source location
            source_location = "Not specified"
            raw_text_excerpt = ""
            
            for keyword in keywords:
                idx = full_text.lower().find(keyword.lower())
                if idx != -1:
                    # Extract context
                    start = max(0, idx - 50)
                    end = min(len(full_text), idx + 150)
                    raw_text_excerpt = full_text[start:end].replace('\n', ' ').strip()
                    
                    # Estimate page/location
                    char_count = 0
                    page_num = 0
                    for item in json.loads(Path('data/test_corpus/mineru_output/P01_main_link01/P01_main/auto/P01_main_content_list.json').read_text('utf-8')):
                        if item.get('type') == 'text':
                            char_count += len(item.get('text', ''))
                            if char_count > idx:
                                page_num = item.get('page_idx', 0)
                                break
                    
                    source_location = f"Page {page_num}, char offset {idx}"
                    break
            
            anchors[dim_name] = {
                'document_id': doc_id,
                'element_type': 'TEXT',
                'element_id': f'{doc_id}_dim_{dim_name}',
                'dimension': dim_name,
                'confidence': 0.85 if dim_name in ['catalyst_design', 'performance', 'reliability'] else 0.75,
                'source_location': source_location,
                'raw_text_excerpt': raw_text_excerpt[:200] if raw_text_excerpt else "",
            }
    
    return anchors


def main():
    """Run EXT-001 with real LLM extraction."""
    print("=== EXT-001 Phase 2: Real LLM Extraction ===\n")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API Base: {os.environ['LLM_API_BASE']}")
    print(f"Model: {os.environ['LLM_MODEL']}\n")

    paper_dir = Path('data/test_corpus/mineru_output/P01_main_link01/P01_main/auto')
    doc_id = 'P01_main'

    print(f"Loading paper content from {paper_dir}...")
    paper_content = load_paper_content(paper_dir)
    print(f"  Title: {paper_content['title'][:80]}...")
    print(f"  Abstract: {len(paper_content['abstract'])} chars")
    print(f"  Key content: {len(paper_content['key_content'])} chars\n")

    print("Running six-dimension extraction with LLM...")
    summarizer = SixDimensionSummarizer()

    try:
        view = summarizer.summarize(paper_content)
        print("  [SUCCESS] LLM extraction complete!\n")
        extraction_method = "llm_auto"
    except Exception as e:
        print(f"  [ERROR] LLM extraction failed: {e}")
        print(f"  Error type: {type(e).__name__}")
        print(f"\n  Cannot proceed with manual fallback - this is a real LLM test.")
        print(f"  Please check API credentials and network connectivity.\n")
        
        # Save error report
        error_report = {
            'doc_id': doc_id,
            'extraction_type': 'six_dimension',
            'extraction_method': 'llm_failed',
            'timestamp': datetime.now().isoformat(),
            'error': str(e),
            'error_type': type(e).__name__,
            'api_base': os.environ['LLM_API_BASE'],
            'model': os.environ['LLM_MODEL'],
            'paper_content_loaded': True,
            'paper_title': paper_content['title'][:100],
        }
        
        output_dir = Path('data/test_corpus/ext01_output')
        output_dir.mkdir(exist_ok=True)
        error_file = output_dir / f'{doc_id}_ext01_llm_failed.json'
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(error_report, f, indent=2, ensure_ascii=False)
        
        print(f"  Error report saved: {error_file}")
        return False

    # Display results
    print("=== Extraction Results ===\n")

    print("1. Catalyst Design:")
    print(f"   System: {view.catalyst_design.catalyst_system}")
    print(f"   Type: {view.catalyst_design.catalyst_type}")
    print(f"   Active: {view.catalyst_design.active_component}")
    print(f"   Support: {view.catalyst_design.support}")
    print(f"   Reaction: {view.catalyst_design.reaction_type}")

    print("\n2. Characterization:")
    print(f"   Techniques: {', '.join(view.characterization.techniques_used[:5])}")
    print(f"   Key findings: {len(view.characterization.key_findings)} items")

    print("\n3. Performance:")
    print(f"   Key claim: {view.performance.key_claim[:80] if view.performance.key_claim else 'N/A'}")
    print(f"   Metrics: {len(view.performance.key_metrics)} items")

    print("\n4. Mechanism:")
    if view.mechanism:
        print(f"   Pathway: {view.mechanism.proposed_pathway[:80] if view.mechanism.proposed_pathway else 'N/A'}")
    else:
        print("   (not extracted)")

    print("\n5. Structure-Activity:")
    if view.structure_activity:
        print(f"   Descriptor: {view.structure_activity.descriptor}")
    else:
        print("   (not extracted)")

    print("\n6. Reliability:")
    print(f"   TOS: {view.reliability.time_on_stream}h")
    print(f"   Cycles: {view.reliability.cycle_count}")
    if view.reliability.deactivation_observed:
        print(f"   Deactivation: {view.reliability.deactivation_observed}")

    # Cross-validation
    print(f"\n=== Cross-Validation ===")
    print(f"Rules checked: {view.cv_rules_checked}")
    print(f"Warnings: {len(view.cv_warnings)}")
    for w in view.cv_warnings:
        print(f"  [{w['severity'].upper()}] {w['rule_id']}: {w['message']}")

    # Completeness
    completeness = view.completeness()
    print(f"\n=== Completeness ===")
    print(f"Present: {', '.join(completeness['present'])}")
    print(f"Missing: {', '.join(completeness['missing'])}")
    print(f"Coverage: {completeness['coverage']:.0%}")

    # Reliability score
    reliability = view.overall_reliability()
    print(f"\nOverall reliability: {reliability:.3f}")

    # Create SourceAnchors
    anchors = create_source_anchors(view, doc_id, paper_content)
    print(f"\n=== Source Anchors ===")
    print(f"Created {len(anchors)} anchors for dimensions with data")
    for dim_name, anchor in anchors.items():
        print(f"  {dim_name}: {anchor['source_location']}")

    # Save results
    output_dir = Path('data/test_corpus/ext01_output')
    output_dir.mkdir(exist_ok=True)

    result = {
        'doc_id': doc_id,
        'extraction_type': 'six_dimension',
        'extraction_method': extraction_method,
        'extraction_version': '3.0',
        'timestamp': datetime.now().isoformat(),
        'llm_config': {
            'api_base': os.environ['LLM_API_BASE'],
            'model': os.environ['LLM_MODEL'],
        },
        'view': view.model_dump(),
        'source_anchors': anchors,
        'cross_validation': {
            'rules_checked': view.cv_rules_checked,
            'warnings': view.cv_warnings,
        },
        'completeness': completeness,
        'reliability_score': reliability,
        'data_quality_flags': {
            'extraction_status': 'LLM_EXTRACTED',
            'evidence_strength': 'auto_extracted',
            'all_dimensions_extracted': completeness['coverage'] == 1.0,
            'source_anchors_complete': len(anchors) > 0,
            'cross_validation_passed': len(view.cv_warnings) == 0,
        },
    }

    output_file = output_dir / f'{doc_id}_ext01_llm.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved: {output_file}")
    print("\n=== EXT-001 Phase 2 Complete ===")
    
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
