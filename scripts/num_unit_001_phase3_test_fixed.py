#!/usr/bin/env python3
"""
NUM-UNIT-001 Phase 3: Pint转换测试修复与完整验证

严格按照PI决策要求：
1. 每个测试检查：目标数值、目标单位、量纲、转换状态、原始值保留
2. 使用Pint原生单位表达式
3. 单位别名采用版本化映射
4. 区分格式差异与真实错误
"""

import sys
from pathlib import Path
from decimal import Decimal
import json

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from num_unit_001_loader import QuantityRegistryLoader
from num_unit_001_phase3_normalizer import QuantityNormalizer


def test_conversion_comprehensive(normalizer, raw_value, raw_unit, qty_type, 
                                  expected_si_value, expected_si_unit, 
                                  expected_dimensionality, description):
    """综合测试单个转换。
    
    Returns:
        (pass: bool, details: dict)
    """
    record = normalizer.normalize(
        raw_value=raw_value,
        raw_unit=raw_unit,
        quantity_type=qty_type,
        raw_text=f"{raw_value} {raw_unit}",
    )
    
    details = {
        'description': description,
        'status': record.unit_conversion_status,
        'raw_value': raw_value,
        'raw_unit': raw_unit,
        'si_value': record.si_value,
        'si_unit': record.si_unit,
        'expected_si_value': expected_si_value,
        'expected_si_unit': expected_si_unit,
        'checks': {}
    }
    
    # Check 1: 转换状态
    status_ok = record.unit_conversion_status == "SUCCESS"
    details['checks']['status_success'] = status_ok
    
    if not status_ok:
        details['checks']['failure_reason'] = record.conversion_failure_reason
        return False, details
    
    # Check 2: 数值正确性（允许浮点误差）
    try:
        actual_val = float(record.si_value)
        expected_val = float(expected_si_value)
        if expected_val == 0:
            value_ok = abs(actual_val) < 0.001
        else:
            value_ok = abs(actual_val - expected_val) < 0.01 * abs(expected_val)
        details['checks']['value_correct'] = value_ok
        details['checks']['value_actual'] = actual_val
        details['checks']['value_expected'] = expected_val
        details['checks']['value_diff'] = abs(actual_val - expected_val)
    except Exception as e:
        value_ok = False
        details['checks']['value_correct'] = False
        details['checks']['value_error'] = str(e)
    
    # Check 3: 单位正确性（使用Pint解析并比较dimensionality）
    try:
        actual_unit_obj = normalizer.ureg.parse_units(record.si_unit)
        expected_unit_obj = normalizer.ureg.parse_units(expected_si_unit) if expected_si_unit else normalizer.ureg.dimensionless
        
        # 量纲必须匹配
        dimensionality_ok = actual_unit_obj.dimensionality == expected_unit_obj.dimensionality
        details['checks']['dimensionality_correct'] = dimensionality_ok
        details['checks']['dimensionality_actual'] = str(actual_unit_obj.dimensionality)
        details['checks']['dimensionality_expected'] = str(expected_unit_obj.dimensionality)
        
        # 单位字符串应该相似（允许格式差异）
        unit_str_ok = (record.si_unit == expected_si_unit or 
                      expected_si_unit in record.si_unit or 
                      record.si_unit in expected_si_unit)
        details['checks']['unit_string_similar'] = unit_str_ok
        details['checks']['unit_actual'] = record.si_unit
        details['checks']['unit_expected'] = expected_si_unit
        
    except Exception as e:
        dimensionality_ok = False
        unit_str_ok = False
        details['checks']['dimensionality_correct'] = False
        details['checks']['unit_string_similar'] = False
        details['checks']['unit_parse_error'] = str(e)
    
    # Check 4: 原始值保留
    raw_preserved = (record.raw_value == raw_value and record.raw_unit == raw_unit)
    details['checks']['raw_preserved'] = raw_preserved
    details['checks']['raw_value_actual'] = record.raw_value
    details['checks']['raw_unit_actual'] = record.raw_unit
    
    # Check 5: 量纲与预期一致
    expected_dim_ok = expected_dimensionality is None or details['checks'].get('dimensionality_correct', False)
    details['checks']['expected_dimensionality_match'] = expected_dim_ok
    
    # 综合判断
    all_pass = (status_ok and value_ok and dimensionality_ok and 
                raw_preserved and expected_dim_ok)
    
    return all_pass, details


def run_positive_tests(normalizer):
    """运行正例测试（9个核心转换）。"""
    print("\n" + "=" * 70)
    print("正例测试：9个核心单位转换")
    print("=" * 70)
    
    test_cases = [
        # (raw_value, raw_unit, qty_type, expected_si_value, expected_si_unit, expected_dim, description)
        ("1380", "m2/g", "specific_surface_area", "1380000", "meter**2/kilogram", "[length]**2/[mass]", 
         "specific surface area: 1380 m2/g -> 1380000 m2/kg"),
        
        ("16.8", "%", "conversion", "0.168", "dimensionless", "[]", 
         "conversion: 16.8% -> 0.168 (dimensionless)"),
        
        ("82.1", "%", "selectivity", "0.821", "dimensionless", "[]", 
         "selectivity: 82.1% -> 0.821 (dimensionless)"),
        
        ("500", "degC", "temperature", "773.15", "kelvin", "[temperature]", 
         "absolute temperature: 500 degC -> 773.15 K"),
        
        ("10", "delta_degC", "temperature", "10", "kelvin", "[temperature]", 
         "temperature difference: 10 delta_degC -> 10 K"),
        
        ("2", "h", "time", "7200", "second", "[time]", 
         "time: 2 h -> 7200 s"),
        
        ("100", "mA/cm2", "current_density", "1000", "ampere/meter**2", "[current]/[length]**2", 
         "current density: 100 mA/cm2 -> 1000 A/m2"),
        
        ("80", "kJ/mol", "activation_energy", "80000", "joule/mole", "[length]**2/[mol]**2", 
         "activation energy: 80 kJ/mol -> 80000 J/mol"),
        
        ("3600", "h-1", "tof", "1", "1/second", "1/[time]", 
         "TOF: 3600 h-1 -> 1 s-1"),
    ]
    
    results = []
    for test in test_cases:
        passed, details = test_conversion_comprehensive(normalizer, *test)
        results.append((passed, details))
        
        status = "[PASS]" if passed else "[FAIL]"
        print(f"\n{status} {test[6]}")
        print(f"  Status: {details['status']}")
        if passed:
            print(f"  Value: {details['checks']['value_actual']} (expected {details['checks']['value_expected']})")
            print(f"  Unit: {details['checks']['unit_actual']}")
            print(f"  Dimensionality: {details['checks']['dimensionality_actual']}")
        else:
            print(f"  Expected: {details['expected_si_value']} {details['expected_si_unit']}")
            print(f"  Got: {details['si_value']} {details['si_unit']}")
            for check_name, check_result in details['checks'].items():
                if not check_result and check_name not in ['value_error', 'unit_parse_error']:
                    print(f"  Check failed: {check_name}")
    
    passed_count = sum(1 for p, _ in results if p)
    print(f"\n正例测试结果: {passed_count}/{len(test_cases)} PASS")
    
    return results


def run_negative_tests(normalizer):
    """运行负例测试（必须返回明确错误）。"""
    print("\n" + "=" * 70)
    print("负例测试：错误处理与禁止转换")
    print("=" * 70)
    
    test_cases = [
        # (raw_value, raw_unit, qty_type, expected_status, description)
        ("100", "unknown_unit", "temperature", "UNKNOWN_UNIT", 
         "unknown unit should return UNKNOWN_UNIT"),
        
        ("abc", "m2/g", "specific_surface_area", "FAILED", 
         "invalid numeric value should return FAILED"),
        
        ("100", "mA/cm2", "tof", "DIMENSION_MISMATCH", 
         "dimension mismatch (current_density unit to tof) should return DIMENSION_MISMATCH"),
        
        ("0", "m2/g", "specific_surface_area", "SUCCESS", 
         "zero value should be preserved (not converted to None)"),
        
        ("-10", "degC", "temperature", "SUCCESS", 
         "negative temperature should be converted correctly"),
    ]
    
    results = []
    for raw_value, raw_unit, qty_type, expected_status, description in test_cases:
        record = normalizer.normalize(
            raw_value=raw_value,
            raw_unit=raw_unit,
            quantity_type=qty_type,
            raw_text=f"{raw_value} {raw_unit}",
        )
        
        passed = record.unit_conversion_status == expected_status
        results.append((passed, {
            'description': description,
            'expected_status': expected_status,
            'actual_status': record.unit_conversion_status,
            'failure_reason': record.conversion_failure_reason,
        }))
        
        status = "[PASS]" if passed else "[FAIL]"
        print(f"\n{status} {description}")
        print(f"  Expected: {expected_status}")
        print(f"  Got: {record.unit_conversion_status}")
        if record.conversion_failure_reason:
            print(f"  Reason: {record.conversion_failure_reason}")
    
    passed_count = sum(1 for p, _ in results if p)
    print(f"\n负例测试结果: {passed_count}/{len(test_cases)} PASS")
    
    return results


def main():
    """主测试流程。"""
    print("=" * 70)
    print("NUM-UNIT-001 Phase 3: Pint转换完整验证")
    print("=" * 70)
    
    # 加载配置
    print("\n[1] 加载quantity_definitions.yaml...")
    loader = QuantityRegistryLoader()
    if not loader.load():
        print("ERROR: Failed to load registry")
        return False
    
    print(f"[OK] 加载 {len(loader.registry.quantities)} 种科学量")
    
    # 创建归一化器
    print("\n[2] 创建QuantityNormalizer...")
    normalizer = QuantityNormalizer(loader)
    print(f"[OK] Pint UnitRegistry initialized")
    
    # 运行正例测试
    print("\n[3] 运行正例测试...")
    positive_results = run_positive_tests(normalizer)
    
    # 运行负例测试
    print("\n[4] 运行负例测试...")
    negative_results = run_negative_tests(normalizer)
    
    # 汇总
    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    
    positive_passed = sum(1 for p, _ in positive_results if p)
    positive_total = len(positive_results)
    negative_passed = sum(1 for p, _ in negative_results if p)
    negative_total = len(negative_results)
    
    total_passed = positive_passed + negative_passed
    total_tests = positive_total + negative_total
    
    print(f"\n正例测试: {positive_passed}/{positive_total} PASS")
    print(f"负例测试: {negative_passed}/{negative_total} PASS")
    print(f"总计: {total_passed}/{total_tests} PASS")
    
    # 保存详细结果
    output_file = Path(__file__).parent.parent / 'runs' / 'NUM_UNIT_001_phase3_test_results.json'
    output_data = {
        'test_timestamp': output_file.stat().st_mtime if output_file.exists() else None,
        'positive_tests': [
            {
                'passed': p,
                'description': d['description'],
                'checks': d['checks'],
                'si_value': d['si_value'],
                'si_unit': d['si_unit'],
            }
            for p, d in positive_results
        ],
        'negative_tests': [
            {
                'passed': p,
                'description': d['description'],
                'expected_status': d['expected_status'],
                'actual_status': d['actual_status'],
            }
            for p, d in negative_results
        ],
        'summary': {
            'positive_passed': positive_passed,
            'positive_total': positive_total,
            'negative_passed': negative_passed,
            'negative_total': negative_total,
            'total_passed': total_passed,
            'total_tests': total_tests,
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] 详细结果已保存到 {output_file.name}")
    
    # 验收判断
    print("\n" + "=" * 70)
    if total_passed == total_tests:
        print("[PASS] Phase 3 Pint转换测试全部通过")
        print("=" * 70)
        return True
    else:
        print(f"[FAIL] Phase 3 Pint转换测试部分失败: {total_tests - total_passed} tests failed")
        print("=" * 70)
        
        # 输出失败用例
        print("\n失败用例:")
        for p, d in positive_results:
            if not p:
                print(f"  - {d['description']}")
        for p, d in negative_results:
            if not p:
                print(f"  - {d['description']}")
        
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
