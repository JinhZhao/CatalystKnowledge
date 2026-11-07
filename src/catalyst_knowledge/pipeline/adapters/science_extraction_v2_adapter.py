"""Science Extraction Adapter V2 — Section-aware, config-driven LLM extraction.

Replaces extraction_adapter.py with:
1. Section-aware chunking (no more 6000-char truncation)
2. Config-driven prompts from YAML (no more hardcoded strings)
3. Data origin classification (ORIGINAL_EXPERIMENT vs LITERATURE_REFERENCE)
4. Unified missing status (REPORTED/NOT_REPORTED/NOT_EXTRACTED/UNRESOLVED/NOT_APPLICABLE)
5. Multi-chunk merging with conflict resolution
6. SourceAnchor tracking per extracted field
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..data_origin_classifier import (
    DataOrigin,
    DataRecord,
    DataStatus,
    check_default_value_anchor,
    check_false_absence,
    merge_chunk_results,
    validate_origin_value,
    validate_status_value,
)
from ...core.llm_service import LLMOutputTruncated
from ..prompt_loader import PromptConfig, load_prompt_config
from ..section_aware_extractor import (
    ChunkBudgetExceeded,
    SectionAwareContentLoader,
    TokenBudget,
    estimate_tokens,
)
from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)

ALL_DIMENSIONS = [
    "catalyst_design",
    "characterization",
    "performance",
    "mechanism",
    "structure_activity",
    "reliability",
]


def _create_llm_service(config: dict):
    from catalyst_knowledge.core.llm_service import LLMService

    llm_cfg = config.get("llm", {})
    api_key = os.environ.get(llm_cfg.get("api_key_env", "LLM_API_KEY"), "")
    api_base = os.environ.get(
        llm_cfg.get("api_base_env", "LLM_API_BASE"),
        llm_cfg.get("default_api_base", ""),
    )
    model = os.environ.get(
        llm_cfg.get("model_env", "LLM_MODEL"),
        llm_cfg.get("default_model", "deepseek-chat"),
    )
    return LLMService(api_key=api_key, api_base=api_base, model=model)


def _find_mineru_auto_dir(mineru_output: str, document_id: str) -> Optional[Path]:
    base = Path(mineru_output)
    if not base.exists():
        return None
    candidates = [
        base / f"{document_id}_batch" / "main" / "auto",
        base / f"{document_id}_batch" / "auto",
        base / document_id / "main" / "auto",
        base / document_id / "auto",
        base / "main" / "auto",
        base / "auto",
    ]
    for c in candidates:
        if c.exists() and list(c.glob("*content_list.json")):
            return c
    for d in base.iterdir():
        if d.is_dir() and document_id in d.name:
            for sub in [d / "main" / "auto", d / "auto"]:
                if sub.exists() and list(sub.glob("*content_list.json")):
                    return sub
    return None


def _extract_with_prompt(
    llm_service,
    prompt_config: PromptConfig,
    dimension: str,
    chunk_content: str,
    document_context: str = "",
    section_title: str = "",
    max_retries: int = 2,
    token_budget: TokenBudget | None = None,
) -> dict:
    from catalyst_knowledge.core.llm_service import ChatMessage

    system_prompt, user_prompt = prompt_config.render_prompt(
        dimension=dimension,
        chunk_content=chunk_content,
        document_context=document_context,
        section_title=section_title,
    )

    total_input_chars = len(system_prompt) + len(user_prompt)
    total_input_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)

    if token_budget is not None:
        total_budget = token_budget.max_input_tokens
        if total_input_tokens > total_budget:
            logger.error(
                "Estimated input tokens exceed budget for %s: ~%d est. tokens > %d "
                "heuristic budget (system=%d chars, user=%d chars, content=%d chars). "
                "NOTE: token counts are heuristic (chars/3.5), not exact tokenizer counts.",
                dimension, total_input_tokens, total_budget,
                len(system_prompt), len(user_prompt), len(chunk_content),
            )
            return {
                "success": False,
                "data": None,
                "error": (
                    f"TOKEN_BUDGET_EXCEEDED: ~{total_input_tokens} estimated input tokens "
                    f"> {total_budget} heuristic budget (content={len(chunk_content)} chars)"
                ),
                "attempts": 0,
                "raw_response": None,
                "token_budget_exceeded": True,
                "input_tokens_estimated": total_input_tokens,
            }

    logger.info(
        "Heuristic token estimate for %s: ~%d est. input tokens "
        "(system=%d chars, user=%d chars; chars/3.5 heuristic)",
        dimension, total_input_tokens, len(system_prompt), len(user_prompt),
    )

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]

    for attempt in range(max_retries + 1):
        try:
            response = llm_service.chat(messages, response_format={"type": "json_object"})
            data = json.loads(response.content)
            return {
                "success": True,
                "data": data,
                "error": None,
                "attempts": attempt + 1,
                "raw_response": response.content,
                "finish_reason": getattr(response, "finish_reason", None),
            }
        except LLMOutputTruncated as e:
            # Truncation is a hard failure — do NOT retry, do NOT parse content.
            # The incomplete JSON must not enter the Canonical Store.
            logger.error(
                "[%s] chunk %s: LLM output truncated (max_tokens=%d) — "
                "marking chunk as FAILED, no retry",
                dimension, chunk_id, e.max_tokens,
            )
            return {
                "success": False,
                "data": None,
                "error": f"LLM_OUTPUT_TRUNCATED: {e}",
                "truncation_error": True,
                "attempts": attempt + 1,
                "raw_response": None,
                "finish_reason": "length",
            }
        except json.JSONDecodeError as e:
            if attempt >= max_retries:
                return {"success": False, "data": None, "error": f"JSON parse error: {e}", "attempts": attempt + 1}
        except Exception as e:
            if attempt >= max_retries:
                return {"success": False, "data": None, "error": f"LLM call failed: {e}", "attempts": attempt + 1}

    return {"success": False, "data": None, "error": "max retries exceeded", "attempts": max_retries + 1}


def _normalize_field_value(field_name: str, raw_value: Any) -> DataRecord:
    """Convert a raw LLM output field into a DataRecord with proper status/origin."""
    if isinstance(raw_value, dict):
        value = raw_value.get("value")
        status_str = raw_value.get("status", "NOT_EXTRACTED")
        origin_str = raw_value.get("origin", "UNKNOWN_ORIGIN")
        source_quote = raw_value.get("source_quote", "")

        status = validate_status_value(status_str)
        origin = validate_origin_value(origin_str)

        if status == DataStatus.REPORTED and value is None:
            status = DataStatus.UNRESOLVED

        return DataRecord(
            field_name=field_name,
            value=value,
            status=status,
            origin=origin,
            source_quote=source_quote,
        )

    if isinstance(raw_value, str):
        lower = raw_value.strip().lower()
        if lower in ("not specified", "not mentioned", "not provided", "not reported", "n/a", "none", ""):
            return DataRecord(
                field_name=field_name,
                value=raw_value,
                status=DataStatus.NOT_EXTRACTED,
                notes=f"LLM returned generic absence string: '{raw_value}'",
            )
        return DataRecord(
            field_name=field_name,
            value=raw_value,
            status=DataStatus.REPORTED,
            origin=DataOrigin.UNKNOWN_ORIGIN,
        )

    if isinstance(raw_value, list):
        normalized_items = []
        for i, item in enumerate(raw_value):
            normalized_items.append(_normalize_field_value(f"{field_name}[{i}]", item))
        has_reported = any(r.status == DataStatus.REPORTED for r in normalized_items)
        return DataRecord(
            field_name=field_name,
            value=raw_value,
            status=DataStatus.REPORTED if has_reported else DataStatus.NOT_EXTRACTED,
            notes=f"Array with {len(normalized_items)} items, {sum(1 for r in normalized_items if r.status == DataStatus.REPORTED)} REPORTED",
        )

    if isinstance(raw_value, (int, float)) and raw_value == 0:
        return DataRecord(
            field_name=field_name,
            value=raw_value,
            status=DataStatus.REPORTED,
            notes="Numeric value is 0 — flagged for verification (may be legitimate or default anchor)",
        )

    return DataRecord(
        field_name=field_name,
        value=raw_value,
        status=DataStatus.REPORTED if raw_value is not None else DataStatus.NOT_EXTRACTED,
        origin=DataOrigin.UNKNOWN_ORIGIN,
    )


def _normalize_dimension_result(dimension: str, raw_data: dict) -> dict:
    """Normalize all fields in a dimension extraction result."""
    normalized = {
        "dimension": dimension,
        "fields": {},
        "validation_warnings": [],
    }

    for field_name, raw_value in raw_data.items():
        record = _normalize_field_value(field_name, raw_value)
        normalized["fields"][field_name] = record.to_dict()

        warning = check_default_value_anchor(record.value, field_name)
        if warning:
            normalized["validation_warnings"].append(warning)

        if isinstance(raw_value, dict):
            source_text = raw_value.get("source_quote", "")
            abs_warning = check_false_absence(record, source_text)
            if abs_warning:
                normalized["validation_warnings"].append(abs_warning)

    return normalized


def _deduplicate_array_items(items: list, similarity_threshold: float = 0.8) -> list:
    """Remove duplicate items from an array field extracted across overlapping chunks.

    Uses string similarity to detect near-duplicate entries that arise when
    the same content appears in the overlap region of adjacent chunks.
    """
    if len(items) <= 1:
        return items

    unique: list = [items[0]]
    for item in items[1:]:
        is_dup = False
        item_str = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
        for existing in unique:
            existing_str = json.dumps(existing, sort_keys=True, ensure_ascii=False, default=str)
            if _string_similarity(item_str, existing_str) >= similarity_threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(item)
    return unique


def _string_similarity(a: str, b: str) -> float:
    """Quick character-level Jaccard similarity between two strings."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _merge_dimension_results(
    dimension: str,
    chunk_results: list[dict],
) -> dict:
    """Merge extraction results from multiple chunks for the same dimension.

    Enhanced with:
    - Overlap-aware deduplication for array fields
    - Cross-section association tracking (which chunks contributed each field)
    - Merge provenance metadata for auditability
    """
    if not chunk_results:
        return {"dimension": dimension, "fields": {}, "merge_notes": "No chunks processed"}

    if len(chunk_results) == 1:
        result = chunk_results[0]
        result["merge_notes"] = "Single chunk, no merge needed"
        result["chunk_count"] = 1
        result["source_chunks"] = [result.get("chunk_id", "unknown")]
        return result

    all_field_names = set()
    for r in chunk_results:
        all_field_names.update(r.get("fields", {}).keys())

    merged_fields = {}
    field_source_map: dict[str, list[str]] = {}

    for field_name in all_field_names:
        records = []
        source_chunks_for_field = []
        for r in chunk_results:
            field_data = r.get("fields", {}).get(field_name)
            if field_data:
                records.append(DataRecord.from_dict(field_data))
                chunk_id = r.get("chunk_id", "unknown")
                if chunk_id not in source_chunks_for_field:
                    source_chunks_for_field.append(chunk_id)

        field_source_map[field_name] = source_chunks_for_field

        if records:
            reported_records = [
                r for r in records
                if (r.status == DataStatus.REPORTED
                    or (isinstance(r.status, str) and r.status == "REPORTED"))
            ]

            if len(reported_records) > 1:
                merged = _merge_with_dedup(field_name, reported_records, records)
            else:
                merged = merge_chunk_results(field_name, records)

            if merged.value and isinstance(merged.value, list) and len(reported_records) > 1:
                all_items = []
                for r in reported_records:
                    if isinstance(r.value, list):
                        all_items.extend(r.value)
                    elif r.value is not None:
                        all_items.append(r.value)
                if all_items:
                    deduped = _deduplicate_array_items(all_items)
                    merged.value = deduped
                    original_count = len(all_items)
                    if len(deduped) < original_count:
                        merged.notes = (
                            f"{merged.notes} | Deduplicated {original_count}->{len(deduped)} items"
                        )
                    else:
                        merged.notes = (
                            f"{merged.notes} | Combined {len(deduped)} items from {len(reported_records)} chunks"
                        )

            merged_fields[field_name] = merged.to_dict()

    all_warnings = []
    for r in chunk_results:
        all_warnings.extend(r.get("validation_warnings", []))

    chunk_ids = [r.get("chunk_id", "?") for r in chunk_results]
    overlap_dedup_count = sum(
        1 for fn, fr in merged_fields.items()
        if isinstance(fr, dict) and (
            "Deduplicated" in fr.get("notes", "")
            or "Combined" in fr.get("notes", "")
        )
    )

    return {
        "dimension": dimension,
        "fields": merged_fields,
        "validation_warnings": list(set(all_warnings)),
        "merge_notes": (
            f"Merged from {len(chunk_results)} chunks: {chunk_ids}"
            + (f" ({overlap_dedup_count} fields deduplicated)" if overlap_dedup_count else "")
        ),
        "chunk_count": len(chunk_results),
        "source_chunks": chunk_ids,
        "field_source_map": field_source_map,
    }


def _merge_with_dedup(
    field_name: str,
    reported_records: list[DataRecord],
    all_records: list[DataRecord],
) -> DataRecord:
    """Merge multiple REPORTED records, detecting overlap duplicates.

    When the same value appears in multiple chunks due to overlap, keep only
    one copy but preserve all source section associations.
    """
    unique_values: dict[str, DataRecord] = {}
    for r in reported_records:
        val_key = json.dumps(r.value, sort_keys=True, ensure_ascii=False, default=str)
        if val_key not in unique_values:
            unique_values[val_key] = r

    if len(unique_values) == 1:
        winner = list(unique_values.values())[0]
        winner.notes = (
            f"Same value found in {len(reported_records)} chunks (overlap dedup). "
            f"Keeping first occurrence."
        )
        return winner

    return merge_chunk_results(field_name, all_records)


def run_science_extraction_v2(
    document_id: str,
    mineru_output: str,
    output_dir: str,
    config: dict,
    use_cache: bool = False,
    prompt_config_path: Optional[str] = None,
    extraction_mode: str = "adaptive",
    doc_type: str = "paper",
    **kwargs,
) -> dict:
    """V2 extraction entry point with adaptive section-aware chunking.

    Args:
        document_id: Document identifier
        mineru_output: Path to MinerU output directory
        output_dir: Output directory for extraction results
        config: Pipeline configuration dict
        use_cache: Whether to use cached results if available
        prompt_config_path: Path to prompt configuration YAML
        extraction_mode: "adaptive" (auto full_text/chunked), "full_text", or "selective"
        doc_type: "paper" or "patent" — affects semantic boundary detection
    """

    if extraction_mode not in ("adaptive", "selective", "full_text"):
        logger.warning(
            "Invalid extraction_mode '%s', defaulting to 'adaptive'",
            extraction_mode
        )
        extraction_mode = "adaptive"

    logger.info(
        "[%s] V2 extraction starting in '%s' mode",
        document_id, extraction_mode
    )

    cache_dir = Path(output_dir) / document_id
    if use_cache and cache_dir.exists():
        cached_files = list(cache_dir.glob("*_v2_extracted.json"))
        version_file = cache_dir / ".prompt_version"
        prompt_version_ok = False
        if version_file.exists() and prompt_config_path:
            import hashlib
            with open(prompt_config_path, "rb") as pf:
                current_hash = hashlib.sha256(pf.read()).hexdigest()[:16]
            stored_hash = version_file.read_text().strip()
            prompt_version_ok = current_hash == stored_hash
        elif not prompt_config_path:
            prompt_version_ok = True

        if len(cached_files) >= len(ALL_DIMENSIONS) and prompt_version_ok:
            logger.info("[%s] Using cached V2 extraction (%d files)", document_id, len(cached_files))
            cached_data = {}
            for f in cached_files:
                dim_name = f.stem.replace("_v2_extracted", "")
                with open(f, "r", encoding="utf-8") as fh:
                    cached_data[dim_name] = json.load(fh)
            return {
                "document_id": document_id,
                "extraction_output_path": str(cache_dir),
                "extraction_status": "PASS",
                "extraction_source": "cache",
                "extraction_version": "v2",
                "dimensions_extracted": list(cached_data.keys()),
            }

    auto_dir = _find_mineru_auto_dir(mineru_output, document_id)
    if auto_dir is None:
        return {
            "document_id": document_id,
            "extraction_output_path": str(cache_dir),
            "extraction_status": "FAILED",
            "error": f"MinerU output not found for '{document_id}'",
            "extraction_version": "v2",
        }

    content_list_path = auto_dir / "main_content_list.json"
    if not content_list_path.exists():
        content_files = list(auto_dir.glob("*content_list.json"))
        if not content_files:
            return {
                "document_id": document_id,
                "extraction_output_path": str(cache_dir),
                "extraction_status": "FAILED",
                "error": f"No content_list.json in {auto_dir}",
                "extraction_version": "v2",
            }
        content_list_path = content_files[0]

    try:
        stage_cfg = config.get("stages", {}).get("science_extraction_v2", {})
        max_chunk_chars = stage_cfg.get("max_chunk_chars", 8000)
        overlap_paragraphs = stage_cfg.get("overlap_paragraphs", 1)
        llm_cfg = config.get("llm", {})
        llm_max_tokens = llm_cfg.get("max_tokens", 4096)
        model_context_limit = llm_cfg.get("model_context_limit", 64000)
        system_prompt_reserve = llm_cfg.get("system_prompt_reserve_tokens", 1000)
        output_reserve = llm_cfg.get("output_reserve_tokens", llm_max_tokens)
        content_budget_tokens = model_context_limit - system_prompt_reserve - output_reserve
        token_budget = TokenBudget(
            max_input_tokens=model_context_limit - output_reserve,
            max_output_tokens=output_reserve,
            system_prompt_tokens=system_prompt_reserve,
            user_prompt_overhead_tokens=0,
        )
        logger.info(
            "Heuristic token budget: model_context_limit=%d, output_reserve=%d, "
            "system_prompt_reserve=%d, content_budget=%d est. tokens (~%d chars). "
            "NOTE: est. tokens use chars/3.5 heuristic; real tokenizer count may differ ±25%%.",
            model_context_limit, output_reserve, system_prompt_reserve,
            content_budget_tokens, int(content_budget_tokens * 3.5),
        )
        loader = SectionAwareContentLoader(
            content_list_path,
            max_chunk_chars=max_chunk_chars,
            token_budget=token_budget,
            document_id=document_id,
            overlap_paragraphs=overlap_paragraphs,
        )
        loader.load()
    except Exception as e:
        return {
            "document_id": document_id,
            "extraction_output_path": str(cache_dir),
            "extraction_status": "FAILED",
            "error": f"Content loader failed: {e}",
            "extraction_version": "v2",
        }

    try:
        prompt_config = load_prompt_config(
            config_path=prompt_config_path,
            config_name="science_extraction_v2",
        )
    except FileNotFoundError as e:
        return {
            "document_id": document_id,
            "extraction_output_path": str(cache_dir),
            "extraction_status": "FAILED",
            "error": f"Prompt config not found: {e}",
            "extraction_version": "v2",
        }

    try:
        llm = _create_llm_service(config)
    except Exception as e:
        return {
            "document_id": document_id,
            "extraction_output_path": str(cache_dir),
            "extraction_status": "FAILED",
            "error": f"LLM service init failed: {e}",
            "extraction_version": "v2",
        }

    cache_dir.mkdir(parents=True, exist_ok=True)

    extraction_input = loader.to_extraction_input()
    input_meta_file = cache_dir / f"{document_id}_extraction_input.json"
    with open(input_meta_file, "w", encoding="utf-8") as f:
        json.dump(extraction_input, f, indent=2, ensure_ascii=False)

    document_context = (
        f"Document: {document_id}, "
        f"Total sections: {extraction_input['total_sections']}, "
        f"Total chars: {extraction_input['total_chars']}, "
        f"Sections: {', '.join(s['title'] for s in extraction_input['sections'][:10])}"
    )

    results = {}
    success_count = 0
    total_chunks = 0
    total_llm_calls = 0
    dimension_modes = {}
    token_budget_exceeded_count = 0

    for dim in ALL_DIMENSIONS:
        logger.info("[%s] V2 extracting dimension: %s (mode=%s, doc_type=%s)",
                    document_id, dim, extraction_mode, doc_type)
        try:
            if extraction_mode == "adaptive":
                chunks = loader.build_adaptive_chunks(dim, doc_type=doc_type)
            else:
                chunks = loader.build_dimension_chunks(dim, mode=extraction_mode)
        except ChunkBudgetExceeded as e:
            logger.error("[%s] %s: %s", document_id, dim, e)
            results[dim] = {
                "dimension": dim,
                "fields": {},
                "validation_warnings": [str(e)],
                "chunk_count": 0,
                "error": "CHUNK_BUDGET_EXCEEDED",
            }
            continue
        chunk_results = []

        if chunks:
            dimension_modes[dim] = chunks[0].input_mode
        else:
            dimension_modes[dim] = "empty"

        for chunk in chunks:
            total_chunks += 1
            section_titles = ", ".join(chunk.sections[:3])
            logger.info(
                "[%s] %s chunk %s: %d chars, ~%d tokens, sections=[%s]",
                document_id, dim, chunk.chunk_id,
                len(chunk.content), estimate_tokens(chunk.content), section_titles,
            )

            result = _extract_with_prompt(
                llm_service=llm,
                prompt_config=prompt_config,
                dimension=dim,
                chunk_content=chunk.content,
                document_context=document_context,
                section_title=section_titles,
                max_retries=prompt_config.max_retries,
                token_budget=token_budget,
            )
            total_llm_calls += 1

            if result.get("token_budget_exceeded"):
                token_budget_exceeded_count += 1

            chunk_file = cache_dir / f"{dim}_{chunk.chunk_id}_raw.json"
            with open(chunk_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)

            if result["success"]:
                normalized = _normalize_dimension_result(dim, result["data"])
                normalized["chunk_id"] = chunk.chunk_id
                normalized["chunk_sections"] = chunk.sections
                normalized["chunk_char_range"] = [chunk.char_offset_start, chunk.char_offset_end]
                normalized["chunk_page_range"] = list(chunk.page_range)
                chunk_results.append(normalized)

        if chunk_results:
            merged = _merge_dimension_results(dim, chunk_results)
            results[dim] = merged

            if merged.get("validation_warnings"):
                logger.warning(
                    "[%s] %s: %d validation warnings",
                    document_id, dim, len(merged["validation_warnings"]),
                )

            dim_success = True
            for field_data in merged.get("fields", {}).values():
                if isinstance(field_data, dict) and field_data.get("status") == "REPORTED":
                    break
            else:
                all_not_extracted = all(
                    isinstance(fd, dict) and fd.get("status") in ("NOT_EXTRACTED", "NOT_REPORTED")
                    for fd in merged.get("fields", {}).values()
                )
                if all_not_extracted:
                    dim_success = False

            if dim_success:
                success_count += 1

            data_file = cache_dir / f"{dim}_v2_extracted.json"
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2, ensure_ascii=False, default=str)
        else:
            results[dim] = {
                "dimension": dim,
                "fields": {},
                "validation_warnings": ["All chunks failed extraction"],
                "chunk_count": len(chunks),
            }

    summary = {
        "document_id": document_id,
        "extraction_version": "v2",
        "extraction_mode": extraction_mode,
        "prompt_version": prompt_config.prompt_version,
        "dimensions_total": len(ALL_DIMENSIONS),
        "dimensions_success": success_count,
        "dimensions_failed": len(ALL_DIMENSIONS) - success_count,
        "total_chunks_processed": total_chunks,
        "total_llm_calls": total_llm_calls,
        "content_stats": {
            "total_chars": extraction_input["total_chars"],
            "total_sections": extraction_input["total_sections"],
            "total_elements": extraction_input["total_elements"],
            "figures_and_tables": len(extraction_input.get("figures_and_tables", [])),
        },
        "timestamp": datetime.now().isoformat(),
    }
    summary_file = cache_dir / "extraction_v2_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    if prompt_config_path:
        import hashlib
        with open(prompt_config_path, "rb") as pf:
            current_hash = hashlib.sha256(pf.read()).hexdigest()[:16]
        (cache_dir / ".prompt_version").write_text(current_hash)

    status = (
        "PASS" if success_count == len(ALL_DIMENSIONS)
        else "PARTIAL" if success_count > 0
        else "FAILED"
    )

    return {
        "document_id": document_id,
        "extraction_mode": extraction_mode,
        "extraction_output_path": str(cache_dir),
        "extraction_status": status,
        "extraction_source": "llm_v2",
        "extraction_version": "v2",
        "dimensions_extracted": [d for d, r in results.items() if r.get("fields")],
        "dimensions_failed": [d for d, r in results.items() if not r.get("fields")],
        "success_count": success_count,
        "total_chunks": total_chunks,
        "total_llm_calls": total_llm_calls,
    }


def create_science_extraction_v2_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for V2 science extraction."""
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("science_extraction_v2", {})

    adapter = StageAdapter(
        stage_name="science_extraction_v2",
        version="2.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=["mineru_output_dir"],
        ),
        output_contract=DataContract(
            required_outputs=["extraction_output_path", "extraction_status"],
        ),
        dependencies=["document_ir"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 600),
    )

    mineru_output = paths.get("mineru_output", "")
    output_dir = paths.get("pipeline_runs", "") + "/extraction_v2"

    adapter.set_function(
        run_science_extraction_v2,
        mineru_output=mineru_output,
        output_dir=output_dir,
        config=config,
    )
    return adapter
