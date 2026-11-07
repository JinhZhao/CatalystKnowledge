"""Phase 3.4.3 — Streamlined Recovery for Critical Missing Data.

Focuses on recovering:
1. Performance: reaction_conditions (failed in Phase 3.4.2)
2. Mechanism: proposed_pathway, intermediates, active_sites (partial data)

Uses simplified prompts and shorter chunks to avoid JSON truncation.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DOCUMENT_ID = "F02"
MINERU_OUTPUT = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3" / "f02_e2e" / "02_pdf_parse"
OUTPUT_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3_4_3" / "f02" / "critical_recovery"


def setup_api(model: str = "GLM-Flash"):
    os.environ["LLM_API_KEY"] = "sk-S4l2Jm-es1eezvaEGTfDWQ"
    os.environ["LLM_API_BASE"] = "https://chemestack.dicp.ac.cn:8443/v1"
    os.environ["LLM_MODEL"] = model


def extract_simple(llm, system_prompt: str, user_prompt: str) -> dict:
    from catalyst_knowledge.core.llm_service import ChatMessage
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    
    try:
        start = time.time()
        response = llm.chat(messages, response_format={"type": "json_object"})
        elapsed = time.time() - start
        
        data = json.loads(response.content)
        return {
            "success": True,
            "data": data,
            "latency": round(elapsed, 2),
            "tokens": response.usage.get("total_tokens", 0) if response.usage else 0,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "latency": 0,
            "tokens": 0,
        }


def recover_performance_conditions():
    """Recover performance reaction_conditions from the most relevant section."""
    from catalyst_knowledge.pipeline.section_aware_extractor import SectionAwareContentLoader
    from catalyst_knowledge.core.llm_service import LLMService
    
    logger.info("=== Recovering Performance Reaction Conditions ===")
    
    setup_api("GLM-Flash")
    llm = LLMService()
    
    # Load content
    content_list_path = MINERU_OUTPUT / "main" / "auto" / "main_content_list.json"
    loader = SectionAwareContentLoader(content_list_path)
    loader.load()
    
    # Find the section with reaction conditions (s06_2_3_catalyst_evaluation)
    target_section = None
    for section in loader.sections:
        if "catalyst evaluation" in section.title.lower() or "2.3" in section.title:
            target_section = section
            break
    
    if not target_section:
        logger.error("Target section not found")
        return None
    
    logger.info(f"Using section: {target_section.title} ({target_section.char_count} chars)")
    
    # Simplified prompt
    system_prompt = """You are a scientific data extraction specialist.
Extract catalytic reaction conditions from the paper text.
Return ONLY valid JSON with these fields:
{
  "temperature_range": "value with unit (e.g., '400-500°C')",
  "pressure": "value with unit (e.g., 'atmospheric' or '0.1 MPa')",
  "gas_composition": "feed gas ratio (e.g., 'C3H8:O2 = 2:1')",
  "flow_rate": "value with unit (e.g., '20 mL/min')",
  "light_source": "lamp type and power (e.g., '300 W Xe lamp')",
  "status": "REPORTED|NOT_REPORTED",
  "origin": "ORIGINAL_EXPERIMENT",
  "source_quote": "exact text from paper"
}"""
    
    user_prompt = f"""Extract reaction conditions from this paper section:

Document: {DOCUMENT_ID}
Section: {target_section.title}

Text:
---
{target_section.text_content[:4000]}
---

Return ONLY valid JSON."""
    
    result = extract_simple(llm, system_prompt, user_prompt)
    
    if result["success"]:
        logger.info(f"SUCCESS: {result['tokens']} tokens, {result['latency']}s")
        return result["data"]
    else:
        logger.error(f"FAILED: {result['error']}")
        return None


def recover_mechanism_key_fields():
    """Recover mechanism proposed_pathway and active_sites."""
    from catalyst_knowledge.pipeline.section_aware_extractor import SectionAwareContentLoader
    from catalyst_knowledge.core.llm_service import LLMService
    
    logger.info("=== Recovering Mechanism Key Fields ===")
    
    setup_api("GLM-Flash")
    llm = LLMService()
    
    # Load content
    content_list_path = MINERU_OUTPUT / "main" / "auto" / "main_content_list.json"
    loader = SectionAwareContentLoader(content_list_path)
    loader.load()
    
    # Find mechanism-related sections
    target_sections = []
    for section in loader.sections:
        if "results" in section.title.lower() or "mechanism" in section.title.lower():
            target_sections.append(section)
    
    if not target_sections:
        logger.error("No mechanism sections found")
        return None
    
    # Use the longest relevant section
    target_section = max(target_sections, key=lambda s: s.char_count)
    logger.info(f"Using section: {target_section.title} ({target_section.char_count} chars)")
    
    # Simplified prompt
    system_prompt = """You are a scientific data extraction specialist.
Extract reaction mechanism information from the paper text.
Return ONLY valid JSON:
{
  "proposed_pathway": {
    "value": "description of reaction pathway",
    "status": "REPORTED|NOT_REPORTED",
    "origin": "ORIGINAL_EXPERIMENT",
    "source_quote": "exact text"
  },
  "active_sites": {
    "value": "description of active sites",
    "status": "REPORTED|NOT_REPORTED",
    "origin": "ORIGINAL_EXPERIMENT",
    "source_quote": "exact text"
  },
  "role_of_light": {
    "value": "how light contributes to mechanism",
    "status": "REPORTED|NOT_REPORTED",
    "origin": "ORIGINAL_EXPERIMENT",
    "source_quote": "exact text"
  }
}"""
    
    user_prompt = f"""Extract mechanism information from this paper section:

Document: {DOCUMENT_ID}
Section: {target_section.title}

Text:
---
{target_section.text_content[:4000]}
---

Return ONLY valid JSON."""
    
    result = extract_simple(llm, system_prompt, user_prompt)
    
    if result["success"]:
        logger.info(f"SUCCESS: {result['tokens']} tokens, {result['latency']}s")
        return result["data"]
    else:
        logger.error(f"FAILED: {result['error']}")
        return None


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Recover performance conditions
    perf_data = recover_performance_conditions()
    if perf_data:
        with open(OUTPUT_DIR / "performance_conditions_recovered.json", "w", encoding="utf-8") as f:
            json.dump(perf_data, f, indent=2, ensure_ascii=False)
    
    # Recover mechanism fields
    mech_data = recover_mechanism_key_fields()
    if mech_data:
        with open(OUTPUT_DIR / "mechanism_key_fields_recovered.json", "w", encoding="utf-8") as f:
            json.dump(mech_data, f, indent=2, ensure_ascii=False)
    
    # Summary
    logger.info("=" * 60)
    logger.info("CRITICAL RECOVERY COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Performance conditions: {'RECOVERED' if perf_data else 'FAILED'}")
    logger.info(f"Mechanism key fields: {'RECOVERED' if mech_data else 'FAILED'}")
    
    return {
        "performance_conditions": perf_data,
        "mechanism_key_fields": mech_data,
    }


if __name__ == "__main__":
    result = main()
    if result is None:
        sys.exit(1)
