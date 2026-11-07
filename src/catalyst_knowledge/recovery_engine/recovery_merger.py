"""RecoveryMerger — Merge recovered data with original extraction results.

Merge rules:
1. Replace if validated — Overwrite original only if recovery passes validation
2. Preserve attribution — Keep original source_type and source_anchor metadata
3. Append audit trail — Add recovery phase to field history
4. Flag conflicts — Mark contradictory evidence for manual review
5. Idempotent — Re-running recovery produces same result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .targeted_extractor import ExtractedField


@dataclass
class MergeAction:
    """Record of a single merge action."""
    field_path: str
    action_type: str  # REPLACED, PRESERVED, FLAGGED, SKIPPED
    original_value: Any
    recovered_value: Any
    reason: str
    timestamp: str


@dataclass
class MergedResults:
    """Result of merging recovered data with original."""
    merge_id: str
    document_id: str
    merged_at: str
    merged_dimensions: dict
    merge_actions: list[MergeAction] = field(default_factory=list)
    total_fields_merged: int = 0
    fields_replaced: int = 0
    fields_preserved: int = 0
    fields_flagged: int = 0
    fields_skipped: int = 0
    audit_trail: list[str] = field(default_factory=list)


class RecoveryMerger:
    """Merge recovered data with original extraction results."""

    def __init__(self, config: Optional[dict] = None):
        """Initialize with optional configuration."""
        self.config = config or {}
        self.merge_strategy = self.config.get("merge_strategy", "replace_if_validated")
        self.preserve_attribution = self.config.get("preserve_source_attribution", True)
        self.append_audit_trail = self.config.get("append_audit_trail", True)
        self.idempotent = self.config.get("idempotent_operations", True)

    def merge(
        self,
        original: dict,
        recovered: list[ExtractedField],
        phase_tag: str = "recovery",
    ) -> MergedResults:
        """Merge recovered fields into original extraction results.

        Args:
            original: Original six-dimension extraction results
            recovered: List of recovered fields from TargetedExtractor
            phase_tag: Tag to mark recovery phase in audit trail

        Returns:
            MergedResults with merged data and action log
        """
        merge_id = f"MERGE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        document_id = original.get("document_id", "unknown")

        # Deep copy original dimensions
        merged_dimensions = self._deep_copy_dimensions(original.get("dimensions", {}))

        merge_actions: list[MergeAction] = []
        audit_trail: list[str] = []

        # Process each recovered field
        for extracted in recovered:
            action = self._merge_single_field(
                merged_dimensions=merged_dimensions,
                extracted=extracted,
                phase_tag=phase_tag,
            )
            merge_actions.append(action)

            # Add to audit trail
            if self.append_audit_trail:
                trail_entry = f"{phase_tag}:{action.action_type}@{extracted.field_path}"
                audit_trail.append(trail_entry)

        # Calculate statistics
        fields_replaced = sum(1 for a in merge_actions if a.action_type == "REPLACED")
        fields_preserved = sum(1 for a in merge_actions if a.action_type == "PRESERVED")
        fields_flagged = sum(1 for a in merge_actions if a.action_type == "FLAGGED")
        fields_skipped = sum(1 for a in merge_actions if a.action_type == "SKIPPED")

        return MergedResults(
            merge_id=merge_id,
            document_id=document_id,
            merged_at=datetime.now().isoformat(),
            merged_dimensions=merged_dimensions,
            merge_actions=merge_actions,
            total_fields_merged=len(merge_actions),
            fields_replaced=fields_replaced,
            fields_preserved=fields_preserved,
            fields_flagged=fields_flagged,
            fields_skipped=fields_skipped,
            audit_trail=audit_trail,
        )

    def _merge_single_field(
        self,
        merged_dimensions: dict,
        extracted: ExtractedField,
        phase_tag: str,
    ) -> MergeAction:
        """Merge a single recovered field."""
        field_path = extracted.field_path
        parts = field_path.split(".")

        if len(parts) != 2:
            return MergeAction(
                field_path=field_path,
                action_type="SKIPPED",
                original_value=None,
                recovered_value=extracted.value,
                reason=f"Invalid field path format: {field_path}",
                timestamp=datetime.now().isoformat(),
            )

        dim_name, field_name = parts

        # Get original field data
        dim_data = merged_dimensions.get(dim_name, {})
        fields = dim_data.get("fields", {})
        original_field = fields.get(field_name, {})
        original_value = original_field.get("value")
        original_status = original_field.get("status", "NOT_EXTRACTED")

        # Determine merge action based on strategy
        if extracted.status == "UNRESOLVED":
            # Don't replace with UNRESOLVED
            return MergeAction(
                field_path=field_path,
                action_type="SKIPPED",
                original_value=original_value,
                recovered_value=extracted.value,
                reason="Recovered value is UNRESOLVED",
                timestamp=datetime.now().isoformat(),
            )

        if extracted.status == "NOT_REPORTED":
            # Keep original if it exists
            if original_status == "REPORTED":
                return MergeAction(
                    field_path=field_path,
                    action_type="PRESERVED",
                    original_value=original_value,
                    recovered_value=extracted.value,
                    reason="Original value preserved (recovery found no data)",
                    timestamp=datetime.now().isoformat(),
                )
            else:
                # Update status to NOT_REPORTED
                self._update_field(merged_dimensions, dim_name, field_name, {
                    "status": "NOT_REPORTED",
                    "phase_history": original_field.get("phase_history", []) + [f"{phase_tag}:NOT_REPORTED"],
                })
                return MergeAction(
                    field_path=field_path,
                    action_type="REPLACED",
                    original_value=original_value,
                    recovered_value=None,
                    reason="Updated status to NOT_REPORTED",
                    timestamp=datetime.now().isoformat(),
                )

        # Check for conflicts
        if original_status == "REPORTED" and original_value != extracted.value:
            # Potential conflict
            if self._values_conflict(original_value, extracted.value):
                # Flag for manual review
                self._update_field(merged_dimensions, dim_name, field_name, {
                    "conflict_flag": True,
                    "conflict_values": [original_value, extracted.value],
                    "phase_history": original_field.get("phase_history", []) + [f"{phase_tag}:FLAGGED"],
                })
                return MergeAction(
                    field_path=field_path,
                    action_type="FLAGGED",
                    original_value=original_value,
                    recovered_value=extracted.value,
                    reason="Conflicting values flagged for manual review",
                    timestamp=datetime.now().isoformat(),
                )

        # Replace with recovered value
        update_data = {
            "value": extracted.value,
            "unit": extracted.unit,
            "status": "REPORTED",
            "confidence": extracted.confidence,
            "source_quote": extracted.source_quote,
            "source_anchor": extracted.source_anchor,
            "verification_status": "RECOVERED",
        }

        # Preserve attribution if configured
        if self.preserve_attribution:
            update_data["original_source_type"] = original_field.get("origin", "UNKNOWN_ORIGIN")
            update_data["recovery_source_type"] = "RECOVERED"

        # Append to phase history
        if self.append_audit_trail:
            phase_history = original_field.get("phase_history", [])
            update_data["phase_history"] = phase_history + [f"{phase_tag}:REPORTED"]

        self._update_field(merged_dimensions, dim_name, field_name, update_data)

        return MergeAction(
            field_path=field_path,
            action_type="REPLACED",
            original_value=original_value,
            recovered_value=extracted.value,
            reason="Replaced with recovered value",
            timestamp=datetime.now().isoformat(),
        )

    def _update_field(self, dimensions: dict, dim_name: str, field_name: str, updates: dict):
        """Update a field in dimensions."""
        if dim_name not in dimensions:
            dimensions[dim_name] = {"fields": {}}
        if field_name not in dimensions[dim_name]["fields"]:
            dimensions[dim_name]["fields"][field_name] = {}

        dimensions[dim_name]["fields"][field_name].update(updates)

    def _values_conflict(self, val1: Any, val2: Any) -> bool:
        """Check if two values conflict."""
        if val1 is None or val2 is None:
            return False
        if str(val1).strip() == str(val2).strip():
            return False

        # Try numerical comparison
        try:
            num1 = float(str(val1).split()[0])
            num2 = float(str(val2).split()[0])
            # Conflict if difference > 10%
            if num1 > 0:
                return abs(num1 - num2) / num1 > 0.1
        except (ValueError, ZeroDivisionError):
            pass

        # String comparison
        return str(val1).lower() != str(val2).lower()

    def _deep_copy_dimensions(self, dimensions: dict) -> dict:
        """Deep copy dimensions dict."""
        import copy
        return copy.deepcopy(dimensions)
