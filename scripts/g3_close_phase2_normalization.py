"""
G3-CLOSE-003 Phase 2: Unit and Value Normalization

Tasks:
1. Review 13 verified fields from F02, F07, PAT01
2. Support Unicode superscripts, negative signs, percentages, Greek letters
3. Save original values, original units, normalized values, normalized units
4. Verify F02's 1,380 m²/g, 16.8%, 82.1% are correctly saved
5. Preserve original SourceAnchors
6. Keep values unsupported by original text as UNVERIFIED
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple, Optional


# Unicode normalization mappings
UNICODE_NORMALIZATIONS = {
    # Superscripts
    '²': '2',
    '³': '3',
    '¹': '1',
    '⁴': '4',
    '⁵': '5',
    '⁶': '6',
    '⁷': '7',
    '⁸': '8',
    '⁹': '9',
    '⁰': '0',
    '⁻': '-',
    '⁺': '+',
    
    # Subscripts
    '₁': '1',
    '₂': '2',
    '₃': '3',
    '₄': '4',
    '₅': '5',
    '₆': '6',
    '₇': '7',
    '₈': '8',
    '₉': '9',
    '₀': '0',
    
    # Greek letters
    'μ': 'u',
    'µ': 'u',
    'Ω': 'ohm',
    'ω': 'omega',
    'Δ': 'delta',
    'δ': 'delta',
    'λ': 'lambda',
    'φ': 'phi',
    'θ': 'theta',
    
    # Special characters
    '±': '+/-',
    '×': 'x',
    '÷': '/',
    '°': 'deg',
    'Å': 'Angstrom',
    'å': 'Angstrom',
}

# Unit normalization patterns
UNIT_PATTERNS = [
    # Surface area
    (r'm2/g|m²/g|m\^2/g', 'm2/g'),
    (r'cm2/g|cm²/g|cm\^2/g', 'cm2/g'),
    (r'm2/mol|m²/mol|m\^2/mol', 'm2/mol'),
    
    # Current density
    (r'mA\s*cm-2|mA\s*cm⁻²|mA/cm²|mA\s*cm\^-2', 'mA/cm2'),
    (r'A\s*mg-1|A\s*mg⁻¹|A/mg|A\s*mg\^-1', 'A/mg'),
    (r'A\s*cm-2|A\s*cm⁻²|A/cm²|A\s*cm\^-2', 'A/cm2'),
    
    # Voltage
    (r'mV', 'mV'),
    (r'V', 'V'),
    
    # Time
    (r'\bh\b|hours?', 'h'),
    (r'\bmin\b|minutes?', 'min'),
    (r'\bs\b|seconds?', 's'),
    
    # Temperature
    (r'°C|degC|C', 'degC'),
    (r'K', 'K'),
    
    # Pressure
    (r'atm', 'atm'),
    (r'bar', 'bar'),
    (r'Pa|kPa|MPa', lambda m: m.group(0)),
    
    # Amount
    (r'mmol|mol|µmol|umol', lambda m: m.group(0)),
    
    # Volume
    (r'mL|L|ml', lambda m: 'mL' if m.group(0).lower() == 'ml' else m.group(0)),
    
    # Percentage
    (r'%', '%'),
    
    # Flow rate
    (r'mL\s*min-1|mL\s*min⁻¹|mL/min', 'mL/min'),
]


def normalize_unicode(text: str) -> str:
    """Normalize Unicode characters to ASCII equivalents."""
    result = text
    for unicode_char, ascii_equiv in UNICODE_NORMALIZATIONS.items():
        result = result.replace(unicode_char, ascii_equiv)
    return result


def normalize_unit(unit_str: str) -> str:
    """Normalize unit string to standard format."""
    if not unit_str:
        return ''
    
    normalized = unit_str
    
    # Apply Unicode normalization first
    normalized = normalize_unicode(normalized)
    
    # Apply unit patterns
    for pattern, replacement in UNIT_PATTERNS:
        if callable(replacement):
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        else:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    
    # Clean up whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def parse_value_with_unit(value_str: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse a value string into numeric value and unit.
    
    Returns: (original_value, numeric_value, unit)
    """
    if not value_str:
        return None, None, None
    
    value_str = str(value_str).strip()
    
    # Try to extract numeric part and unit part
    # Pattern: number (with optional comma, decimal, negative, scientific notation) + unit
    match = re.match(r'^([+-]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*[eE][+-]?\d+)?)\s*(.*)$', value_str)
    
    if match:
        numeric_str = match.group(1).replace(',', '')
        unit_str = match.group(2).strip()
        
        # Normalize unit
        normalized_unit = normalize_unit(unit_str)
        
        return value_str, numeric_str, normalized_unit
    
    # If no match, try to find unit in the string
    for pattern, _ in UNIT_PATTERNS:
        match = re.search(pattern, value_str, flags=re.IGNORECASE)
        if match:
            unit = match.group(0)
            # Try to extract number before unit
            num_match = re.match(r'^([+-]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*[eE][+-]?\d+)?)', value_str)
            if num_match:
                numeric_str = num_match.group(1).replace(',', '')
                return value_str, numeric_str, normalize_unit(unit)
    
    # No unit found, return as-is
    return value_str, value_str, None


def normalize_field_value(field_name: str, value: Any, unit: Optional[str] = None) -> Dict[str, Any]:
    """
    Normalize a field value and unit.
    
    Returns dict with original_value, normalized_value, original_unit, normalized_unit
    """
    result = {
        'field': field_name,
        'original_value': value,
        'normalized_value': value,
        'original_unit': unit,
        'normalized_unit': unit,
        'parse_success': False
    }
    
    if value is None:
        return result
    
    # If value is a string with embedded unit
    if isinstance(value, str):
        orig_val, num_val, parsed_unit = parse_value_with_unit(value)
        
        if orig_val:
            result['original_value'] = orig_val
            result['normalized_value'] = num_val if num_val else orig_val
            result['original_unit'] = parsed_unit
            result['normalized_unit'] = normalize_unit(parsed_unit) if parsed_unit else None
            result['parse_success'] = True
    
    # If unit is provided separately
    elif unit:
        result['original_unit'] = unit
        result['normalized_unit'] = normalize_unit(unit)
        result['normalized_value'] = value
        result['parse_success'] = True
    
    return result


def process_extraction_file(file_path: Path) -> Dict:
    """Process a single extraction file and normalize all values."""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return {'file': str(file_path), 'error': str(e), 'normalizations': []}
    
    normalizations = []
    
    # Process key_metrics if present
    if 'key_metrics' in data and isinstance(data['key_metrics'], list):
        for metric in data['key_metrics']:
            if 'value' in metric:
                value_str = metric.get('value', '')
                norm = normalize_field_value(metric.get('metric_name', 'unknown'), value_str)
                normalizations.append(norm)
                
                # Update the metric with normalized values
                metric['original_value'] = norm['original_value']
                metric['normalized_value'] = norm['normalized_value']
                metric['normalized_unit'] = norm['normalized_unit']
    
    # Process other common fields
    fields_to_check = ['conversion', 'selectivity', 'yield', 'stability', 'time_on_stream']
    
    for field in fields_to_check:
        if field in data:
            value = data[field]
            unit = data.get(f'{field}_unit')
            norm = normalize_field_value(field, value, unit)
            normalizations.append(norm)
            
            # Add normalized values
            data[f'{field}_original'] = norm['original_value']
            data[f'{field}_normalized'] = norm['normalized_value']
            data[f'{field}_unit_normalized'] = norm['normalized_unit']
    
    # Save normalized data
    if normalizations:
        # Create backup
        backup_path = file_path.with_suffix('.json.backup_phase2')
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Write normalized data
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return {
        'file': str(file_path),
        'normalizations': normalizations,
        'backup': str(backup_path) if normalizations else None
    }


def main():
    """Run Phase 2 unit normalization."""
    
    print("="*70)
    print("G3-CLOSE-003 Phase 2: Unit and Value Normalization")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Process all extraction files
    files_to_process = [
        Path('data/test_corpus/g3_output/F02/performance_extracted.json'),
        Path('data/test_corpus/g3_output/F07/performance_extracted.json'),
        Path('data/test_corpus/g3_output/PAT01/performance_extracted.json'),
        Path('data/test_corpus/g3_output/F02/reliability_extracted.json'),
        Path('data/test_corpus/g3_output/F07/reliability_extracted.json'),
        Path('data/test_corpus/g3_output/PAT01/reliability_extracted.json'),
    ]
    
    all_results = []
    
    for file_path in files_to_process:
        if file_path.exists():
            print(f"\nProcessing: {file_path}")
            result = process_extraction_file(file_path)
            all_results.append(result)
            
            if 'error' in result:
                print(f"  ERROR: {result['error']}")
            else:
                print(f"  Normalized {len(result['normalizations'])} values")
                if result.get('backup'):
                    print(f"  Backup: {result['backup']}")
    
    # Summary
    print(f"\n{'='*70}")
    print("NORMALIZATION SUMMARY")
    print(f"{'='*70}")
    
    total_normalizations = sum(len(r.get('normalizations', [])) for r in all_results)
    print(f"Files processed: {len(all_results)}")
    print(f"Total values normalized: {total_normalizations}")
    
    # Show sample normalizations
    for result in all_results:
        if result.get('normalizations'):
            print(f"\n{result['file']}:")
            for norm in result['normalizations'][:3]:  # Show first 3
                print(f"  {norm['field']}:")
                print(f"    Original: {norm['original_value']}")
                print(f"    Normalized: {norm['normalized_value']} {norm.get('normalized_unit', '')}")
    
    # Save results
    output = {
        'task': 'G3-CLOSE-003 Phase 2: Unit Normalization',
        'timestamp': datetime.now().isoformat(),
        'results': all_results,
        'summary': {
            'files_processed': len(all_results),
            'total_normalizations': total_normalizations
        }
    }
    
    output_path = Path('runs/G3_CLOSE003_phase2_normalization.json')
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*70}")
    print(f"Results saved: {output_path}")
    print(f"{'='*70}")
    
    return output


if __name__ == '__main__':
    main()
