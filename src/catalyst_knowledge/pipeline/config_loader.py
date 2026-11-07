"""ConfigLoader — pipeline configuration loading, validation, and merging.

Supports:
- YAML config file loading
- Environment variable injection (API keys never stored in config)
- Schema/prompt version references
- Default config + partial override merging
- Configuration validation with clear error messages
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None
    logger.warning("PyYAML not installed; config loading will fail")


SENSITIVE_KEYS = {"api_key", "api_key_env", "secret", "password", "token"}

REQUIRED_SECTIONS = {"pipeline", "paths", "llm", "stages", "execution"}

DEFAULT_CONFIG: dict[str, Any] = {
    "pipeline": {
        "name": "catalyst-knowledge-pipeline",
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "prompt_version": "1.0.0",
    },
    "llm": {
        "api_key_env": "LLM_API_KEY",
        "api_base_env": "LLM_API_BASE",
        "model_env": "LLM_MODEL",
        "default_model": "deepseek-chat",
        "default_api_base": "https://api.deepseek.com/v1",
        "temperature": 0.1,
        "max_tokens": 4096,
        "timeout_seconds": 300,
        "max_retries": 2,
    },
    "execution": {
        "stop_on_failure": True,
        "dry_run": False,
        "resume": False,
        "log_level": "INFO",
        "idempotent": True,
    },
}


class ConfigValidationError(Exception):
    """Raised when config fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Config validation failed: {'; '.join(errors)}")


class ConfigLoader:
    """Load, validate, and merge pipeline configuration."""

    def __init__(self, config_path: Optional[Path | str] = None):
        self._config: dict[str, Any] = {}
        self._config_path: Optional[Path] = None
        self._config_hash: Optional[str] = None
        if config_path is not None:
            self.load(config_path)

    def load(self, config_path: Path | str) -> dict[str, Any]:
        """Load config from YAML file, merge with defaults, validate."""
        self._config_path = Path(config_path)
        if not self._config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self._config_path}")

        raw = self._load_yaml(self._config_path)
        self._config = self._merge_defaults(raw)
        self._config_hash = self._compute_hash()
        self._inject_env_vars()
        self.validate()
        logger.info("Config loaded from %s (hash=%s)", self._config_path, self._config_hash[:12])
        return self._config

    def load_from_dict(self, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Load config from a dictionary (for testing)."""
        self._config = self._merge_defaults(copy.deepcopy(config_dict))
        self._config_hash = self._compute_hash()
        self._inject_env_vars()
        self.validate()
        return self._config

    @property
    def config(self) -> dict[str, Any]:
        if not self._config:
            raise RuntimeError("No config loaded; call load() first")
        return self._config

    @property
    def config_hash(self) -> Optional[str]:
        return self._config_hash

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a nested config value by dot-separated path.

        Example: loader.get("llm.temperature") -> 0.1
        """
        keys = key_path.split(".")
        node = self.config
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def get_stage_config(self, stage_name: str) -> dict[str, Any]:
        """Get configuration for a specific pipeline stage."""
        stages = self.config.get("stages", {})
        if stage_name not in stages:
            return {"enabled": False, "skip_if_output_exists": False, "timeout_seconds": 300}
        return stages[stage_name]

    def get_path(self, path_key: str) -> Path:
        """Get a resolved path from config."""
        raw = self.get(f"paths.{path_key}")
        if raw is None:
            raise KeyError(f"Path key not found in config: paths.{path_key}")
        return Path(raw)

    def get_llm_config(self) -> dict[str, Any]:
        """Get LLM configuration with resolved credentials."""
        llm = dict(self.config.get("llm", {}))
        env_var = llm.get("api_key_env", "LLM_API_KEY")
        llm["api_key"] = os.environ.get(env_var, "")
        if not llm["api_key"]:
            logger.warning("LLM API key not set in env var %s", env_var)
        return llm

    def validate(self) -> list[str]:
        """Validate config structure. Returns list of errors (empty = valid)."""
        errors: list[str] = []

        for section in REQUIRED_SECTIONS:
            if section not in self._config:
                errors.append(f"Missing required section: {section}")

        pipeline = self._config.get("pipeline", {})
        for field in ("name", "version", "schema_version"):
            if field not in pipeline:
                errors.append(f"Missing pipeline.{field}")

        paths = self._config.get("paths", {})
        for field in ("project_root", "data_root", "manifest"):
            if field not in paths:
                errors.append(f"Missing paths.{field}")

        stages = self._config.get("stages", {})
        if not isinstance(stages, dict):
            errors.append("stages must be a dict")
        else:
            for name, cfg in stages.items():
                if not isinstance(cfg, dict):
                    errors.append(f"stages.{name} must be a dict")

        llm = self._config.get("llm", {})
        temp = llm.get("temperature")
        if temp is not None and not (0.0 <= float(temp) <= 2.0):
            errors.append(f"llm.temperature out of range [0,2]: {temp}")

        if errors:
            raise ConfigValidationError(errors)
        return errors

    def to_safe_dict(self) -> dict[str, Any]:
        """Return config with sensitive values masked (for logging)."""
        safe = copy.deepcopy(self._config)
        self._mask_sensitive(safe)
        return safe

    def to_log_string(self) -> str:
        """Return a log-safe string representation."""
        return json.dumps(self.to_safe_dict(), indent=2, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if yaml is None:
            raise ImportError("PyYAML is required to load config files")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Config file must contain a YAML mapping, got {type(data).__name__}")
        return data

    @staticmethod
    def _merge_defaults(raw: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(DEFAULT_CONFIG)
        ConfigLoader._deep_merge(merged, raw)
        return merged

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigLoader._deep_merge(base[key], value)
            else:
                base[key] = copy.deepcopy(value)

    def _inject_env_vars(self) -> None:
        """Resolve environment variable references in LLM config."""
        llm = self._config.get("llm", {})
        env_var = llm.get("api_key_env", "LLM_API_KEY")
        api_key = os.environ.get(env_var, "")
        if api_key:
            llm["_api_key_resolved"] = True
        else:
            llm["_api_key_resolved"] = False

        base_env = llm.get("api_base_env", "LLM_API_BASE")
        base_val = os.environ.get(base_env, "")
        if base_val:
            llm["api_base"] = base_val

        model_env = llm.get("model_env", "LLM_MODEL")
        model_val = os.environ.get(model_env, "")
        if model_val:
            llm["model"] = model_val

    def _compute_hash(self) -> str:
        safe = self.to_safe_dict()
        json_str = json.dumps(safe, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    @staticmethod
    def _mask_sensitive(obj: Any) -> None:
        if isinstance(obj, dict):
            for key in list(obj.keys()):
                if key.lower() in SENSITIVE_KEYS or key.startswith("_"):
                    obj[key] = "***MASKED***"
                elif isinstance(obj[key], dict):
                    ConfigLoader._mask_sensitive(obj[key])
            if "_api_key_resolved" in obj:
                obj["_api_key_resolved"] = "***MASKED***"
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    ConfigLoader._mask_sensitive(item)
