"""Six Dimension Summarizer — V2 简化版六维抽取。

替代旧版 six_dimension_summarizer.py，使用 Pydantic 模型进行结构化输出。
"""

from __future__ import annotations

import logging
from typing import Any

from catalyst_knowledge.core.llm_service import LLMService, ChatMessage
from catalyst_knowledge.core.six_dimension_schema import SixDimensionView
from catalyst_knowledge.prompts.loader import load_prompt

logger = logging.getLogger(__name__)


class SixDimensionSummarizer:
    """Extract six-dimension structured information from papers.

    V2 简化版：直接使用 LLM structured output，不依赖 LangChain。
    """

    def __init__(self, llm_service: LLMService | None = None):
        self._llm = llm_service or LLMService()
        self._system_prompt = load_prompt("six-dimension-extraction-prompt")

    def summarize(self, paper_content: dict[str, Any]) -> SixDimensionView:
        """Extract six dimensions from paper content.

        Args:
            paper_content: Dict with keys: title, abstract, key_content

        Returns:
            SixDimensionView with extracted information
        """
        title = paper_content.get("title", "")
        abstract = paper_content.get("abstract", "")
        key_content = paper_content.get("key_content", "")[:6000]

        user_prompt = f"""## Input
- **标题**: {title}
- **摘要**: {abstract}
- **关键内容** (前6000字): {key_content}
"""

        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        try:
            result = self._llm.chat_json(messages)
            view = SixDimensionView.model_validate(result)
            logger.info(
                "Six-dimension extraction complete: %d cv_warnings",
                len(view.cv_warnings),
            )
            return view
        except Exception as e:
            logger.error("Six-dimension extraction failed: %s", e)
            raise


class HypothesisGenerator:
    """Generate hypotheses from six-dimension extraction results.

    V2 占位实现：返回空假设集。
    """

    def generate(self, view: SixDimensionView) -> dict[str, Any]:
        """Generate H0/H1/H2 hypotheses.

        Args:
            view: Six-dimension extraction result

        Returns:
            Dict with h0, h1, h2 hypotheses
        """
        return {
            "h0": "No specific hypothesis generated (placeholder)",
            "h1": [],
            "h2": [],
        }


def generate_hypotheses(view: SixDimensionView) -> dict[str, Any]:
    """Convenience function for hypothesis generation."""
    generator = HypothesisGenerator()
    return generator.generate(view)
