"""Prompt loader — single source of truth for all LLM prompts.

Loads prompt files from prompts/ directory with YAML frontmatter stripping.
Usage:
    from catalyst_knowledge.prompts.loader import load_prompt
    
    # Load by filename (without .md extension)
    system_prompt = load_prompt("kimi-web-search-system-prompt")
    
    # Load with version check (optional)
    prompt_text, metadata = load_prompt_with_metadata("catalystgpt-system-prompt")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Prompts directory (relative to this file's parent)
# loader.py → prompts/ → catalyst_knowledge/ → src/ → catalyst-knowledge/ → prompts/
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file by name (without .md extension).
    
    Strips YAML frontmatter and returns only the prompt content.
    
    Args:
        name: Prompt filename without .md extension
              (e.g., "kimi-web-search-system-prompt")
    
    Returns:
        Prompt text content (without frontmatter)
    
    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    prompt_path = PROMPTS_DIR / f"{name}.md"
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    
    content = prompt_path.read_text(encoding="utf-8")
    
    # Strip YAML frontmatter (everything between first two --- markers)
    parts = content.split("---", 2)
    if len(parts) >= 3:
        # parts[0] = empty or pre-frontmatter
        # parts[1] = YAML metadata
        # parts[2] = actual prompt content
        return parts[2].strip()
    
    # No frontmatter found, return as-is
    return content.strip()


def load_prompt_with_metadata(name: str) -> tuple[str, dict[str, Any]]:
    """Load prompt with its YAML frontmatter metadata.
    
    Args:
        name: Prompt filename without .md extension
    
    Returns:
        Tuple of (prompt_text, metadata_dict)
    
    Example metadata:
        {
            "name": "kimi-web-search-system-prompt",
            "version": "1.1.0",
            "description": "...",
            "last_modified": "2026-10-11",
            "category": "external_retrieval",
            "tier": "A",
            ...
        }
    """
    import yaml
    
    prompt_path = PROMPTS_DIR / f"{name}.md"
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    
    content = prompt_path.read_text(encoding="utf-8")
    
    # Parse YAML frontmatter
    parts = content.split("---", 2)
    if len(parts) >= 3:
        try:
            metadata = yaml.safe_load(parts[1])
            prompt_text = parts[2].strip()
            return prompt_text, metadata or {}
        except yaml.YAMLError as e:
            logger.warning("Failed to parse frontmatter for %s: %s", name, e)
            return content.strip(), {}
    
    # No frontmatter
    return content.strip(), {}


def list_available_prompts() -> list[dict[str, str]]:
    """List all available prompt files with their metadata.
    
    Returns:
        List of dicts with keys: name, version, description, category
    """
    if not PROMPTS_DIR.exists():
        return []
    
    prompts = []
    for md_file in sorted(PROMPTS_DIR.glob("*.md")):
        if md_file.name == "README.md":
            continue
        
        try:
            _, metadata = load_prompt_with_metadata(md_file.stem)
            prompts.append({
                "name": md_file.stem,
                "version": metadata.get("version", "unknown"),
                "description": metadata.get("description", ""),
                "category": metadata.get("category", ""),
                "last_modified": metadata.get("last_modified", ""),
            })
        except Exception as e:
            logger.warning("Failed to load metadata for %s: %s", md_file.name, e)
    
    return prompts
