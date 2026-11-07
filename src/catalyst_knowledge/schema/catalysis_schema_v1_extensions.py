"""Catalysis Schema V1 Extensions — 单篇科学知识扩展模型。

SINGLE-PAPER-KNOWLEDGE-001 Phase 2: 模型扩展
- 4 个新模型：Limitation, OpenQuestion, Feasibility, ValidationPlan
- 4 个现有模型扩展：Assertion, Evidence, Observation, Experiment (仅添加可选字段)

设计原则：
1. 向后兼容：所有新字段均为 Optional，不影响现有数据
2. 遵循现有模式：使用 SourceAnchor, DataStatus 等基础类型
3. 不修改冻结契约：Schema version 保持 1.0.0
4. 元科学概念显式化：限制、开放问题、可行性、验证计划独立建模
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .catalysis_schema_v1 import (
    DataStatus,
    SourceAnchor,
    ValueWithSource,
    Reaction,
    CatalystSample,
)


# ---------------------------------------------------------------------------
# 扩展枚举
# ---------------------------------------------------------------------------

class AssertionSource(str, Enum):
    """主张来源。"""
    AUTHOR_STATED = "AUTHOR_STATED"      # 作者明确陈述
    SYSTEM_INFERRED = "SYSTEM_INFERRED"  # 系统推断


class EvidencePolarity(str, Enum):
    """证据极性。"""
    SUPPORTING = "SUPPORTING"      # 支持
    CHALLENGING = "CHALLENGING"    # 挑战
    QUALIFYING = "QUALIFYING"      # 限定条件


class ExperimentStatus(str, Enum):
    """实验状态。"""
    EXECUTED = "EXECUTED"    # 已执行
    PROPOSED = "PROPOSED"    # 提议但未执行


class LimitationType(str, Enum):
    """限制类型。"""
    SCOPE = "SCOPE"                    # 适用范围限制
    ACCURACY = "ACCURACY"              # 精度限制
    ASSUMPTION = "ASSUMPTION"          # 假设限制
    GENERALIZABILITY = "GENERALIZABILITY"  # 可推广性限制
    METHODOLOGY = "METHODOLOGY"        # 方法论限制


class QuestionType(str, Enum):
    """问题类型。"""
    MECHANISM = "MECHANISM"        # 机理问题
    SCOPE = "SCOPE"                # 适用范围问题
    OPTIMIZATION = "OPTIMIZATION"  # 优化问题
    FUNDAMENTAL = "FUNDAMENTAL"    # 基础科学问题
    APPLICATION = "APPLICATION"    # 应用问题


class ResolutionStatus(str, Enum):
    """解决状态。"""
    OPEN = "OPEN"              # 未解决
    PARTIAL = "PARTIAL"        # 部分解决
    RESOLVED = "RESOLVED"      # 已解决
    DEFERRED = "DEFERRED"      # 推迟


class FeasibilityStatus(str, Enum):
    """可行性状态。"""
    FEASIBLE = "FEASIBLE"          # 可行
    CHALLENGING = "CHALLENGING"    # 有挑战
    INFEASIBLE = "INFEASIBLE"      # 不可行
    UNKNOWN = "UNKNOWN"            # 未知


class PlanStatus(str, Enum):
    """计划状态。"""
    PROPOSED = "PROPOSED"      # 已提议
    IN_PROGRESS = "IN_PROGRESS"  # 进行中
    COMPLETED = "COMPLETED"    # 已完成
    ABANDONED = "ABANDONED"    # 已放弃


# ---------------------------------------------------------------------------
# 新模型 1: Limitation (限制)
# ---------------------------------------------------------------------------

class Limitation(BaseModel):
    """科学限制 — 论文中明确指出的研究局限性。

    用于捕捉作者对研究范围、精度、假设等的自我评估。
    """
    limitation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = Field(..., description="来源文档ID")

    # 内容
    content: str = Field(..., description="限制内容描述")
    limitation_type: LimitationType = Field(..., description="限制类型")

    # 关联
    affects_assertion_ids: list[str] = Field(
        default_factory=list,
        description="受影响的科学主张ID"
    )
    affects_experiment_ids: list[str] = Field(
        default_factory=list,
        description="受影响的实验ID"
    )

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")
    stated_by: str = Field(default="AUTHOR", description="陈述者 (AUTHOR/REVIEWER/SYSTEM)")
    status: DataStatus = Field(
        default=DataStatus.REPORTED,
        description="数据状态"
    )

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# 新模型 2: OpenQuestion (开放问题)
# ---------------------------------------------------------------------------

class OpenQuestion(BaseModel):
    """开放问题 — 论文中提出但未完全解决的科学问题。

    用于追踪研究前沿和未来工作方向。
    """
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = Field(..., description="来源文档ID")

    # 内容
    content: str = Field(..., description="问题内容")
    question_type: QuestionType = Field(..., description="问题类型")

    # 关联
    motivates_hypothesis_ids: list[str] = Field(
        default_factory=list,
        description="激发假设ID"
    )
    relates_to_assertion_ids: list[str] = Field(
        default_factory=list,
        description="相关主张ID"
    )

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")
    identified_by: str = Field(default="AUTHOR", description="识别者 (AUTHOR/REVIEWER/SYSTEM)")
    resolution_status: ResolutionStatus = Field(
        default=ResolutionStatus.OPEN,
        description="解决状态"
    )

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# 新模型 3: Feasibility (可行性评估)
# ---------------------------------------------------------------------------

class Feasibility(BaseModel):
    """可行性评估 — 对某个方案或假设的可行性判断。

    用于科研决策支持，评估技术路线的可行性。
    """
    feasibility_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = Field(..., description="来源文档ID")

    # 评估对象
    target_type: str = Field(..., description="目标类型 (hypothesis/method/scale-up)")
    target_id: str = Field(..., description="目标ID")

    # 评估内容
    feasibility_status: FeasibilityStatus = Field(..., description="可行性状态")
    conditions: str = Field(default="", description="可行性条件")
    constraints: list[str] = Field(default_factory=list, description="约束条件列表")
    rationale: str = Field(default="", description="评估依据")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")
    assessed_by: str = Field(default="AUTHOR", description="评估者 (AUTHOR/REVIEWER/SYSTEM)")
    status: DataStatus = Field(
        default=DataStatus.REPORTED,
        description="数据状态"
    )

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# 新模型 4: ValidationPlan (验证计划)
# ---------------------------------------------------------------------------

class ValidationPlan(BaseModel):
    """验证计划 — 提出的实验验证方案。

    用于追踪未来工作建议和实验设计。
    """
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = Field(..., description="来源文档ID")

    # 验证目标
    validates_hypothesis_id: Optional[str] = Field(None, description="验证假设ID")
    validates_assertion_id: Optional[str] = Field(None, description="验证主张ID")

    # 计划内容
    method_description: str = Field(..., description="验证方法描述")
    control_experiments: list[str] = Field(
        default_factory=list,
        description="对照实验列表"
    )
    evaluation_metrics: list[str] = Field(
        default_factory=list,
        description="评估指标列表"
    )

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")
    proposed_by: str = Field(default="AUTHOR", description="提议者 (AUTHOR/REVIEWER/SYSTEM)")
    plan_status: PlanStatus = Field(
        default=PlanStatus.PROPOSED,
        description="计划状态"
    )

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# 现有模型扩展 (通过继承或组合)
# ---------------------------------------------------------------------------

class AssertionExtended(BaseModel):
    """Assertion 扩展版 — 新增元科学字段。

    注意：这是独立模型，不修改原 Assertion。
    使用时可通过 assertion.model_dump() + extension.model_dump() 合并。
    """
    assertion_id: str = Field(..., description="原 Assertion ID")

    # 新增字段 (全部 Optional)
    assertion_source: Optional[AssertionSource] = Field(
        None,
        description="主张来源 (作者陈述/系统推断)"
    )
    validation_status: Optional[str] = Field(
        None,
        description="验证状态 (validated/unvalidated/contested)"
    )
    scope_conditions: Optional[str] = Field(
        None,
        description="适用范围条件"
    )


class EvidenceExtended(BaseModel):
    """Evidence 扩展版 — 新增极性和强度字段。"""
    evidence_id: str = Field(..., description="原 Evidence ID")

    # 新增字段 (全部 Optional)
    evidence_polarity: Optional[EvidencePolarity] = Field(
        None,
        description="证据极性 (支持/挑战/限定)"
    )
    evidence_strength: Optional[str] = Field(
        None,
        description="证据强度 (strong/moderate/weak)"
    )
    qualification_note: Optional[str] = Field(
        None,
        description="限定说明"
    )


class ObservationExtended(BaseModel):
    """Observation 扩展版 — 新增可靠性字段。"""
    observation_id: str = Field(..., description="原 Observation ID")

    # 新增字段 (全部 Optional)
    reliability: Optional[str] = Field(
        None,
        description="可靠性 (HIGH/MEDIUM/LOW)"
    )


class ExperimentExtended(BaseModel):
    """Experiment 扩展版 — 新增状态和验证字段。"""
    experiment_id: str = Field(..., description="原 Experiment ID")

    # 新增字段 (全部 Optional)
    experiment_status: Optional[ExperimentStatus] = Field(
        None,
        description="实验状态 (已执行/提议)"
    )
    validates_hypothesis_ids: list[str] = Field(
        default_factory=list,
        description="验证假设ID列表"
    )
    feasibility_assessment: Optional[str] = Field(
        None,
        description="可行性评估ID"
    )


# ---------------------------------------------------------------------------
# 单篇知识聚合模型
# ---------------------------------------------------------------------------

class SinglePaperKnowledge(BaseModel):
    """单篇科学知识聚合 — 整合所有抽取的知识类型。

    用于组织一篇论文/专利的完整科学知识图谱。
    """
    document_id: str = Field(..., description="文档ID")

    # 核心知识
    assertions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="科学主张列表 (Assertion or AssertionExtended)"
    )
    evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        description="证据列表 (Evidence or EvidenceExtended)"
    )
    experiments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="实验列表 (Experiment or ExperimentExtended)"
    )
    observations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="观测列表 (Observation or ObservationExtended)"
    )

    # 元科学知识
    limitations: list[Limitation] = Field(
        default_factory=list,
        description="研究限制列表"
    )
    open_questions: list[OpenQuestion] = Field(
        default_factory=list,
        description="开放问题列表"
    )
    feasibility_assessments: list[Feasibility] = Field(
        default_factory=list,
        description="可行性评估列表"
    )
    validation_plans: list[ValidationPlan] = Field(
        default_factory=list,
        description="验证计划列表"
    )

    # 关系统计
    relationship_count: int = Field(default=0, description="关系总数")
    object_count: int = Field(default=0, description="对象总数")

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)
    extraction_version: str = Field(default="v1.0", description="抽取版本")


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    # 枚举
    "AssertionSource",
    "EvidencePolarity",
    "ExperimentStatus",
    "LimitationType",
    "QuestionType",
    "ResolutionStatus",
    "FeasibilityStatus",
    "PlanStatus",
    # 新模型
    "Limitation",
    "OpenQuestion",
    "Feasibility",
    "ValidationPlan",
    # 扩展模型
    "AssertionExtended",
    "EvidenceExtended",
    "ObservationExtended",
    "ExperimentExtended",
    # 聚合模型
    "SinglePaperKnowledge",
]
