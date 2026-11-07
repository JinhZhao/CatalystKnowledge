"""Phase 3.4.2 — F02 Real LLM Six-Dimension Extraction with Metadata Tracking.

Uses DICP in-house LLM API (DeepSeek-Flash) to extract all 6 dimensions from F02.
Records per-call metadata: model, tokens, latency, chunk info.

Usage:
    python scripts/phase342_f02_extraction.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DOCUMENT_ID = "F02"
MINERU_OUTPUT = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3" / "f02_e2e" / "02_pdf_parse"
OUTPUT_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3_4_2" / "f02_extraction"
PROMPT_CONFIG = PROJECT_ROOT / "config" / "prompts" / "science_extraction_v2.yaml"

ALL_DIMENSIONS = [
    "catalyst_design",
    "characterization",
    "performance",
    "mechanism",
    "structure_activity",
    "reliability",
]


def setup_api_credentials():
    """Set DICP API credentials."""
    os.environ["LLM_API_KEY"] = "sk-S4l2Jm-es1eezvaEGTfDWQ"
    os.environ["LLM_API_BASE"] = "https://chemestack.dicp.ac.cn:8443/v1"
    os.environ["LLM_MODEL"] = "DeepSeek-Flash"
    logger.info("API credentials configured: DeepSeek-Flash @ chemestack.dicp.ac.cn:8443")


def extract_with_metadata(
    llm_service,
    prompt_config,
    dimension: str,
    chunk_content: str,
    document_context: str,
    section_title: str,
    call_index: int,
) -> dict:
    """Single LLM call with full metadata tracking."""
    from catalyst_knowledge.core.llm_service import ChatMessage

    system_prompt, user_prompt = prompt_config.render_prompt(
        dimension=dimension,
        chunk_content=chunk_content,
        document_context=document_context,
        section_title=section_title,
    )

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]

    call_metadata = {
        "call_index": call_index,
        "dimension": dimension,
        "section_title": section_title,
        "chunk_char_count": len(chunk_content),
        "system_prompt_chars": len(system_prompt),
        "user_prompt_chars": len(user_prompt),
        "timestamp_start": datetime.now().isoformat(),
    }

    start_time = time.time()
    try:
        response = llm_service.chat(messages, response_format={"type": "json_object"})
        elapsed = time.time() - start_time

        call_metadata.update({
            "timestamp_end": datetime.now().isoformat(),
            "latency_seconds": round(elapsed, 2),
            "model_returned": response.model,
            "prompt_tokens": response.usage.get("prompt_tokens", 0) if response.usage else 0,
            "completion_tokens": response.usage.get("completion_tokens", 0) if response.usage else 0,
            "total_tokens": (
                (response.usage.get("prompt_tokens", 0) + response.usage.get("completion_tokens", 0))
                if response.usage else 0
            ),
            "status": "SUCCESS",
            "response_chars": len(response.content),
        })

        try:
            data = json.loads(response.content)
            return {
                "success": True,
                "data": data,
                "metadata": call_metadata,
                "error": None,
            }
        except json.JSONDecodeError as e:
            call_metadata["status"] = "JSON_PARSE_ERROR"
            return {
                "success": False,
                "data": None,
                "metadata": call_metadata,
                "error": f"JSON parse error: {e}",
            }

    except Exception as e:
        elapsed = time.time() - start_time
        call_metadata.update({
            "timestamp_end": datetime.now().isoformat(),
            "latency_seconds": round(elapsed, 2),
            "status": "EXCEPTION",
            "error": str(e),
        })
        return {
            "success": False,
            "data": None,
            "metadata": call_metadata,
            "error": str(e),
        }


def run_extraction():
    """Main extraction loop with metadata collection."""
    from catalyst_knowledge.pipeline.section_aware_extractor import SectionAwareContentLoader
    from catalyst_knowledge.pipeline.prompt_loader import load_prompt_config
    from catalyst_knowledge.pipeline.adapters.science_extraction_v2_adapter import (
        _create_llm_service,
        _normalize_dimension_result,
        _merge_dimension_results,
    )

    setup_api_credentials()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    auto_dir = MINERU_OUTPUT / "main" / "auto"
    content_list_path = auto_dir / "main_content_list.json"

    if not content_list_path.exists():
        logger.error("Content list not found: %s", content_list_path)
        return None

    loader = SectionAwareContentLoader(content_list_path)
    loader.load()
    logger.info("Loaded %d sections, %d chars", len(loader.sections), len(loader.full_text))

    prompt_config = load_prompt_config(PROMPT_CONFIG)
    logger.info("Loaded prompt config v%s", prompt_config.prompt_version)

    config = {
        "llm": {
            "api_key_env": "LLM_API_KEY",
            "api_base_env": "LLM_API_BASE",
            "model_env": "LLM_MODEL",
        }
    }
    llm = _create_llm_service(config)

    extraction_input = loader.to_extraction_input()
    document_context = (
        f"Document: {DOCUMENT_ID}, "
        f"Total sections: {extraction_input['total_sections']}, "
        f"Total chars: {extraction_input['total_chars']}"
    )

    all_call_metadata = []
    dimension_results = {}
    call_index = 0
    total_tokens_prompt = 0
    total_tokens_completion = 0
    total_latency = 0.0

    for dim in ALL_DIMENSIONS:
        logger.info("=" * 60)
        logger.info("DIMENSION: %s", dim)
        logger.info("=" * 60)

        chunks = loader.build_dimension_chunks(dim)
        chunk_results = []

        for chunk in chunks:
            call_index += 1
            section_titles = ", ".join(chunk.sections[:3])
            logger.info(
                "  Call #%d: %s chunk %s (%d chars, sections=[%s])",
                call_index, dim, chunk.chunk_id, len(chunk.content), section_titles,
            )

            result = extract_with_metadata(
                llm_service=llm,
                prompt_config=prompt_config,
                dimension=dim,
                chunk_content=chunk.content,
                document_context=document_context,
                section_title=section_titles,
                call_index=call_index,
            )

            meta = result["metadata"]
            all_call_metadata.append(meta)

            if result["success"]:
                total_tokens_prompt += meta["prompt_tokens"]
                total_tokens_completion += meta["completion_tokens"]
                total_latency += meta["latency_seconds"]
                logger.info(
                    "    -> SUCCESS: %d tokens (%d+%d), %.1fs latency",
                    meta["total_tokens"], meta["prompt_tokens"],
                    meta["completion_tokens"], meta["latency_seconds"],
                )

                normalized = _normalize_dimension_result(dim, result["data"])
                normalized["chunk_id"] = chunk.chunk_id
                normalized["chunk_sections"] = chunk.sections
                normalized["call_metadata"] = meta
                chunk_results.append(normalized)

                chunk_file = OUTPUT_DIR / f"{dim}_{chunk.chunk_id}_raw.json"
                with open(chunk_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            else:
                logger.warning("    -> FAILED: %s", result["error"])

        if chunk_results:
            merged = _merge_dimension_results(dim, chunk_results)
            dimension_results[dim] = merged

            data_file = OUTPUT_DIR / f"{dim}_v2_extracted.json"
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2, ensure_ascii=False, default=str)

            logger.info("  Dimension '%s': merged %d chunks -> %s", dim, len(chunk_results), data_file.name)
        else:
            dimension_results[dim] = {
                "dimension": dim,
                "fields": {},
                "validation_warnings": ["All chunks failed"],
            }

    manifest = {
        "document_id": DOCUMENT_ID,
        "phase": "3.4.2",
        "extraction_version": "v2",
        "prompt_version": prompt_config.prompt_version,
        "timestamp": datetime.now().isoformat(),
        "api_config": {
            "base_url": os.environ["LLM_API_BASE"],
            "model_requested": os.environ["LLM_MODEL"],
        },
        "summary": {
            "dimensions_total": len(ALL_DIMENSIONS),
            "dimensions_with_data": sum(1 for d in dimension_results.values() if d.get("fields")),
            "total_llm_calls": call_index,
            "successful_calls": sum(1 for m in all_call_metadata if m["status"] == "SUCCESS"),
            "failed_calls": sum(1 for m in all_call_metadata if m["status"] != "SUCCESS"),
            "total_tokens_prompt": total_tokens_prompt,
            "total_tokens_completion": total_tokens_completion,
            "total_tokens": total_tokens_prompt + total_tokens_completion,
            "total_latency_seconds": round(total_latency, 2),
            "avg_latency_seconds": round(total_latency / max(call_index, 1), 2),
            "content_chars": extraction_input["total_chars"],
            "content_sections": extraction_input["total_sections"],
        },
        "per_call_metadata": all_call_metadata,
        "dimensions_extracted": list(dimension_results.keys()),
    }

    manifest_file = OUTPUT_DIR / "PHASE342_LLM_EXECUTION_MANIFEST.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)

    logger.info("=" * 60)
    logger.info("EXTRACTION COMPLETE")
    logger.info("=" * 60)
    logger.info("  Total calls: %d", call_index)
    logger.info("  Successful: %d", manifest["summary"]["successful_calls"])
    logger.info("  Failed: %d", manifest["summary"]["failed_calls"])
    logger.info("  Total tokens: %d (prompt=%d, completion=%d)",
                total_tokens_prompt + total_tokens_completion,
                total_tokens_prompt, total_tokens_completion)
    logger.info("  Total latency: %.1fs (avg=%.1fs/call)",
                total_latency, total_latency / max(call_index, 1))
    logger.info("  Manifest: %s", manifest_file.name)

    return manifest


if __name__ == "__main__":
    result = run_extraction()
    if result is None:
        sys.exit(1)
