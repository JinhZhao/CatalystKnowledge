#!/usr/bin/env python3
"""
009-E Phase D: V2适配器隔离测试

验证V2 section-aware适配器能否正确处理F02全文，
不使用6000字符硬截断，而是通过分块处理全文。

测试目标：
1. V2适配器可以加载F02全文（34,457字符）
2. V2适配器可以按章节分块
3. V2适配器可以为每个维度构建多个chunk
4. 分块后的总覆盖率接近100%

注意：
- 本脚本不调用真实LLM（避免成本）
- 仅验证分块逻辑和覆盖率
- 不修改生产代码
- 不覆盖G3历史结果
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from catalyst_knowledge.pipeline.section_aware_extractor import SectionAwareContentLoader


def test_v2_chunking():
    """测试V2适配器的分块逻辑"""
    print("=" * 70)
    print("009-E Phase D: V2适配器隔离测试")
    print("=" * 70)
    
    # 1. 加载F02内容
    content_list_path = Path("D:/Knowledge_World/data/test_corpus/mineru_output/F02_regression/main/auto/main_content_list.json")
    
    if not content_list_path.exists():
        print(f"[ERROR] 文件不存在: {content_list_path}")
        return False
    
    print(f"\n[1/5] 加载F02内容列表...")
    loader = SectionAwareContentLoader(content_list_path, max_chunk_chars=8000)
    loader.load()
    
    full_text = loader.full_text
    sections = loader.sections
    elements = loader.elements
    
    print(f"  [OK] 总字符数: {len(full_text)}")
    print(f"  [OK] 总段落数: {len(elements)}")
    print(f"  [OK] 总章节数: {len(sections)}")
    
    # 2. 检查章节识别
    print(f"\n[2/5] 章节识别结果...")
    for i, section in enumerate(sections[:10]):  # 显示前10个章节
        print(f"  {section.section_id}: {section.title[:50]:50s} ({section.char_count} chars)")
    
    if len(sections) > 10:
        print(f"  ... 还有 {len(sections) - 10} 个章节")
    
    # 3. 测试维度分块
    print(f"\n[3/5] 测试维度分块...")
    dimensions = [
        "catalyst_design",
        "characterization",
        "performance",
        "mechanism",
        "structure_activity",
        "reliability"
    ]
    
    chunk_stats = {}
    for dim in dimensions:
        chunks = loader.build_dimension_chunks(dim)
        total_chars = sum(len(chunk.content) for chunk in chunks)
        chunk_stats[dim] = {
            "chunk_count": len(chunks),
            "total_chars": total_chars,
            "coverage_pct": round(total_chars / len(full_text) * 100, 1)
        }
        print(f"  {dim:20s}: {len(chunks)} chunks, {total_chars:6d} chars, {chunk_stats[dim]['coverage_pct']:5.1f}% coverage")
    
    # 4. 计算总体覆盖率
    print(f"\n[4/5] 覆盖率统计...")
    avg_coverage = sum(stats["coverage_pct"] for stats in chunk_stats.values()) / len(chunk_stats)
    print(f"  [OK] 平均覆盖率: {avg_coverage:.1f}%")
    print(f"  [OK] V1截断覆盖率: 14.1% (6000/34457 chars)")
    print(f"  [OK] 覆盖率提升: {avg_coverage - 14.1:.1f} percentage points")
    
    # 5. 验证分块完整性
    print(f"\n[5/5] 分块完整性验证...")
    all_pass = True
    
    for dim, stats in chunk_stats.items():
        if stats["coverage_pct"] < 90:
            print(f"  [FAIL] {dim}: 覆盖率 {stats['coverage_pct']:.1f}% < 90%")
            all_pass = False
        else:
            print(f"  [OK] {dim}: 覆盖率 {stats['coverage_pct']:.1f}%")
    
    # 生成测试报告
    test_report = {
        "test_id": "009E_PHASE_D_V2_CHUNKING_TEST",
        "timestamp": "2026-11-06T13:00:00Z",
        "document_id": "F02",
        "test_type": "V2_ADAPTER_CHUNKING_VERIFICATION",
        "full_text_length": len(full_text),
        "section_count": len(sections),
        "dimension_stats": chunk_stats,
        "average_coverage_pct": round(avg_coverage, 1),
        "v1_truncation_coverage_pct": 14.1,
        "coverage_improvement_pct": round(avg_coverage - 14.1, 1),
        "all_dimensions_above_90pct": all_pass,
        "test_result": "PASS" if all_pass else "FAIL",
        "conclusion": f"V2适配器通过章节感知分块，将正文覆盖率从14.1%提升到{avg_coverage:.1f}%"
    }
    
    # 保存测试报告
    report_path = Path("D:/Knowledge_World/runs/engineering_closeout_009E/D_V2_CHUNKING_TEST_REPORT.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(test_report, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 70}")
    print(f"结果: {'[PASS]' if all_pass else '[FAIL]'}")
    print(f"测试报告: {report_path}")
    print(f"{'=' * 70}")
    
    return all_pass


if __name__ == "__main__":
    success = test_v2_chunking()
    sys.exit(0 if success else 1)
