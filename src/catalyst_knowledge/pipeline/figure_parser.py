"""FigureParser — 正式 Pipeline 阶段实现。

从 MinerU 产物中发现并结构化所有 Figure：
- 提取原始图像文件并计算 SHA256 哈希（可回溯到原始像素）
- 解析 caption 识别 Figure 编号与多子图结构 ((a)(b)(c) 等)
- 从 middle.json 获取图像在页面上的 bbox 坐标
- 关联正文中的 Figure 引用（复用 figure_text_association_v2）
- 生成稳定 SourceAnchor（page_idx + bbox + element_id）
- 与 Document IR element_id 关联
- 输出统一结构化 JSON

不做：
- 图像视觉内容解析（无凭证时标记 NOT_EXECUTED）
- 子图物理切分（仅标注存在多子图结构）
- 科学解释或推断

状态语义：
- PASS: 全部 figure 成功结构化
- PARTIAL: 部分 figure 结构化成功，部分失败
- FAILED: 无法发现任何 figure（MinerU 产物缺失或解析失败）
- NOT_EXECUTED: 视觉分析步骤因缺凭证未执行（不影响结构化 PASS）
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Data structures
# ============================================================================

@dataclass
class FigurePanel:
    """A detected sub-panel within a multi-panel figure."""
    panel_label: str  # e.g. "a", "(a)", "A", "(A)"
    description: str = ""  # text snippet associated with this panel


@dataclass
class FigureRecord:
    """Structured record for a single figure."""
    figure_id: str  # e.g. "F02_fig_01"
    document_id: str
    namespace: str
    figure_number: int  # 1 for "Figure 1"
    figure_label: str  # "Figure 1"
    caption: str
    caption_raw: list[str] = field(default_factory=list)
    page_idx: int = 0
    image_path: str = ""  # absolute path to extracted image file
    image_sha256: str = ""  # hash of original image file
    image_size_bytes: int = 0
    bbox: Optional[list[int]] = None  # [x0, y0, x1, y1] from middle.json
    page_size: Optional[list[int]] = None  # [width, height] of page
    panels: list[FigurePanel] = field(default_factory=list)
    has_panels: bool = False
    body_references: list[dict] = field(default_factory=list)
    source_anchor: dict = field(default_factory=dict)
    document_ir_element_id: Optional[str] = None
    panel_detection_method: str = "CAPTION_DERIVED"  # CAPTION_DERIVED | IMAGE_SEGMENTATION | UNRESOLVED
    visual_analysis_status: str = "NOT_EXECUTED"  # NOT_EXECUTED | PARTIAL | PASS | FAILED
    visual_analysis_note: str = "Visual content analysis requires vision model credentials"
    extraction_status: str = "PASS"  # PASS | PARTIAL | FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "figure_id": self.figure_id,
            "document_id": self.document_id,
            "namespace": self.namespace,
            "figure_number": self.figure_number,
            "figure_label": self.figure_label,
            "caption": self.caption,
            "caption_raw": self.caption_raw,
            "page_idx": self.page_idx,
            "image_path": self.image_path,
            "image_sha256": self.image_sha256,
            "image_size_bytes": self.image_size_bytes,
            "bbox": self.bbox,
            "page_size": self.page_size,
            "panels": [
                {"panel_label": p.panel_label, "description": p.description}
                for p in self.panels
            ],
            "has_panels": self.has_panels,
            "body_references": self.body_references,
            "source_anchor": self.source_anchor,
            "document_ir_element_id": self.document_ir_element_id,
            "panel_detection_method": self.panel_detection_method,
            "visual_analysis_status": self.visual_analysis_status,
            "visual_analysis_note": self.visual_analysis_note,
            "extraction_status": self.extraction_status,
        }


# ============================================================================
# Core parser
# ============================================================================

class FigureParser:
    """Parse figures from MinerU output into structured records."""

    # Pattern to detect "Figure N" at start of caption
    FIGURE_LABEL_PATTERN = re.compile(
        r"^\s*(?:FIGURE|FIG\.?)\s*(\d+[A-Za-z]?(?:\.\d+)?)",
        re.IGNORECASE,
    )
    # Pattern to detect sub-panel labels like (a), (A), (a)-(c), etc.
    PANEL_PATTERN = re.compile(
        r"\(([a-z])\)(?:\s*[-–]\s*\(([a-z])\))?"
        r"|\(([A-Z])\)(?:\s*[-–]\s*\(([A-Z])\))?"
        r"|[\s,;]\([a-zA-Z]\)\s+"
        r"|\b([a-zA-Z])\)\s+(?=[A-Z])",
    )
    # Pattern for explicit panel enumeration: (A) description (B) description
    PANEL_ENUM_PATTERN = re.compile(
        r"\(([a-zA-Z])\)\s*([^()]+?)(?=\([a-zA-Z]\)|$)",
    )

    def __init__(
        self,
        document_id: str,
        mineru_auto_dir: Path,
        namespace: Optional[str] = None,
        document_ir_content_list: Optional[list[dict]] = None,
    ):
        self.document_id = document_id
        self.namespace = namespace or document_id
        self.mineru_auto_dir = Path(mineru_auto_dir)
        self.content_list_path = self._find_content_list()
        self.middle_path = self.mineru_auto_dir / "main_middle.json"
        self._content_list: list[dict] = []
        self._middle: dict = {}
        self._page_image_index: dict[int, list[dict]] = {}
        # FIX-004: Store Document IR content_list for element_id lookup
        self._document_ir_content_list = document_ir_content_list or []

    def _find_content_list(self) -> Optional[Path]:
        candidates = [
            self.mineru_auto_dir / "main_content_list.json",
        ]
        candidates.extend(self.mineru_auto_dir.glob("*content_list.json"))
        for c in candidates:
            if c.exists():
                return c
        return None

    def load(self) -> None:
        """Load content_list.json and middle.json."""
        if self.content_list_path is None:
            raise FileNotFoundError(
                f"No content_list.json in {self.mineru_auto_dir}"
            )
        with open(self.content_list_path, "r", encoding="utf-8") as f:
            self._content_list = json.load(f)

        if self.middle_path.exists():
            with open(self.middle_path, "r", encoding="utf-8") as f:
                self._middle = json.load(f)
            self._build_page_image_index()

    def _build_page_image_index(self) -> None:
        """Build page_idx -> list of image entries from middle.json."""
        for page_info in self._middle.get("pdf_info", []):
            page_idx = page_info.get("page_idx", 0)
            images = page_info.get("images", [])
            if images:
                self._page_image_index[page_idx] = images

    def _lookup_document_ir_element_id(
        self, page_idx: int, image_index_on_page: int
    ) -> Optional[str]:
        """Look up element_id from Document IR content_list.
        
        FIX-004 P1-NEW-003: Match by page_idx and type=='image', then use
        image_index_on_page to select the correct item.
        """
        if not self._document_ir_content_list:
            return None
        
        # Find all image items on this page
        page_images = [
            item for item in self._document_ir_content_list
            if item.get("page_idx") == page_idx and item.get("type") == "image"
        ]
        
        if image_index_on_page < len(page_images):
            return page_images[image_index_on_page].get("element_id")
        
        return None

    def parse(self) -> list[FigureRecord]:
        """Run full figure parsing pipeline."""
        self.load()
        records: list[FigureRecord] = []
        fig_counter = 0
        
        # FIX-002: Track image index per page for accurate bbox lookup
        page_image_counter: dict[int, int] = {}

        for item in self._content_list:
            if item.get("type") != "image":
                continue
            fig_counter += 1
            
            page_idx = item.get("page_idx", 0)
            image_index_on_page = page_image_counter.get(page_idx, 0)
            page_image_counter[page_idx] = image_index_on_page + 1
            
            try:
                record = self._parse_single_figure(item, fig_counter, image_index_on_page)
                records.append(record)
            except Exception as e:
                logger.warning(
                    "[%s] Failed to parse figure #%d: %s",
                    self.document_id, fig_counter, e,
                )
                records.append(FigureRecord(
                    figure_id=f"{self.document_id}_fig_{fig_counter:02d}",
                    document_id=self.document_id,
                    namespace=self.namespace,
                    figure_number=fig_counter,
                    figure_label=f"Figure {fig_counter}",
                    caption="",
                    extraction_status="FAILED",
                    visual_analysis_status="NOT_EXECUTED",
                    visual_analysis_note=f"Parse failed: {e}",
                ))

        return records

    def _parse_single_figure(
        self, item: dict, fig_counter: int, image_index_on_page: int = 0
    ) -> FigureRecord:
        """Parse a single image item from content_list."""
        caption_raw = item.get("img_caption") or []
        caption = " ".join(caption_raw).strip()

        figure_number, figure_label = self._extract_figure_number(
            caption, fig_counter
        )

        image_rel_path = item.get("img_path", "")
        image_abs_path = self._resolve_image_path(image_rel_path)

        image_sha256 = ""
        image_size = 0
        if image_abs_path is not None and image_abs_path.exists():
            image_sha256 = compute_file_sha256(image_abs_path)
            image_size = image_abs_path.stat().st_size

        page_idx = item.get("page_idx", 0)
        # FIX-002: Use image_index_on_page for accurate bbox lookup
        bbox, page_size = self._lookup_bbox(page_idx, image_index_on_page)

        panels = self._detect_panels(caption)

        source_anchor = self._build_source_anchor(
            page_idx, bbox, page_size, image_abs_path, image_sha256,
        )

        # FIX-004 P1-NEW-003: Look up actual content_list element_id from Document IR
        document_ir_element_id = self._lookup_document_ir_element_id(
            page_idx, image_index_on_page
        )

        return FigureRecord(
            figure_id=f"{self.document_id}_fig_{fig_counter:02d}",
            document_id=self.document_id,
            namespace=self.namespace,
            figure_number=figure_number,
            figure_label=figure_label,
            caption=caption,
            caption_raw=caption_raw,
            page_idx=page_idx,
            image_path=str(image_abs_path) if image_abs_path else "",
            image_sha256=image_sha256,
            image_size_bytes=image_size,
            bbox=bbox,
            page_size=page_size,
            panels=panels,
            has_panels=len(panels) > 0,
            source_anchor=source_anchor,
            document_ir_element_id=document_ir_element_id,
            visual_analysis_status="NOT_EXECUTED",
            visual_analysis_note=(
                "Visual content analysis requires vision model credentials"
            ),
            extraction_status="PASS",
        )

    def _extract_figure_number(
        self, caption: str, default: int
    ) -> tuple[int, str]:
        """Extract figure number from caption text."""
        if not caption:
            return default, f"Figure {default}"
        m = self.FIGURE_LABEL_PATTERN.match(caption)
        if m:
            num_str = m.group(1)
            try:
                num = int(re.sub(r"[^0-9]", "", num_str))
                suffix = num_str[len(str(num)):]
                label = f"Figure {num}{suffix}"
                return num, label
            except ValueError:
                pass
        return default, f"Figure {default}"

    def _resolve_image_path(self, rel_path: str) -> Optional[Path]:
        """Resolve relative image path to absolute path."""
        if not rel_path:
            return None
        p = Path(rel_path)
        if p.is_absolute():
            return p
        return (self.mineru_auto_dir / p).resolve()

    def _lookup_bbox(
        self, page_idx: int, image_index_on_page: int
    ) -> tuple[Optional[list[int]], Optional[list[int]]]:
        """Look up image bbox from middle.json page data.
        
        FIX-002: Use image index instead of filename matching to avoid
        fallback to first image's bbox when span text is empty.
        """
        page_images = self._page_image_index.get(page_idx, [])
        if not page_images:
            return None, None

        # FIX-002: Direct index access instead of filename matching
        if image_index_on_page < len(page_images):
            img_entry = page_images[image_index_on_page]
            entry_bbox = img_entry.get("bbox")
            page_size = self._get_page_size(page_idx)
            return entry_bbox, page_size
        
        # Fallback: index out of range
        logger.warning(
            "[%s] Image index %d out of range for page %d (has %d images)",
            self.document_id, image_index_on_page, page_idx, len(page_images)
        )
        return None, None

    def _get_page_size(self, page_idx: int) -> Optional[list[int]]:
        for page_info in self._middle.get("pdf_info", []):
            if page_info.get("page_idx") == page_idx:
                return page_info.get("page_size")
        return None

    def _detect_panels(self, caption: str) -> list[FigurePanel]:
        """Detect multi-panel structure from caption text."""
        if not caption:
            return []
        panels: list[FigurePanel] = []
        seen: set[str] = set()
        for m in self.PANEL_ENUM_PATTERN.finditer(caption):
            label = m.group(1)
            desc = m.group(2).strip() if m.group(2) else ""
            key = label.lower()
            if key not in seen:
                seen.add(key)
                panels.append(FigurePanel(
                    panel_label=f"({label})",
                    description=desc.rstrip(" ,;"),
                ))
        if len(panels) < 2:
            return []
        return panels

    def _build_source_anchor(
        self,
        page_idx: int,
        bbox: Optional[list[int]],
        page_size: Optional[list[int]],
        image_abs_path: Optional[Path],
        image_sha256: str,
    ) -> dict[str, Any]:
        """Build stable SourceAnchor for this figure."""
        anchor: dict[str, Any] = {
            "document_id": self.document_id,
            "namespace": self.namespace,
            "element_type": "FIGURE",
            "page_idx": page_idx,
            "page_number": page_idx + 1,
        }
        if bbox:
            anchor["bbox"] = {
                "x0": bbox[0], "y0": bbox[1],
                "x1": bbox[2], "y1": bbox[3],
                "coordinate_system": "pt_from_top_left",
            }
        if page_size:
            anchor["page_size"] = {"width": page_size[0], "height": page_size[1]}
        if image_abs_path is not None:
            anchor["image_file"] = {
                "path": str(image_abs_path),
                "filename": image_abs_path.name,
                "sha256": image_sha256,
            }
        anchor["anchor_version"] = "1.0.0"
        return anchor

    def _infer_document_ir_element_id(self, page_idx: int) -> Optional[str]:
        """Infer Document IR element ID from page index."""
        return f"{self.namespace}_p{page_idx}_img"


# ============================================================================
# Body text reference association
# ============================================================================

def associate_body_references(
    figures: list[FigureRecord],
    document_ir_path: Optional[Path],
) -> list[FigureRecord]:
    """Associate each figure with references found in body text.

    Reads Document IR blocks and extracts text references like "Figure 1",
    "Fig. 2a", etc. Does NOT raise if Document IR is missing.
    """
    if document_ir_path is None or not document_ir_path.exists():
        logger.warning(
            "Document IR not found at %s; skipping body reference association",
            document_ir_path,
        )
        return figures

    try:
        with open(document_ir_path, "r", encoding="utf-8") as f:
            doc_ir = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load Document IR: %s", e)
        return figures

    body_text_items: list[dict] = []
    content_list = doc_ir.get("content_list", [])
    for item in content_list:
        if item.get("type") in ("text", "para", "title"):
            body_text_items.append(item)
    if not body_text_items:
        for block in doc_ir.get("blocks", []):
            if block.get("type") in ("text", "para"):
                body_text_items.append(block)

    ref_pattern = re.compile(
        r"(?:Figure|Fig\.?|FIGURE|FIG)\s*(\d+[A-Za-z]?(?:\.\d+)?)"
        r"(?:\s*\(?([a-zA-Z])\))?",
        re.IGNORECASE,
    )

    for fig in figures:
        refs: list[dict] = []
        for item in body_text_items:
            text = item.get("text") or _extract_block_text(item)
            if not text:
                continue
            for m in ref_pattern.finditer(text):
                try:
                    ref_num = int(re.sub(r"[^0-9]", "", m.group(1)))
                except ValueError:
                    continue
                if ref_num != fig.figure_number:
                    continue
                panel = m.group(2) or ""
                refs.append({
                    "element_id": item.get("element_id", ""),
                    "page_idx": item.get("page_idx", 0),
                    "raw_text_snippet": text.strip()[:200],
                    "match_span": [m.start(), m.end()],
                    "panel": panel,
                    "confidence": 0.9,
                    "association_type": "explicit_reference",
                })
        fig.body_references = refs

    return figures


def _extract_block_text(block: dict) -> str:
    """Extract plain text from a Document IR block."""
    if "text" in block and isinstance(block["text"], str):
        return block["text"]
    parts: list[str] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = span.get("text", "")
            if t:
                parts.append(t)
    return " ".join(parts)


# ============================================================================
# Utilities
# ============================================================================

def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def find_mineru_auto_dir(mineru_output: str | Path, document_id: str) -> Optional[Path]:
    """Locate the auto/ directory for a document's MinerU output."""
    base = Path(mineru_output)
    if not base.exists():
        return None
    candidates = [
        base / f"{document_id}_batch" / "main" / "auto",
        base / f"{document_id}_batch" / "auto",
        base / f"{document_id}_regression" / "main" / "auto",
        base / f"{document_id}_regression" / "auto",
        base / document_id / "main" / "auto",
        base / document_id / "auto",
        base / "main" / "auto",
        base / "auto",
    ]
    for c in candidates:
        if c.exists() and list(c.glob("*content_list.json")):
            return c
    for d in base.iterdir():
        if d.is_dir() and document_id.lower() in d.name.lower():
            for sub in [d / "main" / "auto", d / "auto"]:
                if sub.exists() and list(sub.glob("*content_list.json")):
                    return sub
    return None


# ============================================================================
# Pipeline entry point
# ============================================================================

def run_figure_parser(
    document_id: str,
    mineru_output: str,
    output_dir: str,
    namespace: Optional[str] = None,
    document_ir_path: Optional[str] = None,
    **kwargs,
) -> dict[str, Any]:
    """Pipeline-callable figure parser entry point.

    Returns a dict matching the FigureParserOutput contract.
    """
    if namespace is None:
        namespace = document_id

    auto_dir = find_mineru_auto_dir(mineru_output, document_id)
    if auto_dir is None:
        return {
            "document_id": document_id,
            "namespace": namespace,
            "figure_parser_status": "FAILED",
            "figure_parser_output_path": "",
            "figures_processed": 0,
            "figures_failed": 0,
            "extraction_source": "FRESH",
            "error": f"MinerU auto/ directory not found for '{document_id}' in {mineru_output}",
            "implementation_status": "FAILED",
            "source_anchor_preserved": True,
        }

    try:
        # FIX-004: Load Document IR content_list for element_id lookup
        doc_ir_content_list = []
        doc_ir_path = Path(document_ir_path) if document_ir_path else None
        if doc_ir_path and doc_ir_path.exists():
            try:
                with open(doc_ir_path, "r", encoding="utf-8") as f:
                    doc_ir = json.load(f)
                doc_ir_content_list = doc_ir.get("content_list", [])
                logger.info(
                    "[%s] Loaded Document IR with %d content_list items",
                    document_id, len(doc_ir_content_list)
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("[%s] Failed to load Document IR: %s", document_id, e)
        
        parser = FigureParser(
            document_id, auto_dir, namespace,
            document_ir_content_list=doc_ir_content_list
        )
        figures = parser.parse()

        figures = associate_body_references(figures, doc_ir_path)

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        figures_data = [f.to_dict() for f in figures]

        processed = sum(1 for f in figures if f.extraction_status == "PASS")
        failed = sum(1 for f in figures if f.extraction_status == "FAILED")

        if failed == len(figures) and figures:
            overall_status = "FAILED"
        elif failed > 0:
            overall_status = "PARTIAL"
        else:
            overall_status = "PASS"

        output_doc = {
            "parser_id": "FigureParser",
            "parser_version": "1.0.0",
            "document_id": document_id,
            "namespace": namespace,
            "mineru_auto_dir": str(auto_dir),
            "content_list_path": str(parser.content_list_path),
            "figure_count": len(figures_data),
            "figures_processed": processed,
            "figures_failed": failed,
            "overall_status": overall_status,
            "figures": figures_data,
            "visual_analysis_summary": {
                "status": "NOT_EXECUTED",
                "note": "Vision model credentials not configured",
            },
        }

        output_file = out_path / f"{document_id}_figure_parser.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_doc, f, indent=2, ensure_ascii=False)

        logger.info(
            "[%s] FigureParser: %d figures (%d PASS, %d FAILED) -> %s",
            document_id, len(figures_data), processed, failed, output_file,
        )

        return {
            "document_id": document_id,
            "namespace": namespace,
            "figure_parser_status": overall_status,
            "figure_parser_output_path": str(output_file),
            "figures_processed": processed,
            "figures_failed": failed,
            "figure_count": len(figures_data),
            "extraction_source": "FRESH",
            "implementation_status": "PASS",
            "source_anchor_preserved": True,
        }

    except Exception as e:
        logger.error("[%s] FigureParser failed: %s", document_id, e)
        return {
            "document_id": document_id,
            "namespace": namespace,
            "figure_parser_status": "FAILED",
            "figure_parser_output_path": "",
            "figures_processed": 0,
            "figures_failed": 0,
            "extraction_source": "FRESH",
            "error": str(e),
            "implementation_status": "FAILED",
            "source_anchor_preserved": False,
        }
