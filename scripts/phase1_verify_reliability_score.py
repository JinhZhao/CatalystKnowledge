"""
Phase 1 Verification: Reliability Score Calculation Audit

Verify if reliability_score=0.95 in v2_corrected has calculation basis.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.core.six_dimension_schema import SixDimensionView


def verify_reliability_score(extraction_file: Path) -> dict:
    """Verify reliability_score calculation."""
    
    with open(extraction_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"=== Verifying {extraction_file.name} ===\n")
    
    # Extract view data
    view_data = data.get('view', {})
    
    # Create SixDimensionView from data
    try:
        view = SixDimensionView(**view_data)
        
        # Calculate actual reliability score
        calculated_score = view.overall_reliability()
        recorded_score = data.get('reliability_score', 0.0)
        
        print(f"Recorded reliability_score: {recorded_score}")
        print(f"Calculated reliability_score: {calculated_score}")
        print(f"Match: {abs(calculated_score - recorded_score) < 0.001}")
        print()
        
        # Detailed dimension analysis
        weights = {
            "catalyst_design": 1.0, 
            "characterization": 1.2, 
            "performance": 1.0,
            "mechanism": 1.0, 
            "structure_activity": 0.8, 
            "reliability": 1.5,
        }
        
        print("Dimension-by-dimension analysis:")
        confidences = {}
        for name, weight in weights.items():
            dim = getattr(view, name, None)
            if dim is None:
                confidences[name] = 0.0
                print(f"  {name}: None (confidence=0.0, weight={weight})")
                continue
            
            dumped = dim.model_dump(exclude_defaults=True)
            non_empty = sum(1 for v in dumped.values() if v)
            total = max(len(dumped), 1)
            confidence = min(1.0, non_empty / total)
            confidences[name] = confidence
            
            print(f"  {name}: {non_empty}/{total} fields (confidence={confidence:.3f}, weight={weight})")
        
        print()
        weighted_sum = sum(confidences[n] * w for n, w in weights.items())
        total_weight = sum(weights.values())
        print(f"Weighted sum: {weighted_sum:.3f}")
        print(f"Total weight: {total_weight:.1f}")
        print(f"Final score: {weighted_sum / total_weight:.3f}")
        print()
        
        # Check TOS value
        reliability_dim = view_data.get('reliability', {})
        tos = reliability_dim.get('time_on_stream', 0)
        print(f"Time on stream: {tos}h")
        
        if tos == 0:
            print("[ERROR] TOS=0 is suspicious for stability claims")
        elif tos >= 100:
            print(f"[PASS] TOS={tos}h supports stability claims")
        else:
            print(f"[WARN] TOS={tos}h may be insufficient for long-term stability claims")
        
        print()
        
        # Verification result
        if abs(calculated_score - recorded_score) < 0.001:
            return {
                'status': 'VERIFIED',
                'recorded_score': recorded_score,
                'calculated_score': calculated_score,
                'match': True,
                'tos': tos,
                'message': f'Reliability score {recorded_score} verified by calculation'
            }
        else:
            return {
                'status': 'PENDING_VALIDATION',
                'recorded_score': recorded_score,
                'calculated_score': calculated_score,
                'match': False,
                'tos': tos,
                'message': f'Recorded score {recorded_score} does not match calculated {calculated_score}'
            }
    
    except Exception as e:
        print(f"[ERROR] Error creating SixDimensionView: {e}")
        return {
            'status': 'ERROR',
            'error': str(e),
            'message': f'Cannot verify: {e}'
        }


def main():
    """Run verification on v1 and v2 records."""
    
    v1_file = Path('data/test_corpus/ext01_output/P01_main_ext01_v1_INVALIDATED.json')
    v2_file = Path('data/test_corpus/ext01_output/P01_main_ext01_v2_corrected.json')
    
    results = {}
    
    if v1_file.exists():
        results['v1'] = verify_reliability_score(v1_file)
        print("\n" + "="*60 + "\n")
    
    if v2_file.exists():
        results['v2'] = verify_reliability_score(v2_file)
    
    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    
    for version, result in results.items():
        status = result['status']
        if status == 'VERIFIED':
            print(f"{version}: [PASS] {status} - Score {result['calculated_score']} matches recorded {result['recorded_score']}")
        elif status == 'PENDING_VALIDATION':
            print(f"{version}: [WARN] {status} - Recorded {result['recorded_score']} != Calculated {result['calculated_score']}")
        else:
            print(f"{version}: [FAIL] {status} - {result['message']}")
    
    # Save results
    output_file = Path('data/test_corpus/runs/phase1_reliability_score_verification.json')
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved: {output_file}")
    
    return results


if __name__ == '__main__':
    main()
