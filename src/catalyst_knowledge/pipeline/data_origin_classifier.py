"""Data origin classification and unified missing status for scientific extraction.

Provides two key enums:
- DataOrigin: Where did this data come from? (7 categories)
- DataStatus: What is the extraction status? (5 categories)

These replace the V1 approach of using 0/null/"not specified" for missing data,
which caused systematic false-absence failures (Phase 3.3 GAP-C02/C03/C04).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional


class DataOrigin(str, Enum):
    """Classification of scientific data provenance."""
    ORIGINAL_EXPERIMENT = "ORIGINAL_EXPERIMENT"
    CONTROL_EXPERIMENT = "CONTROL_EXPERIMENT"
    LITERATURE_REFERENCE = "LITERATURE_REFERENCE"
    THEORETICAL_CALCULATION = "THEORETICAL_CALCULATION"
    PATENT_EXAMPLE = "PATENT_EXAMPLE"
    SYSTEM_INFERRED = "SYSTEM_INFERRED"
    UNKNOWN_ORIGIN = "UNKNOWN_ORIGIN"


class DataStatus(str, Enum):
    """Unified status for extracted data fields."""
    REPORTED = "REPORTED"
    NOT_REPORTED = "NOT_REPORTED"
    NOT_EXTRACTED = "NOT_EXTRACTED"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DataRecord:
    """A single extracted data field with full provenance tracking."""

    def __init__(
        self,
        field_name: str,
        value: Any = None,
        status: DataStatus = DataStatus.NOT_EXTRACTED,
        origin: DataOrigin = DataOrigin.UNKNOWN_ORIGIN,
        source_quote: str = "",
        source_section: str = "",
        source_page: Optional[int] = None,
        source_char_offset: Optional[int] = None,
        confidence: Optional[float] = None,
        notes: str = "",
    ):
        self.field_name = field_name
        self.value = value
        self.status = status
        self.origin = origin
        self.source_quote = source_quote
        self.source_section = source_section
        self.source_page = source_page
        self.source_char_offset = source_char_offset
        self.confidence = confidence
        self.notes = notes

    def to_dict(self) -> dict:
        d = {
            "field_name": self.field_name,
            "value": self.value,
            "status": self.status.value if isinstance(self.status, DataStatus) else self.status,
            "origin": self.origin.value if isinstance(self.origin, DataOrigin) else self.origin,
        }
        if self.source_quote:
            d["source_quote"] = self.source_quote
        if self.source_section:
            d["source_section"] = self.source_section
        if self.source_page is not None:
            d["source_page"] = self.source_page
        if self.source_char_offset is not None:
            d["source_char_offset"] = self.source_char_offset
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, data: dict) -> DataRecord:
        return cls(
            field_name=data.get("field_name", ""),
            value=data.get("value"),
            status=data.get("status", DataStatus.NOT_EXTRACTED),
            origin=data.get("origin", DataOrigin.UNKNOWN_ORIGIN),
            source_quote=data.get("source_quote", ""),
            source_section=data.get("source_section", ""),
            source_page=data.get("source_page"),
            source_char_offset=data.get("source_char_offset"),
            confidence=data.get("confidence"),
            notes=data.get("notes", ""),
        )

    @classmethod
    def not_reported(cls, field_name: str, notes: str = "") -> DataRecord:
        return cls(field_name=field_name, status=DataStatus.NOT_REPORTED, notes=notes)

    @classmethod
    def not_extracted(cls, field_name: str, notes: str = "") -> DataRecord:
        return cls(field_name=field_name, status=DataStatus.NOT_EXTRACTED, notes=notes)


def validate_origin_value(origin_str: str) -> DataOrigin:
    try:
        return DataOrigin(origin_str)
    except ValueError:
        return DataOrigin.UNKNOWN_ORIGIN


def validate_status_value(status_str: str) -> DataStatus:
    try:
        return DataStatus(status_str)
    except ValueError:
        return DataStatus.UNRESOLVED


def check_false_absence(record: DataRecord, source_text: str = "") -> Optional[str]:
    """Detect potential false absence: status says missing but source text may contain data."""
    if record.status not in (DataStatus.NOT_REPORTED, DataStatus.NOT_EXTRACTED):
        return None

    field_keywords = {
        "synthesis_method": [r"impregnation", r"deposition", r"precipitation", r"calcination",
                             r"synthesis", r"preparation", r"wetness"],
        "time_on_stream": [r"stability", r"time\s+on\s+stream", r"durability", r"\d+\s*h\b",
                           r"lifetime", r"cycle", r"deactivation"],
        "key_metrics": [r"conversion", r"selectivity", r"yield", r"rate", r"\bTOF\b", r"activity"],
        "techniques_used": [r"\bXRD\b", r"\bBET\b", r"\bTEM\b", r"\bSEM\b", r"\bXPS\b",
                            r"\bUV[\-\s]vis\b", r"\bFTIR\b", r"\bRaman\b",
                            r"characterization", r"\bmeasured\b"],
    }

    keywords = field_keywords.get(record.field_name, [])
    found_keywords = [kw for kw in keywords if re.search(kw, source_text, re.IGNORECASE)]

    if found_keywords:
        return (
            f"Potential false absence for '{record.field_name}': "
            f"status={record.status.value} but source contains keywords: {found_keywords}"
        )
    return None


def check_default_value_anchor(value: Any, field_name: str) -> Optional[str]:
    """Detect if LLM returned a default value anchor instead of real data."""
    if isinstance(value, (int, float)) and value == 0:
        return f"Field '{field_name}' has numeric value 0 — likely default anchor, not real data"
    if isinstance(value, list) and len(value) == 0:
        return f"Field '{field_name}' has empty array — likely default anchor"
    if isinstance(value, str):
        normalized = value.strip().lower()
        absence_phrases = (
            "not specified", "not mentioned", "not provided", "not reported",
            "no data", "none", "n/a", "not available",
        )
        if normalized in absence_phrases or any(normalized.startswith(phrase) for phrase in absence_phrases):
            return f"Field '{field_name}' has generic absence string '{value}' — should use DataStatus instead"
    return None


def merge_chunk_results(
    field_name: str,
    results: list[DataRecord],
) -> DataRecord:
    """Merge extraction results from multiple chunks for the same field.

    Priority: REPORTED > UNRESOLVED > NOT_EXTRACTED > NOT_REPORTED > NOT_APPLICABLE
    """
    if not results:
        return DataRecord.not_extracted(field_name)

    status_priority = {
        DataStatus.REPORTED: 5,
        DataStatus.UNRESOLVED: 4,
        DataStatus.NOT_EXTRACTED: 3,
        DataStatus.NOT_REPORTED: 2,
        DataStatus.NOT_APPLICABLE: 1,
    }

    best = max(results, key=lambda r: status_priority.get(
        r.status if isinstance(r.status, DataStatus) else DataStatus(r.status), 0
    ))

    if best.status == DataStatus.REPORTED:
        return best

    all_notes = "; ".join(
        f"chunk_{i}: {r.status.value if isinstance(r.status, DataStatus) else r.status}"
        for i, r in enumerate(results)
    )
    return DataRecord(
        field_name=field_name,
        value=best.value,
        status=best.status,
        origin=best.origin,
        source_quote=best.source_quote,
        notes=f"Merged from {len(results)} chunks: {all_notes}",
    )
