"""
NUM-UNIT-001 Quantity Registry Loader and Validator

Loads quantity_definitions.yaml and validates structure using Pydantic.
"""

import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime


# ============================================================================
# Pydantic Models for Schema Validation
# ============================================================================

class Abbreviation(BaseModel):
    """Abbreviation definition with context requirements."""
    symbol: str
    context_required: bool = True
    disambiguation: Optional[str] = None
    context_examples: Optional[List[str]] = None


class ConversionFormula(BaseModel):
    """Unit conversion formula."""
    from_unit: str = Field(..., alias='from')
    to_unit: str = Field(..., alias='to')
    formula: str
    
    class Config:
        populate_by_name = True


class ConversionRules(BaseModel):
    """Conversion rules for a quantity."""
    allow_auto_convert: Any  # Can be bool or string like "time_only"
    conversion_type: Optional[str] = None
    formulas: Optional[List[ConversionFormula]] = None
    inherits_from: Optional[str] = None
    restrictions: Optional[List[str]] = None
    notes: Optional[List[str]] = None


class ExperimentalContext(BaseModel):
    """Required experimental context."""
    field_name: str


class ValidationRules(BaseModel):
    """Validation rules for quantity values."""
    min_value_si: Optional[float] = None
    max_value_si: Optional[float] = None
    typical_range_si: Optional[List[float]] = None


class DomainUnit(BaseModel):
    """Domain-specific unit definition."""
    unit: str
    display_name: str
    usage: Optional[str] = None
    conversion_to_si: Optional[str] = None


class Quantity(BaseModel):
    """Scientific quantity definition."""
    quantity_type: str
    synonyms: List[str]
    abbreviations: Optional[List[Abbreviation]] = None
    dimension: str
    si_unit: str
    si_unit_note: Optional[str] = None
    domain_units: List[DomainUnit]
    conversion_rules: ConversionRules
    experimental_context_required: Optional[List[str]] = None
    validation_rules: Optional[ValidationRules] = None
    qa_checks: Optional[List[str]] = None
    
    @validator('quantity_type')
    def validate_quantity_type(cls, v):
        if not v or not v.strip():
            raise ValueError('quantity_type cannot be empty')
        return v.strip()
    
    @validator('si_unit')
    def validate_si_unit(cls, v):
        if not v or not v.strip():
            raise ValueError('si_unit cannot be empty')
        return v.strip()
    
    @validator('dimension')
    def validate_dimension(cls, v):
        if not v or not v.strip():
            raise ValueError('dimension cannot be empty')
        return v.strip()


class GlobalValidation(BaseModel):
    """Global validation rules."""
    require_experimental_context: bool = True
    allow_missing_values: bool = True
    missing_value_representation: Any = None
    false_zero_prohibition: bool = True
    unit_parsing: Optional[Dict[str, Any]] = None
    conversion_statuses: Optional[List[Dict[str, str]]] = None
    qa_checks: Optional[List[Dict[str, Any]]] = None


class QuantityRegistry(BaseModel):
    """Complete quantity registry configuration."""
    version: str
    status: str
    created: str
    last_updated: str
    schema_version: str
    quantities: List[Quantity]
    global_validation: Optional[GlobalValidation] = None
    
    @validator('version')
    def validate_version(cls, v):
        if not v or not v.strip():
            raise ValueError('version cannot be empty')
        return v.strip()
    
    @validator('status')
    def validate_status(cls, v):
        valid_statuses = ['engineering_candidate', 'validated', 'deprecated']
        if v not in valid_statuses:
            raise ValueError(f'status must be one of {valid_statuses}')
        return v


# ============================================================================
# Loader Class
# ============================================================================

class QuantityRegistryLoader:
    """Loads and validates quantity registry from YAML file."""
    
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'quantity_definitions.yaml'
        self.config_path = config_path
        self.registry: Optional[QuantityRegistry] = None
        self.quantities_by_type: Dict[str, Quantity] = {}
        self.load_errors: List[str] = []
        self.validation_warnings: List[str] = []
    
    def load(self) -> bool:
        """Load and validate the quantity registry."""
        try:
            if not self.config_path.exists():
                self.load_errors.append(f"Config file not found: {self.config_path}")
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # Validate with Pydantic
            self.registry = QuantityRegistry(**data)
            
            # Build lookup index
            for qty in self.registry.quantities:
                self.quantities_by_type[qty.quantity_type] = qty
            
            # Additional validation checks
            self._validate_pint_units()
            self._validate_conversion_formulas()
            self._check_ambiguous_abbreviations()
            
            return len(self.load_errors) == 0
            
        except yaml.YAMLError as e:
            self.load_errors.append(f"YAML parsing error: {e}")
            return False
        except Exception as e:
            self.load_errors.append(f"Validation error: {e}")
            return False
    
    def _validate_pint_units(self):
        """Validate that units are compatible with Pint."""
        try:
            import pint
            ureg = pint.UnitRegistry()
            
            for qty in self.registry.quantities:
                # Check SI unit
                try:
                    if qty.si_unit not in ['1', 'variable']:
                        ureg.parse_expression(qty.si_unit)
                except Exception as e:
                    self.validation_warnings.append(
                        f"{qty.quantity_type}: SI unit '{qty.si_unit}' may not be Pint-compatible: {e}"
                    )
                
                # Check domain units
                for domain_unit in qty.domain_units:
                    try:
                        if domain_unit.unit not in ['1', 'variable']:
                            ureg.parse_expression(domain_unit.unit)
                    except Exception as e:
                        self.validation_warnings.append(
                            f"{qty.quantity_type}: Domain unit '{domain_unit.unit}' may not be Pint-compatible: {e}"
                        )
        except ImportError:
            self.validation_warnings.append("Pint not installed, skipping unit validation")
    
    def _validate_conversion_formulas(self):
        """Validate conversion formulas are present and parseable."""
        for qty in self.registry.quantities:
            rules = qty.conversion_rules
            
            # Check if auto-convert is allowed but no formulas provided
            if rules.allow_auto_convert and rules.conversion_type != 'none':
                if not rules.formulas and not rules.inherits_from:
                    self.validation_warnings.append(
                        f"{qty.quantity_type}: allow_auto_convert=True but no formulas or inherits_from specified"
                    )
    
    def _check_ambiguous_abbreviations(self):
        """Check for abbreviations that require context disambiguation."""
        for qty in self.registry.quantities:
            if qty.abbreviations:
                for abbr in qty.abbreviations:
                    if abbr.context_required and not abbr.disambiguation:
                        self.validation_warnings.append(
                            f"{qty.quantity_type}: Abbreviation '{abbr.symbol}' requires context but has no disambiguation guidance"
                        )
    
    def get_quantity(self, quantity_type: str) -> Optional[Quantity]:
        """Get quantity definition by type."""
        return self.quantities_by_type.get(quantity_type)
    
    def get_all_quantity_types(self) -> List[str]:
        """Get list of all quantity types."""
        return list(self.quantities_by_type.keys())
    
    def find_by_synonym(self, synonym: str) -> Optional[Quantity]:
        """Find quantity by synonym or quantity_type."""
        synonym_lower = synonym.lower().strip()
        
        # First check if it matches a quantity_type directly
        if synonym_lower in self.quantities_by_type:
            return self.quantities_by_type[synonym_lower]
        
        # Then check synonyms list
        for qty in self.registry.quantities:
            if synonym_lower in [s.lower() for s in qty.synonyms]:
                return qty
        
        return None
    
    def find_by_abbreviation(self, abbr: str, context: Optional[str] = None) -> Optional[Quantity]:
        """Find quantity by abbreviation, with optional context."""
        abbr = abbr.strip()
        candidates = []
        
        for qty in self.registry.quantities:
            if qty.abbreviations:
                for abbr_def in qty.abbreviations:
                    if abbr_def.symbol == abbr:
                        if not abbr_def.context_required:
                            return qty  # Unambiguous match
                        else:
                            candidates.append((qty, abbr_def))
        
        # If no candidates found, return None
        if not candidates:
            return None
        
        # If multiple candidates require context, try to disambiguate
        if len(candidates) > 1:
            if context:
                # Try to match context with examples
                for qty, abbr_def in candidates:
                    if abbr_def.context_examples:
                        for example in abbr_def.context_examples:
                            # Check if context matches example (substring or pattern match)
                            if self._context_matches(context, example, qty.quantity_type):
                                return qty
                
                # If no example matches, check for unit patterns in context
                for qty, abbr_def in candidates:
                    if self._context_has_unit_pattern(context, qty.quantity_type):
                        return qty
            
            # Still ambiguous, return None
            return None
        
        # If one candidate, return it (even without context)
        return candidates[0][0]
    
    def _context_matches(self, context: str, example: str, quantity_type: str) -> bool:
        """Check if context matches an example for a given quantity type."""
        context_lower = context.lower()
        example_lower = example.lower()
        
        # Direct substring match
        if context_lower in example_lower or example_lower in context_lower:
            return True
        
        # Pattern-based matching
        if quantity_type == 'time':
            # Check for time units in context
            time_units = [' h', ' min', ' s', ' hour', ' minute', ' second']
            if any(unit in context_lower for unit in time_units):
                return True
        elif quantity_type == 'temperature':
            # Check for temperature units in context
            temp_units = ['°c', ' k', 'degc', 'kelvin', 'celsius']
            if any(unit in context_lower for unit in temp_units):
                return True
        
        return False
    
    def _context_has_unit_pattern(self, context: str, quantity_type: str) -> bool:
        """Check if context contains unit patterns for a quantity type."""
        context_lower = context.lower()
        
        if quantity_type == 'time':
            time_patterns = [r'\d+\s*h', r'\d+\s*min', r'\d+\s*s\b']
            import re
            return any(re.search(p, context_lower) for p in time_patterns)
        elif quantity_type == 'temperature':
            temp_patterns = [r'\d+\s*°c', r'\d+\s*k\b', r'\d+\s*degc']
            import re
            return any(re.search(p, context_lower) for p in temp_patterns)
        
        return False
    
    def summary(self) -> Dict[str, Any]:
        """Generate summary of loaded registry."""
        if not self.registry:
            return {'error': 'Registry not loaded'}
        
        return {
            'version': self.registry.version,
            'status': self.registry.status,
            'quantity_count': len(self.registry.quantities),
            'quantity_types': self.get_all_quantity_types(),
            'load_errors': self.load_errors,
            'validation_warnings': self.validation_warnings,
            'schema_version': self.registry.schema_version
        }


# ============================================================================
# Main (for testing)
# ============================================================================

def main():
    """Test loader with actual configuration file."""
    print("="*60)
    print("NUM-UNIT-001 Quantity Registry Loader Test")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    loader = QuantityRegistryLoader()
    success = loader.load()
    
    if success:
        print("\n[PASS] Registry loaded successfully")
        summary = loader.summary()
        print(f"\nVersion: {summary['version']}")
        print(f"Status: {summary['status']}")
        print(f"Quantity count: {summary['quantity_count']}")
        print(f"\nQuantity types:")
        for qty_type in summary['quantity_types']:
            qty = loader.get_quantity(qty_type)
            print(f"  - {qty_type}: {qty.si_unit} ({qty.dimension})")
        
        if summary['validation_warnings']:
            print(f"\nValidation warnings ({len(summary['validation_warnings'])}):")
            for warning in summary['validation_warnings'][:10]:
                print(f"  - {warning}")
        
        # Test synonym lookup
        print("\nSynonym lookup tests:")
        test_synonyms = ['温度', 'temperature', '比表面积', 'TOF', '转化率']
        for synonym in test_synonyms:
            qty = loader.find_by_synonym(synonym)
            if qty:
                print(f"  '{synonym}' → {qty.quantity_type} ({qty.si_unit})")
            else:
                print(f"  '{synonym}' → NOT FOUND")
        
        # Test abbreviation lookup
        print("\nAbbreviation lookup tests:")
        test_abbrs = [('T', 'T = 500 °C'), ('T', 'T = 2 h'), ('SSA', None), ('BET', 'BET surface area')]
        for abbr, context in test_abbrs:
            qty = loader.find_by_abbreviation(abbr, context)
            if qty:
                print(f"  '{abbr}' (context: {context}) → {qty.quantity_type}")
            else:
                print(f"  '{abbr}' (context: {context}) → AMBIGUOUS OR NOT FOUND")
        
        print(f"\n{'='*60}")
        print("LOADER TEST: PASS")
        print(f"{'='*60}")
        
    else:
        print("\n[FAIL] Registry loading failed")
        print(f"\nErrors ({len(loader.load_errors)}):")
        for error in loader.load_errors:
            print(f"  - {error}")
        
        print(f"\n{'='*60}")
        print("LOADER TEST: FAIL")
        print(f"{'='*60}")
    
    return success


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
