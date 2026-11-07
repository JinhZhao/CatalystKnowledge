#!/usr/bin/env python3
"""
Re-run only the missing characterization dimension for F02 extraction.
Then generate the extraction summary file.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ['LLM_API_BASE'] = 'https://api.siliconflow.cn/v1'
os.environ['LLM_API_KEY'] = 'sk-axbgbaleimmmpyepwhbgnpldiesqfmwerrwvxbxnscczspdv'
os.environ['LLM_MODEL'] = 'deepseek-ai/DeepSeek-V4-Flash'

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

EXTRACTION_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3" / "f02_e2e" / "05_extraction" / "F02"
MINERU_AUTO = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3" / "f02_e2e" / "02_pdf_parse" / "main" / "auto"


def load_content():
    content_files = list(MINERU_AUTO.glob("*content_list.json"))
    with open(content_files[0], "r", encoding="utf-8") as f:
        content_list = json.load(f)
    text_parts = []
    for item in content_list:
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    return "\n".join(text_parts)


def main():
    char_file = EXTRACTION_DIR / "characterization_extracted.json"
    if char_file.exists() and char_file.stat().st_size > 10:
        print(f"Characterization already exists: {char_file}")
    else:
        print("Re-running characterization extraction...")
        from catalyst_knowledge.pipeline.adapters.extraction_adapter import (
            _extract_single_dimension,
            _create_llm_service,
            DIMENSION_PROMPTS,
        )
        from catalyst_knowledge.pipeline.config_loader import ConfigLoader

        config = ConfigLoader()
        config.load(str(PROJECT_ROOT / "config" / "pipeline.yaml"))
        llm = _create_llm_service(config.config)

        content = load_content()
        print(f"Content length: {len(content)} chars")

        result = _extract_single_dimension(llm, "characterization", content, max_retries=3)
        if result["success"]:
            with open(char_file, "w", encoding="utf-8") as f:
                json.dump(result["data"], f, indent=2, ensure_ascii=False)
            print(f"  OK: {char_file.name} ({result['attempts']} attempts)")
        else:
            print(f"  FAILED: {result['error']}")
            return False

    extracted_files = list(EXTRACTION_DIR.glob("*_extracted.json"))
    dimensions = [f.stem.replace("_extracted", "") for f in extracted_files]
    print(f"\nExtraction files: {len(extracted_files)}/6")
    for d in sorted(dimensions):
        print(f"  - {d}")

    summary = {
        "document_id": "F02",
        "dimensions_total": 6,
        "dimensions_success": len(extracted_files),
        "dimensions_failed": 6 - len(extracted_files),
        "timestamp": datetime.now().isoformat(),
    }
    summary_file = EXTRACTION_DIR / "extraction_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSummary written: {summary_file.name}")
    print(f"Status: {'PASS' if len(extracted_files) == 6 else 'PARTIAL'}")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
