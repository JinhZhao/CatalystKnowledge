"""
G3-05: STORE-001 Multi-Document Storage Verification

Verify multi-document write, query, update, invalidated record isolation, and source anchor back-linking.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent))

from store01_canonical import CanonicalStore


def store_document_objects(doc_id: str, store: CanonicalStore) -> Dict[str, Any]:
    """Store scientific objects for a document."""
    
    print(f"\nStoring document: {doc_id}")
    
    # Load scientific objects
    objects_file = Path(f'data/test_corpus/g3_output/{doc_id}/scientific_objects.json')
    if not objects_file.exists():
        print(f"  [ERROR] scientific_objects.json not found")
        return {'success': False, 'error': 'File not found'}
    
    with open(objects_file, 'r', encoding='utf-8') as f:
        objects_data = json.load(f)
    
    # Store as extraction
    extraction_data = {
        'doc_id': doc_id,
        'extraction_type': 'scientific_objects',
        'extraction_version': '1.0',
        'extraction_method': 'LLM_EXTRACTED',
        'timestamp': datetime.now().isoformat(),
        'objects': objects_data.get('objects', {}),
        'relationships': objects_data.get('relationships', []),
        'statistics': objects_data.get('statistics', {})
    }
    
    # Save to store
    ext_id = f"{doc_id}_g3_objects"
    ext_file = store.store_dir / 'extractions' / f'{ext_id}.json'
    ext_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(ext_file, 'w', encoding='utf-8') as f:
        json.dump(extraction_data, f, indent=2, ensure_ascii=False)
    
    # Update index
    store.index['extractions'][ext_id] = {
        'doc_id': doc_id,
        'hash': f'g3_{doc_id}_{datetime.now().timestamp()}',
        'file': str(ext_file.relative_to(store.store_dir)),
        'saved': datetime.now().isoformat(),
        'extraction_method': 'LLM_EXTRACTED',
        'object_count': extraction_data['statistics'].get('total_objects', 0)
    }
    store._save_index()
    
    print(f"  [PASS] Stored {extraction_data['statistics'].get('total_objects', 0)} objects")
    print(f"         File: {ext_file.name}")
    
    return {
        'success': True,
        'doc_id': doc_id,
        'ext_id': ext_id,
        'object_count': extraction_data['statistics'].get('total_objects', 0),
        'file': str(ext_file)
    }


def query_document(doc_id: str, store: CanonicalStore) -> Dict[str, Any]:
    """Query document from store."""
    
    print(f"\nQuerying document: {doc_id}")
    
    ext_id = f"{doc_id}_g3_objects"
    
    if ext_id not in store.index['extractions']:
        print(f"  [FAIL] Document not found in index")
        return {'success': False, 'error': 'Not in index'}
    
    ext_info = store.index['extractions'][ext_id]
    ext_file = store.store_dir / ext_info['file']
    
    if not ext_file.exists():
        print(f"  [FAIL] File not found: {ext_file}")
        return {'success': False, 'error': 'File not found'}
    
    with open(ext_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    objects = data.get('objects', {})
    relationships = data.get('relationships', [])
    
    print(f"  [PASS] Queried successfully")
    print(f"         Objects: {len(objects)}")
    print(f"         Relationships: {len(relationships)}")
    print(f"         Method: {data.get('extraction_method')}")
    
    return {
        'success': True,
        'doc_id': doc_id,
        'objects': len(objects),
        'relationships': len(relationships),
        'method': data.get('extraction_method')
    }


def update_document(doc_id: str, store: CanonicalStore) -> Dict[str, Any]:
    """Test update functionality."""
    
    print(f"\nTesting update for document: {doc_id}")
    
    ext_id = f"{doc_id}_g3_objects"
    
    if ext_id not in store.index['extractions']:
        print(f"  [FAIL] Document not found in index")
        return {'success': False, 'error': 'Not in index'}
    
    ext_info = store.index['extractions'][ext_id]
    ext_file = store.store_dir / ext_info['file']
    
    # Load existing data
    with open(ext_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Add update metadata
    data['updated'] = datetime.now().isoformat()
    data['update_note'] = 'G3-05 storage verification test'
    
    # Save back
    with open(ext_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Update index
    store.index['extractions'][ext_id]['modified'] = datetime.now().isoformat()
    store._save_index()
    
    print(f"  [PASS] Update successful")
    print(f"         Updated: {data['updated']}")
    
    return {
        'success': True,
        'doc_id': doc_id,
        'updated': data['updated']
    }


def verify_source_anchor_backlink(doc_id: str, store: CanonicalStore) -> Dict[str, Any]:
    """Verify SourceAnchor can link back to original content."""
    
    print(f"\nVerifying SourceAnchor back-linking for: {doc_id}")
    
    ext_id = f"{doc_id}_g3_objects"
    ext_info = store.index['extractions'].get(ext_id)
    
    if not ext_info:
        return {'success': False, 'error': 'Not in index'}
    
    ext_file = store.store_dir / ext_info['file']
    with open(ext_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    objects = data.get('objects', {})
    
    # Check if objects have source anchors
    anchor_count = 0
    for obj_type, obj_data in objects.items():
        if isinstance(obj_data, dict):
            if 'source_anchor' in obj_data:
                anchor_count += 1
                anchor = obj_data['source_anchor']
                # Verify anchor has required fields
                if anchor.get('document_id') == doc_id:
                    print(f"  [PASS] {obj_type} has valid SourceAnchor")
        elif isinstance(obj_data, list):
            for item in obj_data:
                if isinstance(item, dict) and 'source_anchor' in item:
                    anchor_count += 1
                    anchor = item['source_anchor']
                    if anchor.get('document_id') == doc_id:
                        print(f"  [PASS] {obj_type} item has valid SourceAnchor")
    
    print(f"  Total SourceAnchors: {anchor_count}")
    
    return {
        'success': anchor_count > 0,
        'doc_id': doc_id,
        'anchor_count': anchor_count
    }


def verify_invalidated_isolation(store: CanonicalStore) -> Dict[str, Any]:
    """Verify INVALIDATED records are properly isolated."""
    
    print(f"\nVerifying INVALIDATED record isolation...")
    
    # Check that P01 v1_INVALIDATED is not in active index
    p01_v1_in_index = False
    for ext_id, ext_info in store.index['extractions'].items():
        if 'INVALIDATED' in ext_info.get('file', ''):
            p01_v1_in_index = True
            print(f"  [FAIL] INVALIDATED record in index: {ext_id}")
    
    if not p01_v1_in_index:
        print(f"  [PASS] No INVALIDATED records in active index")
    
    # Check that P01 v2_corrected is in index
    p01_v2_in_index = False
    for ext_id, ext_info in store.index['extractions'].items():
        if ext_id == 'P01_main_ext':
            p01_v2_in_index = True
            print(f"  [PASS] P01 v2_corrected in index")
            break
    
    if not p01_v2_in_index:
        print(f"  [WARN] P01 v2_corrected not in index (may be expected)")
    
    return {
        'success': not p01_v1_in_index,
        'invalidated_in_index': p01_v1_in_index,
        'v2_corrected_in_index': p01_v2_in_index
    }


def main():
    """Run STORE-001 multi-document verification."""
    
    print("="*60)
    print("G3-05: STORE-001 Multi-Document Storage Verification")
    print("="*60)
    
    # Initialize store
    store_dir = Path('data/test_corpus/canonical_store')
    store = CanonicalStore(store_dir)
    
    print(f"\nStore initialized: {store_dir}")
    print(f"Existing extractions: {len(store.index['extractions'])}")
    
    doc_ids = ['F02', 'F07', 'PAT01']
    
    results = {
        'storage': {},
        'query': {},
        'update': {},
        'source_anchor': {},
        'invalidated_isolation': {}
    }
    
    # Test 1: Store all documents
    print("\n" + "="*60)
    print("Test 1: Store Documents")
    print("="*60)
    
    for doc_id in doc_ids:
        result = store_document_objects(doc_id, store)
        results['storage'][doc_id] = result
    
    # Test 2: Query all documents
    print("\n" + "="*60)
    print("Test 2: Query Documents")
    print("="*60)
    
    for doc_id in doc_ids:
        result = query_document(doc_id, store)
        results['query'][doc_id] = result
    
    # Test 3: Update documents
    print("\n" + "="*60)
    print("Test 3: Update Documents")
    print("="*60)
    
    for doc_id in doc_ids:
        result = update_document(doc_id, store)
        results['update'][doc_id] = result
    
    # Test 4: Verify SourceAnchor back-linking
    print("\n" + "="*60)
    print("Test 4: SourceAnchor Back-Linking")
    print("="*60)
    
    for doc_id in doc_ids:
        result = verify_source_anchor_backlink(doc_id, store)
        results['source_anchor'][doc_id] = result
    
    # Test 5: Verify INVALIDATED isolation
    print("\n" + "="*60)
    print("Test 5: INVALIDATED Record Isolation")
    print("="*60)
    
    isolation_result = verify_invalidated_isolation(store)
    results['invalidated_isolation'] = isolation_result
    
    # Summary
    print("\n" + "="*60)
    print("STORE-001 VERIFICATION SUMMARY")
    print("="*60)
    
    storage_success = sum(1 for r in results['storage'].values() if r.get('success'))
    query_success = sum(1 for r in results['query'].values() if r.get('success'))
    update_success = sum(1 for r in results['update'].values() if r.get('success'))
    anchor_success = sum(1 for r in results['source_anchor'].values() if r.get('success'))
    
    print(f"Storage: {storage_success}/{len(doc_ids)} successful")
    print(f"Query: {query_success}/{len(doc_ids)} successful")
    print(f"Update: {update_success}/{len(doc_ids)} successful")
    print(f"SourceAnchor: {anchor_success}/{len(doc_ids)} successful")
    print(f"INVALIDATED isolation: {'PASS' if results['invalidated_isolation']['success'] else 'FAIL'}")
    
    # Save results
    output_file = store_dir / 'g3_store_verification.json'
    
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_documents': len(doc_ids),
        'storage_success': storage_success,
        'query_success': query_success,
        'update_success': update_success,
        'source_anchor_success': anchor_success,
        'invalidated_isolation': results['invalidated_isolation'],
        'results': results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved: {output_file}")
    
    return summary


if __name__ == '__main__':
    main()
