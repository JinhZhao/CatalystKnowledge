"""Tests for pipeline/__init__.py — import smoke test."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def test_pipeline_package_importable():
    from catalyst_knowledge.pipeline import __version__
    assert __version__ == "1.0.0"
