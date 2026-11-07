# -*- coding: utf-8 -*-
"""Download missing ch_PP-OCRv3_det_infer.pth model."""

from pathlib import Path
from modelscope.hub.file_download import model_file_download

TARGET_DIR = Path(r"D:\Knowledge_World\models\models\OCR\paddleocr_torch")
TARGET_DIR.mkdir(parents=True, exist_ok=True)

MODEL_ID = "opendatalab/PDF-Extract-Kit"
REVISION = "master"
FILE_PATH = "models/OCR/paddleocr_torch/ch_PP-OCRv3_det_infer.pth"

print(f"Downloading {FILE_PATH}...")
print(f"Target: {TARGET_DIR}")

try:
    downloaded_path = model_file_download(
        model_id=MODEL_ID,
        revision=REVISION,
        file_path=FILE_PATH,
    )
    print(f"Downloaded to: {downloaded_path}")
    
    # Copy to target directory
    import shutil
    target_file = TARGET_DIR / "ch_PP-OCRv3_det_infer.pth"
    shutil.copy2(downloaded_path, target_file)
    print(f"Copied to: {target_file}")
    print("SUCCESS!")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
