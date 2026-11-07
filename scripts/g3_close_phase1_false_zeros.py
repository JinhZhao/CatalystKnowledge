"""
G3-CLOSE-003 Phase 1: False Zero Value Full Audit

Tasks:
1. Locate all TOS=0, cycles=0, conversion=0, selectivity=0, yield=0 in extraction files
2. Check if they have notes indicating "not reported" or similar
3. Distinguish real zeros from missing values
4. Mark false zeros as NOT_EXTRACTED
5. Create revision trails
6. Check impact on reliability scores and relationships
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple


# Fields that commonly have false zero defaults
ZERO_PRONE_FIELDS = [
    'time_on_stream',
    'tos',
    'tos_h',
    'cycle_count',
    'cycles',
    'conversion',
    'selectivity',
    'yield',
    'stability',
    'degradation_rate',
]

# Patterns indicating missing data rather than real zero
MISSING_DATA_PATTERNS = [
    r'not\s+reported',
    r'no\s+.*\s+reported',
    r'not\s+available',
    r'N/A',
    r'none\s+reported',
    r'no\s+data',
    r'not\s+measured',
    r'not\s+tested',
    r'no\s+.*\s+testing',
    r'not\s+specified',
]


def check_if_false_zero(value: Any, note: str = None, context: dict = None) -> Tuple[bool, str]:
    """
    Check if a zero value is false (missing data) or real.
    
    Returns: (is_false_zero, reason)
    """
    if value != 0 and value != 0.0:
        return False, "Not a zero value"
    
    # Check note for missing data patterns
    if note:
        note_lower = note.lower()
        for pattern in MISSING_DATA_PATTERNS:
            if re.search(pattern, note_lower):
                return True, f"Note indicates missing data: {note[:100]}"
    
    # Check context for missing data indicators
    if context:
        context_str = json.dumps(context).lower()
        for pattern in MISSING_DATA_PATTERNS:
            if re.search(pattern, context_str):
                return True, f"Context indicates missing data"
    
    # If value is 0 but no indication of missing data, assume it might be real
    # But flag for review
    return False, "Zero value without missing data indication (may be real or may need review)"


def scan_extraction_file(file_path: Path) -> List[Dict]:
    """Scan a single extraction file for false zeros."""
    
    findings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return [{'file': str(file_path), 'error': str(e)}]
    
    # Recursively search for zero-prone fields
    def search_dict(d: dict, path: str = ""):
        for key, value in d.items():
            current_path = f"{path}.{key}" if path else key
            
            # Check if this is a zero-prone field
            if key.lower() in ZERO_PRONE_FIELDS or any(zf in key.lower() for zf in ZERO_PRONE_FIELDS):
                if value == 0 or value == 0.0:
                    # Look for associated note field
                    note = None
                    for note_key in [f"{key}_note", f"{key}_explanation", "note", "explanation"]:
                        if note_key in d:
                            note = d[note_key]
                            break
                    
                    is_false, reason = check_if_false_zero(value, note, d)
                    
                    findings.append({
                        'file': str(file_path),
                        'field': current_path,
                        'value': value,
                        'note': note,
                        'is_false_zero': is_false,
                        'reason': reason,
                        'action': 'MARK_NOT_EXTRACTED' if is_false else 'REVIEW'
                    })
            
            # Recurse into nested dicts
            if isinstance(value, dict):
                search_dict(value, current_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        search_dict(item, f"{current_path}[{i}]")
    
    # Handle both dict and list at top level
    if isinstance(data, dict):
        search_dict(data)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                search_dict(item, f"[{i}]")
    
    return findings


def scan_directory(dir_path: Path) -> List[Dict]:
    """Scan all JSON files in a directory for false zeros."""
    
    all_findings = []
    
    for json_file in dir_path.rglob('*.json'):
        # Skip summary files and audit results
        if 'summary' in json_file.name or 'audit' in json_file.name:
            continue
        
        findings = scan_extraction_file(json_file)
        all_findings.extend(findings)
    
    return all_findings


def fix_false_zeros(file_path: Path, findings: List[Dict]) -> Dict:
    """Fix false zeros in a file by marking them as NOT_EXTRACTED."""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return {'success': False, 'error': str(e)}
    
    fixes = []
    
    for finding in findings:
        if not finding['is_false_zero']:
            continue
        
        field_path = finding['field']
        
        # Navigate to the field and fix it
        parts = field_path.split('.')
        current = data
        
        for i, part in enumerate(parts[:-1]):
            # Handle array indices
            if '[' in part:
                key, idx = part.split('[')
                idx = int(idx[:-1])
                if key:
                    current = current[key]
                current = current[idx]
            else:
                current = current[part]
        
        # Fix the last part
        last_part = parts[-1]
        if '[' in last_part:
            key, idx = last_part.split('[')
            idx = int(idx[:-1])
            if key:
                current = current[key]
            old_value = current[idx]
            current[idx] = None  # Mark as NOT_EXTRACTED
        else:
            old_value = current[last_part]
            current[last_part] = None  # Mark as NOT_EXTRACTED
        
        fixes.append({
            'field': field_path,
            'old_value': old_value,
            'new_value': None,
            'reason': finding['reason']
        })
    
    if fixes:
        # Create backup
        backup_path = file_path.with_suffix('.json.backup_phase1')
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Write fixed data
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Add revision trail
        trail_file = file_path.parent / 'revision_trail_phase1.json'
        trail = {
            'timestamp': datetime.now().isoformat(),
            'file': str(file_path),
            'backup': str(backup_path),
            'fixes': fixes
        }
        
        existing_trail = []
        if trail_file.exists():
            with open(trail_file, 'r', encoding='utf-8') as f:
                existing_trail = json.load(f)
        
        existing_trail.append(trail)
        
        with open(trail_file, 'w', encoding='utf-8') as f:
            json.dump(existing_trail, f, indent=2, ensure_ascii=False)
    
    return {'success': True, 'fixes': fixes, 'backup': str(backup_path) if fixes else None}


def main():
    """Run Phase 1 false zero audit."""
    
    print("="*70)
    print("G3-CLOSE-003 Phase 1: False Zero Value Full Audit")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Scan all extraction files
    scan_dirs = [
        Path('data/test_corpus/g3_output'),
        Path('data/test_corpus/ext01_output'),
        Path('data/test_corpus/canonical_store'),
    ]
    
    all_findings = []
    
    for scan_dir in scan_dirs:
        if scan_dir.exists():
            print(f"\nScanning: {scan_dir}")
            findings = scan_directory(scan_dir)
            all_findings.extend(findings)
            print(f"  Found {len(findings)} zero values to review")
    
    # Categorize findings
    false_zeros = [f for f in all_findings if f.get('is_false_zero')]
    review_zeros = [f for f in all_findings if not f.get('is_false_zero') and 'error' not in f]
    errors = [f for f in all_findings if 'error' in f]
    
    print(f"\n{'='*70}")
    print("AUDIT SUMMARY")
    print(f"{'='*70}")
    print(f"Total zero values found: {len(all_findings)}")
    print(f"  False zeros (missing data): {len(false_zeros)}")
    print(f"  Review needed: {len(review_zeros)}")
    print(f"  Errors: {len(errors)}")
    
    # Print false zeros
    if false_zeros:
        print(f"\n{'='*70}")
        print("FALSE ZEROS (Missing Data)")
        print(f"{'='*70}")
        
        for finding in false_zeros:
            print(f"\n  File: {finding['file']}")
            print(f"  Field: {finding['field']}")
            print(f"  Value: {finding['value']}")
            print(f"  Note: {finding.get('note', 'N/A')}")
            print(f"  Reason: {finding['reason']}")
            print(f"  Action: {finding['action']}")
    
    # Print review zeros
    if review_zeros:
        print(f"\n{'='*70}")
        print("ZEROS NEEDING REVIEW")
        print(f"{'='*70}")
        
        for finding in review_zeros[:10]:  # Show first 10
            print(f"\n  File: {finding['file']}")
            print(f"  Field: {finding['field']}")
            print(f"  Value: {finding['value']}")
            print(f"  Reason: {finding['reason']}")
        
        if len(review_zeros) > 10:
            print(f"\n  ... and {len(review_zeros) - 10} more")
    
    # Fix false zeros
    if false_zeros:
        print(f"\n{'='*70}")
        print("FIXING FALSE ZEROS")
        print(f"{'='*70}")
        
        # Group by file
        by_file = {}
        for finding in false_zeros:
            file_path = finding['file']
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(finding)
        
        fix_results = []
        
        for file_path, findings in by_file.items():
            print(f"\n  Fixing: {file_path}")
            result = fix_false_zeros(Path(file_path), findings)
            result['file'] = file_path
            fix_results.append(result)
            
            if result['success']:
                print(f"    Fixed {len(result['fixes'])} false zeros")
                if result['backup']:
                    print(f"    Backup: {result['backup']}")
            else:
                print(f"    ERROR: {result['error']}")
    
    # Save audit results
    output = {
        'task': 'G3-CLOSE-003 Phase 1: False Zero Audit',
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_zeros': len(all_findings),
            'false_zeros': len(false_zeros),
            'review_needed': len(review_zeros),
            'errors': len(errors)
        },
        'false_zeros': false_zeros,
        'review_zeros': review_zeros,
        'errors': errors,
        'fix_results': fix_results if false_zeros else []
    }
    
    output_path = Path('runs/G3_CLOSE003_phase1_false_zeros.json')
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*70}")
    print(f"Audit results saved: {output_path}")
    print(f"{'='*70}")
    
    return output


if __name__ == '__main__':
    main()
