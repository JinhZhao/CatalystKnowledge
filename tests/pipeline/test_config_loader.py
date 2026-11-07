"""Tests for pipeline/config_loader.py."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from catalyst_knowledge.pipeline.config_loader import (
    ConfigLoader,
    ConfigValidationError,
    DEFAULT_CONFIG,
)


MINIMAL_VALID_CONFIG = {
    "pipeline": {
        "name": "test-pipeline",
        "version": "1.0.0",
        "schema_version": "1.0.0",
    },
    "paths": {
        "project_root": "/tmp/test",
        "data_root": "/tmp/test/data",
        "manifest": "/tmp/test/manifest.json",
    },
    "llm": {
        "api_key_env": "LLM_API_KEY",
        "default_model": "test-model",
    },
    "stages": {
        "test_stage": {
            "enabled": True,
            "timeout_seconds": 60,
        },
    },
    "execution": {
        "stop_on_failure": True,
        "dry_run": False,
    },
}


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary YAML config file."""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")
    path = tmp_path / "test_config.yaml"
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(MINIMAL_VALID_CONFIG, f)
    return path


class TestConfigLoaderInit:
    def test_create_without_config(self):
        loader = ConfigLoader()
        assert loader._config == {}
        assert loader._config_path is None

    def test_create_with_config_path(self, config_file):
        loader = ConfigLoader(config_file)
        assert loader.config is not None
        assert loader.config["pipeline"]["name"] == "test-pipeline"


class TestConfigLoaderLoad:
    def test_load_valid_yaml(self, config_file):
        loader = ConfigLoader()
        config = loader.load(config_file)
        assert config["pipeline"]["name"] == "test-pipeline"
        assert config["paths"]["project_root"] == "/tmp/test"

    def test_load_missing_file(self, tmp_path):
        loader = ConfigLoader()
        with pytest.raises(FileNotFoundError):
            loader.load(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml_content(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")
        path = tmp_path / "bad.yaml"
        with open(path, "w") as f:
            f.write("- just a list\n- not a dict\n")
        loader = ConfigLoader()
        with pytest.raises(ValueError, match="must contain a YAML mapping"):
            loader.load(path)

    def test_defaults_merged(self, config_file):
        loader = ConfigLoader(config_file)
        config = loader.config
        assert "temperature" in config["llm"]
        assert config["llm"]["temperature"] == 0.1

    def test_config_hash_computed(self, config_file):
        loader = ConfigLoader(config_file)
        assert loader.config_hash is not None
        assert len(loader.config_hash) == 64


class TestConfigLoaderValidation:
    def test_missing_pipeline_fields(self):
        loader = ConfigLoader()
        loader._config = {
            "pipeline": {},
            "paths": {"project_root": "/x", "data_root": "/y", "manifest": "/z"},
            "llm": {},
            "stages": {},
            "execution": {},
        }
        with pytest.raises(ConfigValidationError, match="pipeline"):
            loader.validate()

    def test_missing_paths_section(self):
        loader = ConfigLoader()
        bad = {"pipeline": {"name": "x", "version": "1", "schema_version": "1"},
               "llm": {}, "stages": {}, "execution": {}}
        with pytest.raises(ConfigValidationError, match="paths"):
            loader.load_from_dict(bad)

    def test_invalid_temperature(self):
        loader = ConfigLoader()
        bad = dict(MINIMAL_VALID_CONFIG)
        bad["llm"] = {"temperature": 5.0}
        with pytest.raises(ConfigValidationError, match="temperature"):
            loader.load_from_dict(bad)

    def test_valid_config_passes(self):
        loader = ConfigLoader()
        loader.load_from_dict(MINIMAL_VALID_CONFIG)
        assert loader.config is not None


class TestConfigLoaderGet:
    def test_get_nested_key(self, config_file):
        loader = ConfigLoader(config_file)
        assert loader.get("pipeline.name") == "test-pipeline"
        assert loader.get("llm.temperature") == 0.1

    def test_get_missing_key_returns_default(self, config_file):
        loader = ConfigLoader(config_file)
        assert loader.get("nonexistent.key", "fallback") == "fallback"

    def test_get_path(self, config_file):
        loader = ConfigLoader(config_file)
        p = loader.get_path("project_root")
        assert isinstance(p, Path)
        assert p == Path("/tmp/test")

    def test_get_path_missing_key(self, config_file):
        loader = ConfigLoader(config_file)
        with pytest.raises(KeyError, match="nonexistent"):
            loader.get_path("nonexistent")

    def test_get_stage_config(self, config_file):
        loader = ConfigLoader(config_file)
        sc = loader.get_stage_config("test_stage")
        assert sc["enabled"] is True
        assert sc["timeout_seconds"] == 60

    def test_get_stage_config_missing(self, config_file):
        loader = ConfigLoader(config_file)
        sc = loader.get_stage_config("nonexistent_stage")
        assert sc["enabled"] is False


class TestConfigLoaderEnvVars:
    def test_api_key_from_env(self, config_file, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key-12345")
        loader = ConfigLoader(config_file)
        llm = loader.get_llm_config()
        assert llm["api_key"] == "test-key-12345"

    def test_api_key_missing_env(self, config_file, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        loader = ConfigLoader(config_file)
        llm = loader.get_llm_config()
        assert llm["api_key"] == ""


class TestConfigLoaderSafeOutput:
    def test_to_safe_dict_masks_api_key(self, config_file, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "secret-key-999")
        loader = ConfigLoader(config_file)
        safe = loader.to_safe_dict()
        llm = safe.get("llm", {})
        if "api_key" in llm:
            assert llm["api_key"] == "***MASKED***"

    def test_to_log_string_no_plaintext_key(self, config_file, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "super-secret")
        loader = ConfigLoader(config_file)
        log_str = loader.to_log_string()
        assert "super-secret" not in log_str
