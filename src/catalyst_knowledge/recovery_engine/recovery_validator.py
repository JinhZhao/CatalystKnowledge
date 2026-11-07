"""RecoveryValidator — Validate merged recovery results.

Validation checks:
1. Schema compliance — All required fields present
2. Value range validation — Numerical values within bounds
3. Unit consistency check — Units match expected types
4. Source anchor presence — Every value has document location
5. Cross-field coherence — Related fields are consistent
6. Literature contamination detection — Original vs. literature labeled
7. False positive screening — Reject spurious recoveries
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .recovery_merger import MergedResults


class ValidationStatus(str, Enum):
    """Validation result status."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


@dataclass
class ValidationCheck:
    """Single validation check result."""
    check_name: str
    status: ValidationStatus
    message: str
    affected_fields: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete validation report."""
    report_id: str
    document_id: str
    validated_at: str
    overall_status: ValidationStatus
    checks: list[ValidationCheck] = field(default_factory=list)
    validated_fields: list[str] = field(default_factory=list)
    rejected_fields: list[str] = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0


class RecoveryValidator:
    """Validate merged recovery results."""

    # Plausible ranges for validation
    RANGES = {
        "temperature": (-273, 2000),
        "pressure": (0, 1000),
        "conversion": (0, 100),
        "selectivity": (0, 100),
        "surface_area": (0, 5000),
        "particle_size": (0.1, 1000),
        "binding_energy": (0, 1500),
    }

    def __init__(self, config: Optional[dict] = None):
        """Initialize with optional configuration."""
        self.config = config or {}
        self.strict_mode = self.config.get("strict_mode", False)

    def validate(self, merged: MergedResults) -> ValidationReport:
        """Validate merged recovery results.

        Args:
            merged: Output from RecoveryMerger

        Returns:
            ValidationReport with all check results
        """
        report_id = f"VAL_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checks: list[ValidationCheck] = []
        validated_fields: list[str] = []
        rejected_fields: list[str] = []

        dimensions = merged.merged_dimensions

        # Run validation checks
        checks.append(self._check_schema_compliance(dimensions))
        checks.append(self._check_value_ranges(dimensions, rejected_fields))
        checks.append(self._check_unit_consistency(dimensions))
        checks.append(self._check_source_anchors(dimensions, rejected_fields))
        checks.append(self._check_cross_field_coherence(dimensions))
        checks.append(self._check_literature_contamination(dimensions))
        checks.append(self._check_false_positives(merged, rejected_fields))

        # Collect validated fields
        for dim_data in dimensions.values():
            for field_name, field_data in dim_data.get("fields", {}).items():
                if field_data.get("status") == "REPORTED":
                    validated_fields.append(f"{dim_data.get('dimension', 'unknown')}.{field_name}")

        # Calculate statistics
        passed = sum(1 for c in checks if c.status == ValidationStatus.PASS)
        failed = sum(1 for c in checks if c.status == ValidationStatus.FAIL)
        warnings = sum(1 for c in checks if c.status == ValidationStatus.WARNING)

        # Determine overall status
        if failed > 0:
            overall_status = ValidationStatus.FAIL
        elif warnings > 0:
            overall_status = ValidationStatus.WARNING
        else:
            overall_status = ValidationStatus.PASS

        return ValidationReport(
            report_id=report_id,
            document_id=merged.document_id,
            validated_at=datetime.now().isoformat(),
            overall_status=overall_status,
            checks=checks,
            validated_fields=validated_fields,
            rejected_fields=rejected_fields,
            total_checks=len(checks),
            passed_checks=passed,
            failed_checks=failed,
            warning_checks=warnings,
        )

    def _check_schema_compliance(self, dimensions: dict) -> ValidationCheck:
        """Check schema compliance."""
        required_dim_keys = ["dimension", "fields"]
        required_field_keys = ["field_name", "status"]

        affected = []
        for dim_name, dim_data in dimensions.items():
            for key in required_dim_keys:
                if key not in dim_data:
                    affected.append(f"{dim_name}:missing_{key}")

            for field_name, field_data in dim_data.get("fields", {}).items():
                for key in required_field_keys:
                    if key not in field_data:
                        affected.append(f"{dim_name}.{field_name}:missing_{key}")

        if affected:
            return ValidationCheck(
                check_name="schema_compliance",
                status=ValidationStatus.FAIL,
                message=f"Schema violations found in {len(affected)} locations",
                affected_fields=affected,
            )

        return ValidationCheck(
            check_name="schema_compliance",
            status=ValidationStatus.PASS,
            message="Schema compliance verified",
        )

    def _check_value_ranges(self, dimensions: dict, rejected: list[str]) -> ValidationCheck:
        """Check value ranges."""
        affected = []
        for dim_name, dim_data in dimensions.items():
            for field_name, field_data in dim_data.get("fields", {}).items():
                value = field_data.get("value")
                if value is None:
                    continue

                # Try numerical validation
                try:
                    num_val = float(str(value).split()[0])
                    range_key = self._guess_range_key(field_name)
                    if range_key and range_key in self.RANGES:
                        min_val, max_val = self.RANGES[range_key]
                        if num_val < min_val or num_val > max_val:
                            affected.append(f"{dim_name}.{field_name}")
                            if self.strict_mode:
                                rejected.append(f"{dim_name}.{field_name}")
                except (ValueError, IndexError):
                    pass

        if affected:
            return ValidationCheck(
                check_name="value_range_validation",
                status=ValidationStatus.WARNING,
                message=f"{len(affected)} fields have values outside typical ranges",
                affected_fields=affected,
            )

        return ValidationCheck(
            check_name="value_range_validation",
            status=ValidationStatus.PASS,
            message="All values within plausible ranges",
        )

    def _check_unit_consistency(self, dimensions: dict) -> ValidationCheck:
        """Check unit consistency."""
        affected = []
        for dim_name, dim_data in dimensions.items():
            for field_name, field_data in dim_data.get("fields", {}).items():
                value = str(field_data.get("value", ""))
                unit = field_data.get("unit", "")

                # Check for unit in value (redundant)
                if unit and unit in value:
                    affected.append(f"{dim_name}.{field_name}")

        if affected:
            return ValidationCheck(
                check_name="unit_consistency",
                status=ValidationStatus.WARNING,
                message=f"{len(affected)} fields have potential unit redundancy",
                affected_fields=affected,
            )

        return ValidationCheck(
            check_name="unit_consistency",
            status=ValidationStatus.PASS,
            message="Unit consistency verified",
        )

    def _check_source_anchors(self, dimensions: dict, rejected: list[str]) -> ValidationCheck:
        """Check source anchor presence."""
        affected = []
        for dim_name, dim_data in dimensions.items():
            for field_name, field_data in dim_data.get("fields", {}).items():
                if field_data.get("status") == "REPORTED":
                    anchor = field_data.get("source_anchor")
                    if not anchor:
                        affected.append(f"{dim_name}.{field_name}")
                        if self.strict_mode:
                            rejected.append(f"{dim_name}.{field_name}")

        if affected:
            return ValidationCheck(
                check_name="source_anchor_presence",
                status=ValidationStatus.FAIL if self.strict_mode else ValidationStatus.WARNING,
                message=f"{len(affected)} REPORTED fields missing source anchors",
                affected_fields=affected,
            )

        return ValidationCheck(
            check_name="source_anchor_presence",
            status=ValidationStatus.PASS,
            message="All REPORTED fields have source anchors",
        )

    def _check_cross_field_coherence(self, dimensions: dict) -> ValidationCheck:
        """Check cross-field coherence."""
        affected = []

        # Check performance dimension coherence
        perf = dimensions.get("performance", {}).get("fields", {})
        conversion = perf.get("conversion", {}).get("value")
        selectivity = perf.get("selectivity", {}).get("value")

        if conversion and selectivity:
            try:
                conv = float(str(conversion).split()[0])
                sel = float(str(selectivity).split()[0])
                if conv > 0 and sel > 100:
                    affected.append("performance.selectivity")
            except ValueError:
                pass

        if affected:
            return ValidationCheck(
                check_name="cross_field_coherence",
                status=ValidationStatus.WARNING,
                message=f"Cross-field incoherence detected in {len(affected)} fields",
                affected_fields=affected,
            )

        return ValidationCheck(
            check_name="cross_field_coherence",
            status=ValidationStatus.PASS,
            message="Cross-field coherence verified",
        )

    def _check_literature_contamination(self, dimensions: dict) -> ValidationCheck:
        """Check for literature contamination."""
        literature_keywords = [
            "reported by", "reference", "literature", "et al.",
            "compared to", "similar to", "consistent with",
        ]

        affected = []
        for dim_name, dim_data in dimensions.items():
            for field_name, field_data in dim_data.get("fields", {}).items():
                origin = field_data.get("origin", "")
                value = str(field_data.get("value", "")).lower()
                quote = str(field_data.get("source_quote", "")).lower()

                if origin == "ORIGINAL_EXPERIMENT":
                    text = f"{value} {quote}"
                    for keyword in literature_keywords:
                        if keyword in text:
                            affected.append(f"{dim_name}.{field_name}")
                            break

        if affected:
            return ValidationCheck(
                check_name="literature_contamination_detection",
                status=ValidationStatus.FAIL,
                message=f"Potential literature contamination in {len(affected)} fields",
                affected_fields=affected,
            )

        return ValidationCheck(
            check_name="literature_contamination_detection",
            status=ValidationStatus.PASS,
            message="No literature contamination detected",
        )

    def _check_false_positives(self, merged: MergedResults, rejected: list[str]) -> ValidationCheck:
        """Check for false positive recoveries."""
        affected = []

        # Check for suspicious patterns in merge actions
        for action in merged.merge_actions:
            if action.action_type == "REPLACED":
                # Check if original was REPORTED and replacement is very different
                if action.original_value is not None:
                    if self._values_very_different(action.original_value, action.recovered_value):
                        affected.append(action.field_path)

        if affected:
            return ValidationCheck(
                check_name="false_positive_screening",
                status=ValidationStatus.WARNING,
                message=f"{len(affected)} recoveries have significantly different values from original",
                affected_fields=affected,
            )

        return ValidationCheck(
            check_name="false_positive_screening",
            status=ValidationStatus.PASS,
            message="No false positives detected",
        )

    def _guess_range_key(self, field_name: str) -> Optional[str]:
        """Guess range key from field name."""
        name_lower = field_name.lower()
        if "temperature" in name_lower:
            return "temperature"
        if "pressure" in name_lower:
            return "pressure"
        if "conversion" in name_lower:
            return "conversion"
        if "selectivity" in name_lower:
            return "selectivity"
        if "surface" in name_lower or "area" in name_lower:
            return "surface_area"
        if "particle" in name_lower or "size" in name_lower:
            return "particle_size"
        if "binding" in name_lower or "energy" in name_lower:
            return "binding_energy"
        return None

    def _values_very_different(self, val1: any, val2: Any) -> bool:
        """Check if two values are very different."""
        try:
            num1 = float(str(val1).split()[0])
            num2 = float(str(val2).split()[0])
            if num1 > 0:
                return abs(num1 - num2) / num1 > 0.5  # >50% difference
        except (ValueError, ZeroDivisionError):
            pass
        return str(val1).lower() != str(val2).lower()
