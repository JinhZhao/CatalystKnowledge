"""Config-driven prompt loader for science extraction V2.

Loads prompt templates from YAML configuration files instead of
hardcoded Python strings. Supports common instruction injection
and per-dimension template rendering.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "config" / "prompts"


class PromptConfig:
    """Loaded prompt configuration with template rendering."""

    def __init__(self, config: dict):
        self._config = config
        self.schema_version = config.get("schema_version", "unknown")
        self.prompt_version = config.get("prompt_version", "unknown")
        self.common_instructions = config.get("common_instructions", "")
        self.dimensions = config.get("dimensions", {})
        self.extraction_config = config.get("extraction_config", {})

    def get_dimension_config(self, dimension: str) -> Optional[dict]:
        return self.dimensions.get(dimension)

    def render_prompt(
        self,
        dimension: str,
        chunk_content: str,
        document_context: str = "",
        section_title: str = "",
        extra_vars: Optional[dict] = None,
    ) -> tuple[str, str]:
        dim_cfg = self.get_dimension_config(dimension)
        if dim_cfg is None:
            raise ValueError(f"Unknown dimension: {dimension}")

        system_prompt = dim_cfg.get("system_prompt", "")
        user_template = dim_cfg.get("user_template", "")

        system_prompt = system_prompt.replace("{common_instructions}", self.common_instructions)

        template_vars = {
            "chunk_content": chunk_content,
            "document_context": document_context or "Not provided",
            "section_title": section_title or "Not specified",
            "common_instructions": self.common_instructions,
        }
        if extra_vars:
            template_vars.update(extra_vars)

        user_prompt = user_template
        for key, value in template_vars.items():
            user_prompt = user_prompt.replace(f"{{{key}}}", str(value))

        return system_prompt, user_prompt

    @property
    def max_content_chars(self) -> int:
        return self.extraction_config.get("max_content_chars_per_chunk", 8000)

    @property
    def temperature(self) -> float:
        return self.extraction_config.get("temperature", 0.1)

    @property
    def max_tokens(self) -> int:
        return self.extraction_config.get("max_tokens", 4096)

    @property
    def max_retries(self) -> int:
        return self.extraction_config.get("max_retries", 2)


def load_prompt_config(
    config_path: Optional[Path | str] = None,
    config_name: str = "science_extraction_v2",
) -> PromptConfig:
    if config_path is None:
        config_path = _DEFAULT_PROMPT_PATH / f"{config_name}.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Prompt config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info("Loaded prompt config: %s v%s from %s",
                config.get("schema_version", "?"),
                config.get("prompt_version", "?"),
                config_path.name)
    return PromptConfig(config)
