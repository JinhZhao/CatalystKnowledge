"""
Phase 3: QA Quality Gate Adversarial Testing

Test the 6 QA rules with positive and negative cases to verify they can detect erroneous scientific data.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent))

from qa001_quality_gates import QAGateValidator


def create_test_case(name: str, record: Dict[str, Any], expected_violations: List[str]) -> Dict:
    """Create a test case structure."""
    return {
        'name': name,
        'record': record,
        'expected_violations': expected_violations,
    }


def test_gate_001_evidence_requirement():
    """
    Test QA-GATE-001: confidence > 0.5 must have evidence_quote.
    
    Negative case: High confidence without evidence should trigger violation.
    """
    print("\n" + "="*60)
    print("TEST: QA-GATE-001 Evidence Requirement")
    print("="*60)
    
    # Negative case: high confidence without evidence
    negative_record = {
        'dimensions': {
            'catalyst_design': {
                'catalyst_system': 'Ru NPs/TiN',
                'confidence': 0.9,  # High confidence
                # Missing evidence_quote
            }
        },
        'source_anchors': {},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    validator = QAGateValidator()
    is_valid, violations, warnings = validator.validate(negative_record)
    
    print(f"\nNegative case (high confidence, no evidence):")
    print(f"  Expected: VIOLATION")
    print(f"  Actual: {'VIOLATION' if not is_valid else 'PASS'}")
    print(f"  Violations: {violations}")
    
    has_expected = any('QA-GATE-001' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_expected else '[FAIL]'}")
    
    # Positive case: high confidence with evidence
    positive_record = {
        'dimensions': {
            'catalyst_design': {
                'catalyst_system': 'Ru NPs/TiN',
                'confidence': 0.9,
                'evidence_quote': 'Ru nanoparticles supported on TiN...'
            }
        },
        'source_anchors': {'catalyst_design': {}},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    is_valid, violations, warnings = validator.validate(positive_record)
    
    print(f"\nPositive case (high confidence, with evidence):")
    print(f"  Expected: PASS")
    print(f"  Actual: {'PASS' if is_valid else 'VIOLATION'}")
    print(f"  Violations: {violations}")
    
    has_no_gate001 = not any('QA-GATE-001' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_no_gate001 else '[FAIL]'}")
    
    return has_expected and has_no_gate001


def test_gate_002_not_extracted_protection():
    """
    Test QA-GATE-002: NOT_EXTRACTED should not convert to numeric 0.
    
    Negative case: TOS=0 without explicit evidence should trigger violation.
    """
    print("\n" + "="*60)
    print("TEST: QA-GATE-002 NOT_EXTRACTED Protection")
    print("="*60)
    
    # Negative case: TOS=0 without explanation
    negative_record = {
        'dimensions': {
            'reliability': {
                'time_on_stream': 0,  # Suspicious zero
                # No time_on_stream_note explaining why it's 0
            },
            'performance': {
                'key_claims': ['long-term stability over 100 hours']
            }
        },
        'source_anchors': {'reliability': {}, 'performance': {}},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    validator = QAGateValidator()
    is_valid, violations, warnings = validator.validate(negative_record)
    
    print(f"\nNegative case (TOS=0 with stability claim):")
    print(f"  Expected: VIOLATION")
    print(f"  Actual: {'VIOLATION' if not is_valid else 'PASS'}")
    print(f"  Violations: {violations}")
    
    has_expected = any('QA-GATE-002' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_expected else '[FAIL]'}")
    
    # Positive case: TOS=0 with explicit "not reported" note
    positive_record = {
        'dimensions': {
            'reliability': {
                'time_on_stream': 0,
                'time_on_stream_note': 'Stability test not reported in paper'
            }
        },
        'source_anchors': {'reliability': {}},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    is_valid, violations, warnings = validator.validate(positive_record)
    
    print(f"\nPositive case (TOS=0 with 'not reported' note):")
    print(f"  Expected: PASS (no QA-GATE-002 violation)")
    print(f"  Actual: {'PASS' if is_valid else 'VIOLATION'}")
    print(f"  Violations: {violations}")
    
    has_no_gate002 = not any('QA-GATE-002' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_no_gate002 else '[FAIL]'}")
    
    return has_expected and has_no_gate002


def test_gate_003_scientific_field_integrity():
    """
    Test QA-GATE-003: Scientific fields must have units.
    
    Negative case: Performance metric with value but no unit should trigger violation.
    """
    print("\n" + "="*60)
    print("TEST: QA-GATE-003 Scientific Field Integrity")
    print("="*60)
    
    # Negative case: metric without unit
    negative_record = {
        'dimensions': {
            'performance': {
                'key_metrics': [
                    {
                        'metric_name': 'overpotential',
                        'value': '63',  # Missing unit!
                        'conditions': 'alkaline HER'
                    }
                ]
            }
        },
        'source_anchors': {'performance': {}},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    validator = QAGateValidator()
    is_valid, violations, warnings = validator.validate(negative_record)
    
    print(f"\nNegative case (metric value without unit):")
    print(f"  Expected: VIOLATION")
    print(f"  Actual: {'VIOLATION' if not is_valid else 'PASS'}")
    print(f"  Violations: {violations}")
    
    has_expected = any('QA-GATE-003' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_expected else '[FAIL]'}")
    
    # Positive case: metric with unit
    positive_record = {
        'dimensions': {
            'performance': {
                'key_metrics': [
                    {
                        'metric_name': 'overpotential',
                        'value': '63 mV',
                        'unit': 'mV',
                        'conditions': 'alkaline HER'
                    }
                ]
            }
        },
        'source_anchors': {'performance': {}},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    is_valid, violations, warnings = validator.validate(positive_record)
    
    print(f"\nPositive case (metric value with unit):")
    print(f"  Expected: PASS")
    print(f"  Actual: {'PASS' if is_valid else 'VIOLATION'}")
    print(f"  Violations: {violations}")
    
    has_no_gate003 = not any('QA-GATE-003' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_no_gate003 else '[FAIL]'}")
    
    return has_expected and has_no_gate003


def test_gate_004_source_location():
    """
    Test QA-GATE-004: Dimensions must have source_anchor.
    
    Negative case: Dimension without source_anchor should trigger violation.
    """
    print("\n" + "="*60)
    print("TEST: QA-GATE-004 Source Location Requirement")
    print("="*60)
    
    # Negative case: missing source_anchor
    negative_record = {
        'dimensions': {
            'catalyst_design': {'catalyst_system': 'Ru NPs/TiN'},
            'performance': {'key_claim': 'high activity'}
        },
        'source_anchors': {
            'catalyst_design': {}
            # Missing performance source_anchor!
        },
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    validator = QAGateValidator()
    is_valid, violations, warnings = validator.validate(negative_record)
    
    print(f"\nNegative case (dimension without source_anchor):")
    print(f"  Expected: VIOLATION")
    print(f"  Actual: {'VIOLATION' if not is_valid else 'PASS'}")
    print(f"  Violations: {violations}")
    
    has_expected = any('QA-GATE-004' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_expected else '[FAIL]'}")
    
    # Positive case: all dimensions have source_anchors
    positive_record = {
        'dimensions': {
            'catalyst_design': {'catalyst_system': 'Ru NPs/TiN'},
            'performance': {'key_claim': 'high activity'}
        },
        'source_anchors': {
            'catalyst_design': {},
            'performance': {}
        },
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    is_valid, violations, warnings = validator.validate(positive_record)
    
    print(f"\nPositive case (all dimensions with source_anchors):")
    print(f"  Expected: PASS")
    print(f"  Actual: {'PASS' if is_valid else 'VIOLATION'}")
    print(f"  Violations: {violations}")
    
    has_no_gate004 = not any('QA-GATE-004' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_no_gate004 else '[FAIL]'}")
    
    return has_expected and has_no_gate004


def test_gate_005_contradiction_detection():
    """
    Test QA-GATE-005: Detect contradictions between performance and reliability.
    
    Negative case: Claims stability but TOS=0 should trigger violation.
    """
    print("\n" + "="*60)
    print("TEST: QA-GATE-005 Contradiction Detection")
    print("="*60)
    
    # Negative case: stability claim with TOS=0
    negative_record = {
        'dimensions': {
            'performance': {
                'key_claims': ['excellent long-term stability over 1000 hours']
            },
            'reliability': {
                'time_on_stream': 0  # Contradicts stability claim!
            }
        },
        'source_anchors': {'performance': {}, 'reliability': {}},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    validator = QAGateValidator()
    is_valid, violations, warnings = validator.validate(negative_record)
    
    print(f"\nNegative case (stability claim with TOS=0):")
    print(f"  Expected: VIOLATION")
    print(f"  Actual: {'VIOLATION' if not is_valid else 'PASS'}")
    print(f"  Violations: {violations}")
    
    has_expected = any('QA-GATE-005' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_expected else '[FAIL]'}")
    
    # Positive case: stability claim with TOS=1000
    positive_record = {
        'dimensions': {
            'performance': {
                'key_claims': ['excellent long-term stability over 1000 hours']
            },
            'reliability': {
                'time_on_stream': 1000  # Consistent with claim
            }
        },
        'source_anchors': {'performance': {}, 'reliability': {}},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}
    }
    
    is_valid, violations, warnings = validator.validate(positive_record)
    
    print(f"\nPositive case (stability claim with TOS=1000):")
    print(f"  Expected: PASS")
    print(f"  Actual: {'PASS' if is_valid else 'VIOLATION'}")
    print(f"  Violations: {violations}")
    
    has_no_gate005 = not any('QA-GATE-005' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_no_gate005 else '[FAIL]'}")
    
    return has_expected and has_no_gate005


def test_gate_006_state_classification():
    """
    Test QA-GATE-006: DEMO_INPUT cannot have coverage=1.0.
    
    Negative case: DEMO_INPUT with full coverage should trigger violation.
    """
    print("\n" + "="*60)
    print("TEST: QA-GATE-006 State Classification")
    print("="*60)
    
    # Negative case: DEMO_INPUT with coverage=1.0
    negative_record = {
        'dimensions': {
            'catalyst_design': {},
            'characterization': {},
            'performance': {},
            'mechanism': {},
            'structure_activity': {},
            'reliability': {}
        },
        'source_anchors': {
            'catalyst_design': {},
            'characterization': {},
            'performance': {},
            'mechanism': {},
            'structure_activity': {},
            'reliability': {}
        },
        'completeness': {'coverage': 1.0},  # Full coverage
        'metadata': {'extraction_method': 'DEMO_INPUT'}  # But marked as DEMO!
    }
    
    validator = QAGateValidator()
    is_valid, violations, warnings = validator.validate(negative_record)
    
    print(f"\nNegative case (DEMO_INPUT with coverage=1.0):")
    print(f"  Expected: VIOLATION")
    print(f"  Actual: {'VIOLATION' if not is_valid else 'PASS'}")
    print(f"  Violations: {violations}")
    
    has_expected = any('QA-GATE-006' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_expected else '[FAIL]'}")
    
    # Positive case: LLM_EXTRACTED with coverage=1.0
    positive_record = {
        'dimensions': {
            'catalyst_design': {},
            'characterization': {},
            'performance': {},
            'mechanism': {},
            'structure_activity': {},
            'reliability': {}
        },
        'source_anchors': {
            'catalyst_design': {},
            'characterization': {},
            'performance': {},
            'mechanism': {},
            'structure_activity': {},
            'reliability': {}
        },
        'completeness': {'coverage': 1.0},
        'metadata': {'extraction_method': 'LLM_EXTRACTED'}  # Correct state
    }
    
    is_valid, violations, warnings = validator.validate(positive_record)
    
    print(f"\nPositive case (LLM_EXTRACTED with coverage=1.0):")
    print(f"  Expected: PASS")
    print(f"  Actual: {'PASS' if is_valid else 'VIOLATION'}")
    print(f"  Violations: {violations}")
    
    has_no_gate006 = not any('QA-GATE-006' in v for v in violations)
    print(f"  Result: {'[PASS]' if has_no_gate006 else '[FAIL]'}")
    
    return has_expected and has_no_gate006


def main():
    """Run all adversarial tests."""
    
    print("="*60)
    print("Phase 3: QA Quality Gate Adversarial Testing")
    print("="*60)
    
    results = {}
    
    # Test all 6 gates
    results['gate_001'] = test_gate_001_evidence_requirement()
    results['gate_002'] = test_gate_002_not_extracted_protection()
    results['gate_003'] = test_gate_003_scientific_field_integrity()
    results['gate_004'] = test_gate_004_source_location()
    results['gate_005'] = test_gate_005_contradiction_detection()
    results['gate_006'] = test_gate_006_state_classification()
    
    # Summary
    print("\n" + "="*60)
    print("ADVERSARIAL TEST SUMMARY")
    print("="*60)
    
    pass_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for gate, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{gate}: {status}")
    
    print(f"\nTotal: {pass_count}/{total_count} gates passed adversarial testing")
    print(f"Success rate: {pass_count / total_count * 100:.1f}%")
    
    # Save results
    output_file = Path('data/test_corpus/runs/phase3_qa_adversarial_test.json')
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'test_type': 'QA Quality Gate Adversarial Testing',
        'results': results,
        'pass_count': pass_count,
        'total_count': total_count,
        'success_rate': pass_count / total_count
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\nReport saved: {output_file}")
    
    return pass_count == total_count


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
