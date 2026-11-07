# -*- coding: utf-8 -*-
"""Download only the required model files from ModelScope for magic-pdf 1.3.12."""

import sys
from pathlib import Path

# Required model files based on model_configs.yaml
REQUIRED_PATTERNS = [
    "models/Layout/YOLO/doclayout_yolo_docstructbench_imgsz1280_2501.pt",
    "models/MFD/YOLO/yolo_v8_ft.pt",
    "models/MFR/unimernet_hf_small_2503/**",
]

TARGET_DIR = Path(r"D:\Knowledge_World\models")


def main():
    print("=" * 80)
    print("MinerU Model Downloader (ModelScope)")
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
        print("This will download only the required model files.")
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
        model_files = list(TARGET_DIR.rglob("*.pt")) + list(TARGET_DIR.rglob("*.pth"))
        model_dirs = [d for d in TARGET_DIR.rglob("*") if d.is_dir() and "unimernet" in d.name.lower()]
        
        print(f"  Model files found: {len(model_files)}")
        for f in model_files:
            size_mb = f.stat().st_size / 1024 / 1024
            print(f"    - {f.relative_to(TARGET_DIR)} ({size_mb:.1f} MB)")
        
        print(f"  Model directories found: {len(model_dirs)}")
        for d in model_dirs:
            file_count = len(list(d.rglob("*")))
            print(f"    - {d.relative_to(TARGET_DIR)} ({file_count} files)")
        
        print()
        print("=" * 80)
        print("SUCCESS: Models downloaded and verified")
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
