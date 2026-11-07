"""
G3-VERIFY-002 Part A: TAX-001 Classification Fix

Diagnosed issue: F02 and PAT01 returned empty LLM responses (content=None)
causing JSON parse error "Expecting value: line 1 column 1 (char 0)"

Fixes:
1. Save raw LLM response for every call (debugging evidence)
2. Robust JSON extraction from response (handle markdown wrapping)
3. Schema validation after parsing
4. Limited retry (max 2 attempts) with backoff
5. Preserve original output - never fabricate classification results
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

os.environ['LLM_API_BASE'] = 'https://chemestack.dicp.ac.cn:8443/v1'
if not os.environ.get('LLM_API_KEY'):
    import warnings; warnings.warn("LLM_API_KEY not set in environment", stacklevel=2)
os.environ['LLM_MODEL'] = 'DeepSeek-Flash'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.core.llm_service import LLMService, ChatMessage


TAXONOMY_VOCABULARY_V1 = {
    'version': '1.0',
    'status': 'engineering_candidate',
    'categories': {
        'reaction_type': [
            'hydrogen_evolution', 'oxygen_evolution', 'oxygen_reduction',
            'co2_reduction', 'oxidation', 'reduction', 'coupling',
            'nitration', 'carbonylation', 'oxidative_dehydrogenation',
            'photothermal_catalysis', 'photoelectrochemistry',
            'co2_reduction', 'other'
        ],
        'catalyst_type': [
            'metal_nanoparticle', 'metal_oxide', 'metal_sulfide',
            'carbon_based', 'mof', 'zeolite', 'enzyme',
            'photocatalyst', 'electrocatalyst', 'thermocatalyst',
            'biocatalyst', 'metal_boron_compound', 'other'
        ],
        'application_domain': [
            'energy_conversion', 'environmental_remediation',
            'chemical_synthesis', 'petrochemical', 'pharmaceutical',
            'materials_science', 'other'
        ],
        'document_type': [
            'research_article', 'review', 'patent', 'communication', 'other'
        ]
    }
}


CLASSIFICATION_PROMPT = """You are a scientific document classifier for catalysis research.

Classify the following document into multiple categories. Choose from these exact vocabularies:

## reaction_type options: {reaction_types}
## catalyst_type options: {catalyst_types}
## application_domain options: {application_domains}
## document_type options: {document_types}

## Document information:
- Document ID: {doc_id}
- Title: {title}
- Catalyst system: {catalyst_system}
- Reaction type (from extraction): {reaction_type_extracted}
- Key findings: {key_findings}

## Output format
Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
  "reaction_type": {{
    "labels": ["label1"],
    "confidence": 0.0,
    "evidence": "one sentence from the document"
  }},
  "catalyst_type": {{
    "labels": ["label1"],
    "confidence": 0.0,
    "evidence": "one sentence from the document"
  }},
  "application_domain": {{
    "labels": ["label1"],
    "confidence": 0.0,
    "evidence": "one sentence from the document"
  }},
  "document_type": {{
    "labels": ["label1"],
    "confidence": 0.0,
    "evidence": "one sentence from the document"
  }},
  "overall_confidence": 0.0,
  "pending_review": false,
  "review_reason": ""
}}

Rules:
- Each "labels" array must contain ONLY values from the vocabulary lists above
- confidence must be a float between 0.0 and 1.0
- If uncertain, set pending_review to true
- Do NOT include any text outside the JSON object
"""


def load_document_info(doc_id: str) -> Dict[str, Any]:
    """Load document information for classification."""
    extraction_dir = Path(f'data/test_corpus/g3_output/{doc_id}')
    
    catalyst_design = {}
    characterization = {}
    performance = {}
    
    for name, target in [('catalyst_design', catalyst_design), 
                          ('characterization', characterization),
                          ('performance', performance)]:
        f = extraction_dir / f'{name}_extracted.json'
        if f.exists():
            with open(f, 'r', encoding='utf-8') as fh:
                target.update(json.load(fh))
    
    title = catalyst_design.get('catalyst_system', f'{doc_id} document')
    if isinstance(title, str) and len(title) > 100:
        title = title[:100]
    
    key_findings = characterization.get('key_findings', [])
    if isinstance(key_findings, str):
        key_findings = [key_findings]
    
    return {
        'doc_id': doc_id,
        'title': title,
        'catalyst_system': str(catalyst_design.get('catalyst_system', ''))[:200],
        'reaction_type_extracted': str(catalyst_design.get('reaction_type', ''))[:200],
        'key_findings': '; '.join(str(f) for f in key_findings[:3])[:500]
    }


def extract_json_from_response(response_text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling various formats."""
    if not response_text or not response_text.strip():
        return None
    
    cleaned = response_text.strip()
    
    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Remove markdown code blocks
    md_pattern = r'```(?:json)?\s*\n?(.*?)\n?\s*```'
    match = re.search(md_pattern, cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON object in text
    brace_count = 0
    start = -1
    for i, char in enumerate(cleaned):
        if char == '{':
            if brace_count == 0:
                start = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start >= 0:
                try:
                    return json.loads(cleaned[start:i+1])
                except json.JSONDecodeError:
                    start = -1
    
    return None


def validate_classification_schema(result: dict) -> list:
    """Validate classification result against schema. Returns list of errors."""
    errors = []
    vocab = TAXONOMY_VOCABULARY_V1['categories']
    
    required_categories = ['reaction_type', 'catalyst_type', 'application_domain', 'document_type']
    
    for cat in required_categories:
        if cat not in result:
            errors.append(f"Missing category: {cat}")
            continue
        
        cat_data = result[cat]
        if not isinstance(cat_data, dict):
            errors.append(f"{cat}: not a dict")
            continue
        
        if 'labels' not in cat_data:
            errors.append(f"{cat}: missing labels")
        elif not isinstance(cat_data['labels'], list):
            errors.append(f"{cat}: labels not a list")
        else:
            valid_labels = vocab.get(cat, [])
            for label in cat_data['labels']:
                if label not in valid_labels:
                    errors.append(f"{cat}: invalid label '{label}' (valid: {valid_labels})")
        
        if 'confidence' not in cat_data:
            errors.append(f"{cat}: missing confidence")
        elif not isinstance(cat_data['confidence'], (int, float)):
            errors.append(f"{cat}: confidence not a number")
        elif not (0.0 <= cat_data['confidence'] <= 1.0):
            errors.append(f"{cat}: confidence out of range [0,1]")
        
        if 'evidence' not in cat_data:
            errors.append(f"{cat}: missing evidence")
    
    if 'overall_confidence' not in result:
        errors.append("Missing overall_confidence")
    elif not isinstance(result['overall_confidence'], (int, float)):
        errors.append("overall_confidence not a number")
    
    return errors


def classify_document(doc_id: str, llm: LLMService, output_dir: Path, 
                      max_retries: int = 2) -> Dict[str, Any]:
    """Classify a document using LLM with retry and evidence preservation."""
    
    print(f"\n{'='*50}")
    print(f"Classifying: {doc_id}")
    print(f"{'='*50}")
    
    doc_info = load_document_info(doc_id)
    vocab = TAXONOMY_VOCABULARY_V1['categories']
    
    prompt = CLASSIFICATION_PROMPT.format(
        reaction_types=', '.join(vocab['reaction_type']),
        catalyst_types=', '.join(vocab['catalyst_type']),
        application_domains=', '.join(vocab['application_domain']),
        document_types=', '.join(vocab['document_type']),
        **doc_info
    )
    
    messages = [ChatMessage(role='user', content=prompt)]
    
    raw_file = output_dir / f'classification_raw_response.txt'
    result_file = output_dir / f'classification.json'
    
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        print(f"  Attempt {attempt}/{max_retries}...")
        
        try:
            response = llm.chat(
                messages,
                response_format={'type': 'json_object'}
            )
            
            raw_content = response.content or ""
            
            # Save raw response (always, for evidence)
            with open(raw_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Attempt {attempt} ===\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Model: {llm.model}\n")
                f.write(f"Content length: {len(raw_content)}\n")
                f.write(f"Usage: {response.usage}\n")
                f.write(f"\n--- Raw content ---\n")
                f.write(raw_content)
                f.write(f"\n--- End ---\n")
            
            print(f"  Raw response: {len(raw_content)} chars")
            
            if not raw_content.strip():
                last_error = "Empty response from LLM"
                print(f"  [WARN] {last_error}")
                if attempt < max_retries:
                    time.sleep(2)
                continue
            
            # Extract JSON
            parsed = extract_json_from_response(raw_content)
            
            if parsed is None:
                last_error = f"Could not extract JSON from response (length={len(raw_content)})"
                print(f"  [WARN] {last_error}")
                if attempt < max_retries:
                    time.sleep(2)
                continue
            
            # Validate schema
            schema_errors = validate_classification_schema(parsed)
            
            if schema_errors:
                last_error = f"Schema validation failed: {schema_errors}"
                print(f"  [WARN] {last_error}")
                # Still save the result but mark as failed
                parsed['_schema_errors'] = schema_errors
            
            # Add metadata
            parsed['metadata'] = {
                'doc_id': doc_id,
                'timestamp': datetime.now().isoformat(),
                'model': llm.model,
                'vocabulary_version': TAXONOMY_VOCABULARY_V1['version'],
                'vocabulary_status': TAXONOMY_VOCABULARY_V1['status'],
                'attempt': attempt,
                'raw_response_file': str(raw_file)
            }
            
            # Determine status
            if schema_errors:
                parsed['status'] = 'FAILED'
                parsed['error'] = last_error
                parsed['pending_review'] = True
                parsed['review_reason'] = f'Schema validation failed: {schema_errors}'
            elif parsed.get('pending_review', False):
                parsed['status'] = 'PENDING_REVIEW'
            elif parsed.get('overall_confidence', 0) < 0.7:
                parsed['status'] = 'LOW_CONFIDENCE'
            else:
                parsed['status'] = 'ACCEPTED'
            
            # Save result
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(parsed, f, indent=2, ensure_ascii=False)
            
            print(f"  Status: {parsed['status']}")
            print(f"  Overall confidence: {parsed.get('overall_confidence', 0):.2f}")
            
            for cat in ['reaction_type', 'catalyst_type', 'application_domain', 'document_type']:
                cat_data = parsed.get(cat, {})
                labels = cat_data.get('labels', [])
                conf = cat_data.get('confidence', 0)
                print(f"  {cat}: {labels} (confidence: {conf:.2f})")
            
            return parsed
            
        except Exception as e:
            last_error = f"Exception: {type(e).__name__}: {e}"
            print(f"  [ERROR] {last_error}")
            
            # Save error evidence
            with open(raw_file, 'a', encoding='utf-8') as f:
                f.write(f"\n=== Attempt {attempt} EXCEPTION ===\n")
                f.write(f"{last_error}\n")
            
            if attempt < max_retries:
                time.sleep(3)
    
    # All retries exhausted - save failure record
    print(f"  [FAIL] All {max_retries} attempts failed for {doc_id}")
    
    failure_record = {
        'metadata': {
            'doc_id': doc_id,
            'timestamp': datetime.now().isoformat(),
            'model': llm.model,
            'vocabulary_version': TAXONOMY_VOCABULARY_V1['version'],
            'vocabulary_status': TAXONOMY_VOCABULARY_V1['status'],
            'attempts': max_retries,
            'raw_response_file': str(raw_file)
        },
        'status': 'FAILED',
        'error': last_error,
        'pending_review': True,
        'review_reason': f'Classification failed after {max_retries} attempts: {last_error}'
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(failure_record, f, indent=2, ensure_ascii=False)
    
    return failure_record


def main():
    """Run TAX-001 classification fix for all documents."""
    
    print("="*60)
    print("G3-VERIFY-002 Part A: TAX-001 Classification Fix")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Vocabulary version: {TAXONOMY_VOCABULARY_V1['version']}")
    print(f"Vocabulary status: {TAXONOMY_VOCABULARY_V1['status']}")
    
    llm = LLMService(max_tokens=2048)
    print(f"LLM Service: model={llm.model}, max_tokens=2048")
    
    doc_ids = ['F02', 'F07', 'PAT01']
    all_results = {}
    
    for doc_id in doc_ids:
        output_dir = Path(f'data/test_corpus/g3_output/{doc_id}')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        result = classify_document(doc_id, llm, output_dir, max_retries=2)
        all_results[doc_id] = result
    
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
    
    success_rate = status_counts.get('ACCEPTED', 0) / len(all_results) * 100
    print(f"\nSuccess rate: {success_rate:.1f}%")
    
    # Save summary
    output_dir = Path('data/test_corpus/g3_output')
    summary_file = output_dir / 'classification_v2_summary.json'
    
    summary = {
        'timestamp': datetime.now().isoformat(),
        'task': 'G3-VERIFY-002 Part A: TAX-001 Classification Fix',
        'vocabulary_version': TAXONOMY_VOCABULARY_V1['version'],
        'vocabulary_status': TAXONOMY_VOCABULARY_V1['status'],
        'total_documents': len(all_results),
        'status_counts': status_counts,
        'success_rate': f"{success_rate:.1f}%",
        'documents': {
            doc_id: {
                'status': r.get('status'),
                'overall_confidence': r.get('overall_confidence'),
                'pending_review': r.get('pending_review'),
                'error': r.get('error'),
                'output_file': f'data/test_corpus/g3_output/{doc_id}/classification.json',
                'raw_file': f'data/test_corpus/g3_output/{doc_id}/classification_raw_response.txt'
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
