#!/usr/bin/env python3
"""
NUM-UNIT-001 Phase 3: Pint确定性单位归一化

实现科学数值的SI单位转换，使用Pint库进行确定性换算。
"""

import os
import sys
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent))

try:
    import pint
except ImportError:
    print("ERROR: pint not installed. Run: pip install pint")
    sys.exit(1)

from num_unit_001_loader import QuantityRegistryLoader


@dataclass
class QuantityRecord:
    """统一科学数值记录。"""
    
    # 基本信息
    quantity_type: str
    raw_value: str
    raw_unit: Optional[str]
    raw_text: str
    
    # 转换结果
    si_value: Optional[str] = None  # Decimal字符串
    si_unit: Optional[str] = None
    domain_value: Optional[str] = None  # Decimal字符串
    domain_unit: Optional[str] = None
    
    # 数值类型
    value_kind: str = "scalar"  # scalar/range/uncertainty/inequality
    
    # 上下文
    experimental_context: Optional[Dict[str, Any]] = None
    
    # 溯源
    source_anchor: Optional[Dict[str, Any]] = None
    document_id: Optional[str] = None
    element_id: Optional[str] = None
    
    # 转换状态（三个独立维度）
    unit_conversion_status: str = "NOT_ATTEMPTED"  # SUCCESS/FAILED/DIMENSION_MISMATCH/UNKNOWN_UNIT/NOT_ATTEMPTED
    semantic_comparability_status: str = "NOT_ASSESSED"  # COMPARABLE/NOT_COMPARABLE/REQUIRES_CONTEXT/NOT_ASSESSED
    evidence_verification_status: str = "NOT_VERIFIED"  # VERIFIED/NOT_VERIFIED/CONFLICT/NOT_APPLICABLE
    
    # 转换规则
    conversion_rule_id: Optional[str] = None
    conversion_rule_version: str = "1.0"
    
    # 抽取来源
    extraction_provenance: str = "RULE_EXTRACTED"  # RULE_EXTRACTED/LLM_EXTRACTED/HYBRID
    
    # 失败原因
    conversion_failure_reason: Optional[str] = None
    semantic_failure_reason: Optional[str] = None
    
    # 时间戳
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class QuantityNormalizer:
    """使用Pint进行SI单位归一化。"""
    
    def __init__(self, registry_loader: QuantityRegistryLoader):
        self.registry = registry_loader.registry
        self.ureg = pint.UnitRegistry()
        
        # 建立quantity_type到配置的映射
        self.quantity_configs = {
            q.quantity_type: q for q in self.registry.quantities
        }
        
        # 预定义单位映射（处理非标准单位）
        self.unit_aliases = {
            'm2/g': 'meter**2/gram',
            'm²/g': 'meter**2/gram',
            'm2/kg': 'meter**2/kilogram',
            'm²/kg': 'meter**2/kilogram',
            'kJ/mol': 'kilojoule/mole',
            'J/mol': 'joule/mole',
            'mA/cm2': 'milliampere/centimeter**2',
            'mA/cm²': 'milliampere/centimeter**2',
            'A/m2': 'ampere/meter**2',
            'A/m²': 'ampere/meter**2',
            'degC': 'degree_Celsius',
            '°C': 'degree_Celsius',
            'C': 'degree_Celsius',  # 上下文相关
            'h-1': '1/hour',
            'h⁻¹': '1/hour',
            's-1': '1/second',
            's⁻¹': '1/second',
            'mol/(L·s)': 'mole/(liter*second)',
            'mol/(L*s)': 'mole/(liter*second)',
            'delta_degC': 'delta_degree_Celsius',
            'mL/min': 'milliliter/minute',
            'mL min-1': 'milliliter/minute',
            'mL min⁻¹': 'milliliter/minute',
            'L/h': 'liter/hour',
            'sccm': 'centimeter**3/minute',
            'mL/s': 'milliliter/second',
            'L/min': 'liter/minute',
        }
        
        # SI单位别名（从配置文件格式转为Pint格式）
        self.si_unit_aliases = {
            'm2/kg': 'meter**2/kilogram',
            'm²/kg': 'meter**2/kilogram',
            'A/m2': 'ampere/meter**2',
            'A/m²': 'ampere/meter**2',
            'kJ/mol': 'kilojoule/mole',
            'J/mol': 'joule/mole',
            'mA/cm2': 'milliampere/centimeter**2',
            'mA/cm²': 'milliampere/centimeter**2',
            'm3/s': 'meter**3/second',
            'm³/s': 'meter**3/second',
            'mol/(kg*s)': 'mole/(kilogram*second)',
            'mol/(kg·s)': 'mole/(kilogram*second)',
        }
    
    def normalize(
        self,
        raw_value: str,
        raw_unit: Optional[str],
        quantity_type: str,
        raw_text: str = "",
        value_kind: str = "scalar",
        experimental_context: Optional[Dict[str, Any]] = None,
        source_anchor: Optional[Dict[str, Any]] = None,
        document_id: Optional[str] = None,
        element_id: Optional[str] = None,
    ) -> QuantityRecord:
        """归一化科学数值到SI单位。
        
        Args:
            raw_value: 原始数值（字符串）
            raw_unit: 原始单位（字符串，可为None）
            quantity_type: 科学量类型
            raw_text: 原始文本片段
            value_kind: 数值类型（scalar/range/uncertainty/inequality）
            experimental_context: 实验上下文
            source_anchor: 来源锚点
            document_id: 文档ID
            element_id: 元素ID
        
        Returns:
            QuantityRecord包含转换结果和三个独立状态
        """
        # 创建基础记录
        record = QuantityRecord(
            quantity_type=quantity_type,
            raw_value=raw_value,
            raw_unit=raw_unit,
            raw_text=raw_text,
            value_kind=value_kind,
            experimental_context=experimental_context,
            source_anchor=source_anchor,
            document_id=document_id,
            element_id=element_id,
        )
        
        # 检查quantity_type是否有效
        if quantity_type not in self.quantity_configs:
            record.unit_conversion_status = "FAILED"
            record.conversion_failure_reason = f"Unknown quantity_type: {quantity_type}"
            return record
        
        qty_config = self.quantity_configs[quantity_type]
        
        # 检查是否允许缺失单位
        if raw_unit is None or raw_unit == "":
            if qty_config.validation_rules.allow_missing_unit:
                # 允许无单位（如百分比、计数）
                record.unit_conversion_status = "SUCCESS"
                record.si_value = raw_value
                record.si_unit = qty_config.si_unit
                record.domain_value = raw_value
                record.domain_unit = raw_unit
                return record
            else:
                record.unit_conversion_status = "FAILED"
                record.conversion_failure_reason = "Missing unit not allowed for this quantity"
                return record
        
        # 检查转换规则
        if not qty_config.conversion_rules.allow_auto_convert:
            record.unit_conversion_status = "FAILED"
            record.conversion_failure_reason = f"Auto-conversion disabled for {quantity_type}"
            record.semantic_comparability_status = "NOT_COMPARABLE"
            record.semantic_failure_reason = qty_config.conversion_rules.notes
            return record
        
        # 执行单位转换
        try:
            si_value, si_unit, domain_value, domain_unit, rule_id = self._convert_unit(
                raw_value, raw_unit, qty_config
            )
            
            record.si_value = si_value
            record.si_unit = si_unit
            record.domain_value = domain_value
            record.domain_unit = domain_unit
            record.conversion_rule_id = rule_id
            record.unit_conversion_status = "SUCCESS"
            
            # 评估语义可比性
            self._assess_semantic_comparability(record, qty_config)
            
        except pint.errors.DimensionalityError as e:
            record.unit_conversion_status = "DIMENSION_MISMATCH"
            record.conversion_failure_reason = f"Dimension mismatch: {str(e)}"
        except pint.errors.UndefinedUnitError as e:
            record.unit_conversion_status = "UNKNOWN_UNIT"
            record.conversion_failure_reason = f"Unknown unit: {raw_unit} ({str(e)})"
        except Exception as e:
            record.unit_conversion_status = "FAILED"
            record.conversion_failure_reason = f"Conversion error: {str(e)}"
        
        return record
    
    def _convert_unit(
        self,
        raw_value: str,
        raw_unit: str,
        qty_config: Any
    ) -> Tuple[str, str, str, str, Optional[str]]:
        """执行单位转换。
        
        Returns:
            (si_value, si_unit, domain_value, domain_unit, rule_id)
        """
        # 解析数值
        try:
            value_decimal = Decimal(raw_value)
        except InvalidOperation:
            raise ValueError(f"Invalid numeric value: {raw_value}")
        
        # 规范化单位名称
        normalized_unit = self.unit_aliases.get(raw_unit, raw_unit)
        
        # 检查是否为百分比转换
        if raw_unit == '%':
            # 百分比转为无量纲SI
            si_value = str(value_decimal / Decimal('100'))
            si_unit = ''  # 无量纲
            return si_value, si_unit, raw_value, raw_unit, 'percentage_to_decimal'
        
        # 检查是否为温度转换（需要区分绝对温度和温差）
        if qty_config.quantity_type == 'temperature':
            # 检查转换类型
            if qty_config.conversion_rules.conversion_type == 'affine':
                # 绝对温度：T(K) = T(°C) + 273.15
                if normalized_unit in ['degree_Celsius', '°C']:
                    quantity = self.ureg.Quantity(float(value_decimal), self.ureg.degree_Celsius)
                    si_quantity = quantity.to(self.ureg.kelvin)
                    si_value = str(Decimal(str(si_quantity.magnitude)))
                    si_unit = 'K'
                    return si_value, si_unit, raw_value, raw_unit, 'temperature_affine'
            
            # 温差：ΔT(K) = ΔT(°C)
            elif 'delta' in normalized_unit.lower() or 'Δ' in raw_unit:
                quantity = self.ureg.Quantity(float(value_decimal), self.ureg.delta_degree_Celsius)
                si_quantity = quantity.to(self.ureg.kelvin)
                si_value = str(Decimal(str(si_quantity.magnitude)))
                si_unit = 'kelvin'
                return si_value, si_unit, raw_value, raw_unit, 'temperature_delta'
        
        # 通用转换
        try:
            quantity = self.ureg.Quantity(float(value_decimal), normalized_unit)
            
            # 转换到SI单位
            si_unit_str = qty_config.si_unit
            # 应用SI单位别名
            si_unit_str = self.si_unit_aliases.get(si_unit_str, si_unit_str)
            si_quantity = quantity.to(si_unit_str)
            
            si_value = str(Decimal(str(si_quantity.magnitude)))
            si_unit = str(si_quantity.units)
            
            # 保留domain单位值
            domain_value = raw_value
            domain_unit = raw_unit
            
            # 查找转换规则ID（使用formula字符串作为ID）
            rule_id = None
            for formula in qty_config.conversion_rules.formulas:
                if formula.from_unit == raw_unit and formula.to_unit == si_unit_str:
                    rule_id = formula.formula
                    break
            
            return si_value, si_unit, domain_value, domain_unit, rule_id
        
        except Exception as e:
            raise
    
    def _assess_semantic_comparability(self, record: QuantityRecord, qty_config: Any):
        """评估语义可比性。"""
        
        # TOF特殊处理：时间单位可转换，但活性位点定义不同不可比较
        if qty_config.quantity_type == 'tof':
            if qty_config.conversion_rules.allow_auto_convert == 'time_only':
                record.semantic_comparability_status = "REQUIRES_CONTEXT"
                record.semantic_failure_reason = "TOF time unit converted, but active site definition required for comparability"
                return
        
        # 检查是否需要额外上下文
        if qty_config.experimental_context_required:
            required_contexts = qty_config.experimental_context_required
            if record.experimental_context:
                # 检查是否提供了所有必需上下文
                missing = [ctx for ctx in required_contexts if ctx not in record.experimental_context]
                if missing:
                    record.semantic_comparability_status = "REQUIRES_CONTEXT"
                    record.semantic_failure_reason = f"Missing experimental context: {missing}"
                    return
            else:
                record.semantic_comparability_status = "REQUIRES_CONTEXT"
                record.semantic_failure_reason = f"Requires experimental context: {required_contexts}"
                return
        
        # 默认认为可比较
        record.semantic_comparability_status = "COMPARABLE"


def test_normalizer():
    """测试单位归一化器。"""
    print("=" * 70)
    print("NUM-UNIT-001 Phase 3: Pint单位归一化测试")
    print("=" * 70)
    
    # 加载配置
    print("\n[1] 加载quantity_definitions.yaml...")
    loader = QuantityRegistryLoader()
    if not loader.load():
        print("ERROR: Failed to load registry")
        return
    
    print(f"[OK] 加载 {len(loader.registry.quantities)} 种科学量")
    
    # 创建归一化器
    print("\n[2] 创建QuantityNormalizer...")
    normalizer = QuantityNormalizer(loader)
    print(f"[OK] Pint UnitRegistry initialized")
    
    # 测试用例
    print("\n[3] 执行合成测试...")
    test_cases = [
        # (raw_value, raw_unit, quantity_type, expected_si_value, expected_si_unit, description)
        ("1380", "m2/g", "specific_surface_area", "1380000", "meter**2/kilogram", "specific surface area m2/g to m2/kg"),
        ("16.8", "%", "conversion", "0.168", "", "conversion % to decimal"),
        ("82.1", "%", "selectivity", "0.821", "", "selectivity % to decimal"),
        ("500", "degC", "temperature", "773.15", "kelvin", "absolute temperature degC to K"),
        ("10", "delta_degC", "temperature", "10", "delta_kelvin", "temperature difference degC to K"),
        ("2", "h", "time", "7200", "second", "time h to s"),
        ("100", "mA/cm2", "current_density", "1000", "ampere/meter**2", "current density mA/cm2 to A/m2"),
        ("80", "kJ/mol", "activation_energy", "80000", "joule/mole", "activation energy kJ/mol to J/mol"),
        ("3600", "h-1", "tof", "1", "1/second", "TOF h-1 to s-1"),
    ]
    
    passed = 0
    failed = 0
    
    for raw_value, raw_unit, qty_type, expected_si_val, expected_si_unit, desc in test_cases:
        record = normalizer.normalize(
            raw_value=raw_value,
            raw_unit=raw_unit,
            quantity_type=qty_type,
            raw_text=f"{raw_value} {raw_unit}",
        )
        
        # 检查结果
        if record.unit_conversion_status == "SUCCESS":
            # 比较数值（允许浮点误差）
            try:
                actual_val = float(record.si_value)
                expected_val = float(expected_si_val)
                val_match = abs(actual_val - expected_val) < 0.01 * expected_val
            except:
                val_match = record.si_value == expected_si_val
            
            unit_match = record.si_unit == expected_si_unit or expected_si_unit in record.si_unit
            
            if val_match and unit_match:
                print(f"  [PASS] {desc}")
                print(f"         {raw_value} {raw_unit} → {record.si_value} {record.si_unit}")
                passed += 1
            else:
                print(f"  [FAIL] {desc}")
                print(f"         Expected: {expected_si_val} {expected_si_unit}")
                print(f"         Got:      {record.si_value} {record.si_unit}")
                failed += 1
        else:
            print(f"  [FAIL] {desc}")
            print(f"         Status: {record.unit_conversion_status}")
            print(f"         Reason: {record.conversion_failure_reason}")
            failed += 1
    
    print(f"\n[4] 合成测试结果: {passed}/{len(test_cases)} PASS, {failed}/{len(test_cases)} FAIL")
    
    # 负例测试
    print("\n[5] 执行负例测试...")
    negative_cases = [
        # (raw_value, raw_unit, quantity_type, expected_status, description)
        ("100", "unknown_unit", "temperature", "UNKNOWN_UNIT", "unknown unit"),
        ("abc", "m2/g", "specific_surface_area", "FAILED", "invalid numeric value"),
        ("100", "mA/cm2", "tof", "FAILED", "quantity type mismatch"),
    ]
    
    neg_passed = 0
    neg_failed = 0
    
    for raw_value, raw_unit, qty_type, expected_status, desc in negative_cases:
        record = normalizer.normalize(
            raw_value=raw_value,
            raw_unit=raw_unit,
            quantity_type=qty_type,
            raw_text=f"{raw_value} {raw_unit}",
        )
        
        if record.unit_conversion_status == expected_status:
            print(f"  [PASS] {desc}")
            print(f"         Status: {record.unit_conversion_status}")
            neg_passed += 1
        else:
            print(f"  [FAIL] {desc}")
            print(f"         Expected: {expected_status}")
            print(f"         Got:      {record.unit_conversion_status}")
            print(f"         Reason:   {record.conversion_failure_reason}")
            neg_failed += 1
    
    print(f"\n[6] 负例测试结果: {neg_passed}/{len(negative_cases)} PASS, {neg_failed}/{len(negative_cases)} FAIL")
    
    # 总结
    total_passed = passed + neg_passed
    total_tests = len(test_cases) + len(negative_cases)
    
    print("\n" + "=" * 70)
    print(f"Phase 3 Pint单位归一化测试完成: {total_passed}/{total_tests} PASS")
    print("=" * 70)
    
    if total_passed == total_tests:
        print("\n[OK] Phase 3 Pint引擎验收通过")
        return True
    else:
        print(f"\n[WARN] Phase 3 Pint引擎部分失败: {total_tests - total_passed} tests failed")
        return False


if __name__ == '__main__':
    success = test_normalizer()
    sys.exit(0 if success else 1)
