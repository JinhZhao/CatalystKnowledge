"""QualityAgent — 质量评估智能体.

Responsibilities:
- Receive parsed_paper dict from ParserAgent
- Run rule-based pre-checks (section count, data points, text length)
- Call LLM to assess quality across 5 dimensions
- Return QualityReport with verdict (accept / reject)

Threshold: overall_score >= 0.6 → accept, otherwise reject.
"""

from __future__ import annotations

from typing import Any

from catalyst_knowledge.core.llm_service import LLMService
from catalyst_knowledge.core.quality_assessor import QualityReport, assess_quality


class QualityAgent:
    """质量评估智能体 — 判断解析后的论文是否满足知识库收录标准。"""

    def __init__(self, llm: LLMService | None = None, threshold: float = 0.6):
        self._llm = llm or LLMService()
        self._threshold = threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, parsed_paper: dict) -> dict[str, Any]:
        """Assess the quality of a parsed paper.

        Args:
            parsed_paper: Dict with keys title, abstract, sections, full_text, etc.

        Returns:
            Dict with keys:
            - quality_report: dict (overall_score, verdict, reason, dimension_scores, paper_type, ...)
            - quality_passed: bool
        """
        if not parsed_paper:
            return {
                "quality_report": {
                    "overall_score": 0.0,
                    "verdict": "reject",
                    "reason": "No parsed paper data available.",
                    "dimension_scores": {},
                    "suggestions": "",
                    "paper_type": "research",
                },
                "quality_passed": False,
            }

        report: QualityReport = assess_quality(self._llm, parsed_paper)

        return {
            "quality_report": {
                "overall_score": report.overall_score,
                "verdict": report.verdict,
                "reason": report.reason,
                "dimension_scores": report.dimension_scores,
                "suggestions": report.suggestions,
                "paper_type": report.paper_type,
            },
            "quality_passed": report.verdict == "accept",
        }

    # ------------------------------------------------------------------
    # LangGraph node wrapper
    # ------------------------------------------------------------------

    def as_node(self):
        """Return a function suitable as a LangGraph node."""

        def node(state: dict) -> dict:
            parsed_paper = state.get("parsed_paper", {})
            result = self.run(parsed_paper)

            passed = result["quality_passed"]
            return {
                "quality_report": result["quality_report"],
                "quality_passed": passed,
                "progress": {"quality": "done"},
            }

        return node
