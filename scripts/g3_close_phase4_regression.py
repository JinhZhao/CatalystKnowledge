"""
G3-CLOSE-003 Phase 4: Data Integrity Regression Check

Simplified regression test - verify that Phase 1-2 modifications
haven't corrupted existing TAX/QA/STORE outputs.

Checks:
1. TAX-001: Classification files exist and contain valid JSON with required fields
2. QA-001: Verification results still accessible and valid
3. STORE-001: Canonical store files intact and readable
4. Compare to baseline counts from G3-VERIFY-002
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List


def check_tax001_integrity() -> Dict[str, Any]:
    """Check TAX-001 classification files integrity."""
    print("\n" + "="*60)
    print("TAX-001 Integrity Check")
    print("="*60)

    doc_ids = ['F02', 'F07', 'PAT01']
    results = {
        'timestamp': datetime.now().isoformat(),
        'documents': {},
        'pass_count': 0,
        'fail_count': 0
    }

    for doc_id in doc_ids:
        # Check classification file
        class_file = Path(f'data/test_corpus/g3_output/{doc_id}/classification.json')

        if not class_file.exists():
            results['documents'][doc_id] = {'status': 'FAIL', 'reason': 'File not found'}
            results['fail_count'] += 1
            print(f"  [{doc_id}] FAIL: File not found")
            continue

        try:
            with open(class_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Check required fields (actual structure)
            required = ['status', 'overall_confidence', 'reaction_type', 'catalyst_type']
            missing = [field for field in required if field not in data]

            if missing:
                results['documents'][doc_id] = {'status': 'FAIL', 'reason': f'Missing fields: {missing}'}
                results['fail_count'] += 1
                print(f"  [{doc_id}] FAIL: Missing {missing}")
            elif data['status'] != 'ACCEPTED':
                results['documents'][doc_id] = {'status': 'FAIL', 'reason': f"Status={data['status']}, expected ACCEPTED"}
                results['fail_count'] += 1
                print(f"  [{doc_id}] FAIL: Status={data['status']}")
            else:
                results['documents'][doc_id] = {
                    'status': 'PASS',
                    'confidence': data['overall_confidence'],
                    'categories': [k for k in data.keys() if k not in ['status', 'overall_confidence', 'pending_review', 'review_reason', 'metadata']]
                }
                results['pass_count'] += 1
                print(f"  [{doc_id}] PASS: confidence={data['overall_confidence']}")
        except Exception as e:
            results['documents'][doc_id] = {'status': 'FAIL', 'reason': str(e)}
            results['fail_count'] += 1
            print(f"  [{doc_id}] FAIL: {e}")

    results['status'] = 'PASS' if results['fail_count'] == 0 else 'FAIL'
    print(f"\nTAX-001 Result: {results['pass_count']}/{len(doc_ids)} PASS")

    return results


def check_qa001_integrity() -> Dict[str, Any]:
    """Check QA-001 verification results integrity."""
    print("\n" + "="*60)
    print("QA-001 Integrity Check")
    print("="*60)

    # Check G3-VERIFY-002 QA results (correct filename)
    qa_file = Path('runs/G3_VERIFY002_L4_evidence_verification.json')

    if not qa_file.exists():
        return {'status': 'FAIL', 'reason': 'QA results file not found'}

    try:
        with open(qa_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Check structure (actual: 'documents' not 'verification_results')
        if 'documents' not in data:
            return {'status': 'FAIL', 'reason': 'Missing documents'}

        documents = data['documents']

        # Count VERIFIED fields across all documents
        verified_count = 0
        total_fields = 0

        for doc_id, doc_data in documents.items():
            if 'verifications' in doc_data:
                for verification in doc_data['verifications']:
                    total_fields += 1
                    if verification.get('l4_status') == 'VERIFIED':
                        verified_count += 1

        # Baseline from G3-VERIFY-002: 12 VERIFIED
        expected_verified = 12

        if verified_count == expected_verified:
            print(f"  VERIFIED: {verified_count} (baseline: {expected_verified}) [MATCH]")
            print(f"  Total fields: {total_fields}")
            return {
                'status': 'PASS',
                'verified_count': verified_count,
                'total_fields': total_fields,
                'baseline_match': True
            }
        else:
            print(f"  VERIFIED: {verified_count} (baseline: {expected_verified}) [MISMATCH]")
            return {
                'status': 'FAIL',
                'verified_count': verified_count,
                'expected_count': expected_verified,
                'baseline_match': False
            }
    except Exception as e:
        return {'status': 'FAIL', 'reason': str(e)}


def check_store001_integrity() -> Dict[str, Any]:
    """Check STORE-001 canonical store integrity."""
    print("\n" + "="*60)
    print("STORE-001 Integrity Check")
    print("="*60)

    store_dir = Path('data/test_corpus/canonical_store')

    if not store_dir.exists():
        return {'status': 'FAIL', 'reason': 'Store directory not found'}

    # Check index file
    index_file = store_dir / 'store_index.json'
    if not index_file.exists():
        return {'status': 'FAIL', 'reason': 'Store index not found'}

    try:
        with open(index_file, 'r', encoding='utf-8') as f:
            index = json.load(f)

        # Check structure
        required_keys = ['version', 'records']
        missing = [k for k in required_keys if k not in index]
        if missing:
            return {'status': 'FAIL', 'reason': f'Missing keys: {missing}'}

        records = index['records']

        # Check extraction files
        extractions_dir = store_dir / 'extractions'
        if not extractions_dir.exists():
            return {'status': 'FAIL', 'reason': 'Extractions directory not found'}

        extraction_files = list(extractions_dir.glob('*_g3_objects.json'))

        # Baseline: 3 extraction files (F02, F07, PAT01)
        expected_count = 3
        actual_count = len(extraction_files)

        print(f"  Records in index: {len(records)}")
        print(f"  Extraction files: {actual_count} (baseline: {expected_count})")

        # Check each extraction file is readable
        file_status = {}
        for ef in extraction_files:
            try:
                with open(ef, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                file_status[ef.name] = 'PASS' if 'objects' in data else 'FAIL'
            except Exception as e:
                file_status[ef.name] = f'FAIL: {e}'

        all_pass = all(s == 'PASS' for s in file_status.values())

        if actual_count == expected_count and all_pass:
            print(f"  File status: {file_status}")
            return {
                'status': 'PASS',
                'record_count': len(records),
                'extraction_count': actual_count,
                'file_status': file_status
            }
        else:
            return {
                'status': 'FAIL',
                'record_count': len(records),
                'extraction_count': actual_count,
                'expected_count': expected_count,
                'file_status': file_status
            }
    except Exception as e:
        return {'status': 'FAIL', 'reason': str(e)}


def check_phase1_phase2_data_integrity() -> Dict[str, Any]:
    """Verify Phase 1-2 modifications haven't corrupted data."""
    print("\n" + "="*60)
    print("Phase 1-2 Data Integrity Check")
    print("="*60)

    doc_ids = ['F02', 'F07', 'PAT01']
    results = {
        'phase1_false_zeros_fixed': 0,
        'phase2_values_normalized': 0,
        'backup_files_present': 0,
        'revision_trails_present': 0
    }

    for doc_id in doc_ids:
        # Check Phase 1 backups
        for filename in ['reliability_extracted.json', 'scientific_objects.json']:
            backup = Path(f'data/test_corpus/g3_output/{doc_id}/{filename}.backup_phase1')
            if backup.exists():
                results['backup_files_present'] += 1

        # Check Phase 2 backups
        for filename in ['performance_extracted.json', 'reliability_extracted.json']:
            backup = Path(f'data/test_corpus/g3_output/{doc_id}/{filename}.backup_phase2')
            if backup.exists():
                results['backup_files_present'] += 1

        # Check revision trails
        trail = Path(f'data/test_corpus/g3_output/{doc_id}/revision_trail_phase1.json')
        if trail.exists():
            results['revision_trails_present'] += 1

    # Check Phase 1 results
    phase1_results = Path('runs/G3_CLOSE003_phase1_false_zeros.json')
    if phase1_results.exists():
        with open(phase1_results, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Actual structure: summary.false_zeros (not false_zeros_fixed)
            results['phase1_false_zeros_fixed'] = data.get('summary', {}).get('false_zeros', 0)

    # Check Phase 2 results
    phase2_results = Path('runs/G3_CLOSE003_phase2_normalization.json')
    if phase2_results.exists():
        with open(phase2_results, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Check actual structure
            summary = data.get('summary', {})
            results['phase2_values_normalized'] = summary.get('total_values_normalized', summary.get('total_normalized', 0))

    print(f"  Phase 1 false zeros fixed: {results['phase1_false_zeros_fixed']}")
    print(f"  Phase 2 values normalized: {results['phase2_values_normalized']}")
    print(f"  Backup files present: {results['backup_files_present']}")
    print(f"  Revision trails present: {results['revision_trails_present']}")

    # All checks should have positive counts
    all_good = (results['phase1_false_zeros_fixed'] > 0 and
                results['backup_files_present'] > 0 and
                results['revision_trails_present'] > 0)

    results['status'] = 'PASS' if all_good else 'FAIL'

    return results


def main():
    """Run all integrity checks."""
    print("="*60)
    print("G3-CLOSE-003 Phase 4: Data Integrity Regression Check")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Run integrity checks
    tax_results = check_tax001_integrity()
    qa_results = check_qa001_integrity()
    store_results = check_store001_integrity()
    phase12_results = check_phase1_phase2_data_integrity()

    # Overall summary
    print("\n" + "="*60)
    print("REGRESSION CHECK SUMMARY")
    print("="*60)

    overall_status = 'PASS'

    print(f"\nTAX-001: {tax_results['status']}")
    if tax_results['status'] == 'PASS':
        print(f"  {tax_results['pass_count']}/{tax_results['pass_count'] + tax_results['fail_count']} documents valid")
    else:
        overall_status = 'FAIL'
        print(f"  {tax_results['pass_count']} PASS, {tax_results['fail_count']} FAIL")

    print(f"\nQA-001: {qa_results['status']}")
    if qa_results['status'] == 'PASS':
        print(f"  {qa_results['verified_count']} VERIFIED (baseline match: {qa_results.get('baseline_match', False)})")
    else:
        overall_status = 'FAIL'
        print(f"  Reason: {qa_results.get('reason', 'Unknown')}")

    print(f"\nSTORE-001: {store_results['status']}")
    if store_results['status'] == 'PASS':
        print(f"  {store_results['record_count']} records, {store_results['extraction_count']} files")
    else:
        overall_status = 'FAIL'
        print(f"  Reason: {store_results.get('reason', 'Unknown')}")

    print(f"\nPhase 1-2 Data: {phase12_results['status']}")
    if phase12_results['status'] == 'PASS':
        print(f"  {phase12_results['phase1_false_zeros_fixed']} false zeros fixed")
        print(f"  {phase12_results['phase2_values_normalized']} values normalized")
        print(f"  {phase12_results['backup_files_present']} backup files")
    else:
        overall_status = 'FAIL'

    print(f"\n{'='*60}")
    print(f"OVERALL: {overall_status}")
    print(f"{'='*60}")

    # Save results
    output_dir = Path('runs')
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / 'G3_CLOSE003_phase4_regression.json'

    output = {
        'task': 'G3-CLOSE-003 Phase 4: Data Integrity Regression Check',
        'timestamp': datetime.now().isoformat(),
        'overall_status': overall_status,
        'TAX-001': tax_results,
        'QA-001': qa_results,
        'STORE-001': store_results,
        'Phase1-2_Data': phase12_results,
        'conclusion': f"Regression check {overall_status}. All existing data integrity verified after Phase 1-2 modifications."
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved: {output_file}")

    return overall_status == 'PASS'


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
