"""QualityAssessment — Evaluate extraction quality with 11 checks.

Checks:
1. missing_value_detection — Fields marked NOT_EXTRACTED but data present
2. confidence_threshold — Low confidence extractions
3. source_type_validation — Incorrect source type classification
4. unit_consistency — Unit format inconsistencies
5. range_plausibility — Values outside plausible ranges
6. cross_field_coherence — Inconsistencies between related fields
7. literature_contamination — Literature data mislabeled as original
8. false_negative_detection — LLM claims "no data" when data exists
9. extraction_completeness — Overall field coverage
10. schema_compliance — Schema validation
11. duplicate_detection — DUPLICATE_ENTRY (same source) vs DUPLICATE_DATA (different source)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import yaml


class Severity(str, Enum):
    """Check severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CheckStatus(str, Enum):
    """Check result status."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    """Result of a single quality check."""
    check_name: str
    status: CheckStatus
    severity: Severity
    message: str
    affected_fields: list[str] = field(default_factory=list)
    evidence: Optional[dict] = None


@dataclass
class QualityReport:
    """Comprehensive quality assessment report."""
    overall_score: float
    dimension_scores: dict[str, float]
    check_results: list[CheckResult]
    failed_fields: list[dict]
    total_fields: int
    reported_fields: int
    extraction_metadata: dict = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        """Calculate check pass rate."""
        if not self.check_results:
            return 0.0
        passed = sum(1 for r in self.check_results if r.status == CheckStatus.PASS)
        return passed / len(self.check_results)

    @property
    def critical_failures(self) -> list[CheckResult]:
        """Get all critical failures."""
        return [r for r in self.check_results
                if r.status == CheckStatus.FAIL and r.severity == Severity.CRITICAL]

    @property
    def high_failures(self) -> list[CheckResult]:
        """Get all high severity failures."""
        return [r for r in self.check_results
                if r.status == CheckStatus.FAIL and r.severity == Severity.HIGH]


class QualityAssessment:
    """Evaluate extraction quality with configurable checks."""

    # Default plausible ranges for common quantities
    DEFAULT_RANGES = {
        "temperature_celsius": (-273, 2000),
        "pressure_atm": (0, 1000),
        "conversion_percent": (0, 100),
        "selectivity_percent": (0, 100),
        "surface_area_m2_g": (0, 5000),
        "particle_size_nm": (0.1, 1000),
        "binding_energy_ev": (0, 1500),
    }

    # Keywords indicating literature references
    LITERATURE_KEYWORDS = [
        "reported by", "reference", "literature", "previously",
        "et al.", "compared to", "similar to", "consistent with",
        "Wang et al", "Li et al", "Zhang et al", "Jiang et al",
    ]

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with optional configuration file."""
        self.config = self._load_config(config_path)
        self.checks_enabled = self.config.get("enabled_checks", [
            "missing_value_detection",
            "confidence_threshold",
            "source_type_validation",
            "unit_consistency",
            "range_plausibility",
            "cross_field_coherence",
            "literature_contamination",
            "false_negative_detection",
            "extraction_completeness",
            "schema_compliance",
            "duplicate_detection",
        ])

    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load configuration from YAML file."""
        if config_path is None:
            return {
                "confidence_threshold": 0.7,
                "min_completeness": 0.5,
            }
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def assess(
        self,
        extraction_results: dict,
        document_ir: Optional[dict] = None,
        document_text: Optional[str] = None,
    ) -> QualityReport:
        """Run all enabled quality checks.

        Args:
            extraction_results: Six-dimension extraction output
            document_ir: Document intermediate representation
            document_text: Full document text for cross-reference

        Returns:
            QualityReport with all check results
        """
        check_results: list[CheckResult] = []
        failed_fields: list[dict] = []

        dimensions = extraction_results.get("dimensions", {})

        # Run each enabled check
        if "missing_value_detection" in self.checks_enabled:
            result = self._check_missing_values(dimensions, document_text)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "MISSING_VALUE"))

        if "confidence_threshold" in self.checks_enabled:
            result = self._check_confidence(dimensions)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "LOW_CONFIDENCE"))

        if "source_type_validation" in self.checks_enabled:
            result = self._check_source_type(dimensions)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "INVALID_SOURCE_TYPE"))

        if "unit_consistency" in self.checks_enabled:
            result = self._check_units(dimensions)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "UNIT_INCONSISTENCY"))

        if "range_plausibility" in self.checks_enabled:
            result = self._check_ranges(dimensions)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "VALUE_OUT_OF_RANGE"))

        if "cross_field_coherence" in self.checks_enabled:
            result = self._check_coherence(dimensions)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "CROSS_FIELD_INCOHERENCE"))

        if "literature_contamination" in self.checks_enabled:
            result = self._check_literature_contamination(dimensions)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "LITERATURE_CONTAMINATION"))

        if "false_negative_detection" in self.checks_enabled:
            result = self._check_false_negatives(dimensions, document_text)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "LLM_FALSE_NEGATIVE"))

        if "extraction_completeness" in self.checks_enabled:
            result = self._check_completeness(dimensions)
            check_results.append(result)

        if "schema_compliance" in self.checks_enabled:
            result = self._check_schema_compliance(extraction_results)
            check_results.append(result)

        if "duplicate_detection" in self.checks_enabled:
            result = self._check_duplicates(dimensions)
            check_results.append(result)
            if result.status == CheckStatus.FAIL:
                failed_fields.extend(self._build_failed_fields(result, "DUPLICATE_ENTRY"))

        # Calculate scores
        total_fields, reported_fields = self._count_fields(dimensions)
        dimension_scores = self._calculate_dimension_scores(dimensions)
        overall_score = self._calculate_overall_score(check_results, dimension_scores)

        return QualityReport(
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            check_results=check_results,
            failed_fields=failed_fields,
            total_fields=total_fields,
            reported_fields=reported_fields,
            extraction_metadata={
                "timestamp": str(__import__("datetime").datetime.now()),
                "checks_run": len(check_results),
                "checks_passed": sum(1 for r in check_results if r.status == CheckStatus.PASS),
            }
        )

    def _check_missing_values(self, dimensions: dict, document_text: Optional[str]) -> CheckResult:
        """Check for fields marked NOT_EXTRACTED but data may be present."""
        affected = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                status = field_data.get("status", "")
                if status in ["NOT_EXTRACTED", "NOT_REPORTED"]:
                    # Check if document text contains potential values
                    if document_text and self._text_contains_value(document_text, field_name):
                        affected.append(f"{dim_name}.{field_name}")

        if affected:
            return CheckResult(
                check_name="missing_value_detection",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                message=f"Found {len(affected)} fields marked NOT_EXTRACTED but data may be present",
                affected_fields=affected,
                evidence={"fields": affected}
            )
        return CheckResult(
            check_name="missing_value_detection",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="No missing values detected"
        )

    def _check_confidence(self, dimensions: dict) -> CheckResult:
        """Check for low confidence extractions."""
        threshold = self.config.get("confidence_threshold", 0.7)
        affected = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                confidence = field_data.get("confidence", 1.0)
                if confidence < threshold and field_data.get("status") == "REPORTED":
                    affected.append(f"{dim_name}.{field_name}")

        if affected:
            return CheckResult(
                check_name="confidence_threshold",
                status=CheckStatus.WARNING,
                severity=Severity.MEDIUM,
                message=f"Found {len(affected)} fields with confidence < {threshold}",
                affected_fields=affected
            )
        return CheckResult(
            check_name="confidence_threshold",
            status=CheckStatus.PASS,
            severity=Severity.MEDIUM,
            message=f"All fields have confidence >= {threshold}"
        )

    def _check_source_type(self, dimensions: dict) -> CheckResult:
        """Validate source type classifications."""
        valid_types = [
            "ORIGINAL_EXPERIMENT", "CONTROL_EXPERIMENT", "LITERATURE_REFERENCE",
            "THEORETICAL_CALCULATION", "PATENT_EXAMPLE", "SYSTEM_INFERRED", "UNKNOWN_ORIGIN"
        ]
        affected = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                origin = field_data.get("origin", "")
                if origin and origin not in valid_types:
                    affected.append(f"{dim_name}.{field_name}")

        if affected:
            return CheckResult(
                check_name="source_type_validation",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                message=f"Found {len(affected)} fields with invalid source type",
                affected_fields=affected
            )
        return CheckResult(
            check_name="source_type_validation",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="All source types are valid"
        )

    def _check_units(self, dimensions: dict) -> CheckResult:
        """Check for unit inconsistencies."""
        affected = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                value = field_data.get("value", "")
                unit = field_data.get("unit", "")
                if value and unit:
                    # Check if value contains unit (redundant)
                    if unit in str(value):
                        affected.append(f"{dim_name}.{field_name}")

        if affected:
            return CheckResult(
                check_name="unit_consistency",
                status=CheckStatus.WARNING,
                severity=Severity.LOW,
                message=f"Found {len(affected)} fields with potential unit redundancy",
                affected_fields=affected
            )
        return CheckResult(
            check_name="unit_consistency",
            status=CheckStatus.PASS,
            severity=Severity.LOW,
            message="No unit inconsistencies detected"
        )

    def _check_ranges(self, dimensions: dict) -> CheckResult:
        """Check for values outside plausible ranges."""
        affected = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                value = field_data.get("value")
                unit = field_data.get("unit", "")
                if value and self._is_numeric(value):
                    num_val = float(str(value).split()[0])
                    range_key = self._guess_range_key(field_name, unit)
                    if range_key and range_key in self.DEFAULT_RANGES:
                        min_val, max_val = self.DEFAULT_RANGES[range_key]
                        if num_val < min_val or num_val > max_val:
                            affected.append(f"{dim_name}.{field_name}")

        if affected:
            return CheckResult(
                check_name="range_plausibility",
                status=CheckStatus.FAIL,
                severity=Severity.HIGH,
                message=f"Found {len(affected)} fields with values outside plausible ranges",
                affected_fields=affected
            )
        return CheckResult(
            check_name="range_plausibility",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="All values within plausible ranges"
        )

    def _check_coherence(self, dimensions: dict) -> CheckResult:
        """Check cross-field coherence."""
        affected = []
        # Example: conversion and selectivity should sum reasonably
        perf = dimensions.get("performance", {}).get("fields", {})
        conversion = perf.get("conversion", {}).get("value")
        selectivity = perf.get("selectivity", {}).get("value")

        if conversion and selectivity:
            if self._is_numeric(conversion) and self._is_numeric(selectivity):
                conv = float(conversion)
                sel = float(selectivity)
                if conv > 0 and sel > 100:
                    affected.append("performance.selectivity")

        if affected:
            return CheckResult(
                check_name="cross_field_coherence",
                status=CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                message=f"Found {len(affected)} cross-field incoherences",
                affected_fields=affected
            )
        return CheckResult(
            check_name="cross_field_coherence",
            status=CheckStatus.PASS,
            severity=Severity.MEDIUM,
            message="Cross-field coherence verified"
        )

    def _check_literature_contamination(self, dimensions: dict) -> CheckResult:
        """Detect literature data mislabeled as original experiment."""
        affected = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                origin = field_data.get("origin", "")
                value = str(field_data.get("value", ""))
                source_quote = str(field_data.get("source_quote", ""))

                # Check if marked as original but contains literature keywords
                if origin == "ORIGINAL_EXPERIMENT":
                    text_to_check = f"{value} {source_quote}".lower()
                    for keyword in self.LITERATURE_KEYWORDS:
                        if keyword.lower() in text_to_check:
                            affected.append(f"{dim_name}.{field_name}")
                            break

        if affected:
            return CheckResult(
                check_name="literature_contamination",
                status=CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message=f"Found {len(affected)} fields with potential literature contamination",
                affected_fields=affected
            )
        return CheckResult(
            check_name="literature_contamination",
            status=CheckStatus.PASS,
            severity=Severity.CRITICAL,
            message="No literature contamination detected"
        )

    def _check_false_negatives(self, dimensions: dict, document_text: Optional[str]) -> CheckResult:
        """Detect LLM false negatives (claims no data when data exists)."""
        if not document_text:
            return CheckResult(
                check_name="false_negative_detection",
                status=CheckStatus.SKIP,
                severity=Severity.HIGH,
                message="Document text not provided, skipping false negative detection"
            )

        affected = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                status = field_data.get("status", "")
                source_quote = field_data.get("source_quote", "")

                # Check if marked as NOT_REPORTED but might have data
                if status == "NOT_REPORTED":
                    # Look for numerical patterns near field-related keywords
                    if self._text_may_contain_data(document_text, field_name):
                        affected.append(f"{dim_name}.{field_name}")

        if affected:
            return CheckResult(
                check_name="false_negative_detection",
                status=CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message=f"Found {len(affected)} potential LLM false negatives",
                affected_fields=affected
            )
        return CheckResult(
            check_name="false_negative_detection",
            status=CheckStatus.PASS,
            severity=Severity.CRITICAL,
            message="No false negatives detected"
        )

    def _check_completeness(self, dimensions: dict) -> CheckResult:
        """Check overall extraction completeness."""
        total, reported = self._count_fields(dimensions)
        if total == 0:
            return CheckResult(
                check_name="extraction_completeness",
                status=CheckStatus.SKIP,
                severity=Severity.MEDIUM,
                message="No fields to evaluate"
            )

        completeness = reported / total
        min_completeness = self.config.get("min_completeness", 0.5)

        if completeness < min_completeness:
            return CheckResult(
                check_name="extraction_completeness",
                status=CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                message=f"Completeness {completeness:.1%} below threshold {min_completeness:.1%}",
                evidence={"completeness": completeness, "threshold": min_completeness}
            )
        return CheckResult(
            check_name="extraction_completeness",
            status=CheckStatus.PASS,
            severity=Severity.MEDIUM,
            message=f"Completeness {completeness:.1%} meets threshold"
        )

    def _check_schema_compliance(self, extraction_results: dict) -> CheckResult:
        """Validate schema compliance."""
        required_keys = ["dimensions", "document_id"]
        missing = [k for k in required_keys if k not in extraction_results]

        if missing:
            return CheckResult(
                check_name="schema_compliance",
                status=CheckStatus.FAIL,
                severity=Severity.CRITICAL,
                message=f"Missing required schema keys: {missing}"
            )
        return CheckResult(
            check_name="schema_compliance",
            status=CheckStatus.PASS,
            severity=Severity.CRITICAL,
            message="Schema compliance verified"
        )

    def _check_duplicates(self, dimensions: dict) -> CheckResult:
        """Detect duplicate entries and duplicate data across dimensions.

        Three outcomes per pair:
        - DUPLICATE_ENTRY: Same source + conditions + sample → extraction error → FAIL
        - DUPLICATE_DATA: Different source/conditions → legitimate → WARNING
        - UNRESOLVED: Insufficient metadata to judge → WARNING, no auto-recovery
        """
        entry_duplicates = []
        data_duplicates = []
        unresolved_pairs = []

        field_entries = self._collect_field_entries(dimensions)

        groups: dict[str, list[tuple[str, str, dict]]] = {}
        for dim_name, field_name, field_data in field_entries:
            norm = self._normalize_value(field_data.get("value"))
            if norm is None:
                continue
            groups.setdefault(norm, []).append((dim_name, field_name, field_data))

        for norm_val, entries in groups.items():
            if len(entries) < 2:
                continue
            for i, (dim_a, fld_a, data_a) in enumerate(entries):
                for dim_b, fld_b, data_b in entries[i + 1:]:
                    path_a = f"{dim_a}.{fld_a}"
                    path_b = f"{dim_b}.{fld_b}"
                    if path_a == path_b:
                        continue
                    verdict = self._compare_source_identity(data_a, data_b)
                    if verdict == "SAME_SOURCE":
                        entry_duplicates.append((path_a, path_b, norm_val))
                    elif verdict == "DIFFERENT_SOURCE":
                        data_duplicates.append((path_a, path_b, norm_val))
                    else:
                        unresolved_pairs.append((path_a, path_b, norm_val))

        affected = []
        evidence: dict[str, Any] = {
            "duplicate_entries": [],
            "duplicate_data": [],
            "unresolved": [],
        }

        for path_a, path_b, val in entry_duplicates:
            if path_a not in affected:
                affected.append(path_a)
            if path_b not in affected:
                affected.append(path_b)
            evidence["duplicate_entries"].append({
                "field_a": path_a, "field_b": path_b, "normalized_value": val,
            })

        for path_a, path_b, val in data_duplicates:
            if path_a not in affected:
                affected.append(path_a)
            if path_b not in affected:
                affected.append(path_b)
            evidence["duplicate_data"].append({
                "field_a": path_a, "field_b": path_b, "normalized_value": val,
                "note": "Same value, different source/conditions — likely legitimate",
            })

        for path_a, path_b, val in unresolved_pairs:
            if path_a not in affected:
                affected.append(path_a)
            if path_b not in affected:
                affected.append(path_b)
            evidence["unresolved"].append({
                "field_a": path_a, "field_b": path_b, "normalized_value": val,
                "note": "Insufficient metadata — requires human review",
            })

        if entry_duplicates:
            return CheckResult(
                check_name="duplicate_detection",
                status=CheckStatus.FAIL,
                severity=Severity.MEDIUM,
                message=(
                    f"Found {len(entry_duplicates)} DUPLICATE_ENTRY, "
                    f"{len(data_duplicates)} DUPLICATE_DATA, "
                    f"{len(unresolved_pairs)} UNRESOLVED"
                ),
                affected_fields=affected,
                evidence=evidence,
            )

        if data_duplicates or unresolved_pairs:
            parts = []
            if data_duplicates:
                parts.append(f"{len(data_duplicates)} DUPLICATE_DATA")
            if unresolved_pairs:
                parts.append(f"{len(unresolved_pairs)} UNRESOLVED")
            return CheckResult(
                check_name="duplicate_detection",
                status=CheckStatus.WARNING,
                severity=Severity.LOW,
                message=f"Found {', '.join(parts)} (not auto-deduplicated)",
                affected_fields=affected,
                evidence=evidence,
            )

        return CheckResult(
            check_name="duplicate_detection",
            status=CheckStatus.PASS,
            severity=Severity.MEDIUM,
            message="No duplicate entries detected",
        )

    def _collect_field_entries(
        self, dimensions: dict
    ) -> list[tuple[str, str, dict]]:
        """Collect (dim_name, field_name, field_data) triples from all dimensions.

        Handles both single-field dicts and list-of-entries fields (e.g.
        experiment_matrix entries stored as a list under one field_name).
        """
        entries = []
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                if isinstance(field_data, list):
                    for idx, item in enumerate(field_data):
                        if isinstance(item, dict):
                            entries.append((
                                dim_name,
                                f"{field_name}[{idx}]",
                                item,
                            ))
                elif isinstance(field_data, dict):
                    entries.append((dim_name, field_name, field_data))
        return entries

    def _normalize_value(self, value: Any) -> Optional[str]:
        """Normalize a field value for comparison. Returns None for empty/missing."""
        if value is None or value == "" or value == []:
            return None
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    parts.append(json.dumps(item, sort_keys=True, ensure_ascii=False))
                else:
                    parts.append(str(item).strip().lower())
            return "|".join(sorted(parts)) if parts else None
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        s = str(value).strip().lower()
        return s if s and s not in ("not_reported", "not_extracted", "not_applicable", "") else None

    def _compare_source_identity(self, data_a: dict, data_b: dict) -> str:
        """Compare source identity of two field entries.

        Returns:
            "SAME_SOURCE" — sufficient metadata confirms same origin/conditions/sample
            "DIFFERENT_SOURCE" — metadata confirms different sources
            "UNRESOLVED" — insufficient metadata to determine (neither auto-dedup nor clear)
        """
        source_keys = ["origin", "source_quote", "source_anchor"]
        context_keys = ["conditions", "sample", "catalyst"]
        all_keys = source_keys + context_keys

        has_meta_a = any(
            data_a.get(k) for k in all_keys
            if not isinstance(data_a.get(k), (dict, list)) or data_a.get(k)
        )
        has_meta_b = any(
            data_b.get(k) for k in all_keys
            if not isinstance(data_b.get(k), (dict, list)) or data_b.get(k)
        )

        if not has_meta_a and not has_meta_b:
            return "UNRESOLVED"

        origin_a = str(data_a.get("origin", "")).strip()
        origin_b = str(data_b.get("origin", "")).strip()
        if origin_a and origin_b and origin_a != origin_b:
            return "DIFFERENT_SOURCE"

        quote_a = str(data_a.get("source_quote", "")).strip()
        quote_b = str(data_b.get("source_quote", "")).strip()
        if quote_a and quote_b and quote_a != quote_b:
            return "DIFFERENT_SOURCE"

        cond_a = str(self._get_field_meta(data_a, "conditions")).strip()
        cond_b = str(self._get_field_meta(data_b, "conditions")).strip()
        if cond_a and cond_b and cond_a != cond_b:
            return "DIFFERENT_SOURCE"

        sample_a = str(self._get_field_meta(data_a, "sample", "catalyst")).strip()
        sample_b = str(self._get_field_meta(data_b, "sample", "catalyst")).strip()
        if sample_a and sample_b and sample_a != sample_b:
            return "DIFFERENT_SOURCE"

        if has_meta_a and has_meta_b:
            return "SAME_SOURCE"

        return "UNRESOLVED"

    def _get_field_meta(self, data: dict, *keys: str) -> str:
        """Get metadata from field data, trying multiple keys."""
        for key in keys:
            val = data.get(key)
            if val:
                return str(val)
        return ""

    # Helper methods

    def _count_fields(self, dimensions: dict) -> tuple[int, int]:
        """Count total and reported fields."""
        total = 0
        reported = 0
        for dim_data in dimensions.values():
            fields = dim_data.get("fields", {})
            for field_data in fields.values():
                total += 1
                if field_data.get("status") == "REPORTED":
                    reported += 1
        return total, reported

    def _calculate_dimension_scores(self, dimensions: dict) -> dict[str, float]:
        """Calculate per-dimension quality scores."""
        scores = {}
        for dim_name, dim_data in dimensions.items():
            fields = dim_data.get("fields", {})
            if not fields:
                scores[dim_name] = 0.0
                continue
            reported = sum(1 for f in fields.values() if f.get("status") == "REPORTED")
            scores[dim_name] = reported / len(fields)
        return scores

    def _calculate_overall_score(self, check_results: list[CheckResult], dim_scores: dict[str, float]) -> float:
        """Calculate overall quality score."""
        # Weight: 50% check pass rate, 50% dimension coverage
        check_score = sum(1 for r in check_results if r.status == CheckStatus.PASS) / max(len(check_results), 1)
        dim_score = sum(dim_scores.values()) / max(len(dim_scores), 1)
        return 0.5 * check_score + 0.5 * dim_score

    def _text_contains_value(self, text: str, field_name: str) -> bool:
        """Check if text likely contains value for field."""
        # Simple heuristic: look for numerical patterns
        patterns = [
            r"\d+\.?\d*\s*(nm|°C|K|atm|bar|Pa|m2/g|eV|mol|%|mg|g)",
            r"\d+\.?\d*\s*[×x]\s*10\^?\-?\d+",
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _text_may_contain_data(self, text: str, field_name: str) -> bool:
        """Check if text may contain data for field."""
        # Look for field-related keywords with numerical values
        keywords = field_name.replace("_", " ").split()
        for keyword in keywords:
            if len(keyword) > 3:
                pattern = rf"{keyword}.*?\d+\.?\d*"
                if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                    return True
        return False

    def _is_numeric(self, value: Any) -> bool:
        """Check if value is numeric."""
        try:
            float(str(value).split()[0])
            return True
        except (ValueError, IndexError):
            return False

    def _guess_range_key(self, field_name: str, unit: str) -> Optional[str]:
        """Guess range key from field name and unit."""
        if "temperature" in field_name.lower() or "°C" in unit or "K" in unit:
            return "temperature_celsius"
        if "pressure" in field_name.lower() or "atm" in unit or "bar" in unit:
            return "pressure_atm"
        if "conversion" in field_name.lower() or "%" in unit:
            return "conversion_percent"
        if "selectivity" in field_name.lower():
            return "selectivity_percent"
        if "surface" in field_name.lower() or "m2/g" in unit:
            return "surface_area_m2_g"
        if "particle" in field_name.lower() or "size" in field_name.lower() or "nm" in unit:
            return "particle_size_nm"
        if "binding" in field_name.lower() or "eV" in unit:
            return "binding_energy_ev"
        return None

    def _build_failed_fields(self, result: CheckResult, failure_mode: str) -> list[dict]:
        """Build failed field records from check result."""
        return [
            {
                "field_path": field,
                "failure_mode": failure_mode,
                "severity": result.severity.value,
                "message": result.message,
            }
            for field in result.affected_fields
        ]
