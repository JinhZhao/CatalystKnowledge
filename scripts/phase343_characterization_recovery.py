"""Phase 3.4.3 — Characterization Dimension Recovery Script.

Splits characterization into 3 sub-tasks:
A. Structural and Morphological (XRD, BET, TEM, SEM, particle size, morphology)
B. Electronic and Chemical (XPS, UV-vis, Raman, FTIR, oxidation state)
C. In-situ and Operando (in-situ, operando, active site identification)

Uses section-aware chunking and implements JSON recovery for incomplete responses.
"""

from __future__ import annotations

import json
import logging
import os
import re
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
OUTPUT_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3_4_3" / "f02" / "characterization_recovery"
PROMPT_CONFIG = PROJECT_ROOT / "config" / "prompts" / "science_extraction_v2.yaml"


def setup_api_credentials(model: str = "DeepSeek-Flash"):
    """Set DICP API credentials."""
    os.environ["LLM_API_KEY"] = "sk-S4l2Jm-es1eezvaEGTfDWQ"
    os.environ["LLM_API_BASE"] = "https://chemestack.dicp.ac.cn:8443/v1"
    os.environ["LLM_MODEL"] = model
    logger.info(f"API credentials configured: {model} @ chemestack.dicp.ac.cn:8443")


def safe_json_parse(response_text: str) -> dict | None:
    """Attempt to parse JSON with recovery for truncated responses."""
    if not response_text or not response_text.strip():
        return None
    
    # Try direct parse first
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    
    # Try to find and extract JSON object
    json_match = re.search(r'\{[\s\S]*\}', response_text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # Try to fix common truncation issues
    fixed = response_text.rstrip()
    if fixed.endswith(','):
        fixed = fixed[:-1] + '}'
    elif not fixed.endswith('}'):
        fixed += '}'
    
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


def extract_with_retry(
    llm_service,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 2,
    retry_delay: float = 5.0,
) -> dict:
    """Extract with retry logic and JSON recovery."""
    from catalyst_knowledge.core.llm_service import ChatMessage
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    
    for attempt in range(max_retries + 1):
        try:
            start_time = time.time()
            response = llm_service.chat(messages, response_format={"type": "json_object"})
            elapsed = time.time() - start_time
            
            parsed = safe_json_parse(response.content)
            
            if parsed is not None:
                return {
                    "success": True,
                    "data": parsed,
                    "attempts": attempt + 1,
                    "latency_seconds": round(elapsed, 2),
                    "tokens": response.usage.get("total_tokens", 0) if response.usage else 0,
                    "raw_response": response.content,
                    "parse_status": "SUCCESS",
                }
            else:
                logger.warning(f"JSON parse failed on attempt {attempt + 1}, retrying...")
                if attempt < max_retries:
                    time.sleep(retry_delay * (attempt + 1))
                
        except Exception as e:
            logger.error(f"LLM call failed on attempt {attempt + 1}: {e}")
            if attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
    
    return {
        "success": False,
        "data": None,
        "attempts": max_retries + 1,
        "error": "Max retries exceeded or persistent JSON parse failure",
        "parse_status": "FAILED",
    }


def create_characterization_prompts(subtask: str) -> tuple[str, str]:
    """Create specialized prompts for each characterization sub-task."""
    
    common_instructions = """
    ## CRITICAL RULES
    
    1. Extract SPECIFIC technique names (XRD, BET, TEM, XPS, UV-vis, etc.)
    2. Extract SPECIFIC numerical results with units (e.g., "S_BET = 4.6 m2/g", "particle size = 7.4 nm")
    3. For EVERY extracted field, provide:
       - value: specific finding
       - status: REPORTED | NOT_REPORTED | NOT_EXTRACTED
       - origin: ORIGINAL_EXPERIMENT | LITERATURE_REFERENCE | THEORETICAL_CALCULATION
       - source_quote: exact text from paper supporting this extraction
    
    4. Do NOT use 0, null, or empty arrays for missing data. Use status NOT_REPORTED instead.
    5. Distinguish this paper's original data from cited literature.
    """
    
    if subtask == "A":
        system_prompt = f"""You are a scientific data extraction specialist in catalysis research.
Your task is to extract STRUCTURAL AND MORPHOLOGICAL characterization data.
{common_instructions}

Focus on: XRD (crystal structure), BET (surface area, pore size), TEM/SEM (morphology, particle size), crystallinity."""
        
        user_template = """Extract structural and morphological characterization from the following paper section.

**Document**: {document_context}
**Section**: {section_title}

**Text to extract from**:
---
{chunk_content}
---

Return ONLY valid JSON:
{{
  "techniques_used": [
    {{
      "technique_name": "XRD|BET|TEM|SEM|other",
      "what_was_measured": "crystal structure|surface area|particle morphology|pore size|etc.",
      "key_result": "specific numerical result with units",
      "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
      "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
      "source_quote": "exact text with numbers"
    }}
  ],
  "morphology": {{
    "value": "specific morphological findings (e.g., 'BN nanosheets with Cu nanoparticles of 7.4-12.7 nm')",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "structure": {{
    "value": "crystallographic findings (e.g., 'hexagonal BN phase confirmed by XRD peaks at 26.6° and 41.7°')",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "surface_properties": {{
    "value": "BET surface area, pore size, pore volume with numbers",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "particle_size": {{
    "value": "particle size range with units (e.g., '7.4-12.7 nm')",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }}
}}"""
    
    elif subtask == "B":
        system_prompt = f"""You are a scientific data extraction specialist in catalysis research.
Your task is to extract ELECTRONIC AND CHEMICAL characterization data.
{common_instructions}

Focus on: XPS (oxidation state, binding energy), UV-vis/DRS (optical properties, LSPR), Raman, FTIR, electronic structure."""
        
        user_template = """Extract electronic and chemical characterization from the following paper section.

**Document**: {document_context}
**Section**: {section_title}

**Text to extract from**:
---
{chunk_content}
---

Return ONLY valid JSON:
{{
  "techniques_used": [
    {{
      "technique_name": "XPS|UV-vis|UV-vis DRS|Raman|FTIR|other",
      "what_was_measured": "oxidation state|binding energy|optical absorption|LSPR|vibrational modes|etc.",
      "key_result": "specific numerical result with units (e.g., 'Cu 2p3/2 at 932.5 eV')",
      "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
      "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
      "source_quote": "exact text with numbers"
    }}
  ],
  "electronic_properties": {{
    "value": "electronic structure findings (e.g., 'Cu 2p3/2 binding energy at 932.5 eV indicating Cu0/Cu+')",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "optical_properties": {{
    "value": "optical properties (e.g., 'LSPR absorption peak at 550-600 nm in UV-vis DRS')",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "oxidation_state": {{
    "value": "oxidation state information (e.g., 'Cu0 and Cu+ species coexist')",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "chemical_bonding": {{
    "value": "chemical bonding information from XPS/FTIR/Raman",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }}
}}"""
    
    else:  # subtask == "C"
        system_prompt = f"""You are a scientific data extraction specialist in catalysis research.
Your task is to extract IN-SITU AND OPERANDO characterization data.
{common_instructions}

Focus on: in-situ characterization, operando evidence, active site identification, structural evolution during reaction."""
        
        user_template = """Extract in-situ and operando characterization from the following paper section.

**Document**: {document_context}
**Section**: {section_title}

**Text to extract from**:
---
{chunk_content}
---

Return ONLY valid JSON:
{{
  "insitu_techniques": [
    {{
      "technique_name": "in-situ XRD|in-situ XPS|operando Raman|etc.",
      "conditions": "measurement conditions (temperature, gas, etc.)",
      "key_finding": "what was observed under reaction conditions",
      "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
      "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
      "source_quote": "exact text"
    }}
  ],
  "active_sites": {{
    "value": "description of proposed active sites with evidence",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "structural_evolution": {{
    "value": "how structure changes during reaction",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }},
  "operando_evidence": {{
    "value": "operando evidence for mechanism",
    "status": "REPORTED|NOT_REPORTED|NOT_EXTRACTED",
    "origin": "ORIGINAL_EXPERIMENT|LITERATURE_REFERENCE",
    "source_quote": "exact text"
  }}
}}"""
    
    return system_prompt, user_template


def run_characterization_recovery():
    """Main recovery loop for characterization dimension."""
    from catalyst_knowledge.pipeline.section_aware_extractor import SectionAwareContentLoader
    from catalyst_knowledge.core.llm_service import LLMService
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load content
    auto_dir = MINERU_OUTPUT / "main" / "auto"
    content_list_path = auto_dir / "main_content_list.json"
    
    if not content_list_path.exists():
        logger.error(f"Content list not found: {content_list_path}")
        return None
    
    loader = SectionAwareContentLoader(content_list_path)
    loader.load()
    logger.info(f"Loaded {len(loader.sections)} sections, {len(loader.full_text)} chars")
    
    document_context = f"Document: {DOCUMENT_ID}, Total sections: {len(loader.sections)}, Total chars: {len(loader.full_text)}"
    
    # Define sub-tasks
    subtasks = {
        "A": {"name": "Structural_Morphological", "model": "GLM-Pro"},
        "B": {"name": "Electronic_Chemical", "model": "DeepSeek-Flash"},
        "C": {"name": "InSitu_Operando", "model": "GLM-Pro"},
    }
    
    all_results = {}
    call_metadata = []
    call_index = 0
    
    for subtask_id, subtask_info in subtasks.items():
        logger.info("=" * 60)
        logger.info(f"SUB-TASK {subtask_id}: {subtask_info['name']}")
        logger.info(f"Model: {subtask_info['model']}")
        logger.info("=" * 60)
        
        setup_api_credentials(subtask_info['model'])
        llm = LLMService()
        
        system_prompt, user_template = create_characterization_prompts(subtask_id)
        
        # Get relevant sections for this sub-task
        relevant_sections = loader.get_relevant_sections("characterization")
        
        # Build chunks (limit to 2 chunks per sub-task to control length)
        chunks = []
        current_chunk = ""
        current_sections = []
        
        for section in relevant_sections[:6]:  # Limit to first 6 sections
            if len(current_chunk) + section.char_count > 8000 and current_chunk:
                chunks.append({
                    "content": current_chunk,
                    "sections": current_sections[:],
                })
                current_chunk = ""
                current_sections = []
            
            current_chunk += "\n\n" + section.text_content
            current_sections.append(section.section_id)
            
            if len(chunks) >= 2:  # Max 2 chunks per sub-task
                break
        
        if current_chunk and len(chunks) < 2:
            chunks.append({
                "content": current_chunk,
                "sections": current_sections,
            })
        
        logger.info(f"Created {len(chunks)} chunks for sub-task {subtask_id}")
        
        # Process each chunk
        subtask_results = []
        for chunk_idx, chunk in enumerate(chunks):
            call_index += 1
            chunk_id = f"char_{subtask_id}_chunk_{chunk_idx}"
            
            logger.info(f"  Call #{call_index}: {chunk_id} ({len(chunk['content'])} chars)")
            
            user_prompt = user_template.format(
                document_context=document_context,
                section_title=", ".join(chunk['sections'][:3]),
                chunk_content=chunk['content'][:8000],  # Limit input length
            )
            
            result = extract_with_retry(
                llm_service=llm,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_retries=2,
                retry_delay=5.0,
            )
            
            meta = {
                "call_index": call_index,
                "subtask": subtask_id,
                "subtask_name": subtask_info['name'],
                "chunk_id": chunk_id,
                "model_used": subtask_info['model'],
                "chunk_char_count": len(chunk['content']),
                "status": "SUCCESS" if result['success'] else "FAILED",
                "parse_status": result.get('parse_status', 'UNKNOWN'),
                "attempts": result.get('attempts', 0),
                "latency_seconds": result.get('latency_seconds', 0),
                "tokens": result.get('tokens', 0),
                "timestamp": datetime.now().isoformat(),
            }
            call_metadata.append(meta)
            
            if result['success']:
                logger.info(f"    -> SUCCESS: {result['tokens']} tokens, {result['latency_seconds']}s")
                subtask_results.append(result['data'])
                
                # Save raw response
                raw_file = OUTPUT_DIR / f"{chunk_id}_raw.json"
                with open(raw_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            else:
                logger.warning(f"    -> FAILED: {result.get('error', 'Unknown error')}")
        
        all_results[subtask_id] = subtask_results
        logger.info(f"Sub-task {subtask_id}: {len(subtask_results)}/{len(chunks)} chunks successful")
    
    # Merge results
    merged = merge_characterization_results(all_results)
    
    # Save merged result
    merged_file = OUTPUT_DIR / "characterization_v2_extracted.json"
    with open(merged_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    
    # Save call metadata
    meta_file = OUTPUT_DIR / "characterization_call_metadata.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(call_metadata, f, indent=2, ensure_ascii=False)
    
    logger.info("=" * 60)
    logger.info("CHARACTERIZATION RECOVERY COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total calls: {call_index}")
    logger.info(f"Successful: {sum(1 for m in call_metadata if m['status'] == 'SUCCESS')}")
    logger.info(f"Failed: {sum(1 for m in call_metadata if m['status'] == 'FAILED')}")
    logger.info(f"Merged result: {merged_file.name}")
    
    return merged


def merge_characterization_results(subtask_results: dict) -> dict:
    """Merge results from 3 sub-tasks into unified characterization schema."""
    merged = {
        "dimension": "characterization",
        "fields": {},
        "validation_warnings": [],
        "merge_notes": f"Merged from {len(subtask_results)} sub-tsks",
        "subtask_sources": {
            "A": "Structural_Morphological",
            "B": "Electronic_Chemical",
            "C": "InSitu_Operando",
        },
    }
    
    # Merge techniques_used arrays
    all_techniques = []
    for subtask_id, results in subtask_results.items():
        for result in results:
            techniques = result.get("techniques_used", [])
            if isinstance(techniques, list):
                all_techniques.extend(techniques)
    
    if all_techniques:
        merged["fields"]["techniques_used"] = {
            "value": all_techniques,
            "status": "REPORTED",
            "origin": "ORIGINAL_EXPERIMENT",
            "source_quote": f"Merged from {len(all_techniques)} technique entries",
        }
    
    # Merge other fields (take first REPORTED value)
    field_names = [
        "morphology", "structure", "surface_properties", "particle_size",
        "electronic_properties", "optical_properties", "oxidation_state", "chemical_bonding",
        "active_sites", "structural_evolution", "operando_evidence",
    ]
    
    for field_name in field_names:
        for subtask_id, results in subtask_results.items():
            for result in results:
                if field_name in result:
                    field_data = result[field_name]
                    if isinstance(field_data, dict) and field_data.get("status") == "REPORTED":
                        merged["fields"][field_name] = field_data
                        break
            if field_name in merged["fields"]:
                break
    
    return merged


if __name__ == "__main__":
    result = run_characterization_recovery()
    if result is None:
        sys.exit(1)
