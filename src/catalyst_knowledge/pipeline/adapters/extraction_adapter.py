"""Adapter for six-dimension LLM extraction.

Uses LLMService from src/catalyst_knowledge/core/llm_service.py
with config-driven credentials (no hardcoded API keys).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..stage_adapter import DataContract, StageAdapter

logger = logging.getLogger(__name__)

DIMENSION_PROMPTS = {
    "catalyst_design": """Extract catalyst design information from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "catalyst_system": "full catalyst system description",
  "catalyst_type": "type of catalyst",
  "active_component": "active catalytic component",
  "support": "support material",
  "synthesis_method": "synthesis method",
  "reaction_type": "target reaction type",
  "design_rationale": "design rationale if mentioned"
}

Paper excerpt:
{content}
""",
    "characterization": """Extract characterization results from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "techniques_used": ["list", "of", "techniques"],
  "key_findings": ["list", "of", "key", "findings"],
  "in_situ_evidence": "in-situ characterization evidence or null",
  "morphological_evidence": "morphology description",
  "electronic_evidence": "electronic structure description"
}

Paper excerpt:
{content}
""",
    "performance": """Extract performance metrics from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "key_metrics": [
    {
      "metric_name": "metric name",
      "value": "numeric value with unit",
      "conditions": "measurement conditions"
    }
  ],
  "key_claim": "main performance claim",
  "benchmark_comparison": "comparison to benchmarks or empty string",
  "reaction_conditions": "reaction conditions",
  "experiment_matrix": []
}

Paper excerpt:
{content}
""",
    "mechanism": """Extract mechanism information from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "proposed_pathway": "proposed reaction pathway",
  "rate_determining_step": "rate determining step or null",
  "intermediates": ["list", "of", "intermediates"],
  "computational_support": "computational evidence or null",
  "experimental_support": "experimental evidence or null"
}

Paper excerpt:
{content}
""",
    "structure_activity": """Extract structure-activity relationship from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "descriptor": "structure descriptor",
  "relationship_type": "type of relationship",
  "evidence_strength": "strong/moderate/weak",
  "data_points": 0
}

Paper excerpt:
{content}
""",
    "reliability": """Extract reliability and stability data from the following paper excerpt.
Return ONLY valid JSON with this exact structure:
{
  "time_on_stream": 0,
  "time_on_stream_note": "description of stability test conditions",
  "cycle_count": 0,
  "mass_transfer_verification": "mass transfer verification method or null",
  "reproducibility": "reproducibility evidence or null",
  "deactivation_observed": "deactivation description or null"
}

Paper excerpt:
{content}
""",
}

ALL_DIMENSIONS = list(DIMENSION_PROMPTS.keys())


def _load_content_list(mineru_auto_dir: Path) -> str:
    """Load text content from a MinerU content_list.json file."""
    content_files = list(mineru_auto_dir.glob("*content_list.json"))
    if not content_files:
        raise FileNotFoundError(f"No content_list.json in {mineru_auto_dir}")

    with open(content_files[0], "r", encoding="utf-8") as f:
        content_list = json.load(f)

    text_parts = []
    for item in content_list:
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    return "\n".join(text_parts)


def _find_mineru_auto_dir(mineru_output: str, document_id: str) -> Optional[Path]:
    """Find the MinerU auto/ directory for a document."""
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


def _extract_single_dimension(
    llm_service,
    dimension: str,
    content: str,
    max_retries: int = 2,
) -> dict:
    """Extract a single dimension using LLM."""
    from catalyst_knowledge.core.llm_service import ChatMessage

    prompt_template = DIMENSION_PROMPTS.get(dimension)
    if not prompt_template:
        return {"success": False, "data": None, "error": f"Unknown dimension: {dimension}"}

    original_length = len(content)
    content_truncated = content[:6000] if len(content) > 6000 else content
    truncated_length = len(content_truncated)
    truncation_ratio = (original_length - truncated_length) / original_length if original_length > 0 else 0
    
    if truncation_ratio > 0:
        logger.critical(
            "V1 DEPRECATED: Truncation %d->%d chars (%.1f%% lost). Use V2 adapter with extraction_mode='full_text'.",
            original_length, truncated_length, truncation_ratio * 100
        )
    
    prompt = prompt_template.replace("{content}", content_truncated)
    messages = [ChatMessage(role="user", content=prompt)]

    for attempt in range(max_retries + 1):
        try:
            response = llm_service.chat(messages, response_format={"type": "json_object"})
            data = json.loads(response.content)
            result = {"success": True, "data": data, "error": None, "attempts": attempt + 1}
            if truncation_ratio > 0:
                result["truncation_warning"] = {
                    "original_length": original_length,
                    "truncated_length": truncated_length,
                    "truncation_ratio": truncation_ratio,
                    "adapter_version": "v1_deprecated",
                    "recommendation": "Use V2 adapter with extraction_mode='full_text'"
                }
            return result
        except json.JSONDecodeError as e:
            if attempt >= max_retries:
                return {"success": False, "data": None, "error": f"JSON parse error: {e}", "attempts": attempt + 1}
        except Exception as e:
            if attempt >= max_retries:
                return {"success": False, "data": None, "error": f"LLM call failed: {e}", "attempts": attempt + 1}

    return {"success": False, "data": None, "error": "max retries exceeded"}


def _create_llm_service(config: dict):
    """Create LLMService from pipeline config (no hardcoded credentials)."""
    from catalyst_knowledge.core.llm_service import LLMService

    llm_cfg = config.get("llm", {})
    api_key_env = llm_cfg.get("api_key_env", "LLM_API_KEY")
    api_base_env = llm_cfg.get("api_base_env", "LLM_API_BASE")
    model_env = llm_cfg.get("model_env", "LLM_MODEL")

    api_key = os.environ.get(api_key_env, "")
    api_base = os.environ.get(api_base_env, llm_cfg.get("default_api_base", ""))
    model = os.environ.get(model_env, llm_cfg.get("default_model", "deepseek-chat"))

    if not api_key:
        logger.warning("API key env var %s not set; LLM calls will fail", api_key_env)
    if not api_base:
        logger.warning("API base env var %s not set and no default", api_base_env)

    return LLMService(api_key=api_key, api_base=api_base, model=model)


def run_extraction(
    document_id: str,
    mineru_output: str,
    output_dir: str,
    config: dict,
    use_cache: bool = True,
    **kwargs,
) -> dict:
    """Pipeline-callable six-dimension extraction entry point.

    Uses LLMService with config-driven credentials.
    If use_cache=True and cached output exists, returns cached data without LLM call.
    """
    cache_dir = Path(output_dir) / document_id
    if use_cache and cache_dir.exists():
        cached_files = list(cache_dir.glob("*_extracted.json"))
        if len(cached_files) >= len(ALL_DIMENSIONS):
            logger.info("[%s] Using cached extraction output (%d files)", document_id, len(cached_files))
            cached_data = {}
            for f in cached_files:
                dim_name = f.stem.replace("_extracted", "")
                with open(f, "r", encoding="utf-8") as fh:
                    cached_data[dim_name] = json.load(fh)
            return {
                "document_id": document_id,
                "extraction_output_path": str(cache_dir),
                "extraction_status": "PASS",
                "extraction_source": "cache",
                "dimensions_extracted": list(cached_data.keys()),
            }

    auto_dir = _find_mineru_auto_dir(mineru_output, document_id)
    if auto_dir is None:
        return {
            "document_id": document_id,
            "extraction_status": "FAILED",
            "error": f"MinerU output not found for '{document_id}'",
        }

    try:
        content = _load_content_list(auto_dir)
    except FileNotFoundError as e:
        return {
            "document_id": document_id,
            "extraction_status": "FAILED",
            "error": str(e),
        }

    if not content.strip():
        return {
            "document_id": document_id,
            "extraction_status": "FAILED",
            "error": "Empty document content",
        }

    try:
        llm = _create_llm_service(config)
    except Exception as e:
        return {
            "document_id": document_id,
            "extraction_status": "FAILED",
            "error": f"LLM service init failed: {e}",
        }

    cache_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    success_count = 0

    for dim in ALL_DIMENSIONS:
        logger.info("[%s] Extracting dimension: %s", document_id, dim)
        result = _extract_single_dimension(llm, dim, content)
        results[dim] = result

        raw_file = cache_dir / f"{dim}_raw_response.txt"
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(result.get("raw_response", "") or "")

        if result["success"]:
            success_count += 1
            data_file = cache_dir / f"{dim}_extracted.json"
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(result["data"], f, indent=2, ensure_ascii=False)

    summary = {
        "document_id": document_id,
        "dimensions_total": len(ALL_DIMENSIONS),
        "dimensions_success": success_count,
        "dimensions_failed": len(ALL_DIMENSIONS) - success_count,
        "timestamp": datetime.now().isoformat(),
    }
    summary_file = cache_dir / "extraction_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    status = "PASS" if success_count == len(ALL_DIMENSIONS) else "PARTIAL" if success_count > 0 else "FAILED"

    if status == "FAILED":
        raise RuntimeError(
            f"All {len(ALL_DIMENSIONS)} extraction dimensions failed for document '{document_id}'. "
            f"Success count: {success_count}/{len(ALL_DIMENSIONS)}. "
            f"Check LLM credentials and API connectivity."
        )

    return {
        "document_id": document_id,
        "extraction_output_path": str(cache_dir),
        "extraction_status": status,
        "extraction_source": "llm",
        "dimensions_extracted": [d for d, r in results.items() if r["success"]],
        "dimensions_failed": [d for d, r in results.items() if not r["success"]],
        "success_count": success_count,
    }


def create_extraction_adapter(config: dict) -> StageAdapter:
    """Create a StageAdapter for six-dimension LLM extraction."""
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("six_dimension_extraction", {})

    adapter = StageAdapter(
        stage_name="six_dimension_extraction",
        version="3.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=["mineru_output_dir"],
        ),
        output_contract=DataContract(
            required_outputs=["extraction_output_path", "extraction_status"],
        ),
        dependencies=["document_ir"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 300),
    )

    mineru_output = paths.get("mineru_output", "")
    output_dir = paths.get("pipeline_runs", "") + "/extraction"

    adapter.set_function(
        run_extraction,
        mineru_output=mineru_output,
        output_dir=output_dir,
        config=config,
    )
    return adapter
