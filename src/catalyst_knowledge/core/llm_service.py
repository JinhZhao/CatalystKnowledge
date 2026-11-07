"""LLM Service — V2 简化版 LLM 调用服务。

替代旧版 llm_service.py，提供最小化 LLM 调用接口。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Chat message."""
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatResponse:
    """Chat response from LLM."""
    content: str
    model: str
    usage: dict[str, int] | None = None
    finish_reason: str | None = None


class LLMOutputTruncated(RuntimeError):
    """LLM output was truncated at max_tokens (finish_reason='length').

    Raised by LLMService.chat() when the API signals the response did not
    complete naturally. Callers must treat this as a hard failure: the
    content field is incomplete and must not be parsed as JSON or written
    to the Canonical Store as a successful extraction.
    """

    def __init__(self, max_tokens: int, model: str, detail: str = ""):
        self.max_tokens = max_tokens
        self.model = model
        self.detail = detail
        msg = (
            f"LLM output truncated at max_tokens={max_tokens} "
            f"(model={model}, finish_reason=length)"
        )
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class LLMService:
    """Minimal LLM service for quality assessment and extraction.

    V2 简化版：直接调用 OpenAI-compatible API，不支持分级路由。
    """

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")
        self.api_base = api_base or os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.api_key:
            logger.warning("LLM_API_KEY not set, LLM calls will fail")

    def chat(
        self,
        messages: list[ChatMessage],
        response_format: dict | None = None,
    ) -> ChatResponse:
        """Send chat request to LLM.

        Args:
            messages: List of chat messages
            response_format: Optional JSON schema for structured output

        Returns:
            ChatResponse with content and usage
        """
        try:
            import openai

            import httpx

            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=httpx.Timeout(300.0, connect=30.0),
            )

            # Convert messages to OpenAI format
            oai_messages = [{"role": m.role, "content": m.content} for m in messages]

            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": oai_messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            if response_format:
                kwargs["response_format"] = response_format

            response = client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            content = choice.message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            }

            if finish_reason == "length":
                # Hard failure: truncated output must not be consumed as valid.
                # Diagnostic intentionally omits raw content (may be sensitive).
                logger.error(
                    "LLM output truncated at max_tokens=%d (model=%s, "
                    "finish_reason=length, content_length=%d chars). "
                    "Raising LLMOutputTruncated — caller must treat as failure.",
                    self.max_tokens, self.model, len(content),
                )
                raise LLMOutputTruncated(
                    max_tokens=self.max_tokens,
                    model=self.model,
                    detail=f"content_length={len(content)} chars",
                )

            if finish_reason not in (None, "stop", "end_turn", "complete"):
                # Unusual finish_reason (e.g. 'content_filter') — log but do not block.
                logger.warning(
                    "LLM response finished with unexpected reason: %s (model=%s)",
                    finish_reason, self.model,
                )

            return ChatResponse(
                content=content,
                model=self.model,
                usage=usage,
                finish_reason=finish_reason,
            )

        except ImportError:
            logger.error("openai package not installed")
            raise
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise

    def chat_json(self, messages: list[ChatMessage]) -> dict:
        """Chat and parse JSON response.

        Args:
            messages: List of chat messages

        Returns:
            Parsed JSON dict
        """
        response = self.chat(
            messages,
            response_format={"type": "json_object"},
        )
        return json.loads(response.content)
