"""Test 012-A: finish_reason observability in LLMService.

Verifies the minimal fix for the silent-truncation defect found in 011 audit:
LLMService.chat() must surface finish_reason from the OpenAI API response and
log a warning when finish_reason == "length" (output truncated at max_tokens).
"""
from __future__ import annotations

import logging
import sys
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
    """Install an openai module mock into sys.modules.

    chat() does `import openai` inside the function body, so injecting a mock
    module into sys.modules is the cleanest interception point.
    """
    mock_openai_module = MagicMock()
    mock_openai_module.OpenAI.return_value = mock_client
    sys.modules["openai"] = mock_openai_module
    return mock_openai_module


def uninstall_openai_mock():
    sys.modules.pop("openai", None)


print("=" * 60)
print("Test 012-A: finish_reason observability")
print("=" * 60)


# ---- Test 1: ChatResponse dataclass has finish_reason field ----
print("\n=== Test 1: ChatResponse dataclass contract ===")
r_default = ChatResponse(content="x", model="m")
check("finish_reason field exists", hasattr(r_default, "finish_reason"))
check("finish_reason defaults to None", r_default.finish_reason is None)

r_set = ChatResponse(content="x", model="m", finish_reason="stop")
check("finish_reason accepts 'stop'", r_set.finish_reason == "stop")

r_len = ChatResponse(content="x", model="m", finish_reason="length")
check("finish_reason accepts 'length'", r_len.finish_reason == "length")


# ---- Test 2: chat() extracts finish_reason from API response ----
print("\n=== Test 2: chat() extracts finish_reason ===")

service = LLMService(api_key="test-key")

mock_choice_stop = SimpleNamespace(
    message=SimpleNamespace(content='{"ok": true}'),
    finish_reason="stop",
)
mock_response_stop = SimpleNamespace(
    choices=[mock_choice_stop],
    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
)

mock_client = MagicMock()
mock_client.chat.completions.create.return_value = mock_response_stop

install_openai_mock(mock_client)
try:
    result = service.chat([ChatMessage(role="user", content="hi")])
finally:
    uninstall_openai_mock()

check("chat returns ChatResponse", isinstance(result, ChatResponse))
check("finish_reason is 'stop'", result.finish_reason == "stop",
      f"got {result.finish_reason!r}")
check("content preserved", result.content == '{"ok": true}')
check("usage captured", result.usage == {"prompt_tokens": 10, "completion_tokens": 5})


# ---- Test 3: finish_reason='length' triggers warning log ----
print("\n=== Test 3: truncation warning on finish_reason='length' ===")

mock_choice_len = SimpleNamespace(
    message=SimpleNamespace(content='{"partial":'),
    finish_reason="length",
)
mock_response_len = SimpleNamespace(
    choices=[mock_choice_len],
    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4096),
)
mock_client.chat.completions.create.return_value = mock_response_len

logger = logging.getLogger("catalyst_knowledge.core.llm_service")

captured_records: list[logging.LogRecord] = []


class ListHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        captured_records.append(record)


list_handler = ListHandler(level=logging.WARNING)
logger.addHandler(list_handler)
logger.setLevel(logging.WARNING)

install_openai_mock(mock_client)
try:
    raised = False
    try:
        result = service.chat([ChatMessage(role="user", content="hi")])
    except LLMOutputTruncated as e:
        raised = True
        trunc_exc = e
finally:
    uninstall_openai_mock()
    logger.removeHandler(list_handler)

check("finish_reason is 'length' raises LLMOutputTruncated", raised)
if raised:
    check("exception carries max_tokens", trunc_exc.max_tokens == 4096)
    check("exception carries model", trunc_exc.model == service.model)
check("warning was logged before exception", len(captured_records) >= 1,
      f"got {len(captured_records)} warning(s)")
if captured_records:
    msg = captured_records[0].getMessage()
    check("warning mentions max_tokens", "max_tokens" in msg,
          f"msg={msg!r}")
    check("warning mentions finish_reason=length", "finish_reason=length" in msg)
    check("warning mentions truncation",
          "truncated" in msg.lower() or "incomplete" in msg.lower())


# ---- Test 4: graceful when finish_reason attribute missing ----
print("\n=== Test 4: graceful degradation (no finish_reason attr) ===")

# Use a plain object without finish_reason to exercise the getattr(..., None) path
class ChoiceNoFinishReason:
    def __init__(self, content: str):
        self.message = SimpleNamespace(content=content)


mock_choice_noattr = ChoiceNoFinishReason("hello")
mock_response_noattr = SimpleNamespace(
    choices=[mock_choice_noattr],
    usage=None,
)
mock_client.chat.completions.create.return_value = mock_response_noattr

install_openai_mock(mock_client)
try:
    result = service.chat([ChatMessage(role="user", content="hi")])
finally:
    uninstall_openai_mock()

check("chat succeeds without finish_reason attr", result.finish_reason is None,
      f"got {result.finish_reason!r}")
check("content preserved", result.content == "hello")
check("usage defaults to zeros", result.usage == {"prompt_tokens": 0, "completion_tokens": 0})


# ---- Test 5: chat_json still works (backward compat) ----
print("\n=== Test 5: chat_json backward compatibility ===")

mock_choice_json = SimpleNamespace(
    message=SimpleNamespace(content='{"key": "value"}'),
    finish_reason="stop",
)
mock_response_json = SimpleNamespace(
    choices=[mock_choice_json],
    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
)
mock_client.chat.completions.create.return_value = mock_response_json

install_openai_mock(mock_client)
try:
    parsed = service.chat_json([ChatMessage(role="user", content="give json")])
finally:
    uninstall_openai_mock()

check("chat_json returns dict", isinstance(parsed, dict))
check("chat_json parsed content", parsed == {"key": "value"})


# ---- Summary ----
print("\n" + "=" * 60)
print(f"Results: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} total")
print("=" * 60)
if FAIL == 0:
    print("VERDICT: ALL PASS — finish_reason observability confirmed")
else:
    print(f"VERDICT: {FAIL} FAIL — review above")
    sys.exit(1)
