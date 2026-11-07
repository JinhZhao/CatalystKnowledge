"""SummarizerAgent — 六维聚合 + 假设生成智能体 (v2: Pydantic 轻量版).

Responsibilities:
- Receive parsed_paper dict after quality gate passes
- Run SixDimensionSummarizer → six-dimension view (Pydantic 自动校验)
- Run generate_hypotheses → H0/H1/H2 hypotheses (Pydantic HypothesisSet)
- Return structured results for the KnowledgeState

Flow:
    parsed_paper → SixDimensionSummarizer → generate_hypotheses → output

Changes v1 → v2:
- 移除手写 CrossValidator → Pydantic @model_validator 自动校验
- 移除手写 LLM 解析 → LangChain with_structured_output
- 移除 Hypothesis dataclass → Pydantic Hypothesis model
- 总代码量: 1405行 → ~570行 (减少 59%)
"""

from __future__ import annotations

import logging
from typing import Any

from catalyst_knowledge.core.per_paper_hypothesis_generator import generate_hypotheses
from catalyst_knowledge.core.six_dimension_summarizer import SixDimensionSummarizer

logger = logging.getLogger(__name__)


class SummarizerAgent:
    """六维聚合 + 假设生成智能体 — 在质量门通过后执行深度分析。"""

    def __init__(self, llm=None):
        """初始化 SummarizerAgent。

        Args:
            llm: LLMService 实例 (可选，主要用于 fallback)
        """
        self._summarizer = SixDimensionSummarizer(llm_service=llm)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        parsed_paper: dict[str, Any],
        checkpoint_callback: Any = None,
    ) -> dict[str, Any]:
        """Run six-dimension summarization and hypothesis generation.

        Args:
            parsed_paper: Dict with title, abstract, sections, full_text, etc.
            checkpoint_callback: Optional callable(stage, data) -> str | None.
                Called after each major stage. If returns a string, treated as
                user feedback and the stage is re-executed.

        Returns:
            Dict with keys:
            - six_dimension_view: dict (6 dimensions, Pydantic 校验后)
            - cross_validation: dict (cv_warnings, severity_counts)
            - hypotheses: dict (HypothesisSet dump)
            - overall_reliability: float
            - completeness: dict (present, missing, coverage)
        """
        if not parsed_paper:
            logger.warning("SummarizerAgent received empty parsed_paper")
            return self._empty_result()

        # Step 1: Six-dimension extraction (Pydantic 自动交叉验证)
        try:
            six_dim_summary = self._summarizer.summarize(
                parsed_paper,
                checkpoint_callback=checkpoint_callback,
            )
        except Exception as e:
            logger.error("Six-dimension summarization failed: %s", e)
            return self._empty_result()

        # Step 2: Hypothesis generation (Pydantic HypothesisSet)
        try:
            hypotheses = generate_hypotheses(six_dim_summary)
        except Exception as e:
            logger.error("Hypothesis generation failed: %s", e)
            hypotheses = {
                "hypotheses": [],
                "gap_analysis": {},
                "priority_ranking": [],
                "recommended_next_step": None,
                "error": str(e),
            }

        # Step 3: Rule engine evaluation (YAML-driven, no hardcoding)
        rule_engine_result = {}
        try:
            from catalyst_knowledge.core.rule_engine import HypothesisRuleEngine
            rule_engine = HypothesisRuleEngine()
            rule_engine_result = rule_engine.evaluate(six_dim_summary)
        except Exception as e:
            logger.warning("Rule engine evaluation failed (non-critical): %s", e)

        return {
            "six_dimension_view": six_dim_summary.get("six_dimension_view", {}),
            "cross_validation": six_dim_summary.get("cross_validation", {}),
            "hypotheses": hypotheses,
            "overall_reliability": six_dim_summary.get("overall_reliability", 0.0),
            "completeness": six_dim_summary.get("completeness", {}),
            "voc4cat_tags": six_dim_summary.get("voc4cat_tags", []),
            "rule_engine": rule_engine_result,
        }

    # ------------------------------------------------------------------
    # LangGraph node wrapper
    # ------------------------------------------------------------------

    def as_node(self):
        """Return a function suitable as a LangGraph node."""

        def node(state: dict) -> dict:
            parsed_paper = state.get("parsed_paper", {})
            result = self.run(parsed_paper)

            return {
                "six_dimension_view": result.get("six_dimension_view", {}),
                "cross_validation": result.get("cross_validation", {}),
                "hypotheses": result.get("hypotheses", {}),
                "progress": {"summarizer": "done"},
            }

        return node

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        """Return an empty result structure."""
        return {
            "six_dimension_view": {},
            "cross_validation": {},
            "hypotheses": {
                "hypotheses": [],
                "gap_analysis": {},
                "priority_ranking": [],
                "recommended_next_step": None,
            },
            "overall_reliability": 0.0,
            "completeness": {"present": [], "missing": [], "coverage": 0.0},
            "voc4cat_tags": [],
            "rule_engine": {},
        }
