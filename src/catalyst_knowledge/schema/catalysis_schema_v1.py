"""Catalysis Schema V1 — 核心数据契约。

参考标准：
- CoreMeta4Cat: 催化实验元数据主框架
- ORD (Open Reaction Database): 反应实验细节
- Voc4Cat: 催化受控词表
- ChEBI/RDKit: 化学实体规范化

设计原则：
1. 实验与观测分开 (Experiment vs Observation)
2. 科学主张与实际测量分开 (Assertion vs Evidence)
3. 表/图/SI 与原始文档元素之间可回链 (SourceAnchor)
4. 双层分类：文献级 Taxonomy + 对象级 Ontology
5. 数据状态显式标注 (DataStatus enum)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# 基础枚举与类型
# ---------------------------------------------------------------------------

class DataStatus(str, Enum):
    """数据状态枚举 — 标注每个字段的来源可靠性。

    REPORTED: 原文明确报告
    NORMALIZED: 经单位换算或标准化处理
    INFERRED: 从上下文推断（需标注依据）
    PREDICTED: 模型预测值
    UNKNOWN: 未知，细分为：
        - NOT_REPORTED: 原文未报告
        - NOT_EXTRACTED: 未进行抽取
        - NOT_APPLICABLE: 不适用
        - CONFLICTED: 存在冲突数据
    """
    REPORTED = "REPORTED"
    NORMALIZED = "NORMALIZED"
    INFERRED = "INFERRED"
    PREDICTED = "PREDICTED"
    NOT_REPORTED = "NOT_REPORTED"
    NOT_EXTRACTED = "NOT_EXTRACTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTED = "CONFLICTED"


class DocumentType(str, Enum):
    """文献类型。"""
    RESEARCH = "research"          # 研究论文
    REVIEW = "review"              # 综述
    COMMUNICATION = "communication"  # 通讯
    PATENT = "patent"              # 专利
    DATASHEET = "datasheet"        # 数据表
    UNKNOWN = "unknown"


class ElementType(str, Enum):
    """文档元素类型。"""
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    SCHEME = "scheme"              # 反应式/流程图
    EQUATION = "equation"
    CODE = "code"
    REFERENCE = "reference"


# ---------------------------------------------------------------------------
# 来源锚点 (SourceAnchor)
# ---------------------------------------------------------------------------

class SourceAnchor(BaseModel):
    """字段级来源锚点 — 追踪每个数据项的原始位置。

    用于审计和溯源，确保每个抽取值都能回链到原文。
    """
    document_id: str = Field(..., description="来源文档ID")
    element_type: ElementType = Field(..., description="元素类型")
    element_id: str = Field(..., description="元素ID (如 table_3, figure_1)")
    location: str = Field(default="", description="具体位置 (如 'Row 2, Column 3')")
    page: Optional[int] = Field(None, description="页码")
    block_index: Optional[int] = Field(None, description="Document IR 中的块索引")
    raw_text: Optional[str] = Field(None, description="原始文本片段")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="锚点置信度")

    model_config = {"frozen": True}


class ValueWithSource(BaseModel):
    """带来源的值 — 同时记录原始值、标准值和来源。"""
    raw_value: str = Field(..., description="原文报告的原始值 (含单位)")
    normalized_value: Optional[float] = Field(None, description="标准化后的数值")
    normalized_unit: Optional[str] = Field(None, description="标准化单位")
    status: DataStatus = Field(default=DataStatus.REPORTED, description="数据状态")
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")
    extraction_version: str = Field(default="v1", description="抽取版本")
    notes: Optional[str] = Field(None, description="备注 (如推断依据)")

    @model_validator(mode="after")
    def check_normalized_consistency(self) -> "ValueWithSource":
        """确保标准化值与单位同时存在。"""
        if self.normalized_value is not None and self.normalized_unit is None:
            raise ValueError("normalized_unit required when normalized_value is set")
        return self


# ---------------------------------------------------------------------------
# 文档与附件 (Document, Attachment, DocumentElement)
# ---------------------------------------------------------------------------

class Attachment(BaseModel):
    """附件 — SI、表格数据文件、图像等。"""
    attachment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = Field(..., description="文件名")
    file_type: str = Field(..., description="文件类型 (pdf, xlsx, csv, png, etc.)")
    file_hash: Optional[str] = Field(None, description="文件SHA256哈希")
    file_size: Optional[int] = Field(None, description="文件大小(字节)")
    url: Optional[str] = Field(None, description="来源URL")
    relation: str = Field(default="supplementary", description="与主文档关系")
    parsed_content_id: Optional[str] = Field(None, description="解析后的Document IR ID")

    model_config = {"frozen": True}


class DocumentElement(BaseModel):
    """文档元素 — MinerU 解析后的 Document IR 元素。"""
    element_id: str = Field(..., description="元素唯一ID")
    element_type: ElementType = Field(..., description="元素类型")
    content: str = Field(default="", description="元素内容 (文本/Markdown/JSON)")
    bbox: Optional[tuple[float, float, float, float]] = Field(None, description="边界框")
    page: int = Field(default=0, description="页码")
    children: list[str] = Field(default_factory=list, description="子元素ID列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元素元数据")

    # 表格专用
    table_headers: Optional[list[list[str]]] = Field(None, description="多级表头")
    table_footnotes: Optional[list[str]] = Field(None, description="表格脚注")

    # 图片专用
    image_path: Optional[str] = Field(None, description="裁剪后的图片路径")
    caption: Optional[str] = Field(None, description="图注")
    is_chemical_diagram: bool = Field(default=False, description="是否为化学结构图")


class Document(BaseModel):
    """文档 — 论文、专利或其他文献的主体记录。"""
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doi: Optional[str] = Field(None, description="DOI")
    title: str = Field(..., description="标题")
    authors: list[str] = Field(default_factory=list, description="作者列表")
    publication_year: Optional[int] = Field(None, description="发表年份")
    journal: Optional[str] = Field(None, description="期刊/来源")
    document_type: DocumentType = Field(default=DocumentType.UNKNOWN)
    abstract: Optional[str] = Field(None, description="摘要")

    # 专利专用
    patent_number: Optional[str] = Field(None, description="专利号")
    patent_family: Optional[str] = Field(None, description="专利族")
    application_date: Optional[datetime] = Field(None, description="申请日")
    publication_date: Optional[datetime] = Field(None, description="公开日")
    grant_date: Optional[datetime] = Field(None, description="授权日")

    # 关联
    attachments: list[Attachment] = Field(default_factory=list, description="附件列表")
    elements: list[DocumentElement] = Field(default_factory=list, description="文档元素")

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    parser_version: str = Field(default="MinerU-v1", description="解析器版本")

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: Optional[str]) -> Optional[str]:
        """验证DOI格式。"""
        if v is not None and not v.startswith("10."):
            raise ValueError(f"Invalid DOI format: {v}")
        return v


# ---------------------------------------------------------------------------
# 双层分类：文献级 Taxonomy + 对象级 Ontology
# ---------------------------------------------------------------------------

class TaxonomyAssignment(BaseModel):
    """文献级多标签分类。

    第一层：基于元数据的初步分类
    第二层：基于全文的复核分类
    """
    document_id: str = Field(..., description="文档ID")
    layer: str = Field(..., description="分类层级: metadata / fulltext / reviewed")

    # Voc4Cat 受控词表标签
    reaction_types: list[str] = Field(default_factory=list, description="反应类型标签")
    catalyst_types: list[str] = Field(default_factory=list, description="催化剂类型标签")
    material_classes: list[str] = Field(default_factory=list, description="材料类别标签")
    application_areas: list[str] = Field(default_factory=list, description="应用领域标签")

    # 置信度与依据
    confidence: dict[str, float] = Field(default_factory=dict, description="各标签置信度")
    evidence: list[SourceAnchor] = Field(default_factory=list, description="分类依据")

    # 历史
    assigned_at: datetime = Field(default_factory=datetime.now)
    assigned_by: str = Field(default="auto", description="分配者 (auto / reviewer_name)")
    revision_history: list[dict[str, Any]] = Field(default_factory=list, description="修订历史")


class OntologyMapping(BaseModel):
    """对象级本体映射 — 科学对象的标准ID对齐。"""
    local_name: str = Field(..., description="本地名称/同义词")
    standard_id: Optional[str] = Field(None, description="标准ID (ChEBI/InChI/SMILES)")
    ontology_source: Optional[str] = Field(None, description="来源本体 (ChEBI/Voc4Cat)")
    mapping_confidence: float = Field(default=1.0, description="映射置信度")
    is_resolved: bool = Field(default=False, description="是否已解决歧义")
    alternatives: list[str] = Field(default_factory=list, description="候选标准ID")


# ---------------------------------------------------------------------------
# 化学实体与催化剂
# ---------------------------------------------------------------------------

class ChemicalEntity(BaseModel):
    """化学实体 — 催化剂、底物、产物、溶剂等。"""
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="名称")
    role: str = Field(..., description="角色: catalyst/substrate/product/solvent/reagent/support/ligand")

    # 化学标识
    smiles: Optional[str] = Field(None, description="SMILES")
    inchi: Optional[str] = Field(None, description="InChI")
    chebi_id: Optional[str] = Field(None, description="ChEBI ID")
    formula: Optional[str] = Field(None, description="分子式")
    molecular_weight: Optional[float] = Field(None, description="分子量")

    # 本体映射
    ontology: Optional[OntologyMapping] = Field(None, description="本体映射")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")


class CatalystSample(BaseModel):
    """催化剂样品 — 具体的催化剂制备记录。"""
    sample_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # 组成
    active_component: Optional[ChemicalEntity] = Field(None, description="活性组分")
    support: Optional[ChemicalEntity] = Field(None, description="载体")
    ligand: Optional[ChemicalEntity] = Field(None, description="配体")
    promoter: Optional[ChemicalEntity] = Field(None, description="助剂")
    composition_description: str = Field(default="", description="组成描述 (如 'Pt/TiO2 1wt%')")

    # 制备
    synthesis_method: str = Field(default="", description="合成方法")
    synthesis_details: dict[str, Any] = Field(default_factory=dict, description="合成细节")

    # 表征
    particle_size: Optional[ValueWithSource] = Field(None, description="粒径")
    surface_area: Optional[ValueWithSource] = Field(None, description="比表面积")
    characterization_methods: list[str] = Field(default_factory=list, description="表征方法")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")


# ---------------------------------------------------------------------------
# 反应、实验与观测
# ---------------------------------------------------------------------------

class Reaction(BaseModel):
    """反应 — 化学反应的定义。"""
    reaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reaction_type: str = Field(..., description="反应类型 (来自Voc4Cat)")
    name: str = Field(default="", description="反应名称")

    # 参与者
    substrates: list[ChemicalEntity] = Field(default_factory=list, description="底物")
    products: list[ChemicalEntity] = Field(default_factory=list, description="产物")
    catalyst: Optional[CatalystSample] = Field(None, description="催化剂")
    reagents: list[ChemicalEntity] = Field(default_factory=list, description="试剂")
    solvents: list[ChemicalEntity] = Field(default_factory=list, description="溶剂")

    # 本体映射
    ontology: Optional[OntologyMapping] = Field(None, description="反应本体映射")


class Experiment(BaseModel):
    """实验 — 具体的实验执行记录。

    注意：Experiment 与 Observation 分开。
    Experiment 记录实验设置，Observation 记录实验结果。
    """
    experiment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reaction: Reaction = Field(..., description="关联反应")

    # 实验条件
    temperature: Optional[ValueWithSource] = Field(None, description="温度")
    pressure: Optional[ValueWithSource] = Field(None, description="压力")
    time: Optional[ValueWithSource] = Field(None, description="反应时间")
    atmosphere: Optional[str] = Field(None, description="气氛")
    stirring_rate: Optional[ValueWithSource] = Field(None, description="搅拌速率")

    # 催化剂用量
    catalyst_loading: Optional[ValueWithSource] = Field(None, description="催化剂负载量")
    substrate_amount: Optional[ValueWithSource] = Field(None, description="底物用量")

    # 实验细节
    procedure: str = Field(default="", description="实验步骤描述")
    scale: str = Field(default="", description="规模 (mg/mmol/mol)")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")
    source_document_id: Optional[str] = Field(None, description="来源文档ID")


class Observation(BaseModel):
    """观测 — 实验结果的具体测量值。"""
    observation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str = Field(..., description="关联实验ID")

    # 测量值
    metric_name: str = Field(..., description="指标名称 (conversion/yield/selectivity/TOF等)")
    value: ValueWithSource = Field(..., description="测量值")

    # 条件标注
    at_conversion: Optional[float] = Field(None, description="在特定转化率下")
    at_time_point: Optional[float] = Field(None, description="在特定时间点")
    product_specification: Optional[str] = Field(None, description="产物规格 (如 'major product')")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")


# ---------------------------------------------------------------------------
# 科学主张与证据
# ---------------------------------------------------------------------------

class Assertion(BaseModel):
    """科学主张 — 论文中提出的科学论断。

    注意：Assertion 与 Evidence 分开。
    Assertion 是主张内容，Evidence 是支持证据。
    """
    assertion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = Field(..., description="主张内容")
    assertion_type: str = Field(..., description="主张类型 (mechanism/finding/hypothesis/conclusion)")

    # 关联
    experiment_ids: list[str] = Field(default_factory=list, description="支持的实验ID")
    observation_ids: list[str] = Field(default_factory=list, description="支持的观测ID")
    document_id: str = Field(..., description="来源文档ID")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")
    confidence: float = Field(default=1.0, description="主张置信度")


class Evidence(BaseModel):
    """证据 — 支持科学主张的具体数据。"""
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    assertion_id: str = Field(..., description="支持的主张ID")

    # 证据类型
    evidence_type: str = Field(..., description="证据类型 (experimental/computational/literature)")
    data_source: str = Field(..., description="数据来源 (table/figure/text/SI)")

    # 关联数据
    observation_ids: list[str] = Field(default_factory=list, description="关联观测ID")
    raw_values: list[dict[str, Any]] = Field(default_factory=list, description="原始数据值")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")


# ---------------------------------------------------------------------------
# 专利专用扩展
# ---------------------------------------------------------------------------

class PatentClaim(BaseModel):
    """专利权利要求 — 与实验证据分开存储。"""
    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patent_document_id: str = Field(..., description="专利文档ID")
    claim_number: int = Field(..., description="权利要求编号")
    claim_type: str = Field(..., description="类型: independent/dependent")
    text: str = Field(..., description="权利要求文本")

    # 范围标注
    covers_examples: bool = Field(default=False, description="是否覆盖实施例")
    scope_note: str = Field(default="", description="范围说明")


class PatentExample(BaseModel):
    """专利实施例 — 具体的实验示例。"""
    example_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patent_document_id: str = Field(..., description="专利文档ID")
    example_number: str = Field(..., description="实施例编号")
    example_type: str = Field(..., description="类型: example/comparative_example")

    # 关联实验
    experiment: Optional[Experiment] = Field(None, description="关联实验")
    results: list[Observation] = Field(default_factory=list, description="结果观测")

    # 来源
    source: Optional[SourceAnchor] = Field(None, description="来源锚点")


# ---------------------------------------------------------------------------
# Schema 版本与元数据
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"
SCHEMA_NAME = "Catalysis Schema V1"


class SchemaMetadata(BaseModel):
    """Schema 元数据 — 记录抽取使用的 Schema 版本。"""
    schema_name: str = Field(default=SCHEMA_NAME)
    schema_version: str = Field(default=SCHEMA_VERSION)
    extraction_timestamp: datetime = Field(default_factory=datetime.now)
    extractor_name: str = Field(default="unknown", description="抽取工具名称")
    extractor_version: str = Field(default="unknown", description="抽取工具版本")
    prompt_version: Optional[str] = Field(None, description="使用的 Prompt 版本")


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    # 枚举
    "DataStatus",
    "DocumentType",
    "ElementType",
    # 来源
    "SourceAnchor",
    "ValueWithSource",
    # 文档
    "Attachment",
    "DocumentElement",
    "Document",
    # 分类
    "TaxonomyAssignment",
    "OntologyMapping",
    # 化学
    "ChemicalEntity",
    "CatalystSample",
    # 反应
    "Reaction",
    "Experiment",
    "Observation",
    # 主张
    "Assertion",
    "Evidence",
    # 专利
    "PatentClaim",
    "PatentExample",
    # 元数据
    "SchemaMetadata",
    "SCHEMA_VERSION",
    "SCHEMA_NAME",
]
