"""
G3-03: TAX-001 Literature Classification

Verify literature-level multi-label classification workflow.
Record classification results, confidence, evidence, vocabulary version, and pending status.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

os.environ['LLM_API_BASE'] = 'https://chemestack.dicp.ac.cn:8443/v1'
if not os.environ.get('LLM_API_KEY'):
    import warnings; warnings.warn("LLM_API_KEY not set in environment", stacklevel=2)
os.environ['LLM_MODEL'] = 'DeepSeek-Flash'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.core.llm_service import LLMService, ChatMessage


# Engineering taxonomy vocabulary (V1)
TAXONOMY_VOCABULARY_V1 = {
    'version': '1.0',
    'status': 'engineering_candidate',
    'categories': {
        'reaction_type': [
            'hydrogen_evolution',
            'oxygen_evolution',
            'oxygen_reduction',
            'co2_reduction',
            'oxidation',
            'reduction',
            'coupling',
            'nitration',
            'carbonylation',
            'other'
        ],
        'catalyst_type': [
            'metal_nanoparticle',
            'metal_oxide',
            'metal_sulfide',
            'carbon_based',
            'mof',
            'zeolite',
            'enzyme',
            'photocatalyst',
            'electrocatalyst',
            'thermocatalyst',
            'biocatalyst',
            'other'
        ],
        'application_domain': [
            'energy_conversion',
            'environmental_remediation',
            'chemical_synthesis',
            'petrochemical',
            'pharmaceutical',
            'materials_science',
            'other'
        ],
        'document_type': [
            'research_article',
            'review',
            'patent',
            'communication',
            'other'
        ]
    }
}


CLASSIFICATION_PROMPT = """Classify the following scientific document into multiple categories.

Available categories:
- reaction_type: {reaction_types}
- catalyst_type: {catalyst_types}
- application_domain: {application_domains}
- document_type: {document_types}

Document information:
Title: {title}
Catalyst system: {catalyst_system}
Reaction type (from extraction): {reaction_type_extracted}
Key findings: {key_findings}

Return ONLY valid JSON with this structure:
{{
  "reaction_type": {{
    "labels": ["label1", "label2"],
    "confidence": 0.0-1.0,
    "evidence": "brief evidence"
  }},
  "catalyst_type": {{
    "labels": ["label1", "label2"],
    "confidence": 0.0-1.0,
    "evidence": "brief evidence"
  }},
  "application_domain": {{
    "labels": ["label1", "label2"],
    "confidence": 0.0-1.0,
    "evidence": "brief evidence"
  }},
  "document_type": {{
    "labels": ["label1"],
    "confidence": 0.0-1.0,
    "evidence": "brief evidence"
  }},
  "overall_confidence": 0.0-1.0,
  "pending_review": true/false,
  "review_reason": "reason if pending"
}}

If uncertain about any classification, set pending_review to true and explain why.
"""


def load_document_info(doc_id: str) -> Dict[str, Any]:
    """Load document information for classification."""
    
    extraction_dir = Path(f'data/test_corpus/g3_output/{doc_id}')
    
    # Load extraction results
    catalyst_design_file = extraction_dir / 'catalyst_design_extracted.json'
    characterization_file = extraction_dir / 'characterization_extracted.json'
    
    catalyst_design = {}
    characterization = {}
    
    if catalyst_design_file.exists():
        with open(catalyst_design_file, 'r', encoding='utf-8') as f:
            catalyst_design = json.load(f)
    
    if characterization_file.exists():
        with open(characterization_file, 'r', encoding='utf-8') as f:
            characterization = json.load(f)
    
    return {
        'doc_id': doc_id,
        'title': catalyst_design.get('catalyst_system', f'{doc_id} document'),
        'catalyst_system': catalyst_design.get('catalyst_system', ''),
        'reaction_type_extracted': catalyst_design.get('reaction_type', ''),
        'key_findings': characterization.get('key_findings', [])
    }


def classify_document(doc_id: str, llm: LLMService) -> Dict[str, Any]:
    """Classify a document using LLM."""
    
    print(f"\nClassifying document: {doc_id}")
    
    # Load document info
    doc_info = load_document_info(doc_id)
    
    # Prepare prompt
    vocab = TAXONOMY_VOCABULARY_V1['categories']
    
    prompt = CLASSIFICATION_PROMPT.format(
        reaction_types=', '.join(vocab['reaction_type']),
        catalyst_types=', '.join(vocab['catalyst_type']),
        application_domains=', '.join(vocab['application_domain']),
        document_types=', '.join(vocab['document_type']),
        title=doc_info['title'][:100],
        catalyst_system=doc_info['catalyst_system'][:100],
        reaction_type_extracted=doc_info['reaction_type_extracted'][:100],
        key_findings='; '.join(doc_info['key_findings'][:3])
    )
    
    messages = [ChatMessage(role='user', content=prompt)]
    
    try:
        response = llm.chat(
            messages,
            response_format={'type': 'json_object'}
        )
        
        classification = json.loads(response.content)
        
        # Add metadata
        classification['metadata'] = {
            'doc_id': doc_id,
            'timestamp': datetime.now().isoformat(),
            'model': llm.model,
            'vocabulary_version': TAXONOMY_VOCABULARY_V1['version'],
            'vocabulary_status': TAXONOMY_VOCABULARY_V1['status']
        }
        
        # Determine status
        if classification.get('pending_review', False):
            classification['status'] = 'PENDING_REVIEW'
        elif classification.get('overall_confidence', 0) < 0.7:
            classification['status'] = 'LOW_CONFIDENCE'
        else:
            classification['status'] = 'ACCEPTED'
        
        print(f"  Status: {classification['status']}")
        print(f"  Overall confidence: {classification.get('overall_confidence', 0):.2f}")
        
        # Show key classifications
        for category in ['reaction_type', 'catalyst_type', 'application_domain']:
            cat_data = classification.get(category, {})
            labels = cat_data.get('labels', [])
            conf = cat_data.get('confidence', 0)
            print(f"  {category}: {labels} (confidence: {conf:.2f})")
        
        return classification
        
    except Exception as e:
        print(f"  [ERROR] Classification failed: {e}")
        return {
            'metadata': {
                'doc_id': doc_id,
                'timestamp': datetime.now().isoformat(),
                'model': llm.model,
                'vocabulary_version': TAXONOMY_VOCABULARY_V1['version'],
                'vocabulary_status': TAXONOMY_VOCABULARY_V1['status']
            },
            'status': 'FAILED',
            'error': str(e),
            'pending_review': True,
            'review_reason': f'Classification failed: {e}'
        }


def main():
    """Run TAX-001 classification for all documents."""
    
    print("="*60)
    print("G3-03: TAX-001 Literature Classification")
    print("="*60)
    print(f"Vocabulary version: {TAXONOMY_VOCABULARY_V1['version']}")
    print(f"Vocabulary status: {TAXONOMY_VOCABULARY_V1['status']}")
    
    # Initialize LLM service
    llm = LLMService(max_tokens=1024)
    print(f"\nLLM Service: model={llm.model}")
    
    doc_ids = ['F02', 'F07', 'PAT01']
    
    all_results = {}
    
    for doc_id in doc_ids:
        result = classify_document(doc_id, llm)
        all_results[doc_id] = result
        
        # Save individual result
        output_dir = Path(f'data/test_corpus/g3_output/{doc_id}')
        output_file = output_dir / 'classification.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    
    # Summary
    print("\n" + "="*60)
    print("CLASSIFICATION SUMMARY")
    print("="*60)
    
    status_counts = {}
    for doc_id, result in all_results.items():
        status = result.get('status', 'UNKNOWN')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f"Total documents: {len(all_results)}")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")
    
    print("\nVocabulary:")
    print(f"  Version: {TAXONOMY_VOCABULARY_V1['version']}")
    print(f"  Status: {TAXONOMY_VOCABULARY_V1['status']}")
    print(f"  Categories: {len(TAXONOMY_VOCABULARY_V1['categories'])}")
    
    # Save overall summary
    output_dir = Path('data/test_corpus/g3_output')
    summary_file = output_dir / 'classification_summary.json'
    
    summary = {
        'timestamp': datetime.now().isoformat(),
        'vocabulary_version': TAXONOMY_VOCABULARY_V1['version'],
        'vocabulary_status': TAXONOMY_VOCABULARY_V1['status'],
        'total_documents': len(all_results),
        'status_counts': status_counts,
        'documents': {
            doc_id: {
                'status': r.get('status'),
                'overall_confidence': r.get('overall_confidence'),
                'pending_review': r.get('pending_review'),
                'output_file': f'data/test_corpus/g3_output/{doc_id}/classification.json'
            }
            for doc_id, r in all_results.items()
        }
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nSummary saved: {summary_file}")
    
    return all_results


if __name__ == '__main__':
    main()
