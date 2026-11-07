#!/usr/bin/env python3
"""
Phase 2: Per-Dimension LLM Extraction

Extract each of the 6 dimensions independently to avoid token truncation.
Order: catalyst_design → characterization → performance → mechanism → structure_activity → reliability
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Set LLM API credentials
os.environ['LLM_API_BASE'] = 'https://chemestack.dicp.ac.cn:8443/v1'
if not os.environ.get('LLM_API_KEY'):
    import warnings; warnings.warn("LLM_API_KEY not set in environment", stacklevel=2)
os.environ['LLM_MODEL'] = 'DeepSeek-Flash'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.core.llm_service import LLMService, ChatMessage


# Dimension-specific prompts
DIMENSION_PROMPTS = {
    'catalyst_design': """Extract catalyst design information from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "catalyst_system": "full catalyst system description",
  "catalyst_type": "type of catalyst",
  "active_component": "active catalytic component",
  "support": "support material",
  "synthesis_method": "synthesis method",
  "reaction_type": "target reaction type",
  "design_rationale": "design rationale if mentioned"
}

Paper excerpt:
{content}
""",
    
    'characterization': """Extract characterization results from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "techniques_used": ["list", "of", "techniques"],
  "key_findings": ["list", "of", "key", "findings"],
  "in_situ_evidence": "in-situ characterization evidence or null",
  "morphological_evidence": "morphology description",
  "electronic_evidence": "electronic structure description"
}

Paper excerpt:
{content}
""",
    
    'performance': """Extract performance metrics from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "key_metrics": [
    {
      "metric_name": "metric name",
      "value": "numeric value with unit",
      "conditions": "measurement conditions"
    }
  ],
  "key_claim": "main performance claim",
  "benchmark_comparison": "comparison to benchmarks or empty string",
  "reaction_conditions": "reaction conditions",
  "experiment_matrix": []
}

Paper excerpt:
{content}
""",
    
    'mechanism': """Extract mechanism information from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "proposed_pathway": "proposed reaction pathway",
  "rate_determining_step": "rate determining step or null",
  "intermediates": ["list", "of", "intermediates"],
  "computational_support": "computational evidence or null",
  "experimental_support": "experimental evidence or null"
}

Paper excerpt:
{content}
""",
    
    'structure_activity': """Extract structure-activity relationship from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "descriptor": "structure descriptor",
  "relationship_type": "type of relationship",
  "evidence_strength": "strong/moderate/weak",
  "data_points": number of data points
}

If no clear structure-activity relationship is mentioned, return:
{
  "descriptor": null,
  "relationship_type": null,
  "evidence_strength": null,
  "data_points": 0
}

Paper excerpt:
{content}
""",
    
    'reliability': """Extract reliability and stability data from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "time_on_stream": numeric value in hours (use 0 only if explicitly stated as no stability test),
  "time_on_stream_note": "description of stability test conditions",
  "cycle_count": number of cycles (0 if not mentioned),
  "mass_transfer_verification": "mass transfer verification method or null",
  "reproducibility": "reproducibility evidence or null",
  "deactivation_observed": "deactivation description or null"
}

IMPORTANT: If the paper mentions stability testing for hundreds or thousands of hours, extract the actual number. Do NOT use 0 as default.

Paper excerpt:
{content}
"""
}


def load_paper_content(paper_dir: Path) -> str:
    """Load paper content from MinerU output."""
    cl_path = None
    for f in paper_dir.rglob('*content_list.json'):
        cl_path = f
        break
    
    if not cl_path:
        raise FileNotFoundError(f"No content_list.json found in {paper_dir}")
    
    with open(cl_path, 'r', encoding='utf-8') as f:
        content_list = json.load(f)
    
    # Extract full text
    full_text = ''
    for item in content_list:
        if item.get('type') == 'text':
            text = item.get('text', '')
            full_text += text + '\n'
    
    return full_text


def extract_dimension(
    llm: LLMService,
    dimension: str,
    content: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Extract a single dimension from paper content.
    
    Returns:
        {
            'success': bool,
            'data': dict or None,
            'raw_response': str,
            'error': str or None,
            'attempts': int
        }
    """
    prompt_template = DIMENSION_PROMPTS.get(dimension)
    if not prompt_template:
        return {
            'success': False,
            'data': None,
            'raw_response': '',
            'error': f'Unknown dimension: {dimension}',
            'attempts': 0
        }
    
    # Truncate content to avoid token limits
    # Use first 6000 chars for most dimensions
    content_truncated = content[:6000] if len(content) > 6000 else content
    
    prompt = prompt_template.replace('{content}', content_truncated)
    
    messages = [ChatMessage(role='user', content=prompt)]
    
    for attempt in range(max_retries + 1):
        try:
            response = llm.chat(
                messages,
                response_format={'type': 'json_object'}
            )
            
            raw_response = response.content
            
            # Parse JSON
            data = json.loads(raw_response)
            
            return {
                'success': True,
                'data': data,
                'raw_response': raw_response,
                'error': None,
                'attempts': attempt + 1
            }
            
        except json.JSONDecodeError as e:
            if attempt < max_retries:
                continue
            return {
                'success': False,
                'data': None,
                'raw_response': raw_response if 'raw_response' in locals() else '',
                'error': f'JSON parse error: {str(e)}',
                'attempts': attempt + 1
            }
        except Exception as e:
            if attempt < max_retries:
                continue
            return {
                'success': False,
                'data': None,
                'raw_response': '',
                'error': f'LLM call failed: {str(e)}',
                'attempts': attempt + 1
            }


def main():
    """Run per-dimension extraction."""
    
    print("="*60)
    print("Phase 2: Per-Dimension LLM Extraction")
    print("="*60)
    print()
    
    # Load paper content
    paper_dir = Path('data/test_corpus/mineru_output/P01_main_link01/P01_main/auto')
    print(f"Loading paper content from: {paper_dir}")
    
    try:
        content = load_paper_content(paper_dir)
        print(f"Content loaded: {len(content)} chars")
    except Exception as e:
        print(f"[ERROR] Failed to load paper content: {e}")
        return
    
    print()
    
    # Initialize LLM service
    llm = LLMService(max_tokens=2048)  # Reduced per-dimension
    print(f"LLM Service initialized: model={llm.model}, max_tokens={llm.max_tokens}")
    print()
    
    # Extract each dimension
    dimensions = [
        'catalyst_design',
        'characterization',
        'performance',
        'mechanism',
        'structure_activity',
        'reliability'
    ]
    
    results = {}
    output_dir = Path('data/test_corpus/ext01_output/phase2_per_dimension')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for dim in dimensions:
        print(f"Extracting dimension: {dim}")
        
        result = extract_dimension(llm, dim, content)
        results[dim] = result
        
        # Save raw response
        raw_file = output_dir / f'{dim}_raw_response.txt'
        with open(raw_file, 'w', encoding='utf-8') as f:
            f.write(result['raw_response'])
        
        if result['success']:
            print(f"  [PASS] Extracted successfully (attempts: {result['attempts']})")
            
            # Save extracted data
            data_file = output_dir / f'{dim}_extracted.json'
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(result['data'], f, indent=2, ensure_ascii=False)
            
            # Show key fields
            data = result['data']
            if dim == 'catalyst_design':
                print(f"         catalyst_system: {data.get('catalyst_system', 'N/A')[:50]}")
            elif dim == 'performance':
                metrics = data.get('key_metrics', [])
                print(f"         key_metrics: {len(metrics)} items")
            elif dim == 'reliability':
                tos = data.get('time_on_stream', 'N/A')
                print(f"         time_on_stream: {tos}h")
        else:
            print(f"  [FAIL] {result['error']} (attempts: {result['attempts']})")
        
        print()
    
    # Summary
    print("="*60)
    print("EXTRACTION SUMMARY")
    print("="*60)
    
    success_count = sum(1 for r in results.values() if r['success'])
    total_count = len(results)
    
    print(f"Total dimensions: {total_count}")
    print(f"Successful: {success_count}")
    print(f"Failed: {total_count - success_count}")
    print(f"Success rate: {success_count / total_count * 100:.1f}%")
    print()
    
    # Check key scientific data
    reliability_result = results.get('reliability', {})
    if reliability_result.get('success'):
        tos = reliability_result['data'].get('time_on_stream', 'N/A')
        print(f"Reliability TOS: {tos}h")
        if tos == 0:
            print("[WARN] TOS=0 detected - verify if this is correct")
        elif tos >= 100:
            print(f"[PASS] TOS={tos}h supports stability claims")
    else:
        print("Reliability: NOT EXTRACTED")
    
    print()
    
    # Save summary
    summary = {
        'timestamp': datetime.now().isoformat(),
        'paper': 'P01_main',
        'model': llm.model,
        'max_tokens_per_dimension': llm.max_tokens,
        'dimensions': {
            dim: {
                'success': r['success'],
                'attempts': r['attempts'],
                'error': r['error']
            }
            for dim, r in results.items()
        },
        'success_rate': success_count / total_count,
        'output_dir': str(output_dir)
    }
    
    summary_file = output_dir / 'extraction_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"Summary saved: {summary_file}")
    
    return results


if __name__ == '__main__':
    main()
