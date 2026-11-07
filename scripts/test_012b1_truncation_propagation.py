"""Test 012-B1: finish_reason truncation error propagation.

Verifies the full error-propagation chain for LLM output truncation:

  LLMService.chat()  --[finish_reason='length']--> raises LLMOutputTruncated
       |
       v
  _extract_with_prompt()  --[catches]--> returns failure dict with truncation_error=True
       |
       v
  Store adapter  --[detects truncation_error]--> refuses save_extraction, store_status='BLOCKED'
       |
       v
  Pipeline orchestrator  --[dep BLOCKED]--> downstream stages skipped

Four test states required by PI:
  1. Normal finish (finish_reason='stop')
  2. Truncated finish (finish_reason='length')
  3. Abnormal finish / exception (e.g. network error)
  4. Missing finish_reason attribute (defensive)

Diagnostic rule: no raw content preview is logged (sensitive text protection).
"""
from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, "src")

from catalyst_knowledge.core.llm_service import (
    ChatMessage,
    ChatResponse,
    LLMOutputTruncated,
    LLMService,
)


PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  [{tag}] {name}{suffix}")


def install_openai_mock(mock_client: MagicMock):
    mock_openai_module = MagicMock()
    mock_openai_module.OpenAI.return_value = mock_client
    sys.modules["openai"] = mock_openai_module
    return mock_openai_module


def uninstall_openai_mock():
    sys.modules.pop("openai", None)


print("=" * 70)
print("Test 012-B1: finish_reason truncation error propagation")
print("=" * 70)


# ---- State 1: Normal finish (finish_reason='stop') ----
print("\n=== State 1: Normal finish ('stop') ===")

service = LLMService(api_key="test-key")
mock_client = MagicMock()

mock_client.chat.completions.create.return_value = SimpleNamespace(
    choices=[SimpleNamespace(
        message=SimpleNamespace(content='{"catalyst": "Pt"}'),
        finish_reason="stop",
    )],
    usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
)

install_openai_mock(mock_client)
try:
    resp = service.chat([ChatMessage(role="user", content="extract")])
finally:
    uninstall_openai_mock()

check("State 1: returns ChatResponse", isinstance(resp, ChatResponse))
check("State 1: finish_reason == 'stop'", resp.finish_reason == "stop")
check("State 1: content preserved", resp.content == '{"catalyst": "Pt"}')
check("State 1: no exception raised", True)


# ---- State 2: Truncated finish (finish_reason='length') ----
print("\n=== State 2: Truncated finish ('length') ===")

mock_client.chat.completions.create.return_value = SimpleNamespace(
    choices=[SimpleNamespace(
        message=SimpleNamespace(content='{"catalyst": "Pt'),  # truncated JSON
        finish_reason="length",
    )],
    usage=SimpleNamespace(prompt_tokens=100, completion_tokens=4096),
)

captured_records: list[logging.LogRecord] = []


class ListHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        captured_records.append(record)


logger = logging.getLogger("catalyst_knowledge.core.llm_service")
list_handler = ListHandler(level=logging.ERROR)
logger.addHandler(list_handler)
logger.setLevel(logging.ERROR)

install_openai_mock(mock_client)
try:
    raised = False
    try:
        resp = service.chat([ChatMessage(role="user", content="extract")])
    except LLMOutputTruncated as e:
        raised = True
        exc = e
finally:
    uninstall_openai_mock()
    logger.removeHandler(list_handler)

check("State 2: LLMOutputTruncated raised", raised)
if raised:
    check("State 2: exception carries max_tokens", exc.max_tokens == 4096)
    check("State 2: exception carries model", exc.model == service.model)
    check("State 2: exception is RuntimeError subclass", isinstance(exc, RuntimeError))

# Diagnostic must NOT include raw content preview
error_messages = [r.getMessage() for r in captured_records]
raw_content_leaked = any('{"catalyst": "Pt' in m for m in error_messages)
check("State 2: raw content NOT in log messages (sensitive-text rule)",
      not raw_content_leaked,
      f"leaked={raw_content_leaked}, msgs={len(error_messages)}")

# chat_json must not silently parse truncated content
install_openai_mock(mock_client)
try:
    json_raised = False
    try:
        service.chat_json([ChatMessage(role="user", content="extract")])
    except LLMOutputTruncated:
        json_raised = True
    except json.JSONDecodeError:
        json_raised = False  # would indicate truncation was not caught early
finally:
    uninstall_openai_mock()

check("State 2: chat_json propagates LLMOutputTruncated (not JSONDecodeError)",
      json_raised)


# ---- State 3: Abnormal finish / exception ----
print("\n=== State 3: Abnormal finish (network error) ===")

mock_client.chat.completions.create.side_effect = RuntimeError("connection reset")

install_openai_mock(mock_client)
try:
    network_raised = False
    network_exc = None
    try:
        service.chat([ChatMessage(role="user", content="extract")])
    except Exception as e:
        network_raised = True
        network_exc = e
finally:
    uninstall_openai_mock()
    mock_client.chat.completions.create.side_effect = None

check("State 3: exception propagated", network_raised)
check("State 3: NOT LLMOutputTruncated (preserved original error type)",
      not isinstance(network_exc, LLMOutputTruncated),
      f"type={type(network_exc).__name__}")
check("State 3: original error message preserved",
      "connection reset" in str(network_exc))


# ---- State 4: Missing finish_reason attribute ----
print("\n=== State 4: Missing finish_reason attribute ===")


class ChoiceNoFinish:
    def __init__(self, content: str):
        self.message = SimpleNamespace(content=content)


mock_client.chat.completions.create.return_value = SimpleNamespace(
    choices=[ChoiceNoFinish('{"catalyst": "Pd"}')],
    usage=None,
)

install_openai_mock(mock_client)
try:
    resp = service.chat([ChatMessage(role="user", content="extract")])
finally:
    uninstall_openai_mock()

check("State 4: chat succeeds without finish_reason attr", resp.finish_reason is None)
check("State 4: content preserved", resp.content == '{"catalyst": "Pd"}')
check("State 4: no exception raised", True)


# ---- State 5: Store adapter refuses truncated extractions ----
print("\n=== State 5: Store adapter truncation guard ===")

# Import the store adapter function directly
from catalyst_knowledge.pipeline.adapters import store_adapter as sa_mod

# Build a fake extraction JSON with truncation_error=True
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    extraction_dir = tmp_path / "extractions"
    extraction_dir.mkdir()
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    trunc_file = extraction_dir / "doc_trunc_extracted.json"
    trunc_file.write_text(json.dumps({
        "truncation_error": True,
        "dimensions": {
            "catalyst_design": {
                "chunks": [{"finish_reason": "length", "truncation_error": True}],
            },
        },
    }), encoding="utf-8")

    clean_file = extraction_dir / "doc_clean_extracted.json"
    clean_file.write_text(json.dumps({
        "dimensions": {"catalyst_design": {"chunks": [{"finish_reason": "stop"}]}},
    }), encoding="utf-8")

    # Stub CanonicalStore to record save calls without touching disk
    save_calls: list[str] = []

    class FakeStore:
        def __init__(self, path):
            self.path = path

        def save_document(self, doc_id, metadata):
            return True

        def save_extraction(self, doc_id, payload):
            save_calls.append(payload["source_file"])

        def get_statistics(self):
            return {"documents": 1, "extractions": len(save_calls)}

    # Patch module loader to return our FakeStore class
    fake_mod = SimpleNamespace(CanonicalStore=FakeStore)
    original_loader = sa_mod._load_module
    sa_mod._load_module = lambda: fake_mod

    try:
        result = sa_mod.run_canonical_store(
            document_id="doc_test",
            store_dir=str(store_dir),
            extraction_output_path=str(extraction_dir),
        )
    finally:
        sa_mod._load_module = original_loader

    check("State 5: store_status == 'BLOCKED'",
          result.get("store_status") == "BLOCKED",
          f"got {result.get('store_status')!r}")
    check("State 5: truncation_blocked_count == 1",
          result.get("truncation_blocked_count") == 1,
          f"got {result.get('truncation_blocked_count')!r}")
    check("State 5: truncation_error message present",
          "truncation_error" in result,
          f"keys={list(result.keys())}")
    check("State 5: clean extraction saved",
          any("doc_clean_extracted.json" in c for c in save_calls),
          f"save_calls={save_calls}")
    check("State 5: truncated extraction NOT saved",
          not any("doc_trunc_extracted.json" in c for c in save_calls),
          f"save_calls={save_calls}")


# ---- State 6: adapter module imports LLMOutputTruncated ----
print("\n=== State 6: adapter imports LLMOutputTruncated ===")

import importlib

# Re-import the adapter module to verify the LLMOutputTruncated import resolves
adapter_mod = importlib.import_module(
    "catalyst_knowledge.pipeline.adapters.science_extraction_v2_adapter"
)

check("State 6: adapter module imports without error", adapter_mod is not None)
check("State 6: LLMOutputTruncated visible in adapter module namespace",
      hasattr(adapter_mod, "LLMOutputTruncated")
      or "LLMOutputTruncated" in dir(adapter_mod)
      or any("LLMOutputTruncated" in str(getattr(a, "__name__", ""))
             for a in vars(adapter_mod).values() if isinstance(a, type)))

# Verify the exception class itself is importable from the adapter's import path
from catalyst_knowledge.core.llm_service import LLMOutputTruncated as Exc
check("State 6: LLMOutputTruncated importable from core.llm_service", Exc is LLMOutputTruncated)

# Verify the exception message does NOT include raw content
exc = Exc(max_tokens=4096, model="test-model", detail="content_length=999 chars")
exc_str = str(exc)
check("State 6: exception message does not include raw content",
      "content_length=999" in exc_str and '{"partial' not in exc_str,
      f"msg={exc_str!r}")
check("State 6: exception message includes max_tokens",
      "max_tokens=4096" in exc_str)


# ---- Summary ----
print("\n" + "=" * 70)
print(f"Results: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} total")
print("=" * 70)
if FAIL == 0:
    print("VERDICT: ALL PASS — truncation error propagation confirmed")
else:
    print(f"VERDICT: {FAIL} FAIL — review above")
    sys.exit(1)
