#!/usr/bin/env python3
"""
EXT-001 Phase 2: 真实LLM六维自动抽取 (v2 - 增强错误处理)

使用配置的LLM API执行P01主论文的完整六维抽取
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

# Set LLM API credentials
os.environ['LLM_API_BASE'] = 'https://chemestack.dicp.ac.cn:8443/v1'
if not os.environ.get('LLM_API_KEY'):
    import warnings; warnings.warn("LLM_API_KEY not set in environment", stacklevel=2)
os.environ['LLM_MODEL'] = 'DeepSeek-Flash'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.core.llm_service import LLMService, ChatMessage
from catalyst_knowledge.core.six_dimension_schema import SixDimensionView
from catalyst_knowledge.prompts.loader import load_prompt


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


def extract_json_from_response(response_text: str, save_raw: bool = True) -> dict:
    """Extract JSON from LLM response, handling various formats."""
    # Save raw response for debugging
    if save_raw:
        raw_file = Path('data/test_corpus/ext01_output/llm_raw_response.txt')
        raw_file.parent.mkdir(exist_ok=True)
        with open(raw_file, 'w', encoding='utf-8') as f:
            f.write(response_text)
        print(f"  Raw response saved: {raw_file}")
    
    # Clean up common issues
    cleaned = response_text.strip()
    
    # Remove markdown code blocks if present
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        # Remove first and last lines if they're markdown
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        cleaned = '\n'.join(lines).strip()
    
    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  Direct parse failed: {e}")
    
    # Try to find JSON block with regex (more permissive)
    # Look for opening { and matching closing }
    brace_count = 0
    start_idx = -1
    end_idx = -1
    
    for i, char in enumerate(cleaned):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i
                break
    
    if start_idx >= 0 and end_idx > start_idx:
        json_str = cleaned[start_idx:end_idx+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"  Brace-matched parse failed: {e}")
    
    # Last resort: try to find any JSON-like structure
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not extract JSON from response. First 300 chars: {cleaned[:300]}")


def run_llm_extraction(paper_content: dict) -> dict:
    """Run LLM extraction with robust error handling."""
    llm = LLMService()
    
    try:
        system_prompt = load_prompt("six-dimension-extraction-prompt")
    except Exception as e:
        print(f"  [WARN] Could not load prompt: {e}")
        system_prompt = """You are a scientific literature extraction assistant. Extract six dimensions of catalysis research from the provided paper content. Return a JSON object with the following structure:

{
  "catalyst_design": {
    "catalyst_system": "string",
    "catalyst_type": "string",
    "active_component": "string",
    "support": "string",
    "synthesis_method": "string",
    "reaction_type": "string",
    "design_rationale": "string"
  },
  "characterization": {
    "techniques_used": ["string"],
    "key_findings": ["string"],
    "in_situ_evidence": "string or null",
    "morphological_evidence": "string",
    "electronic_evidence": "string"
  },
  "performance": {
    "key_metrics": [{"metric_name": "string", "value": "string", "conditions": "string"}],
    "key_claim": "string",
    "benchmark_comparison": "string",
    "reaction_conditions": "string",
    "experiment_matrix": []
  },
  "mechanism": {
    "proposed_pathway": "string",
    "rate_determining_step": "string or null",
    "intermediates": ["string"],
    "computational_support": "string or null",
    "experimental_support": "string"
  },
  "structure_activity": {
    "descriptor": "string or null",
    "relationship_type": "string",
    "evidence_strength": "string",
    "data_points": 0
  },
  "reliability": {
    "time_on_stream": 0.0,
    "cycle_count": 0,
    "mass_transfer_verification": "string or null",
    "reproducibility": "string or null",
    "deactivation_observed": "string or null"
  }
}

Extract only information explicitly stated in the paper. Use null for missing data, never use 0 or empty strings as defaults."""

    user_prompt = f"""## Input
- **标题**: {paper_content['title']}
- **摘要**: {paper_content['abstract']}
- **关键内容** (前6000字): {paper_content['key_content'][:6000]}

Please extract the six dimensions and return a JSON object."""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]

    print("  Calling LLM API...")
    
    # Try with response_format first
    try:
        response = llm.chat(messages, response_format={"type": "json_object"})
        print(f"  Response received: {len(response.content)} chars")
        result = extract_json_from_response(response.content)
        print("  [SUCCESS] JSON parsed from response")
        return result
    except Exception as e:
        print(f"  [WARN] response_format failed: {e}")
        print("  Retrying without response_format...")
    
    # Retry without response_format
    try:
        response = llm.chat(messages)
        print(f"  Response received: {len(response.content)} chars")
        result = extract_json_from_response(response.content)
        print("  [SUCCESS] JSON parsed from response")
        return result
    except Exception as e:
        print(f"  [ERROR] Extraction failed: {e}")
        raise


def create_source_anchors(view: SixDimensionView, doc_id: str, paper_content: dict) -> dict:
    """Create SourceAnchor objects for each dimension with real locations."""
    anchors = {}
    
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
            source_location = "Not specified"
            raw_text_excerpt = ""
            
            for keyword in keywords:
                idx = full_text.lower().find(keyword.lower())
                if idx != -1:
                    start = max(0, idx - 50)
                    end = min(len(full_text), idx + 150)
                    raw_text_excerpt = full_text[start:end].replace('\n', ' ').strip()
                    source_location = f"char offset {idx}"
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
    print("=== EXT-001 Phase 2: Real LLM Extraction (v2) ===\n")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API Base: {os.environ['LLM_API_BASE']}")
    print(f"Model: {os.environ['LLM_MODEL']}\n")

    paper_dir = Path('data/test_corpus/mineru_output/P01_main_link01/P01_main/auto')
    doc_id = 'P01_main'

    print(f"Loading paper content...")
    paper_content = load_paper_content(paper_dir)
    print(f"  Title: {paper_content['title'][:80]}...")
    print(f"  Abstract: {len(paper_content['abstract'])} chars")
    print(f"  Key content: {len(paper_content['key_content'])} chars\n")

    print("Running six-dimension extraction with LLM...")
    
    try:
        llm_result = run_llm_extraction(paper_content)
        print("\n  Validating with Pydantic schema...")
        view = SixDimensionView.model_validate(llm_result)
        print("  [SUCCESS] Schema validation passed!\n")
        extraction_method = "llm_auto"
    except Exception as e:
        print(f"\n  [ERROR] Extraction failed: {e}")
        print(f"  Error type: {type(e).__name__}\n")
        
        error_report = {
            'doc_id': doc_id,
            'extraction_type': 'six_dimension',
            'extraction_method': 'llm_failed',
            'timestamp': datetime.now().isoformat(),
            'error': str(e),
            'error_type': type(e).__name__,
            'api_base': os.environ['LLM_API_BASE'],
            'model': os.environ['LLM_MODEL'],
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
    print(f"Created {len(anchors)} anchors")

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
