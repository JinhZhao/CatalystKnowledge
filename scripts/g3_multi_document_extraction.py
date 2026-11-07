#!/usr/bin/env python3
"""
G3-STRUCTURE-001: Multi-Document Real LLM Six-Dimension Extraction

Extract 6 dimensions from F02, F07, and PAT01 using per-dimension approach.
Record success rate, field coverage, SourceAnchor coverage, and failure reasons.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# LLM API credentials — read from environment variables (never hardcode keys)
# Set these before running: export LLM_API_KEY=... LLM_API_BASE=... LLM_MODEL=...
if not os.environ.get('LLM_API_KEY'):
    import warnings
    warnings.warn(
        "LLM_API_KEY environment variable not set. "
        "Set it before running: export LLM_API_KEY=your-key-here",
        stacklevel=2,
    )
if not os.environ.get('LLM_API_BASE'):
    os.environ['LLM_API_BASE'] = 'https://chemestack.dicp.ac.cn:8443/v1'
if not os.environ.get('LLM_MODEL'):
    os.environ['LLM_MODEL'] = 'DeepSeek-Flash'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.core.llm_service import LLMService, ChatMessage


# Dimension-specific prompts (same as Phase 2)
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


def load_document_content(doc_id: str) -> tuple:
    """Load document content from MinerU output."""
    
    # Map document IDs to their paths
    doc_paths = {
        'F02': 'data/test_corpus/mineru_output/F02_regression/main/auto',
        'F07': 'data/test_corpus/mineru_output/F07_test/main/auto',
        'PAT01': 'data/test_corpus/mineru_output/PAT01_batch/US20100029974A1/auto',
    }
    
    if doc_id not in doc_paths:
        raise ValueError(f"Unknown document ID: {doc_id}")
    
    paper_dir = Path(doc_paths[doc_id])
    
    # Find content_list.json
    content_file = None
    for f in paper_dir.rglob('*content_list.json'):
        content_file = f
        break
    
    if not content_file or not content_file.exists():
        raise FileNotFoundError(f"No content_list.json found for {doc_id} in {paper_dir}")
    
    with open(content_file, 'r', encoding='utf-8') as f:
        content_list = json.load(f)
    
    # Extract full text
    full_text = ''
    for item in content_list:
        if item.get('type') == 'text':
            text = item.get('text', '')
            full_text += text + '\n'
    
    return full_text, len(content_list)


def extract_dimension(
    llm: LLMService,
    dimension: str,
    content: str,
    max_retries: int = 2
) -> Dict[str, Any]:
    """Extract a single dimension from document content."""
    
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


def extract_all_dimensions(doc_id: str, llm: LLMService) -> Dict[str, Any]:
    """Extract all 6 dimensions from a document."""
    
    print(f"\n{'='*60}")
    print(f"Processing document: {doc_id}")
    print(f"{'='*60}")
    
    # Load content
    try:
        content, block_count = load_document_content(doc_id)
        print(f"Content loaded: {len(content)} chars, {block_count} blocks")
    except Exception as e:
        print(f"[ERROR] Failed to load content: {e}")
        return {
            'doc_id': doc_id,
            'success': False,
            'error': str(e),
            'dimensions': {},
            'summary': {}
        }
    
    # Extract each dimension
    dimensions_order = [
        'catalyst_design',
        'characterization',
        'performance',
        'mechanism',
        'structure_activity',
        'reliability'
    ]
    
    results = {}
    output_dir = Path(f'data/test_corpus/g3_output/{doc_id}')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for dim in dimensions_order:
        print(f"\nExtracting dimension: {dim}")
        
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
                print(f"         catalyst_system: {data.get('catalyst_system', 'N/A')[:60]}")
            elif dim == 'performance':
                metrics = data.get('key_metrics', [])
                print(f"         key_metrics: {len(metrics)} items")
            elif dim == 'reliability':
                tos = data.get('time_on_stream', 'N/A')
                print(f"         time_on_stream: {tos}h")
        else:
            print(f"  [FAIL] {result['error']} (attempts: {result['attempts']})")
    
    # Calculate summary statistics
    success_count = sum(1 for r in results.values() if r['success'])
    total_count = len(results)
    
    # Calculate field coverage
    field_coverage = {}
    for dim, result in results.items():
        if result['success'] and result['data']:
            data = result['data']
            non_null_fields = sum(1 for v in data.values() if v is not None and v != '' and v != [])
            total_fields = len(data)
            field_coverage[dim] = non_null_fields / total_fields if total_fields > 0 else 0
        else:
            field_coverage[dim] = 0
    
    avg_field_coverage = sum(field_coverage.values()) / len(field_coverage) if field_coverage else 0
    
    summary = {
        'doc_id': doc_id,
        'timestamp': datetime.now().isoformat(),
        'content_length': len(content),
        'block_count': block_count,
        'dimensions_extracted': success_count,
        'dimensions_total': total_count,
        'success_rate': success_count / total_count if total_count > 0 else 0,
        'field_coverage': field_coverage,
        'avg_field_coverage': avg_field_coverage,
        'output_dir': str(output_dir)
    }
    
    # Save summary
    summary_file = output_dir / 'extraction_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"Document {doc_id} Summary:")
    print(f"  Success rate: {summary['success_rate'] * 100:.1f}% ({success_count}/{total_count})")
    print(f"  Avg field coverage: {summary['avg_field_coverage'] * 100:.1f}%")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")
    
    return {
        'doc_id': doc_id,
        'success': True,
        'dimensions': results,
        'summary': summary
    }


def main():
    """Run multi-document extraction."""
    
    print("="*60)
    print("G3-STRUCTURE-001: Multi-Document Real LLM Extraction")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Initialize LLM service
    llm = LLMService(max_tokens=2048)
    print(f"\nLLM Service: model={llm.model}, max_tokens={llm.max_tokens}")
    
    # Documents to process
    doc_ids = ['F02', 'F07', 'PAT01']
    
    all_results = {}
    
    for doc_id in doc_ids:
        result = extract_all_dimensions(doc_id, llm)
        all_results[doc_id] = result
    
    # Overall summary
    print("\n" + "="*60)
    print("OVERALL SUMMARY")
    print("="*60)
    
    total_docs = len(all_results)
    successful_docs = sum(1 for r in all_results.values() if r.get('success'))
    
    print(f"Total documents: {total_docs}")
    print(f"Successful: {successful_docs}")
    print(f"Failed: {total_docs - successful_docs}")
    print()
    
    for doc_id, result in all_results.items():
        if result.get('success'):
            summary = result['summary']
            print(f"{doc_id}:")
            print(f"  Success rate: {summary['success_rate'] * 100:.1f}%")
            print(f"  Field coverage: {summary['avg_field_coverage'] * 100:.1f}%")
            print(f"  Dimensions: {summary['dimensions_extracted']}/{summary['dimensions_total']}")
        else:
            print(f"{doc_id}: FAILED - {result.get('error', 'unknown')}")
    
    # Save overall results
    output_dir = Path('data/test_corpus/g3_output')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    overall_summary = {
        'timestamp': datetime.now().isoformat(),
        'model': llm.model,
        'max_tokens_per_dimension': llm.max_tokens,
        'total_documents': total_docs,
        'successful_documents': successful_docs,
        'documents': {
            doc_id: {
                'success': r.get('success', False),
                'summary': r.get('summary', {}),
                'error': r.get('error')
            }
            for doc_id, r in all_results.items()
        }
    }
    
    summary_file = output_dir / 'multi_document_extraction_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(overall_summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nOverall summary saved: {summary_file}")
    
    return all_results


if __name__ == '__main__':
    main()
