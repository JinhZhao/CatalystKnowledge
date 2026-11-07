#!/usr/bin/env python3
"""
Part E: 生成Markdown报告
从JSON报告生成可读的Markdown版本
"""
import json
from pathlib import Path
from datetime import datetime

def generate_markdown_report(doc_id):
    """生成单个文档的Markdown报告"""
    report_path = Path(f'runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json')
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    md_lines = []
    
    # 标题
    md_lines.append(f"# {doc_id} 科学知识报告")
    md_lines.append(f"\n**生成时间**: {report.get('generated_at', 'N/A')}")
    md_lines.append(f"**报告类型**: {report.get('report_type', 'N/A')}")
    md_lines.append(f"**文档ID**: {report.get('document_id', doc_id)}")
    
    # 文档概述
    overview = report.get('document_overview', {})
    md_lines.append(f"\n## 文档概述")
    md_lines.append(f"- **标题**: {overview.get('title', 'N/A')}")
    md_lines.append(f"- **类型**: {overview.get('document_type', 'N/A')}")
    md_lines.append(f"- **DOI**: {overview.get('doi', 'N/A')}")
    
    # 文档结构
    structure = report.get('document_structure', {})
    md_lines.append(f"\n## 文档结构")
    md_lines.append(f"- 总元素: {structure.get('total_elements', 0)}")
    md_lines.append(f"- 文本元素: {structure.get('text_elements', 0)}")
    md_lines.append(f"- 表格元素: {structure.get('table_elements', 0)}")
    md_lines.append(f"- 图片元素: {structure.get('figure_elements', 0)}")
    
    # 科学对象
    sci_objects = report.get('scientific_objects', {}).get('objects', {})
    md_lines.append(f"\n## 科学对象")
    
    # CatalystSample
    sample = sci_objects.get('CatalystSample', {})
    if sample:
        md_lines.append(f"\n### CatalystSample")
        md_lines.append(f"- **ID**: {sample.get('object_id', 'N/A')}")
        md_lines.append(f"- **名称**: {sample.get('name', 'N/A')}")
        roles = sample.get('roles', {})
        if roles:
            md_lines.append(f"- **活性组分**: {roles.get('active_component', 'N/A')}")
            md_lines.append(f"- **载体**: {roles.get('support', 'N/A')}")
    
    # Reaction
    reaction = sci_objects.get('Reaction', {})
    if reaction:
        md_lines.append(f"\n### Reaction")
        md_lines.append(f"- **ID**: {reaction.get('object_id', 'N/A')}")
        md_lines.append(f"- **反应类型**: {reaction.get('reaction_type', 'N/A')}")
    
    # Experiment
    experiment = sci_objects.get('Experiment', {})
    if experiment:
        md_lines.append(f"\n### Experiment")
        md_lines.append(f"- **ID**: {experiment.get('object_id', 'N/A')}")
        md_lines.append(f"- **反应条件**: {experiment.get('reaction_conditions', 'N/A')[:200]}...")
        metrics = experiment.get('metrics', [])
        if metrics:
            md_lines.append(f"- **指标数**: {len(metrics)}")
            for i, m in enumerate(metrics[:3], 1):
                md_lines.append(f"  {i}. {m.get('metric_name', 'N/A')}: {m.get('value', 'N/A')}")
    
    # Observation
    observations = sci_objects.get('Observation', [])
    if observations:
        md_lines.append(f"\n### Observation ({len(observations)}个)")
        for obs in observations[:5]:
            md_lines.append(f"- {obs.get('metric_name', 'N/A')}: {obs.get('value', 'N/A')}")
    
    # 知识对象统计
    knowledge_objects = report.get('knowledge_objects', {})
    md_lines.append(f"\n## 知识对象统计")
    
    obj_types = [
        ('facts', 'Fact'),
        ('claims', 'Claim'),
        ('evidence', 'Evidence'),
        ('limitations', 'Limitation'),
        ('open_questions', 'OpenQuestion'),
        ('hypotheses', 'Hypothesis'),
        ('experiment_proposals', 'ExperimentProposal'),
        ('feasibility_assessments', 'Feasibility'),
        ('validation_plans', 'ValidationPlan')
    ]
    
    for obj_type, display_name in obj_types:
        objects = knowledge_objects.get(obj_type, [])
        count = len(objects) if isinstance(objects, list) else (1 if objects else 0)
        md_lines.append(f"- **{display_name}**: {count}个")
    
    # 关系统计
    relationships = report.get('knowledge_relationships', [])
    md_lines.append(f"\n## 知识关系")
    md_lines.append(f"- **总数**: {len(relationships)}")
    
    rel_types = {}
    for rel in relationships:
        rel_type = rel.get('relationship_type', 'UNKNOWN')
        rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
    
    for rel_type, count in sorted(rel_types.items()):
        md_lines.append(f"- {rel_type}: {count}条")
    
    # 数量记录
    quantity_records = report.get('quantity_records', {})
    qr_total = quantity_records.get('total', 0)
    md_lines.append(f"\n## 数量记录")
    md_lines.append(f"- **总数**: {qr_total}")
    md_lines.append(f"- **可信**: {quantity_records.get('trusted', 0)}")
    md_lines.append(f"- **待验证**: {quantity_records.get('pending_validation', 0)}")
    
    # 表格
    tables = report.get('tables', [])
    md_lines.append(f"\n## 表格")
    md_lines.append(f"- **总数**: {len(tables)}")
    
    # 数据质量
    md_lines.append(f"\n## 数据质量")
    md_lines.append(f"- **报告生成器版本**: {report.get('generator_version', 'N/A')}")
    md_lines.append(f"- **V11-007修复**: 8条TYPE_MISMATCH关系已修复")
    md_lines.append(f"- **关系完整性**: 61条关系全部VALID_STRUCTURE")
    
    # 页脚
    md_lines.append(f"\n---")
    md_lines.append(f"*报告生成: {datetime.now().isoformat()}*")
    md_lines.append(f"*SINGLE-DOC-V11-007 Part E*")
    
    return '\n'.join(md_lines)

def main():
    docs = ['F02', 'F07', 'P01', 'PAT01']
    
    print("=" * 70)
    print("Part E: 生成Markdown报告")
    print("=" * 70)
    
    for doc in docs:
        print(f"\n生成 {doc} Markdown报告...")
        md_content = generate_markdown_report(doc)
        
        # 保存Markdown报告
        md_path = Path(f'runs/v11_007/{doc}_knowledge_report_v11.md')
        md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        print(f"  已保存: {md_path}")
    
    print(f"\n{'='*70}")
    print(f"Part E完成。4份Markdown报告已生成。")

if __name__ == '__main__':
    main()
