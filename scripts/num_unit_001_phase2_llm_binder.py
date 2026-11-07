#!/usr/bin/env python3
"""
NUM-UNIT-001 Phase 2 Part B: LLM Semantic Binding

Bind numeric candidates to scientific quantity types using LLM semantic judgment.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

# Set LLM API credentials
os.environ['LLM_API_BASE'] = 'https://chemestack.dicp.ac.cn:8443/v1'
if not os.environ.get('LLM_API_KEY'):
    import warnings; warnings.warn("LLM_API_KEY not set in environment", stacklevel=2)
os.environ['LLM_MODEL'] = 'DeepSeek-Flash'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent))

from catalyst_knowledge.core.llm_service import LLMService, ChatMessage
from num_unit_001_loader import QuantityRegistryLoader


@dataclass
class SemanticBinding:
    """LLM semantic binding result for a numeric candidate."""
    candidate_id: str
    quantity_type: Optional[str]  # None if AMBIGUOUS
    confidence: float  # 0.0-1.0
    binding_status: str  # "SUCCESS", "AMBIGUOUS", "LOW_CONFIDENCE", "LLM_ERROR"
    catalyst: Optional[str] = None
    reaction: Optional[str] = None
    sample: Optional[str] = None
    experiment: Optional[str] = None
    measurement_context: Optional[str] = None
    reasoning: Optional[str] = None
    llm_model: str = "DeepSeek-Flash"
    prompt_version: str = "v1.0"
    raw_llm_response: Optional[str] = None
    timestamp: str = ""


class LLMSemanticBinder:
    """Bind numeric candidates to quantity types using LLM."""
    
    def __init__(self, registry_loader: QuantityRegistryLoader):
        self.registry = registry_loader.registry
        self.llm = LLMService(temperature=0.1, max_tokens=2048)
        
        # Build quantity type list for prompt
        self.quantity_types = [q.quantity_type for q in self.registry.quantities]
    
    def bind_candidate(
        self,
        candidate: Dict[str, Any],
        context_text: str,
        candidate_id: str
    ) -> SemanticBinding:
        """Bind a single numeric candidate to a quantity type.
        
        Args:
            candidate: NumericCandidate dict from rule extraction
            context_text: Surrounding text context (±200 chars)
            candidate_id: Unique identifier for this candidate
        
        Returns:
            SemanticBinding with quantity_type and confidence
        """
        # Build prompt
        prompt = self._build_binding_prompt(candidate, context_text)
        
        try:
            messages = [
                ChatMessage(role="system", content="You are a scientific data extraction assistant. Analyze numeric values in catalysis research papers and identify their quantity types."),
                ChatMessage(role="user", content=prompt)
            ]
            
            response = self.llm.chat_json(messages)
            
            # Parse response
            quantity_type = response.get('quantity_type')
            confidence = float(response.get('confidence', 0.0))
            reasoning = response.get('reasoning', '')
            
            # Validate quantity_type
            if quantity_type and quantity_type not in self.quantity_types:
                # LLM hallucinated a quantity type
                return SemanticBinding(
                    candidate_id=candidate_id,
                    quantity_type=None,
                    confidence=0.0,
                    binding_status="LLM_ERROR",
                    reasoning=f"Invalid quantity_type: {quantity_type}",
                    raw_llm_response=json.dumps(response),
                    timestamp=datetime.now().isoformat()
                )
            
            # Determine binding status
            if quantity_type is None or response.get('ambiguous', False):
                binding_status = "AMBIGUOUS"
                quantity_type = None
            elif confidence < 0.6:
                binding_status = "LOW_CONFIDENCE"
            else:
                binding_status = "SUCCESS"
            
            return SemanticBinding(
                candidate_id=candidate_id,
                quantity_type=quantity_type,
                confidence=confidence,
                binding_status=binding_status,
                catalyst=response.get('catalyst'),
                reaction=response.get('reaction'),
                sample=response.get('sample'),
                experiment=response.get('experiment'),
                measurement_context=response.get('measurement_context'),
                reasoning=reasoning,
                raw_llm_response=json.dumps(response),
                timestamp=datetime.now().isoformat()
            )
        
        except Exception as e:
            return SemanticBinding(
                candidate_id=candidate_id,
                quantity_type=None,
                confidence=0.0,
                binding_status="LLM_ERROR",
                reasoning=f"LLM call failed: {str(e)}",
                timestamp=datetime.now().isoformat()
            )
    
    def _build_binding_prompt(self, candidate: Dict[str, Any], context: str) -> str:
        """Build prompt for LLM binding."""
        raw_text = candidate.get('raw_text', '')
        raw_value = candidate.get('raw_value', '')
        raw_unit = candidate.get('raw_unit', '')
        
        prompt = f"""Analyze this numeric value from a catalysis research paper and identify its scientific quantity type.

NUMERIC CANDIDATE:
- Raw text: "{raw_text}"
- Value: {raw_value}
- Unit: {raw_unit if raw_unit else '(none)'}

SURROUNDING CONTEXT (±200 characters):
{context}

VALID QUANTITY TYPES (choose one):
{chr(10).join('- ' + qt for qt in self.quantity_types)}

INSTRUCTIONS:
1. Identify which quantity type this value represents based on the unit and context
2. If the unit/meaning is ambiguous (e.g., "T" could be temperature or time), return quantity_type: null and ambiguous: true
3. Extract additional context: catalyst name, reaction type, sample ID, experiment type, measurement conditions
4. Provide confidence score (0.0-1.0) based on clarity of unit and context
5. If you cannot determine the quantity type with confidence, return quantity_type: null

RESPOND WITH ONLY VALID JSON (no markdown, no explanation):
{{
  "quantity_type": "<one of the valid types above, or null if ambiguous>",
  "confidence": <0.0 to 1.0>,
  "ambiguous": <true if unclear which quantity type>,
  "catalyst": "<catalyst name if mentioned, else null>",
  "reaction": "<reaction type if mentioned, else null>",
  "sample": "<sample ID if mentioned, else null>",
  "experiment": "<experiment type if mentioned, else null>",
  "measurement_context": "<measurement conditions if mentioned, else null>",
  "reasoning": "<brief explanation of your decision>"
}}
"""
        return prompt
    
    def bind_batch(
        self,
        candidates: List[Dict[str, Any]],
        document_text: str,
        max_candidates: Optional[int] = None
    ) -> List[SemanticBinding]:
        """Bind a batch of candidates from a document.
        
        Args:
            candidates: List of NumericCandidate dicts
            document_text: Full document text for context extraction
            max_candidates: Limit number of candidates to process (for testing)
        
        Returns:
            List of SemanticBinding objects
        """
        if max_candidates:
            candidates = candidates[:max_candidates]
        
        bindings = []
        
        for idx, candidate in enumerate(candidates):
            # Extract context around candidate position
            source_anchor = candidate.get('source_anchor', {})
            start_pos = source_anchor.get('start_char', 0)
            
            # Get ±200 chars of context
            context_start = max(0, start_pos - 200)
            context_end = min(len(document_text), start_pos + 200)
            context_text = document_text[context_start:context_end]
            
            # Generate candidate ID
            candidate_id = f"cand_{idx:04d}"
            
            # Bind candidate
            binding = self.bind_candidate(candidate, context_text, candidate_id)
            bindings.append(binding)
            
            # Progress indicator
            if (idx + 1) % 10 == 0:
                print(f"  Processed {idx + 1}/{len(candidates)} candidates...")
        
        return bindings


def test_llm_binder():
    """Test LLM binder with sample candidates."""
    print("=" * 70)
    print("NUM-UNIT-001 Phase 2 Part B: LLM Semantic Binding Test")
    print("=" * 70)
    
    # Load registry
    print("\n[1] Loading quantity registry...")
    loader = QuantityRegistryLoader()
    if not loader.load():
        print("ERROR: Failed to load registry")
        return
    
    print(f"[OK] Loaded {len(loader.registry.quantities)} quantities")
    
    # Create binder
    print("\n[2] Creating LLM binder...")
    binder = LLMSemanticBinder(loader)
    print(f"[OK] Binder ready, model={binder.llm.model}")
    
    # Test with sample candidates
    print("\n[3] Testing with sample candidates...")
    
    sample_text = """
    The h-BN/cordierite catalyst achieved 16.8% propane conversion at T = 450 °C 
    with a specific surface area of 1,380 m2/g. The reaction was run for T = 2 h 
    at P = 0.1 MPa. The TOF was 0.05 s-1 and activation energy Ea = 85 kJ/mol.
    """
    
    # Load candidates from Phase 2 rule extraction (if available)
    candidates_file = Path(__file__).parent.parent / 'runs' / 'NUM_UNIT_001_phase2_F02_candidates.json'
    
    if candidates_file.exists():
        print(f"\n[4] Loading candidates from {candidates_file.name}...")
        with open(candidates_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Handle both list and dict structures
            if isinstance(data, list):
                candidates = data
            else:
                candidates = data.get('candidates', [])
        
        # Load F02 document text for context
        f02_doc_file = Path(__file__).parent.parent / 'data' / 'test_corpus' / 'F02' / 'main.md'
        if f02_doc_file.exists():
            with open(f02_doc_file, 'r', encoding='utf-8') as f:
                document_text = f.read()
        else:
            document_text = sample_text
        
        print(f"[OK] Loaded {len(candidates)} candidates")
        
        # Process first 5 candidates as test
        print("\n[5] Binding first 5 candidates...")
        bindings = binder.bind_batch(candidates, document_text, max_candidates=5)
        
        # Report results
        print("\n[6] Binding results:")
        for binding in bindings:
            print(f"\n  Candidate: {binding.candidate_id}")
            print(f"    Quantity Type: {binding.quantity_type}")
            print(f"    Confidence: {binding.confidence:.2f}")
            print(f"    Status: {binding.binding_status}")
            if binding.catalyst:
                print(f"    Catalyst: {binding.catalyst}")
            if binding.reasoning:
                print(f"    Reasoning: {binding.reasoning[:100]}...")
        
        # Summary statistics
        success_count = sum(1 for b in bindings if b.binding_status == "SUCCESS")
        ambiguous_count = sum(1 for b in bindings if b.binding_status == "AMBIGUOUS")
        error_count = sum(1 for b in bindings if b.binding_status == "LLM_ERROR")
        
        print(f"\n[7] Summary:")
        print(f"  SUCCESS: {success_count}/{len(bindings)}")
        print(f"  AMBIGUOUS: {ambiguous_count}/{len(bindings)}")
        print(f"  LLM_ERROR: {error_count}/{len(bindings)}")
        
        # Save results
        output_file = Path(__file__).parent.parent / 'runs' / 'NUM_UNIT_001_phase2_llm_bindings_sample.json'
        output_data = {
            'task': 'NUM-UNIT-001 Phase 2 Part B: LLM Semantic Binding (Sample)',
            'timestamp': datetime.now().isoformat(),
            'bindings': [asdict(b) for b in bindings],
            'summary': {
                'total': len(bindings),
                'success': success_count,
                'ambiguous': ambiguous_count,
                'error': error_count
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n[OK] Results saved to {output_file.name}")
        
    else:
        print(f"\n[4] No candidates file found, creating synthetic test...")
        
        # Create synthetic candidates for testing
        synthetic_candidates = [
            {
                'raw_text': '16.8%',
                'raw_value': '16.8',
                'raw_unit': '%',
                'source_anchor': {'start_char': 50}
            },
            {
                'raw_text': '450 °C',
                'raw_value': '450',
                'raw_unit': '°C',
                'source_anchor': {'start_char': 100}
            },
            {
                'raw_text': '1,380 m2/g',
                'raw_value': '1380',
                'raw_unit': 'm2/g',
                'source_anchor': {'start_char': 150}
            }
        ]
        
        print("\n[5] Binding synthetic candidates...")
        bindings = []
        for idx, cand in enumerate(synthetic_candidates):
            candidate_id = f"synth_{idx:04d}"
            binding = binder.bind_candidate(cand, sample_text, candidate_id)
            bindings.append(binding)
            
            print(f"\n  {candidate_id}: {cand['raw_text']}")
            print(f"    → {binding.quantity_type} (confidence={binding.confidence:.2f}, status={binding.binding_status})")
            if binding.reasoning:
                print(f"    → {binding.reasoning[:100]}...")
        
        # Save results
        output_file = Path(__file__).parent.parent / 'runs' / 'NUM_UNIT_001_phase2_llm_bindings_synthetic.json'
        output_data = {
            'task': 'NUM-UNIT-001 Phase 2 Part B: LLM Semantic Binding (Synthetic)',
            'timestamp': datetime.now().isoformat(),
            'bindings': [asdict(b) for b in bindings],
            'summary': {
                'total': len(bindings),
                'success': sum(1 for b in bindings if b.binding_status == "SUCCESS"),
                'ambiguous': sum(1 for b in bindings if b.binding_status == "AMBIGUOUS"),
                'error': sum(1 for b in bindings if b.binding_status == "LLM_ERROR")
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n[OK] Results saved to {output_file.name}")
    
    print("\n" + "=" * 70)
    print("Phase 2 Part B LLM Semantic Binding Test Complete")
    print("=" * 70)


if __name__ == '__main__':
    test_llm_binder()
