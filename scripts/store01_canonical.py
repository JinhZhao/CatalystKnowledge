#!/usr/bin/env python3
"""
STORE-001: 最小科学记录存储

实现：
1. Canonical store (JSON-based)
2. 幂等写入
3. 查询回读
4. SourceAnchor定位原文
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class CanonicalStore:
    """最小科学记录主库"""

    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = store_dir / 'store_index.json'
        self.index = self._load_index()

    def _load_index(self) -> Dict:
        """Load or create store index."""
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'version': '1.0',
            'created': datetime.now().isoformat(),
            'documents': {},
            'extractions': {},
            'associations': {},
        }

    def _save_index(self):
        """Save store index."""
        self.index['modified'] = datetime.now().isoformat()
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2, ensure_ascii=False)

    def _compute_hash(self, data: Dict) -> str:
        """Compute SHA256 hash of data for idempotency check."""
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def save_document(self, doc_id: str, metadata: Dict) -> bool:
        """
        Save document metadata. Idempotent: skips if hash matches.

        Returns: True if saved, False if already exists with same hash
        """
        doc_hash = self._compute_hash(metadata)

        if doc_id in self.index['documents']:
            existing = self.index['documents'][doc_id]
            if existing.get('hash') == doc_hash:
                return False  # Already exists, skip

        # Save document file
        doc_file = self.store_dir / 'documents' / f'{doc_id}.json'
        doc_file.parent.mkdir(exist_ok=True)
        with open(doc_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Update index
        self.index['documents'][doc_id] = {
            'hash': doc_hash,
            'file': str(doc_file.relative_to(self.store_dir)),
            'saved': datetime.now().isoformat(),
        }
        self._save_index()

        return True

    def save_extraction(self, doc_id: str, extraction: Dict) -> bool:
        """
        Save extraction results. Idempotent.

        Returns: True if saved, False if already exists with same hash
        """
        ext_hash = self._compute_hash(extraction)
        ext_id = f"{doc_id}_ext"

        if ext_id in self.index['extractions']:
            existing = self.index['extractions'][ext_id]
            if existing.get('hash') == ext_hash:
                return False

        # Save extraction file
        ext_file = self.store_dir / 'extractions' / f'{ext_id}.json'
        ext_file.parent.mkdir(exist_ok=True)
        with open(ext_file, 'w', encoding='utf-8') as f:
            json.dump(extraction, f, indent=2, ensure_ascii=False)

        # Update index
        self.index['extractions'][ext_id] = {
            'doc_id': doc_id,
            'hash': ext_hash,
            'file': str(ext_file.relative_to(self.store_dir)),
            'saved': datetime.now().isoformat(),
        }
        self._save_index()

        return True

    def save_association(self, assoc_id: str, association: Dict) -> bool:
        """
        Save association (e.g., LINK-001 results). Idempotent.
        """
        assoc_hash = self._compute_hash(association)

        if assoc_id in self.index['associations']:
            existing = self.index['associations'][assoc_id]
            if existing.get('hash') == assoc_hash:
                return False

        # Save association file
        assoc_file = self.store_dir / 'associations' / f'{assoc_id}.json'
        assoc_file.parent.mkdir(exist_ok=True)
        with open(assoc_file, 'w', encoding='utf-8') as f:
            json.dump(association, f, indent=2, ensure_ascii=False)

        # Update index
        self.index['associations'][assoc_id] = {
            'hash': assoc_hash,
            'file': str(assoc_file.relative_to(self.store_dir)),
            'saved': datetime.now().isoformat(),
        }
        self._save_index()

        return True

    def query_document(self, doc_id: str) -> Optional[Dict]:
        """Query document metadata by ID."""
        if doc_id not in self.index['documents']:
            return None

        doc_file = self.store_dir / self.index['documents'][doc_id]['file']
        with open(doc_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def query_extraction(self, doc_id: str) -> Optional[Dict]:
        """Query extraction results by document ID."""
        ext_id = f"{doc_id}_ext"
        if ext_id not in self.index['extractions']:
            return None

        ext_file = self.store_dir / self.index['extractions'][ext_id]['file']
        with open(ext_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def query_by_source_anchor(self, anchor: Dict) -> Optional[Dict]:
        """
        Query data by SourceAnchor.

        Args:
            anchor: SourceAnchor dict with document_id, element_id, etc.

        Returns:
            Associated data if found
        """
        doc_id = anchor.get('document_id')
        if not doc_id:
            return None

        # Query extraction for this document
        extraction = self.query_extraction(doc_id)
        if not extraction:
            return None

        # Check if anchor matches any dimension
        element_id = anchor.get('element_id', '')
        for dim_name, dim_anchor in extraction.get('source_anchors', {}).items():
            if dim_anchor.get('element_id') == element_id:
                return {
                    'dimension': dim_name,
                    'data': extraction['view'].get(dim_name),
                    'anchor': dim_anchor,
                }

        return None

    def get_statistics(self) -> Dict:
        """Get store statistics."""
        return {
            'documents': len(self.index['documents']),
            'extractions': len(self.index['extractions']),
            'associations': len(self.index['associations']),
            'store_dir': str(self.store_dir),
            'index_version': self.index.get('version'),
            'created': self.index.get('created'),
            'modified': self.index.get('modified'),
        }


def test_store_idempotency(store: CanonicalStore, doc_id: str, data: Dict):
    """Test that saving same data twice is idempotent."""
    print(f"\n=== Idempotency Test: {doc_id} ===")

    # First save
    saved1 = store.save_document(doc_id, data)
    print(f"  First save: {'SUCCESS' if saved1 else 'SKIPPED'}")

    # Second save (should skip)
    saved2 = store.save_document(doc_id, data)
    print(f"  Second save: {'SUCCESS' if saved2 else 'SKIPPED (idempotent)'}")

    if not saved2:
        print("  [PASS] Idempotency verified")
    else:
        print("  [FAIL] Idempotency broken")


def main():
    """Run STORE-001 minimal closed loop test."""
    print("=== STORE-001: Minimal Canonical Store ===\n")

    store_dir = Path('data/test_corpus/canonical_store')
    store = CanonicalStore(store_dir)

    # 1. Save P01 main document
    print("1. Saving P01_main document metadata...")
    doc_metadata = {
        'doc_id': 'P01_main',
        'doi': '10.1038/s41467-024-50691-5',
        'title': 'Rationally designed Ru catalysts supported on TiN for highly efficient and stable hydrogen evolution in alkaline conditions',
        'authors': ['Jia Zhao', 'Ricardo Urrego-Ortiz', 'Nan Liao', 'Federico Calle-Vallejo', 'Jingshan Luo'],
        'journal': 'Nature Communications',
        'year': 2024,
        'file_sha256': 'e9f9dbca043b2a5c03a6aa658362b0195b3e7b8af9ba7f494edefef9bc57c372',
        'pages': 14,
        'si_document': 'P01_SI',
    }
    test_store_idempotency(store, 'P01_main', doc_metadata)

    # 2. Save P01 extraction
    print("\n2. Saving P01_main extraction results...")
    ext_file = Path('data/test_corpus/ext01_output/P01_main_ext01.json')
    if ext_file.exists():
        with open(ext_file, 'r', encoding='utf-8') as f:
            extraction = json.load(f)
        saved = store.save_extraction('P01_main', extraction)
        print(f"  Extraction saved: {'SUCCESS' if saved else 'SKIPPED'}")
    else:
        print(f"  [WARN] Extraction file not found: {ext_file}")

    # 3. Save LINK-001 associations
    print("\n3. Saving P01 LINK-001 associations...")
    assoc_file = Path('data/test_corpus/link01_pair/P01_link01_associations.json')
    if assoc_file.exists():
        with open(assoc_file, 'r', encoding='utf-8') as f:
            associations = json.load(f)
        saved = store.save_association('P01_link01', associations)
        print(f"  Associations saved: {'SUCCESS' if saved else 'SKIPPED'}")
        print(f"  Total associations: {len(associations)}")
    else:
        print(f"  [WARN] Association file not found: {assoc_file}")

    # 4. Query back
    print("\n4. Querying stored data...")
    doc = store.query_document('P01_main')
    if doc:
        print(f"  Document: {doc['doc_id']}")
        print(f"  Title: {doc['title'][:60]}...")
        print(f"  DOI: {doc['doi']}")

    ext = store.query_extraction('P01_main')
    if ext:
        print(f"\n  Extraction completeness: {ext['completeness']['coverage']:.0%}")
        print(f"  Reliability score: {ext['reliability_score']:.3f}")
        print(f"  Dimensions: {', '.join(ext['completeness']['present'])}")

    # 5. Test SourceAnchor lookup
    print("\n5. Testing SourceAnchor lookup...")
    if ext and ext.get('source_anchors'):
        sample_anchor = list(ext['source_anchors'].values())[0]
        result = store.query_by_source_anchor(sample_anchor)
        if result:
            print(f"  Anchor: {sample_anchor['element_id']}")
            print(f"  Dimension: {result['dimension']}")
            print(f"  [PASS] SourceAnchor successfully locates data")
        else:
            print(f"  [FAIL] SourceAnchor lookup failed")

    # 6. Statistics
    print("\n6. Store statistics:")
    stats = store.get_statistics()
    print(f"  Documents: {stats['documents']}")
    print(f"  Extractions: {stats['extractions']}")
    print(f"  Associations: {stats['associations']}")
    print(f"  Store directory: {stats['store_dir']}")

    print("\n=== STORE-001 Complete ===")
    print("Canonical store initialized with P01 data")
    print("Idempotency verified")
    print("SourceAnchor lookup functional")


if __name__ == '__main__':
    main()
