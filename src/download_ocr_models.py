# -*- coding: utf-8 -*-
"""Download OCR models required by magic-pdf 1.3.12."""

import sys
from pathlib import Path

# Additional required model files
REQUIRED_PATTERNS = [
    "models/OCR/**",
]

TARGET_DIR = Path(r"D:\Knowledge_World\models")


def main():
    print("=" * 80)
    print("MinerU OCR Model Downloader (ModelScope)")
    print("=" * 80)
    print()
    print(f"Target directory: {TARGET_DIR}")
    print(f"Required patterns: {len(REQUIRED_PATTERNS)}")
    for pattern in REQUIRED_PATTERNS:
        print(f"  - {pattern}")
    print()
    
    try:
        from modelscope.hub.snapshot_download import snapshot_download
        
        print("Starting download from ModelScope...")
        print("This will download OCR model files.")
        print()
        
        snapshot_download(
            model_id='OpenDataLab/PDF-Extract-Kit-1.0',
            cache_dir=str(TARGET_DIR),
            allow_patterns=REQUIRED_PATTERNS,
        )
        
        print()
        print("Download complete!")
        print()
        
        # Verify downloaded files
        print("Verifying downloaded files...")
        ocr_files = list(TARGET_DIR.rglob("*OCR*"))
        
        print(f"  OCR files/directories found: {len(ocr_files)}")
        for f in ocr_files[:10]:  # Show first 10
            if f.is_file():
                size_mb = f.stat().st_size / 1024 / 1024
                print(f"    - {f.relative_to(TARGET_DIR)} ({size_mb:.1f} MB)")
            else:
                print(f"    - {f.relative_to(TARGET_DIR)}/")
        
        print()
        print("=" * 80)
        print("SUCCESS: OCR models downloaded")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 80)
        print(f"FAILED: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
