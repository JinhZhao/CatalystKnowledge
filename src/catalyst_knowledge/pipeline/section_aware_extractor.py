"""Section-aware content loader for scientific document extraction.

Parses MinerU content_list.json preserving document structure (sections,
pages, element types), builds targeted chunks for LLM extraction, and
tracks character offsets for SourceAnchor generation.

Replaces the flat text + 6000-char truncation approach in extraction_adapter.py.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ChunkBudgetExceeded(Exception):
    """Raised when a chunk exceeds the configured max_chunk_chars hard limit."""


@dataclass
class DocumentSection:
    """A logical section of a scientific document."""
    section_id: str
    title: str
    level: int
    start_idx: int
    end_idx: int
    page_start: int
    page_end: int
    char_offset_start: int
    char_offset_end: int
    text_content: str
    elements: list[dict] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text_content)


@dataclass
class ContentElement:
    """A single element from content_list.json with position tracking."""
    index: int
    element_type: str
    text: str
    page_idx: int
    text_level: Optional[int]
    char_offset: int
    raw: dict


@dataclass
class ExtractionChunk:
    """A chunk of content targeted at a specific extraction dimension."""
    chunk_id: str
    dimension: str
    sections: list[str]
    content: str
    char_offset_start: int
    char_offset_end: int
    page_range: tuple[int, int]
    element_indices: list[int]
    context_before: str = ""
    context_after: str = ""
    document_id: str = ""
    input_mode: str = "full_text"
    overlap_chars: int = 0
    estimated_tokens: int = 0

    @property
    def total_chars(self) -> int:
        return len(self.content) + len(self.context_before) + len(self.context_after)

    def __post_init__(self):
        if self.estimated_tokens == 0 and self.content:
            self.estimated_tokens = estimate_tokens(self.content)


CHARS_PER_TOKEN = 3.5
# NOTE: This is a heuristic for English scientific prose. Real tokenizers
# (tiktoken, sentencepiece) vary 2.5-4.5 chars/token depending on language,
# formula density, and table markup. The budget code below uses this estimate
# with a safety margin; do NOT cite it as "exact token count".


def estimate_tokens(text: str) -> int:
    """Heuristic token estimate: len(text) / 3.5 + 1.

    NOT an exact tokenizer count. This is a conservative heuristic tuned for
    English catalysis papers. Actual token count may differ ±25% depending on
    text composition (formulas, tables, non-ASCII, code). The budget logic
    uses this only as a routing signal (full_text vs chunked) and relies on
    a hard per-chunk char cap (max_chunk_chars) as the binding constraint.
    """
    if not text:
        return 0
    return int(len(text) / CHARS_PER_TOKEN) + 1


@dataclass
class TokenBudget:
    """Token budget for a single LLM call.

    All fields are HEURISTIC token estimates derived from character counts
    using CHARS_PER_TOKEN (3.5 chars/token). They are routing signals, not
    exact tokenizer counts. The hard binding constraint is max_chunk_chars
    enforced at chunk assembly time.
    """
    max_input_tokens: int
    max_output_tokens: int
    system_prompt_tokens: int = 0
    user_prompt_overhead_tokens: int = 0

    @property
    def available_for_content(self) -> int:
        return max(
            0,
            self.max_input_tokens
            - self.system_prompt_tokens
            - self.user_prompt_overhead_tokens,
        )

    @property
    def available_content_chars(self) -> int:
        return int(self.available_for_content * CHARS_PER_TOKEN)

    def check_content_fits(self, content: str) -> bool:
        return estimate_tokens(content) <= self.available_for_content


DIMENSION_SECTION_RELEVANCE = {
    "catalyst_design": [
        "experimental", "catalyst preparation", "synthesis", "materials",
        "introduction", "results", "preparation"
    ],
    "characterization": [
        "experimental", "catalyst characterization", "characterization",
        "results", "physicochemical", "optical", "properties"
    ],
    "performance": [
        "results", "performance", "catalytic", "activity", "conversion",
        "selectivity", "discussion", "odhp", "propane"
    ],
    "mechanism": [
        "results", "discussion", "mechanism", "pathway", "intermediate",
        "lsp", "active site"
    ],
    "structure_activity": [
        "results", "discussion", "structure-activity", "relationship",
        "correlation", "surface area", "particle size", "morphology"
    ],
    "reliability": [
        "results", "stability", "durability", "cycle", "time on stream",
        "deactivation", "discussion", "performance", "photothermal",
        "conversion", "long-term"
    ],
}


class SectionAwareContentLoader:
    """Loads and structures MinerU content_list.json for section-aware extraction."""

    SECTION_HEADER_OVERHEAD = 60

    def __init__(
        self,
        content_list_path: Path,
        max_chunk_chars: int = 8000,
        token_budget: Optional[TokenBudget] = None,
        document_id: str = "",
        overlap_paragraphs: int = 1,
    ):
        self.content_list_path = Path(content_list_path)
        self.document_id = document_id
        self.overlap_paragraphs = overlap_paragraphs
        self.max_chunk_chars = max_chunk_chars
        self.token_budget = token_budget
        if token_budget is not None:
            budget_chars = token_budget.available_content_chars
            if budget_chars < max_chunk_chars:
                logger.info(
                    "Token budget limits content to %d chars (vs max_chunk_chars=%d)",
                    budget_chars, max_chunk_chars,
                )
                self.max_chunk_chars = budget_chars
        self._content_list: list[dict] = []
        self._elements: list[ContentElement] = []
        self._sections: list[DocumentSection] = []
        self._full_text: str = ""
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        with open(self.content_list_path, "r", encoding="utf-8") as f:
            self._content_list = json.load(f)
        self._build_elements()
        self._build_sections()
        self._loaded = True
        logger.info(
            "Loaded %d elements, %d sections, %d chars from %s",
            len(self._elements), len(self._sections),
            len(self._full_text), self.content_list_path.name,
        )

    def _build_elements(self) -> None:
        offset = 0
        for i, item in enumerate(self._content_list):
            elem_type = item.get("type", "text")
            if elem_type == "text":
                text = item.get("text", "")
            elif elem_type == "image":
                captions = item.get("img_caption", [])
                text = " ".join(captions) if captions else f"[Image: {item.get('img_path', '')}]"
            elif elem_type == "table":
                captions = item.get("table_caption", [])
                text = " ".join(captions) if captions else f"[Table: {item.get('img_path', '')}]"
            else:
                text = item.get("text", "")

            elem = ContentElement(
                index=i,
                element_type=elem_type,
                text=text,
                page_idx=item.get("page_idx", 0),
                text_level=item.get("text_level"),
                char_offset=offset,
                raw=item,
            )
            self._elements.append(elem)
            offset += len(text) + 1

        self._full_text = "\n".join(e.text for e in self._elements if e.text.strip())

    def _build_sections(self) -> None:
        heading_indices = []
        for i, elem in enumerate(self._elements):
            if elem.text_level is not None and elem.element_type == "text":
                heading_indices.append(i)

        if not heading_indices:
            section = DocumentSection(
                section_id="full_document",
                title="Full Document",
                level=0,
                start_idx=0,
                end_idx=len(self._elements),
                page_start=0,
                page_end=max((e.page_idx for e in self._elements), default=0),
                char_offset_start=0,
                char_offset_end=len(self._full_text),
                text_content=self._full_text,
                elements=[e.raw for e in self._elements],
            )
            self._sections.append(section)
            return

        for si, start_idx in enumerate(heading_indices):
            end_idx = heading_indices[si + 1] if si + 1 < len(heading_indices) else len(self._elements)
            heading_elem = self._elements[start_idx]
            title = heading_elem.text.strip()
            section_id = self._make_section_id(title, si)

            section_elements = self._elements[start_idx:end_idx]
            section_text = "\n".join(e.text for e in section_elements if e.text.strip())

            pages = [e.page_idx for e in section_elements]
            section = DocumentSection(
                section_id=section_id,
                title=title,
                level=heading_elem.text_level or 0,
                start_idx=start_idx,
                end_idx=end_idx,
                page_start=min(pages) if pages else 0,
                page_end=max(pages) if pages else 0,
                char_offset_start=heading_elem.char_offset,
                char_offset_end=(
                    self._elements[end_idx - 1].char_offset + len(self._elements[end_idx - 1].text)
                    if end_idx > 0 else heading_elem.char_offset
                ),
                text_content=section_text,
                elements=[e.raw for e in section_elements],
            )
            self._sections.append(section)

    @staticmethod
    def _make_section_id(title: str, index: int) -> str:
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", title.strip().lower())
        clean = clean.strip("_")[:40]
        return f"s{index:02d}_{clean}" if clean else f"s{index:02d}_untitled"

    @property
    def sections(self) -> list[DocumentSection]:
        self.load()
        return self._sections

    @property
    def full_text(self) -> str:
        self.load()
        return self._full_text

    @property
    def elements(self) -> list[ContentElement]:
        self.load()
        return self._elements

    _EXCLUDED_SECTION_PATTERNS = [
        re.compile(r"^references?\s*$", re.IGNORECASE),
        re.compile(r"^bibliography\s*$", re.IGNORECASE),
        re.compile(r"^acknowledge?ments?\s*$", re.IGNORECASE),
        re.compile(r"^supporting information\s*$", re.IGNORECASE),
        re.compile(r"^supplementary\s", re.IGNORECASE),
        re.compile(r"^funding\s*$", re.IGNORECASE),
        re.compile(r"^author contributions?\s*$", re.IGNORECASE),
        re.compile(r"^conflicts? of interest\s*$", re.IGNORECASE),
        re.compile(r"^data availability\s*$", re.IGNORECASE),
    ]

    def _is_excluded_section(self, title: str) -> bool:
        title_stripped = title.strip()
        for pat in self._EXCLUDED_SECTION_PATTERNS:
            if pat.search(title_stripped):
                return True
        return False

    def get_relevant_sections(self, dimension: str, mode: str = "selective") -> list[DocumentSection]:
        """Get sections relevant to a dimension.
    
    Args:
        dimension: Extraction dimension (catalyst_design, characterization, etc.)
        mode: "selective" (keyword filtering, default) or "full_text" (all sections)
    
    Returns:
        List of DocumentSection objects
    """
        self.load()
        
        if mode == "full_text":
            all_sections = [s for s in self._sections if not self._is_excluded_section(s.title)]
            total_chars = sum(s.char_count for s in all_sections)
            logger.info(
                "full_text mode for %s: %d sections, %d chars (100%% coverage)",
                dimension, len(all_sections), total_chars
            )
            return all_sections
        
        # selective mode (existing logic)
        keywords = DIMENSION_SECTION_RELEVANCE.get(dimension, [])
        if not keywords:
            return [s for s in self._sections if not self._is_excluded_section(s.title)]

        relevant = []
        for section in self._sections:
            if self._is_excluded_section(section.title):
                continue
            title_lower = section.title.lower()
            text_lower = section.text_content[:2000].lower()
            for kw in keywords:
                if kw in title_lower or kw in text_lower:
                    relevant.append(section)
                    break

        if not relevant:
            return [s for s in self._sections if not self._is_excluded_section(s.title)]
        
        relevant_chars = sum(s.char_count for s in relevant)
        all_chars = sum(s.char_count for s in self._sections if not self._is_excluded_section(s.title))
        coverage_pct = (relevant_chars / all_chars * 100) if all_chars > 0 else 0
        logger.info(
            "selective mode for %s: %d/%d sections, %d/%d chars (%.1f%% coverage)",
            dimension, len(relevant), len([s for s in self._sections if not self._is_excluded_section(s.title)]),
            relevant_chars, all_chars, coverage_pct
        )
        return relevant

    def _split_oversized_section(
        self, section: DocumentSection, max_content_chars: int
    ) -> list[DocumentSection]:
        """Split a section that exceeds max_content_chars at paragraph boundaries.

        The overhead for section header formatting is accounted for, so each
        resulting sub-section's formatted text fits within max_chunk_chars.
        """
        overhead = self.SECTION_HEADER_OVERHEAD
        effective_limit = max_content_chars - overhead
        if section.char_count <= effective_limit:
            return [section]

        paragraphs = re.split(r'\n(?=\S)', section.text_content)
        if len(paragraphs) <= 1:
            paragraphs = re.split(r'(?<=[.。])\s+', section.text_content)
        paragraphs = [p for p in paragraphs if p.strip()]

        if not paragraphs:
            return [section]

        sub_sections: list[DocumentSection] = []
        current_paras: list[str] = []
        current_chars = 0
        sub_idx = 0

        for para in paragraphs:
            para_len = len(para)
            if para_len > effective_limit:
                if current_paras:
                    sub_content = "\n".join(current_paras)
                    sub_sections.append(self._make_sub_section(
                        section, sub_content, sub_idx, len(sub_sections)
                    ))
                    sub_idx += 1
                    current_paras = []
                    current_chars = 0
                sentences = re.split(r'(?<=[.。])\s+', para)
                for sent in sentences:
                    sent_len = len(sent)
                    if sent_len > effective_limit:
                        for i in range(0, sent_len, effective_limit):
                            piece = sent[i:i + effective_limit]
                            sub_sections.append(self._make_sub_section(
                                section, piece, sub_idx, len(sub_sections)
                            ))
                            sub_idx += 1
                    elif current_chars + sent_len > effective_limit and current_paras:
                        sub_content = "\n".join(current_paras)
                        sub_sections.append(self._make_sub_section(
                            section, sub_content, sub_idx, len(sub_sections)
                        ))
                        sub_idx += 1
                        current_paras = [sent]
                        current_chars = sent_len
                    else:
                        current_paras.append(sent)
                        current_chars += sent_len
            elif current_chars + para_len > effective_limit and current_paras:
                sub_content = "\n".join(current_paras)
                sub_sections.append(self._make_sub_section(
                    section, sub_content, sub_idx, len(sub_sections)
                ))
                sub_idx += 1
                current_paras = [para]
                current_chars = para_len
            else:
                current_paras.append(para)
                current_chars += para_len

        if current_paras:
            sub_content = "\n".join(current_paras)
            sub_sections.append(self._make_sub_section(
                section, sub_content, sub_idx, len(sub_sections)
            ))

        if not sub_sections:
            return [section]

        logger.info(
            "Split section '%s' (%d chars) into %d sub-sections (limit=%d)",
            section.title[:50], section.char_count, len(sub_sections), effective_limit,
        )
        return sub_sections

    @staticmethod
    def _make_sub_section(
        original: DocumentSection,
        content: str,
        sub_index: int,
        global_index: int,
    ) -> DocumentSection:
        return DocumentSection(
            section_id=f"{original.section_id}_sub{sub_index}",
            title=original.title if sub_index == 0 else f"{original.title} (cont. {sub_index})",
            level=original.level,
            start_idx=original.start_idx,
            end_idx=original.end_idx,
            page_start=original.page_start,
            page_end=original.page_end,
            char_offset_start=original.char_offset_start,
            char_offset_end=original.char_offset_start + len(content),
            text_content=content,
            elements=original.elements,
        )

    def build_chunk(
        self,
        dimension: str,
        sections: list[DocumentSection],
        chunk_index: int = 0,
    ) -> ExtractionChunk:
        if not sections:
            return ExtractionChunk(
                chunk_id=f"{dimension}_chunk_{chunk_index}",
                dimension=dimension,
                sections=[],
                content="",
                char_offset_start=0,
                char_offset_end=0,
                page_range=(0, 0),
                element_indices=[],
            )

        combined_text = "\n\n---\n\n".join(
            f"[Section: {s.title} (pp.{s.page_start}-{s.page_end})]\n{s.text_content}"
            for s in sections
        )

        if len(combined_text) <= self.max_chunk_chars:
            all_indices = []
            for s in sections:
                all_indices.extend(range(s.start_idx, s.end_idx))
            return ExtractionChunk(
                chunk_id=f"{dimension}_chunk_{chunk_index}",
                dimension=dimension,
                sections=[s.section_id for s in sections],
                content=combined_text,
                char_offset_start=sections[0].char_offset_start,
                char_offset_end=sections[-1].char_offset_end,
                page_range=(sections[0].page_start, sections[-1].page_end),
                element_indices=all_indices,
            )

        accumulated = ""
        selected_sections = []
        for s in sections:
            candidate = accumulated + ("\n\n---\n\n" if accumulated else "") + \
                f"[Section: {s.title} (pp.{s.page_start}-{s.page_end})]\n{s.text_content}"
            if len(candidate) > self.max_chunk_chars and accumulated:
                break
            accumulated = candidate
            selected_sections.append(s.section_id)

        all_indices = []
        for s in sections:
            if s.section_id in selected_sections:
                all_indices.extend(range(s.start_idx, s.end_idx))

        return ExtractionChunk(
            chunk_id=f"{dimension}_chunk_{chunk_index}",
            dimension=dimension,
            sections=selected_sections,
            content=accumulated,
            char_offset_start=sections[0].char_offset_start,
            char_offset_end=sections[-1].char_offset_end,
            page_range=(sections[0].page_start, sections[-1].page_end),
            element_indices=all_indices,
        )

    def build_dimension_chunks(self, dimension: str, mode: str = "selective") -> list[ExtractionChunk]:
        """Build chunks for a dimension.

        Oversized sections are split at paragraph boundaries before grouping,
        ensuring no chunk exceeds max_chunk_chars.

    Args:
        dimension: Extraction dimension
        mode: "selective" (keyword filtering) or "full_text" (all sections)

    Returns:
        List of ExtractionChunk objects
    """
        self.load()
        relevant = self.get_relevant_sections(dimension, mode=mode)

        if not relevant:
            return [self.build_chunk(dimension, self._sections)]

        expanded: list[DocumentSection] = []
        for section in relevant:
            subs = self._split_oversized_section(section, self.max_chunk_chars)
            expanded.extend(subs)

        chunks = []
        remaining = list(expanded)
        chunk_idx = 0

        while remaining:
            batch = []
            batch_chars = 0
            while remaining:
                s = remaining[0]
                formatted_len = len(s.text_content) + self.SECTION_HEADER_OVERHEAD
                addition = formatted_len + (20 if batch else 0)
                if batch_chars + addition > self.max_chunk_chars and batch:
                    break
                batch.append(remaining.pop(0))
                batch_chars += addition

            chunk = self.build_chunk(dimension, batch, chunk_idx)
            if len(chunk.content) > self.max_chunk_chars:
                raise ChunkBudgetExceeded(
                    f"Chunk {chunk.chunk_id} has {len(chunk.content)} chars "
                    f"(budget={self.max_chunk_chars}). "
                    f"Section splitting failed to produce compliant chunks."
                )
            chunks.append(chunk)
            chunk_idx += 1

        total_chars = sum(len(c.content) for c in chunks)
        max_chunk_size = max((len(c.content) for c in chunks), default=0)
        logger.info(
            "Built %d chunks for %s (%s mode): %d total chars, max chunk=%d chars (budget=%d)",
            len(chunks), dimension, mode, total_chars, max_chunk_size, self.max_chunk_chars,
        )
        return chunks

    def build_adaptive_chunks(
        self,
        dimension: str,
        doc_type: str = "paper",
    ) -> list[ExtractionChunk]:
        """Adaptive chunking: full-text if budget allows, otherwise semantic split with overlap.

        Args:
            dimension: Extraction dimension
            doc_type: "paper" (split at sections) or "patent" (split at claims/examples)

        Returns:
            List of ExtractionChunk objects with input_mode set to "full_text" or "chunked"
        """
        self.load()
        non_excluded = [s for s in self._sections if not self._is_excluded_section(s.title)]
        total_text = "\n\n---\n\n".join(
            f"[Section: {s.title} (pp.{s.page_start}-{s.page_end})]\n{s.text_content}"
            for s in non_excluded
        )
        total_tokens = estimate_tokens(total_text)

        if self.token_budget is not None and total_tokens <= self.token_budget.available_for_content:
            logger.info(
                "ADAPTIVE [%s] %s: full_text mode (%d tokens <= %d budget)",
                self.document_id, dimension, total_tokens,
                self.token_budget.available_for_content,
            )
            chunk = self._build_full_text_chunk(dimension, non_excluded)
            return [chunk]

        if self.token_budget is None and len(total_text) <= self.max_chunk_chars:
            logger.info(
                "ADAPTIVE [%s] %s: full_text mode (%d chars <= %d limit, no budget set)",
                self.document_id, dimension, len(total_text), self.max_chunk_chars,
            )
            chunk = self._build_full_text_chunk(dimension, non_excluded)
            return [chunk]

        logger.info(
            "ADAPTIVE [%s] %s: chunked mode (%d tokens > %d budget, doc_type=%s)",
            self.document_id, dimension, total_tokens,
            self.token_budget.available_for_content if self.token_budget else -1,
            doc_type,
        )
        return self._build_chunked_with_overlap(dimension, non_excluded, doc_type)

    def _build_full_text_chunk(
        self, dimension: str, sections: list[DocumentSection]
    ) -> ExtractionChunk:
        combined = "\n\n---\n\n".join(
            f"[Section: {s.title} (pp.{s.page_start}-{s.page_end})]\n{s.text_content}"
            for s in sections
        )
        all_indices = []
        for s in sections:
            all_indices.extend(range(s.start_idx, s.end_idx))
        return ExtractionChunk(
            chunk_id=f"{dimension}_full",
            dimension=dimension,
            sections=[s.section_id for s in sections],
            content=combined,
            char_offset_start=sections[0].char_offset_start if sections else 0,
            char_offset_end=sections[-1].char_offset_end if sections else 0,
            page_range=(
                sections[0].page_start if sections else 0,
                sections[-1].page_end if sections else 0,
            ),
            element_indices=all_indices,
            document_id=self.document_id,
            input_mode="full_text",
            overlap_chars=0,
        )

    def _build_chunked_with_overlap(
        self,
        dimension: str,
        sections: list[DocumentSection],
        doc_type: str,
    ) -> list[ExtractionChunk]:
        boundary_sections = self._detect_semantic_boundaries(sections, doc_type)
        groups = self._group_by_boundaries(sections, boundary_sections)

        chunks: list[ExtractionChunk] = []
        chunk_idx = 0
        prev_tail_paragraphs: list[str] = []

        for group in groups:
            group_text = "\n\n---\n\n".join(
                f"[Section: {s.title} (pp.{s.page_start}-{s.page_end})]\n{s.text_content}"
                for s in group
            )
            overlap_text = ""
            if prev_tail_paragraphs and self.overlap_paragraphs > 0:
                overlap_text = "\n".join(prev_tail_paragraphs)
                group_text = overlap_text + "\n\n[CONTINUATION FROM PREVIOUS CHUNK]\n\n" + group_text

            logger.debug(
                "Group %d: group_text=%d chars, overlap=%d chars, budget=%d",
                chunk_idx, len(group_text), len(overlap_text), self.max_chunk_chars,
            )

            if len(group_text) <= self.max_chunk_chars:
                chunk = self._make_extraction_chunk(
                    dimension, group, chunk_idx, group_text,
                    overlap_chars=len(overlap_text),
                )
                chunks.append(chunk)
                chunk_idx += 1
                prev_tail_paragraphs = self._tail_paragraphs(group, self.overlap_paragraphs)
            else:
                logger.debug(
                    "Group %d exceeds budget, calling _split_group_with_overflow",
                    chunk_idx,
                )
                sub_chunks = self._split_group_with_overflow(
                    dimension, group, chunk_idx, prev_tail_paragraphs,
                )
                chunks.extend(sub_chunks)
                chunk_idx += len(sub_chunks)
                prev_tail_paragraphs = self._tail_paragraphs(group, self.overlap_paragraphs)

        for i, c in enumerate(chunks):
            if len(c.content) > self.max_chunk_chars:
                logger.error(
                    "Chunk %d (%s) has %d chars, exceeds budget %d",
                    i, c.chunk_id, len(c.content), self.max_chunk_chars,
                )
                raise ChunkBudgetExceeded(
                    f"Adaptive chunk {c.chunk_id} has {len(c.content)} chars "
                    f"(budget={self.max_chunk_chars})."
                )

        total_chars = sum(len(c.content) for c in chunks)
        logger.info(
            "ADAPTIVE [%s] %s: %d chunks, %d total chars, mode=chunked",
            self.document_id, dimension, len(chunks), total_chars,
        )
        return chunks

    def _detect_semantic_boundaries(
        self, sections: list[DocumentSection], doc_type: str
    ) -> set[str]:
        boundary_ids: set[str] = set()
        patent_markers = ["claim", "example", "embodiment", "implementation", "comparison"]
        for s in sections:
            title_lower = s.title.lower()
            if doc_type == "patent":
                for marker in patent_markers:
                    if marker in title_lower:
                        boundary_ids.add(s.section_id)
                        break
            if re.match(r'^\d+[\.\)]', s.title.strip()):
                boundary_ids.add(s.section_id)
        return boundary_ids

    def _group_by_boundaries(
        self,
        sections: list[DocumentSection],
        boundary_ids: set[str],
    ) -> list[list[DocumentSection]]:
        if not boundary_ids:
            return self._greedy_group(sections)

        groups: list[list[DocumentSection]] = []
        current: list[DocumentSection] = []
        for s in sections:
            if s.section_id in boundary_ids and current:
                groups.append(current)
                current = []
            current.append(s)
        if current:
            groups.append(current)
        return self._merge_small_groups(groups)

    def _greedy_group(self, sections: list[DocumentSection]) -> list[list[DocumentSection]]:
        groups: list[list[DocumentSection]] = []
        current: list[DocumentSection] = []
        current_chars = 0
        for s in sections:
            if current_chars + s.char_count > self.max_chunk_chars and current:
                groups.append(current)
                current = []
                current_chars = 0
            current.append(s)
            current_chars += s.char_count + self.SECTION_HEADER_OVERHEAD
        if current:
            groups.append(current)
        return groups

    def _merge_small_groups(
        self, groups: list[list[DocumentSection]]
    ) -> list[list[DocumentSection]]:
        merged: list[list[DocumentSection]] = []
        buffer: list[DocumentSection] = []
        buffer_chars = 0
        for group in groups:
            group_chars = sum(s.char_count for s in group) + len(group) * self.SECTION_HEADER_OVERHEAD
            if buffer_chars + group_chars <= self.max_chunk_chars:
                buffer.extend(group)
                buffer_chars += group_chars
            else:
                if buffer:
                    merged.append(buffer)
                buffer = list(group)
                buffer_chars = group_chars
        if buffer:
            merged.append(buffer)
        return merged if merged else [groups[0]] if groups else []

    def _split_group_with_overflow(
        self,
        dimension: str,
        group: list[DocumentSection],
        start_idx: int,
        prev_tail: list[str],
    ) -> list[ExtractionChunk]:
        expanded: list[DocumentSection] = []
        for s in group:
            subs = self._split_oversized_section(s, self.max_chunk_chars)
            expanded.extend(subs)

        chunks: list[ExtractionChunk] = []
        batch: list[DocumentSection] = []
        batch_chars = 0
        chunk_idx = start_idx
        overlap_text = ""
        if prev_tail and self.overlap_paragraphs > 0:
            overlap_text = "\n".join(prev_tail)

        for s in expanded:
            formatted_len = len(s.text_content) + self.SECTION_HEADER_OVERHEAD
            overlap_len = len(overlap_text) + (40 if overlap_text else 0)
            total_needed = overlap_len + batch_chars + formatted_len + (20 if batch else 0)

            if total_needed > self.max_chunk_chars and batch:
                content = self._format_batch(batch, overlap_text)
                if len(content) > self.max_chunk_chars:
                    overlap_text = self._truncate_overlap(overlap_text, batch_chars, self.max_chunk_chars)
                    content = self._format_batch(batch, overlap_text)
                chunk = self._make_extraction_chunk(
                    dimension, batch, chunk_idx, content,
                    overlap_chars=len(overlap_text),
                )
                chunks.append(chunk)
                chunk_idx += 1
                tail = self._tail_paragraphs(batch, self.overlap_paragraphs)
                overlap_text = "\n".join(tail) if tail else ""
                batch = []
                batch_chars = 0
            batch.append(s)
            batch_chars += formatted_len

        if batch:
            content = self._format_batch(batch, overlap_text)
            if len(content) > self.max_chunk_chars:
                overlap_text = self._truncate_overlap(overlap_text, batch_chars, self.max_chunk_chars)
                content = self._format_batch(batch, overlap_text)
            chunk = self._make_extraction_chunk(
                dimension, batch, chunk_idx, content,
                overlap_chars=len(overlap_text),
            )
            chunks.append(chunk)

        return chunks

    def _truncate_overlap(self, overlap_text: str, content_chars: int, max_chars: int) -> str:
        """Truncate overlap text to ensure the total chunk fits within max_chars."""
        if not overlap_text:
            return overlap_text
        available = max_chars - content_chars - 50
        if available <= 0:
            return ""
        if len(overlap_text) <= available:
            return overlap_text
        truncated = overlap_text[:available]
        last_para = truncated.rfind("\n\n")
        if last_para > available // 2:
            truncated = truncated[:last_para]
        return truncated

    def _format_batch(self, sections: list[DocumentSection], overlap_text: str = "") -> str:
        parts = []
        if overlap_text:
            parts.append(overlap_text)
            parts.append("[CONTINUATION FROM PREVIOUS CHUNK]")
        for s in sections:
            parts.append(
                f"[Section: {s.title} (pp.{s.page_start}-{s.page_end})]\n{s.text_content}"
            )
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _tail_paragraphs(sections: list[DocumentSection], n: int) -> list[str]:
        if not sections or n <= 0:
            return []
        all_paras: list[str] = []
        for s in sections:
            paras = [p.strip() for p in re.split(r'\n(?=\S)', s.text_content) if p.strip()]
            all_paras.extend(paras)
        return all_paras[-n:] if all_paras else []

    def _make_extraction_chunk(
        self,
        dimension: str,
        sections: list[DocumentSection],
        chunk_index: int,
        content: str,
        overlap_chars: int = 0,
    ) -> ExtractionChunk:
        all_indices = []
        for s in sections:
            all_indices.extend(range(s.start_idx, s.end_idx))
        return ExtractionChunk(
            chunk_id=f"{dimension}_chunk_{chunk_index}",
            dimension=dimension,
            sections=[s.section_id for s in sections],
            content=content,
            char_offset_start=sections[0].char_offset_start if sections else 0,
            char_offset_end=sections[-1].char_offset_end if sections else 0,
            page_range=(
                sections[0].page_start if sections else 0,
                sections[-1].page_end if sections else 0,
            ),
            element_indices=all_indices,
            document_id=self.document_id,
            input_mode="chunked",
            overlap_chars=overlap_chars,
        )

    def get_element_at_offset(self, char_offset: int) -> Optional[ContentElement]:
        self.load()
        for elem in reversed(self._elements):
            if elem.char_offset <= char_offset:
                return elem
        return self._elements[0] if self._elements else None

    def get_figure_table_elements(self) -> list[ContentElement]:
        self.load()
        return [e for e in self._elements if e.element_type in ("image", "table")]

    def get_section_containing_offset(self, char_offset: int) -> Optional[DocumentSection]:
        self.load()
        for section in self._sections:
            if section.char_offset_start <= char_offset <= section.char_offset_end:
                return section
        return None

    def to_extraction_input(self) -> dict:
        self.load()
        return {
            "total_chars": len(self._full_text),
            "total_elements": len(self._elements),
            "total_sections": len(self._sections),
            "sections": [
                {
                    "section_id": s.section_id,
                    "title": s.title,
                    "level": s.level,
                    "page_range": [s.page_start, s.page_end],
                    "char_count": s.char_count,
                    "char_offset_range": [s.char_offset_start, s.char_offset_end],
                }
                for s in self._sections
            ],
            "figures_and_tables": [
                {
                    "index": e.index,
                    "type": e.element_type,
                    "page_idx": e.page_idx,
                    "caption": e.text[:200],
                    "char_offset": e.char_offset,
                }
                for e in self.get_figure_table_elements()
            ],
        }
