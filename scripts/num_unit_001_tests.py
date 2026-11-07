"""
NUM-UNIT-001 Basic Unit Tests

Tests for quantity registry configuration, loader, and validator.
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from num_unit_001_loader import QuantityRegistryLoader


def test_registry_loads():
    """Test that registry loads without errors."""
    print("\n" + "="*60)
    print("TEST 1: Registry Loading")
    print("="*60)
    
    loader = QuantityRegistryLoader()
    success = loader.load()
    
    assert success, f"Registry failed to load: {loader.load_errors}"
    assert loader.registry is not None, "Registry is None after loading"
    assert len(loader.registry.quantities) > 0, "No quantities loaded"
    
    print(f"[PASS] Registry loaded: {len(loader.registry.quantities)} quantities")
    return loader


def test_quantity_count(loader):
    """Test that expected number of quantities are present."""
    print("\n" + "="*60)
    print("TEST 2: Quantity Count")
    print("="*60)
    
    expected_count = 17  # Per PI decision
    actual_count = len(loader.registry.quantities)
    
    # Allow for additional quantities (e.g., time and time_on_stream are separate)
    assert actual_count >= expected_count, f"Expected at least {expected_count} quantities, got {actual_count}"
    
    print(f"[PASS] Quantity count: {actual_count} (expected >= {expected_count})")


def test_required_quantities(loader):
    """Test that all required quantity types are present."""
    print("\n" + "="*60)
    print("TEST 3: Required Quantity Types")
    print("="*60)
    
    required_types = [
        'temperature',
        'pressure',
        'time',
        'time_on_stream',
        'specific_surface_area',
        'conversion',
        'selectivity',
        'yield',
        'current_density',
        'overpotential',
        'activation_energy',
        'tof',
        'ton',
        'reaction_rate',
        'concentration',
        'mass',
        'volumetric_flow_rate'
    ]
    
    actual_types = loader.get_all_quantity_types()
    
    missing = []
    for req_type in required_types:
        if req_type in actual_types:
            print(f"  [PASS] {req_type}")
        else:
            print(f"  [FAIL] {req_type} - MISSING")
            missing.append(req_type)
    
    assert len(missing) == 0, f"Missing required quantity types: {missing}"
    print(f"\n[PASS] All {len(required_types)} required quantity types present")


def test_si_units_defined(loader):
    """Test that all quantities have SI units defined."""
    print("\n" + "="*60)
    print("TEST 4: SI Units Defined")
    print("="*60)
    
    missing_si = []
    for qty in loader.registry.quantities:
        if qty.si_unit and qty.si_unit.strip():
            print(f"  [PASS] {qty.quantity_type}: {qty.si_unit}")
        else:
            print(f"  [FAIL] {qty.quantity_type}: SI unit missing")
            missing_si.append(qty.quantity_type)
    
    assert len(missing_si) == 0, f"Missing SI units for: {missing_si}"
    print(f"\n[PASS] All quantities have SI units defined")


def test_dimensions_defined(loader):
    """Test that all quantities have dimensions defined."""
    print("\n" + "="*60)
    print("TEST 5: Physical Dimensions Defined")
    print("="*60)
    
    missing_dim = []
    for qty in loader.registry.quantities:
        if qty.dimension and qty.dimension.strip():
            print(f"  [PASS] {qty.quantity_type}: {qty.dimension}")
        else:
            print(f"  [FAIL] {qty.quantity_type}: dimension missing")
            missing_dim.append(qty.quantity_type)
    
    assert len(missing_dim) == 0, f"Missing dimensions for: {missing_dim}"
    print(f"\n[PASS] All quantities have dimensions defined")


def test_domain_units_present(loader):
    """Test that all quantities have domain units defined."""
    print("\n" + "="*60)
    print("TEST 6: Domain Units Present")
    print("="*60)
    
    missing_units = []
    for qty in loader.registry.quantities:
        if qty.domain_units and len(qty.domain_units) > 0:
            print(f"  [PASS] {qty.quantity_type}: {len(qty.domain_units)} domain units")
        else:
            print(f"  [FAIL] {qty.quantity_type}: no domain units")
            missing_units.append(qty.quantity_type)
    
    assert len(missing_units) == 0, f"Missing domain units for: {missing_units}"
    print(f"\n[PASS] All quantities have domain units defined")


def test_synonym_lookup(loader):
    """Test synonym lookup functionality."""
    print("\n" + "="*60)
    print("TEST 7: Synonym Lookup")
    print("="*60)
    
    test_cases = [
        ('temperature', 'temperature'),
        ('温度', 'temperature'),
        ('T', None),  # Ambiguous without context
        ('specific_surface_area', 'specific_surface_area'),
        ('比表面积', 'specific_surface_area'),
        ('BET', 'specific_surface_area'),
        ('SSA', 'specific_surface_area'),
        ('conversion', 'conversion'),
        ('转化率', 'conversion'),
        ('TOF', 'tof'),
        ('转换频率', 'tof'),
    ]
    
    passed = 0
    failed = 0
    
    for synonym, expected_type in test_cases:
        qty = loader.find_by_synonym(synonym)
        if expected_type is None:
            # Should not find exact match
            if qty is None:
                print(f"  [PASS] '{synonym}' → None (as expected)")
                passed += 1
            else:
                print(f"  [FAIL] '{synonym}' → {qty.quantity_type} (expected None)")
                failed += 1
        else:
            if qty and qty.quantity_type == expected_type:
                print(f"  [PASS] '{synonym}' → {qty.quantity_type}")
                passed += 1
            else:
                actual = qty.quantity_type if qty else None
                print(f"  [FAIL] '{synonym}' → {actual} (expected {expected_type})")
                failed += 1
    
    assert failed == 0, f"{failed} synonym lookup tests failed"
    print(f"\n[PASS] {passed}/{passed+failed} synonym lookups successful")


def test_abbreviation_lookup(loader):
    """Test abbreviation lookup with context."""
    print("\n" + "="*60)
    print("TEST 8: Abbreviation Lookup with Context")
    print("="*60)
    
    test_cases = [
        ('T', 'T = 500 °C', 'temperature'),
        ('T', 'T = 2 h', 'time'),
        ('SSA', None, 'specific_surface_area'),
        ('BET', 'BET surface area', 'specific_surface_area'),
        ('TOF', None, 'tof'),
        ('X', 'X_C3H8 = 16.8%', 'conversion'),
    ]
    
    passed = 0
    failed = 0
    
    for abbr, context, expected_type in test_cases:
        qty = loader.find_by_abbreviation(abbr, context)
        if qty and qty.quantity_type == expected_type:
            print(f"  [PASS] '{abbr}' (context: {context}) → {qty.quantity_type}")
            passed += 1
        else:
            actual = qty.quantity_type if qty else None
            print(f"  [FAIL] '{abbr}' (context: {context}) → {actual} (expected {expected_type})")
            failed += 1
    
    assert failed == 0, f"{failed} abbreviation lookup tests failed"
    print(f"\n[PASS] {passed}/{passed+failed} abbreviation lookups successful")


def test_specific_surface_area_units(loader):
    """Test that specific_surface_area has correct SI and domain units."""
    print("\n" + "="*60)
    print("TEST 9: Specific Surface Area Units (PI Requirement)")
    print("="*60)
    
    qty = loader.get_quantity('specific_surface_area')
    assert qty is not None, "specific_surface_area not found"
    
    # Check SI unit is m2/kg
    assert qty.si_unit == 'm2/kg', f"SI unit should be m2/kg, got {qty.si_unit}"
    print(f"  [PASS] SI unit: {qty.si_unit}")
    
    # Check domain units include m2/g
    domain_unit_strs = [du.unit for du in qty.domain_units]
    assert 'm2/g' in domain_unit_strs, f"Domain units should include m2/g, got {domain_unit_strs}"
    print(f"  [PASS] Domain units include m2/g")
    
    # Check conversion formula exists
    assert qty.conversion_rules.formulas is not None, "No conversion formulas"
    assert len(qty.conversion_rules.formulas) > 0, "Empty conversion formulas"
    print(f"  [PASS] Conversion formulas present: {len(qty.conversion_rules.formulas)}")
    
    print(f"\n[PASS] Specific surface area units correctly defined")


def test_tof_conversion_restrictions(loader):
    """Test that TOF has proper conversion restrictions."""
    print("\n" + "="*60)
    print("TEST 10: TOF Conversion Restrictions (PI Requirement)")
    print("="*60)
    
    qty = loader.get_quantity('tof')
    assert qty is not None, "tof not found"
    
    # Check allow_auto_convert is not True (should be "time_only" or False)
    assert qty.conversion_rules.allow_auto_convert != True, \
        "TOF should not allow full auto-convert"
    print(f"  [PASS] TOF allow_auto_convert: {qty.conversion_rules.allow_auto_convert}")
    
    # Check restrictions are documented
    assert qty.conversion_rules.restrictions is not None, "No restrictions documented"
    assert len(qty.conversion_rules.restrictions) > 0, "Empty restrictions"
    print(f"  [PASS] TOF restrictions documented: {len(qty.conversion_rules.restrictions)}")
    
    # Check experimental context required
    assert qty.experimental_context_required is not None, "No experimental context required"
    assert 'active_site_definition' in qty.experimental_context_required, \
        "active_site_definition should be required"
    print(f"  [PASS] Experimental context required: {qty.experimental_context_required}")
    
    print(f"\n[PASS] TOF conversion restrictions properly defined")


def test_temperature_conversion(loader):
    """Test temperature conversion rules."""
    print("\n" + "="*60)
    print("TEST 11: Temperature Conversion (PI Requirement)")
    print("="*60)
    
    qty = loader.get_quantity('temperature')
    assert qty is not None, "temperature not found"
    
    # Check conversion type is affine
    assert qty.conversion_rules.conversion_type == 'affine', \
        f"Temperature conversion should be affine, got {qty.conversion_rules.conversion_type}"
    print(f"  [PASS] Conversion type: {qty.conversion_rules.conversion_type}")
    
    # Check formulas include degC to K
    assert qty.conversion_rules.formulas is not None, "No conversion formulas"
    formulas = qty.conversion_rules.formulas
    has_c_to_k = any(f.from_unit == 'degC' and f.to_unit == 'K' for f in formulas)
    assert has_c_to_k, "Missing degC to K conversion"
    print(f"  [PASS] degC to K conversion formula present")
    
    # Check notes mention affine conversion
    assert qty.conversion_rules.notes is not None, "No notes"
    has_affine_note = any('affine' in note.lower() for note in qty.conversion_rules.notes)
    assert has_affine_note, "Notes should mention affine conversion"
    print(f"  [PASS] Affine conversion documented in notes")
    
    print(f"\n[PASS] Temperature conversion properly defined")


def test_global_validation_rules(loader):
    """Test global validation rules."""
    print("\n" + "="*60)
    print("TEST 12: Global Validation Rules")
    print("="*60)
    
    assert loader.registry.global_validation is not None, "No global validation"
    gv = loader.registry.global_validation
    
    # Check false zero prohibition
    assert gv.false_zero_prohibition == True, "False zero prohibition should be True"
    print(f"  [PASS] False zero prohibition: {gv.false_zero_prohibition}")
    
    # Check missing values allowed
    assert gv.allow_missing_values == True, "Missing values should be allowed"
    print(f"  [PASS] Missing values allowed: {gv.allow_missing_values}")
    
    # Check conversion statuses defined
    assert gv.conversion_statuses is not None, "No conversion statuses"
    assert len(gv.conversion_statuses) > 0, "Empty conversion statuses"
    print(f"  [PASS] Conversion statuses defined: {len(gv.conversion_statuses)}")
    
    # Check QA checks defined
    assert gv.qa_checks is not None, "No QA checks"
    assert len(gv.qa_checks) > 0, "Empty QA checks"
    print(f"  [PASS] QA checks defined: {len(gv.qa_checks)}")
    
    print(f"\n[PASS] Global validation rules properly defined")


def main():
    """Run all unit tests."""
    print("="*60)
    print("NUM-UNIT-001 Unit Tests")
    print("="*60)
    
    tests = [
        test_registry_loads,
        test_quantity_count,
        test_required_quantities,
        test_si_units_defined,
        test_dimensions_defined,
        test_domain_units_present,
        test_synonym_lookup,
        test_abbreviation_lookup,
        test_specific_surface_area_units,
        test_tof_conversion_restrictions,
        test_temperature_conversion,
        test_global_validation_rules,
    ]
    
    passed = 0
    failed = 0
    loader = None
    
    for test_func in tests:
        try:
            if test_func == test_registry_loads:
                loader = test_func()
            else:
                test_func(loader)
            passed += 1
        except AssertionError as e:
            print(f"\n[FAIL] {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"\n[ERROR] {test_func.__name__}: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
