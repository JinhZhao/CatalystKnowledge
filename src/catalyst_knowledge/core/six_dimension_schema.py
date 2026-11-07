"""Six-Dimension Schema — Pydantic v2 统一模型 + 交叉验证。

将六维催化文献提取的结构定义和交叉验证规则统一在 Pydantic v2 中：
  - 维度数据模型: CatalystDesign / Characterization / Performance / ...
  - 交叉验证: @model_validator 自动校验维度间证据自洽性
  - 假设模型: Hypothesis / HypothesisSet (H0/H1/H2 结构化输出)
  - Voc4Cat 标签: 自动注入词汇标准化 IRI

替代原 cross_validator.py (439行) + per_paper_hypothesis_generator.py (432行)
总计 ~350 行 (减少 66%)。

Usage:
    from catalyst_knowledge.core.six_dimension_schema import SixDimensionView, HypothesisSet

    view = SixDimensionView.model_validate(llm_output)
    # 自动触发交叉验证，warnings 存入 view.cv_warnings
    print(view.cv_warnings)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator, field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 维度数据模型
# ---------------------------------------------------------------------------

class CatalystDesign(BaseModel):
    """维度1: 催化剂设计"""
    catalyst_system: str = Field(default="", description="完整催化剂名称, e.g. 'Pt/TiO2'")
    catalyst_type: str = Field(default="", description="类别: single_atom/nanoparticle/supported_metal/MOF/zeolite/perovskite")
    active_component: str = Field(default="", description="活性组分, e.g. 'Pt', 'Cu'")
    support: str = Field(default="", description="载体材料, e.g. 'TiO2', 'Al2O3'")
    synthesis_method: str = Field(default="", description="合成方法, e.g. 'impregnation'")
    reaction_type: str = Field(default="", description="目标反应, e.g. 'CO oxidation', 'HER'")
    design_rationale: str = Field(default="", description="设计理由")


class Characterization(BaseModel):
    """维度2: 表征证据"""
    techniques_used: list[str] = Field(default_factory=list, description="表征方法列表")
    key_findings: list[str] = Field(default_factory=list, description="关键表征结果")
    in_situ_evidence: Optional[str] = Field(default=None, description="原位表征证据")
    morphological_evidence: str = Field(default="", description="形貌证据: 粒径、分散度、比表面积")
    electronic_evidence: str = Field(default="", description="电子结构证据: 氧化态、d带中心")


class PerformanceMetric(BaseModel):
    """单个性能指标"""
    metric_name: str = Field(default="", description="指标名称")
    value: str = Field(default="", description="数值 (含单位)")
    conditions: str = Field(default="", description="测试条件")


class ExperimentRecord(BaseModel):
    """单条实验记录 — 用于提取配体×条件→产物映射矩阵。

    BL-002: 压缩闭环不固化实验结果修复
    - 明确结构化提取 ligand/catalyst/solvent/temp/time → product/selectivity/yield
    - 支持发散转化场景（如 Pd 催化二烯羰基化的多条路径）
    """
    experiment_id: str = Field(default="", description="实验编号，如 '5a', '4a'")
    ligand: str = Field(default="", description="配体，如 'PAd₃', 'Xantphos'")
    catalyst: str = Field(default="", description="催化剂体系，如 'Pd(OAc)₂/Ligand'")
    solvent: str = Field(default="", description="溶剂，如 'HFIP', 'DCE'")
    temperature: str = Field(default="", description="温度，如 '80°C', 'rt'")
    time: str = Field(default="", description="反应时间，如 '48h', '12h'")
    additive: str = Field(default="", description="添加剂/助剂，如 'Ca(NTf₂)₂'")
    product: str = Field(default="", description="主产物或产物类型，如 '5-endo-trig 环化产物'")
    selectivity: str = Field(default="", description="选择性数据，如 '3:1', '95:5'")
    yield_value: str = Field(default="", description="产率，如 '72%', '65%'")
    pathway: str = Field(default="", description="反应路径描述，如 'π-allyl 路径'")
    notes: str = Field(default="", description="其他备注，如副产物、特殊现象")


class Performance(BaseModel):
    """维度3: 性能指标"""
    key_metrics: list[PerformanceMetric] = Field(default_factory=list)
    key_claim: str = Field(default="", description="核心性能声称 (一句话)")
    benchmark_comparison: str = Field(default="", description="与最先进水平的对比")
    reaction_conditions: str = Field(default="", description="反应条件: T/P/GHSV 等")
    experiment_matrix: list[ExperimentRecord] = Field(default_factory=list, description="实验条件矩阵 (BL-002)")


class Mechanism(BaseModel):
    """维度4: 机理路径"""
    proposed_pathway: str = Field(default="", description="反应机理/路径描述")
    rate_determining_step: Optional[str] = Field(default=None, description="决速步 (RDS)")
    intermediates: list[str] = Field(default_factory=list, description="关键中间体")
    computational_support: Optional[str] = Field(default=None, description="DFT/计算证据")
    experimental_support: str = Field(default="", description="实验证据")


class StructureActivity(BaseModel):
    """维度5: 构效关系"""
    descriptor: Optional[str] = Field(default=None, description="关键描述符, e.g. 'd-band center'")
    relationship_type: str = Field(default="", description="关系类型: volcano/linear/inverse")
    evidence_strength: str = Field(default="", description="证据强度: strong/moderate/weak")
    data_points: int = Field(default=0, description="对比催化剂数量")


class Reliability(BaseModel):
    """维度6: 可靠性"""
    time_on_stream: float = Field(default=0, description="稳定性测试时长 (小时)")
    cycle_count: int = Field(default=0, description="循环测试次数")
    mass_transfer_verification: Optional[str] = Field(default=None, description="传质验证方法")
    reproducibility: Optional[str] = Field(default=None, description="可重复性证据")
    deactivation_observed: Optional[str] = Field(default=None, description="失活观察")


# ---------------------------------------------------------------------------
# 六维聚合视图 — 含交叉验证
# ---------------------------------------------------------------------------

class DimensionConfidence(BaseModel):
    """单个维度的数据 + 置信度"""
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SixDimensionView(BaseModel):
    """六维聚合视图 — Pydantic v2 自动交叉验证。

    使用方式:
        view = SixDimensionView.model_validate(llm_output)
        if view.cv_warnings:
            for w in view.cv_warnings:
                print(w["message"])
    """
    catalyst_design: CatalystDesign = Field(default_factory=CatalystDesign)
    characterization: Characterization = Field(default_factory=Characterization)
    performance: Performance = Field(default_factory=Performance)
    mechanism: Optional[Mechanism] = None
    structure_activity: Optional[StructureActivity] = None
    reliability: Reliability = Field(default_factory=Reliability)

    # 交叉验证结果 (非序列化字段)
    model_config = {"arbitrary_types_allowed": True}
    cv_warnings: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    cv_rules_checked: int = Field(default=0, exclude=True)

    # ── 交叉验证规则 ──────────────────────────────────────────────────

    @model_validator(mode="after")
    def _cross_validate(self) -> "SixDimensionView":
        """运行所有交叉验证规则，结果存入 cv_warnings。"""
        warnings: list[dict[str, Any]] = []
        rules_checked = 0

        design = self.catalyst_design
        char = self.characterization
        perf = self.performance
        mech = self.mechanism
        sa = self.structure_activity
        rel = self.reliability

        techniques_upper = [t.upper() for t in char.techniques_used]
        char_text = str(char.model_dump()).lower()

        # Rule 1: 合成↔表征 — 浸渍法 → 需 BET
        rules_checked += 1
        synthesis = design.synthesis_method.lower()
        impregnation_kw = ["incipient wetness", "wet impregnation", "dry impregnation",
                           "等体积浸渍", "浸渍法", "impregnation"]
        if any(kw in synthesis for kw in impregnation_kw):
            has_bet = any(t in techniques_upper for t in ["BET", "BJH"]) or "比表面积" in char_text
            if not has_bet:
                warnings.append({
                    "rule_id": "CV-SYNTH-CHAR-001",
                    "severity": "medium",
                    "message": "浸渍法合成催化剂但未报告 BET 比表面积/孔体积数据",
                    "dimensions": ["catalyst_design", "characterization"],
                })

        # Rule 2: 类型↔证据 — SAC → 需 EXAFS/HAADF
        rules_checked += 1
        cat_type = design.catalyst_type.lower()
        sac_kw = ["single_atom", "single atom", "单原子", "sac", "sas"]
        if any(kw in cat_type for kw in sac_kw):
            atomic_evidence = ["EXAFS", "HAADF", "XANES", "XAFS", "AC-STEM"]
            has_atomic = any(t in techniques_upper for t in atomic_evidence)
            if not has_atomic:
                warnings.append({
                    "rule_id": "CV-TYPE-CHAR-001",
                    "severity": "high",
                    "message": "声称单原子催化剂 (SAC) 但无原子级表征证据 (EXAFS/HAADF-STEM/XANES)",
                    "dimensions": ["catalyst_design", "characterization"],
                })

        # Rule 3: 性能↔可靠性 — 声称高稳定性 → TOS ≥ 100h
        rules_checked += 1
        perf_text = str(perf.model_dump()).lower()
        stability_kw = ["stable", "stability", "durability", "lifetime", "稳定", "耐久"]
        if any(kw in perf_text for kw in stability_kw):
            if rel.time_on_stream < 100:
                warnings.append({
                    "rule_id": "CV-PERF-REL-001",
                    "severity": "medium",
                    "message": f"声称高稳定性但 TOS 仅 {rel.time_on_stream}h，不足以支撑结论 (建议≥100h)",
                    "dimensions": ["performance", "reliability"],
                })

        # Rule 4: 机理↔表征 — 原位机理 → 需原位表征
        rules_checked += 1
        if mech:
            mech_text = str(mech.model_dump()).lower()
            insitu_kw = ["in-situ", "in situ", "operando", "原位"]
            if any(kw in mech_text for kw in insitu_kw):
                insitu_char = ["in-situ", "in situ", "operando", "原位", "time-resolved"]
                if not any(kw in char_text for kw in insitu_char):
                    warnings.append({
                        "rule_id": "CV-MECH-CHAR-001",
                        "severity": "medium",
                        "message": "机理讨论涉及原位分析但缺少原位表征数据支撑",
                        "dimensions": ["mechanism", "characterization"],
                    })

        # Rule 5: 构效↔性能 — 声称描述符关联 → 需系列数据
        rules_checked += 1
        if sa and sa.descriptor:
            perf_text2 = str(perf.model_dump()).lower()
            series_kw = ["series", "系列", "different", "不同", "comparison", "对比", "multiple"]
            if not any(kw in perf_text2 for kw in series_kw):
                warnings.append({
                    "rule_id": "CV-SA-PERF-001",
                    "severity": "medium",
                    "message": "构效关系声称描述符关联但性能数据未包含系列催化剂对比",
                    "dimensions": ["structure_activity", "performance"],
                })

        # Rule 6: 可靠性 — Weisz-Prater 超标
        rules_checked += 1
        if rel.mass_transfer_verification:
            try:
                wp_val = float(rel.mass_transfer_verification)
                if wp_val > 0.3:
                    warnings.append({
                        "rule_id": "CV-REL-001",
                        "severity": "high",
                        "message": f"Weisz-Prater = {wp_val} > 0.3，未排除传质限制",
                        "dimensions": ["reliability"],
                    })
            except (ValueError, TypeError):
                pass  # 非数值型传质验证，跳过此规则

        self.cv_warnings = warnings
        self.cv_rules_checked = rules_checked
        return self

    # ── 便捷方法 ──────────────────────────────────────────────────────

    def completeness(self) -> dict[str, Any]:
        """分析六维完整性"""
        dims = {
            "catalyst_design": self.catalyst_design,
            "characterization": self.characterization,
            "performance": self.performance,
            "mechanism": self.mechanism,
            "structure_activity": self.structure_activity,
            "reliability": self.reliability,
        }
        present, missing = [], []
        for name, dim in dims.items():
            if dim is not None and dim.model_dump(exclude_defaults=True):
                present.append(name)
            else:
                missing.append(name)
        return {
            "present": present,
            "missing": missing,
            "coverage": round(len(present) / 6, 2),
        }

    def overall_reliability(self) -> float:
        """加权可靠性评分"""
        weights = {
            "catalyst_design": 1.0, "characterization": 1.2, "performance": 1.0,
            "mechanism": 1.0, "structure_activity": 0.8, "reliability": 1.5,
        }
        # 基于维度数据非空程度估算置信度
        confidences = {}
        for name, weight in weights.items():
            dim = getattr(self, name, None)
            if dim is None:
                confidences[name] = 0.0
                continue
            dumped = dim.model_dump(exclude_defaults=True)
            non_empty = sum(1 for v in dumped.values() if v)
            total = max(len(dumped), 1)
            confidences[name] = min(1.0, non_empty / total)

        weighted_sum = sum(confidences[n] * w for n, w in weights.items())
        total_weight = sum(weights.values())
        return round(weighted_sum / total_weight, 3) if total_weight else 0.0


# ---------------------------------------------------------------------------
# 假设模型
# ---------------------------------------------------------------------------

class HypothesisType(str, Enum):
    BASELINE = "baseline"      # H0
    CHALLENGE = "challenge"    # H1
    EXTENSION = "extension"    # H2


class Hypothesis(BaseModel):
    """单条可验证假设"""
    id: str = Field(description="假设 ID, e.g. 'H0', 'H1a', 'H2-mechanism'")
    h_type: HypothesisType = Field(description="假设类型")
    statement: str = Field(description="假设陈述，必须可证伪")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度")
    innovation: int = Field(default=3, ge=1, le=5, description="创新性 (1-5)")
    feasibility: int = Field(default=3, ge=1, le=5, description="可行性 (1-5)")
    impact: int = Field(default=3, ge=1, le=5, description="影响力 (1-5)")
    falsifiability: int = Field(default=4, ge=1, le=5, description="可证伪性 (1-5)")
    validation_experiment: Optional[str] = Field(default=None, description="验证实验设计")
    inferred_from: Optional[str] = Field(default=None, description="推理来源")
    trigger_rule: Optional[str] = Field(default=None, description="触发规则 ID")
    # Voc4Cat ontology tags (populated by normalize_hypothesis post-processing)
    reaction_type: Optional[str] = Field(default=None, description="目标反应, e.g. 'CO oxidation'")
    catalyst_class: Optional[str] = Field(default=None, description="催化剂类别, e.g. 'Electrocatalysts'")
    reaction_type_voc4cat: Optional[str] = Field(default=None, description="Voc4Cat short IRI for reaction_type")
    catalyst_class_voc4cat: Optional[str] = Field(default=None, description="Voc4Cat short IRI for catalyst_class")

    def composite_score(self) -> float:
        """加权综合评分: 创新性30% + 可行性25% + 影响力30% + 可证伪性15%"""
        return (self.innovation * 0.30 + self.feasibility * 0.25
                + self.impact * 0.30 + self.falsifiability * 0.15)


class HypothesisSet(BaseModel):
    """单篇文献的假设集"""
    source_paper: str = Field(default="", description="文献标识")
    reliability_score: float = Field(default=0.0, description="综合可靠性")
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    priority_ranking: list[str] = Field(default_factory=list, description="假设 ID 优先级排序")
    recommended_next_step: Optional[str] = Field(default=None, description="推荐下一步")
    gap_analysis: dict[str, Any] = Field(default_factory=dict, description="缺口分析")


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def build_six_dimension_view(llm_output: dict) -> SixDimensionView:
    """从 LLM 输出构建六维视图，自动触发交叉验证。

    Args:
        llm_output: LLM 返回的原始 dict (已解析 JSON)

    Returns:
        SixDimensionView (已校验 + 交叉验证完成)
    """
    return SixDimensionView.model_validate(llm_output)
