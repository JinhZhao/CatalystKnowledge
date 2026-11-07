"""
QA-001: Minimum Quality Gates for Scientific Record Admission

Validates that extracted data meets minimum scientific integrity standards
before entering the canonical store.

Rules:
1. No evidence → cannot mark as REPORTED
2. NOT_EXTRACTED → cannot convert to numeric 0
3. Scientific fields must retain original values, units, experimental context
4. Records without source location → only as unverified candidates
5. Invalid/contradictory data → cannot enter quality scoring
6. STORE-001 must distinguish DEMO_INPUT / LLM_EXTRACTED / VERIFIED states
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime


class QAGateValidator:
    """Validates scientific records against QA-001 quality gates."""
    
    def __init__(self):
        self.violations = []
        self.warnings = []
        
    def validate(self, record: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate a record against all QA gates.
        
        Returns:
            (is_valid, violations, warnings)
        """
        self.violations = []
        self.warnings = []
        
        # Gate 1: Evidence requirement
        self._check_evidence_requirement(record)
        
        # Gate 2: NOT_EXTRACTED protection
        self._check_not_extracted_protection(record)
        
        # Gate 3: Scientific field integrity
        self._check_scientific_field_integrity(record)
        
        # Gate 4: Source location requirement
        self._check_source_location(record)
        
        # Gate 5: Contradiction detection
        self._check_contradictions(record)
        
        # Gate 6: State classification
        self._check_state_classification(record)
        
        is_valid = len(self.violations) == 0
        return is_valid, self.violations, self.warnings
    
    def _check_evidence_requirement(self, record: Dict[str, Any]):
        """Gate 1: No evidence → cannot mark as REPORTED."""
        dimensions = record.get('dimensions', {})
        
        for dim_name, dim_data in dimensions.items():
            if not dim_data:
                continue
                
            # Check if marked as REPORTED without evidence
            evidence_fields = ['evidence_quote', 'evidence', 'source_anchor', 'stability_evidence']
            has_evidence = any(dim_data.get(field) for field in evidence_fields)
            
            # Check for confidence score (implies REPORTED status)
            confidence = dim_data.get('confidence', 0)
            
            if confidence > 0.5 and not has_evidence:
                violation = f"QA-GATE-001: Dimension '{dim_name}' has confidence={confidence} but no evidence_quote"
                self.violations.append(violation)
    
    def _check_not_extracted_protection(self, record: Dict[str, Any]):
        """Gate 2: NOT_EXTRACTED → cannot convert to numeric 0."""
        dimensions = record.get('dimensions', {})
        
        # Check reliability dimension specifically
        reliability = dimensions.get('reliability', {})
        
        # time_on_stream should not be 0 unless explicitly stated in paper
        tos = reliability.get('time_on_stream')
        if tos == 0:
            # Check if there's evidence for 0 or if it's a default
            tos_note = reliability.get('time_on_stream_note', '')
            if 'not reported' not in tos_note.lower() and 'no stability' not in tos_note.lower():
                violation = f"QA-GATE-002: time_on_stream=0 without NOT_EXTRACTED marker or explicit evidence"
                self.violations.append(violation)
        
        # cycle_count should not be 0 unless explicitly stated
        cycle_count = reliability.get('cycle_count')
        if cycle_count == 0:
            cycle_note = reliability.get('cycle_count_note', '')
            if 'not reported' not in cycle_note.lower() and 'no cycling' not in cycle_note.lower():
                warning = f"QA-GATE-002-WARN: cycle_count=0 - verify this is not a default value"
                self.warnings.append(warning)
    
    def _check_scientific_field_integrity(self, record: Dict[str, Any]):
        """Gate 3: Scientific fields must retain original values, units, experimental context."""
        dimensions = record.get('dimensions', {})
        
        # Check performance dimension
        performance = dimensions.get('performance', {})
        key_metrics = performance.get('key_metrics', [])
        
        for metric in key_metrics:
            if not isinstance(metric, dict):
                continue
            
            # Must have value, unit, and conditions
            if 'value' in metric:
                if 'unit' not in metric or not metric['unit']:
                    violation = f"QA-GATE-003: Performance metric '{metric.get('name', 'unknown')}' has value but no unit"
                    self.violations.append(violation)
                
                if 'conditions' not in metric or not metric['conditions']:
                    warning = f"QA-GATE-003-WARN: Performance metric '{metric.get('name', 'unknown')}' missing experimental conditions"
                    self.warnings.append(warning)
        
        # Check catalyst_design dimension
        catalyst_design = dimensions.get('catalyst_design', {})
        if catalyst_design:
            required_fields = ['catalyst_system', 'active_component', 'support']
            for field in required_fields:
                if not catalyst_design.get(field):
                    warning = f"QA-GATE-003-WARN: catalyst_design missing field '{field}'"
                    self.warnings.append(warning)
    
    def _check_source_location(self, record: Dict[str, Any]):
        """Gate 4: Records without source location → only as unverified candidates."""
        source_anchors = record.get('source_anchors', {})
        
        if not source_anchors:
            warning = "QA-GATE-004-WARN: No source_anchors - record should be marked as unverified candidate"
            self.warnings.append(warning)
            return
        
        # Check each dimension has a source anchor
        dimensions = record.get('dimensions', {})
        for dim_name in dimensions.keys():
            if dim_name not in source_anchors:
                violation = f"QA-GATE-004: Dimension '{dim_name}' has no source_anchor - cannot be VERIFIED"
                self.violations.append(violation)
    
    def _check_contradictions(self, record: Dict[str, Any]):
        """Gate 5: Invalid/contradictory data → cannot enter quality scoring."""
        dimensions = record.get('dimensions', {})
        
        # Cross-validation: performance vs reliability
        performance = dimensions.get('performance', {})
        reliability = dimensions.get('reliability', {})
        
        # If performance claims long-term stability, reliability must have TOS > 0
        key_claims = performance.get('key_claims', [])
        stability_keywords = ['long-term', 'stability', 'hours', 'h ', 'durability']
        
        has_stability_claim = any(
            any(kw in claim.lower() for kw in stability_keywords)
            for claim in key_claims
        )
        
        if has_stability_claim:
            tos = reliability.get('time_on_stream', 0)
            if tos == 0:
                violation = f"QA-GATE-005: Performance claims stability but time_on_stream=0 (contradiction)"
                self.violations.append(violation)
    
    def _check_state_classification(self, record: Dict[str, Any]):
        """Gate 6: STORE-001 must distinguish DEMO_INPUT / LLM_EXTRACTED / VERIFIED states."""
        metadata = record.get('metadata', {})
        
        # Check extraction_method field
        extraction_method = metadata.get('extraction_method', '')
        
        valid_methods = ['DEMO_INPUT', 'LLM_EXTRACTED', 'MANUAL_REVIEW', 'VERIFIED']
        if extraction_method and extraction_method not in valid_methods:
            warning = f"QA-GATE-006-WARN: extraction_method='{extraction_method}' not in standard states"
            self.warnings.append(warning)
        
        # Check completeness score
        completeness = record.get('completeness', {})
        coverage = completeness.get('coverage', 0)
        
        # If coverage is 1.0 but method is DEMO_INPUT, that's suspicious
        if coverage == 1.0 and extraction_method == 'DEMO_INPUT':
            violation = f"QA-GATE-006: DEMO_INPUT cannot have coverage=1.0 (demo data is incomplete by definition)"
            self.violations.append(violation)


def validate_extraction_file(extraction_path: Path) -> Dict[str, Any]:
    """
    Validate an extraction JSON file against QA gates.
    
    Returns:
        Validation report with pass/fail status and details
    """
    with open(extraction_path, 'r', encoding='utf-8') as f:
        record = json.load(f)
    
    validator = QAGateValidator()
    is_valid, violations, warnings = validator.validate(record)
    
    report = {
        'file': str(extraction_path),
        'timestamp': datetime.now().isoformat(),
        'valid': is_valid,
        'violations': violations,
        'warnings': warnings,
        'record_metadata': {
            'doc_id': record.get('doc_id'),
            'extraction_method': record.get('metadata', {}).get('extraction_method'),
            'completeness_coverage': record.get('completeness', {}).get('coverage'),
            'reliability_score': record.get('reliability_score'),
        }
    }
    
    return report


def main():
    """Run QA-001 validation on all extraction files."""
    print("=== QA-001: Minimum Quality Gates Validation ===\n")
    
    # Find all extraction files
    extraction_dir = Path('data/test_corpus/ext01_output')
    extraction_files = list(extraction_dir.glob('P*_ext01_*.json'))
    
    print(f"Found {len(extraction_files)} extraction files\n")
    
    all_reports = []
    pass_count = 0
    fail_count = 0
    
    for extraction_file in sorted(extraction_files):
        print(f"Validating: {extraction_file.name}")
        
        try:
            report = validate_extraction_file(extraction_file)
            all_reports.append(report)
            
            if report['valid']:
                print(f"  [PASS] - {len(report['warnings'])} warnings")
                pass_count += 1
            else:
                print(f"  [FAIL] - {len(report['violations'])} violations, {len(report['warnings'])} warnings")
                fail_count += 1
            
            # Show violations
            for v in report['violations']:
                print(f"    VIOLATION: {v}")
            
            # Show warnings (limit to 3)
            for w in report['warnings'][:3]:
                print(f"    WARNING: {w}")
            
            if len(report['warnings']) > 3:
                print(f"    ... and {len(report['warnings']) - 3} more warnings")
            
        except Exception as e:
            print(f"  [ERROR] {e}")
            fail_count += 1
        
        print()
    
    # Summary
    print("=== Summary ===")
    print(f"Total files: {len(extraction_files)}")
    print(f"PASS: {pass_count}")
    print(f"FAIL: {fail_count}")
    print(f"Pass rate: {pass_count / len(extraction_files) * 100:.1f}%")
    print()
    
    # Save report
    report_file = extraction_dir / 'QA001_quality_gates_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_files': len(extraction_files),
            'pass_count': pass_count,
            'fail_count': fail_count,
            'reports': all_reports
        }, f, indent=2, ensure_ascii=False)
    
    print(f"Report saved: {report_file}")
    
    return fail_count == 0


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
