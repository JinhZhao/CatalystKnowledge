"""Numeric Anchor Checker — validate physical plausibility of claims.

Checks extracted numeric values against domain-specific ranges to flag
suspicious claims before human review or KB injection.

Usage:
    checker = NumericAnchorChecker()
    result = checker.check_claim(claim)  # Returns ValidationResult with warnings
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class NumericCheckResult:
    """Result of numeric anchor check."""
    
    is_plausible: bool
    warnings: list[str] | None = None
    flagged_values: list[dict[str, Any]] | None = None


class NumericAnchorChecker:
    """Check numeric values in claims against physical plausibility ranges."""
    
    def __init__(self, anchors_file: str | None = None):
        """Initialize with audit anchors YAML.
        
        Args:
            anchors_file: Path to audit_anchors.yaml. If None, uses default location.
        """
        if anchors_file is None:
            # Default: project_root/config/audit_anchors.yaml
            project_root = Path(__file__).parent.parent.parent.parent
            anchors_file = str(project_root / "config" / "audit_anchors.yaml")
        
        self._anchors = self._load_anchors(anchors_file)
        self._unit_conversions = self._anchors.get("unit_conversions", {})
    
    def _load_anchors(self, filepath: str) -> dict[str, Any]:
        """Load audit anchors from YAML file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not isinstance(data, dict):
                logger.warning("[NumericAnchor] Invalid YAML format, using empty anchors")
                return {}
            
            logger.info(
                "[NumericAnchor] Loaded %d anchor definitions from %s",
                len([k for k in data if k != "unit_conversions"]),
                filepath,
            )
            
            return data
        
        except FileNotFoundError:
            logger.warning("[NumericAnchor] Anchors file not found: %s", filepath)
            return {}
        except Exception as e:
            logger.error("[NumericAnchor] Failed to load anchors: %s", e)
            return {}
    
    def check_claim(self, claim_value: str) -> NumericCheckResult:
        """Check a claim's numeric values against anchor ranges.
        
        Args:
            claim_value: The value field from CitedClaim (e.g., "活化能为85 kJ/mol")
        
        Returns:
            NumericCheckResult with warnings for suspicious values
        """
        warnings = []
        flagged_values = []
        
        # Extract all numeric patterns from claim
        numbers = self._extract_numbers(claim_value)
        
        if not numbers:
            # No numeric values found, nothing to check
            return NumericCheckResult(is_plausible=True)
        
        # Check each extracted number against relevant anchors
        for num_info in numbers:
            value = num_info['value']
            unit = num_info.get('unit', '').lower()
            quantity_name = num_info.get('quantity', '')
            
            # Try to match against known anchors
            anchor = self._find_matching_anchor(quantity_name, unit)
            
            if anchor:
                # Normalize value to canonical unit
                normalized_value = self._normalize_unit(value, unit, anchor['unit'])
                
                # Check range
                min_val, max_val = anchor['range']
                if normalized_value < min_val or normalized_value > max_val:
                    warning_msg = (
                        f"数值可疑: {value} {unit} "
                        f"(合理范围: {min_val}-{max_val} {anchor['unit']}) - "
                        f"{anchor.get('note', '')}"
                    )
                    warnings.append(warning_msg)
                    flagged_values.append({
                        "original_value": value,
                        "original_unit": unit,
                        "normalized_value": normalized_value,
                        "canonical_unit": anchor['unit'],
                        "quantity": quantity_name,
                        "reason": "out_of_range",
                    })
                    logger.warning("[NumericAnchor] Flagged: %s", warning_msg)
        
        is_plausible = len(warnings) == 0
        
        return NumericCheckResult(
            is_plausible=is_plausible,
            warnings=warnings if warnings else None,
            flagged_values=flagged_values if flagged_values else None,
        )
    
    def _extract_numbers(self, text: str) -> list[dict[str, Any]]:
        """Extract numeric values with units and quantity names from text.
        
        Patterns:
        - "活化能为85 kJ/mol" → {value: 85, unit: "kJ/mol", quantity: "活化能"}
        - "TOF = 1.5 s^-1" → {value: 1.5, unit: "s^-1", quantity: "TOF"}
        - "温度200°C" → {value: 200, unit: "°C", quantity: "温度"}
        
        Returns list of dicts with 'value', 'unit', 'quantity' keys.
        """
        results = []
        
        # Pattern 1: Chinese quantity + number + unit
        # e.g., "活化能为85 kJ/mol", "温度200°C"
        pattern1 = re.compile(
            r'([\u4e00-\u9fa5]+?)'  # Quantity name (Chinese chars)
            r'(?:为|=|：|:)?'        # Optional separator
            r'(-?\d+\.?\d*)'       # Number (with optional decimal)
            r'\s*'
            r'([a-zA-Z°%^/\-\+\^0-9]+)'  # Unit (alphanumeric + symbols)
        )
        
        for match in pattern1.finditer(text):
            quantity_cn = match.group(1).strip()
            value_str = match.group(2)
            unit = match.group(3).strip()
            
            try:
                value = float(value_str)
                quantity_en = self._translate_quantity(quantity_cn)
                
                results.append({
                    "value": value,
                    "unit": unit,
                    "quantity": quantity_en,
                    "original_text": match.group(0),
                })
            except ValueError:
                continue
        
        # Pattern 2: English acronym + number + unit
        # e.g., "TOF = 1.5 s^-1", "FE = 95%"
        pattern2 = re.compile(
            r'([A-Z][A-Za-z0-9]*)'  # Acronym (starts with capital)
            r'\s*=?\s*'             # Optional equals sign
            r'(-?\d+\.?\d*)'       # Number
            r'\s*'
            r'([a-zA-Z°%^/\-\+\^0-9]+)'  # Unit
        )
        
        for match in pattern2.finditer(text):
            quantity_abbr = match.group(1).strip()
            value_str = match.group(2)
            unit = match.group(3).strip()
            
            try:
                value = float(value_str)
                results.append({
                    "value": value,
                    "unit": unit,
                    "quantity": quantity_abbr.lower(),
                    "original_text": match.group(0),
                })
            except ValueError:
                continue
        
        return results
    
    def _translate_quantity(self, chinese_term: str) -> str:
        """Translate Chinese quantity terms to English anchor keys.
        
        This is a simple mapping; can be extended with more terms.
        """
        translation_map = {
            "活化能": "activation_energy",
            "吸附能": "adsorption_energy",
            "反应温度": "reaction_temperature",
            "温度": "reaction_temperature",
            "转换频率": "turnover_frequency",
            "法拉第效率": "faradaic_efficiency",
            "选择性": "selectivity",
            "转化率": "conversion",
            "电流密度": "current_density",
            "过电位": "overpotential",
            "结合能": "binding_energy",
            "粒径": "particle_size",
            "比表面积": "surface_area",
            "孔径": "pore_size",
            "稳定性": "stability_hours",
            "产率": "yield",
            "时空产率": "space_time_yield",
        }
        
        # Exact match first
        if chinese_term in translation_map:
            return translation_map[chinese_term]
        
        # Partial match
        for cn_term, en_key in translation_map.items():
            if cn_term in chinese_term:
                return en_key
        
        # Return original if no match
        return chinese_term.lower()
    
    def _find_matching_anchor(self, quantity: str, unit: str) -> dict | None:
        """Find the appropriate anchor for a quantity-unit pair."""
        # Direct key match
        if quantity in self._anchors and quantity != "unit_conversions":
            return self._anchors[quantity]
        
        # Try common aliases
        alias_map = {
            "fe": "faradaic_efficiency",
            "tof": "turnover_frequency",
            "ea": "activation_energy",
            "temp": "reaction_temperature",
        }
        
        if quantity in alias_map:
            key = alias_map[quantity]
            if key in self._anchors:
                return self._anchors[key]
        
        return None
    
    def _normalize_unit(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convert value from one unit to canonical unit using conversion factors."""
        if from_unit.lower() == to_unit.lower():
            return value
        
        # Build conversion key
        conversion_key = f"{from_unit.lower()}_to_{to_unit.lower()}"
        
        if conversion_key in self._unit_conversions:
            factor = self._unit_conversions[conversion_key]
            return value * factor
        
        # Common hardcoded conversions
        if from_unit.lower() == "kcal/mol" and to_unit.lower() == "kj/mol":
            return value * 4.184
        elif from_unit.lower() == "ev" and to_unit.lower() == "kj/mol":
            return value * 96.485
        elif from_unit.lower() == "j/mol" and to_unit.lower() == "kj/mol":
            return value / 1000.0
        
        # No conversion found, return as-is (will likely fail range check)
        logger.debug(
            "[NumericAnchor] No conversion for %s → %s, using raw value",
            from_unit, to_unit,
        )
        return value
