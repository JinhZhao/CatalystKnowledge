#!/usr/bin/env python3
"""
Part A: Experiment统一整合
将scientific_objects中的Experiment与tables、quantity_records关联
"""
import json
from pathlib import Path

def integrate_experiments(doc_id):
    """整合单个文档的实验数据"""
    report_path = Path(f'runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json')
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # 提取实验对象（每个文档只有1个Experiment对象）
    sci_objects = report.get('scientific_objects', {}).get('objects', {})
    experiment = sci_objects.get('Experiment', {})
    sample = sci_objects.get('CatalystSample', {})
    reaction = sci_objects.get('Reaction', {})
    observations = sci_objects.get('Observation', [])  # Observation是列表
    
    # 转换为列表以便统一处理
    experiments = [experiment] if experiment else []
    samples = [sample] if sample else []
    reactions = [reaction] if reaction else []
    # observations已经是列表
    
    # 提取表格数据
    tables = report.get('tables', [])
    
    # 提取数量记录（dict结构，包含'records'列表）
    quantity_records_data = report.get('quantity_records', {})
    quantity_records = quantity_records_data.get('records', [])
    
    # 建立关联
    experiment_integration = []
    for exp in experiments:
        exp_id = exp.get('object_id', '')
        # 兼容两种字段名：document_id 或 doc_id
        exp_doc_id = exp.get('document_id', '') or exp.get('doc_id', '')
        
        # 查找关联的样本（通过document_id或doc_id匹配）
        related_samples = []
        for sample in samples:
            sample_doc_id = sample.get('document_id', '') or sample.get('doc_id', '')
            if sample_doc_id == exp_doc_id:
                related_samples.append({
                    'sample_id': sample.get('object_id'),
                    'catalyst_name': sample.get('name', ''),
                    'composition': sample.get('roles', {})
                })
        
        # 查找关联的反应（通过document_id或doc_id匹配）
        related_reactions = []
        for reaction in reactions:
            reaction_doc_id = reaction.get('document_id', '') or reaction.get('doc_id', '')
            if reaction_doc_id == exp_doc_id:
                related_reactions.append({
                    'reaction_id': reaction.get('object_id'),
                    'reaction_type': reaction.get('reaction_type', ''),
                    'conditions': reaction.get('proposed_pathway', '')
                })
        
        # 查找关联的表格行（通过element_id匹配）
        related_table_rows = []
        for table in tables:
            table_id = table.get('element_id', '')
            # 简单关联：如果表格ID包含文档ID
            if exp_doc_id and exp_doc_id in table_id:
                related_table_rows.append({
                    'table_id': table_id,
                    'page': table.get('page'),
                    'note': 'Same document'
                })
        
        # 查找关联的数量记录（通过doc_id匹配）
        related_quantities = []
        for qr in quantity_records:
            if qr.get('doc_id') == exp_doc_id:
                source_anchor = qr.get('source_anchor') or {}
                related_quantities.append({
                    'quantity_id': qr.get('record_id'),
                    'quantity_type': qr.get('quantity_type'),
                    'value': qr.get('three_layer_values', {}).get('raw', {}).get('value'),
                    'unit': qr.get('three_layer_values', {}).get('raw', {}).get('unit'),
                    'source_element': source_anchor.get('element_id')
                })
        
        # 查找关联的观察（通过document_id或doc_id匹配）
        related_observations = []
        for obs in observations:
            obs_doc_id = obs.get('document_id', '') or obs.get('doc_id', '')
            if obs_doc_id == exp_doc_id:
                related_observations.append({
                    'observation_id': obs.get('object_id'),
                    'metric_name': obs.get('metric_name'),
                    'value': obs.get('value')
                })
        
        # 判断整合状态
        has_sample = len(related_samples) > 0
        has_reaction = len(related_reactions) > 0
        has_quantities = len(related_quantities) > 0
        
        if has_sample and has_reaction and has_quantities:
            integration_status = 'COMPLETE'
        elif has_sample or has_reaction:
            integration_status = 'PARTIAL'
        else:
            integration_status = 'MINIMAL'
        
        experiment_integration.append({
            'experiment_id': exp_id,
            'document_id': exp_doc_id,
            'related_samples': related_samples,
            'related_reactions': related_reactions,
            'related_table_rows': related_table_rows,
            'related_quantities': related_quantities,
            'related_observations': related_observations,
            'integration_status': integration_status,
            'chain_completeness': {
                'CatalystSample': has_sample,
                'Reaction': has_reaction,
                'QuantityRecord': has_quantities,
                'Observation': len(related_observations) > 0
            }
        })
    
    return {
        'doc_id': doc_id,
        'total_experiments': len(experiments),
        'integrated_experiments': len([e for e in experiment_integration if e['integration_status'] == 'COMPLETE']),
        'partial_experiments': len([e for e in experiment_integration if e['integration_status'] == 'PARTIAL']),
        'minimal_experiments': len([e for e in experiment_integration if e['integration_status'] == 'MINIMAL']),
        'experiment_details': experiment_integration
    }

def main():
    docs = ['F02', 'F07', 'P01', 'PAT01']
    all_integrations = {}
    
    for doc in docs:
        print(f"Integrating experiments for {doc}...")
        integration = integrate_experiments(doc)
        all_integrations[doc] = integration
        print(f"  Total: {integration['total_experiments']}, "
              f"Complete: {integration['integrated_experiments']}, "
              f"Partial: {integration['partial_experiments']}, "
              f"Minimal: {integration['minimal_experiments']}")
    
    # 保存结果
    output_path = Path('runs/final_006/part_a_experiment_integration.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_integrations, f, ensure_ascii=False, indent=2)
    
    print(f"\nPart A complete. Results saved to {output_path}")
    
    # 生成摘要
    total_exp = sum(i['total_experiments'] for i in all_integrations.values())
    total_complete = sum(i['integrated_experiments'] for i in all_integrations.values())
    total_partial = sum(i['partial_experiments'] for i in all_integrations.values())
    total_minimal = sum(i['minimal_experiments'] for i in all_integrations.values())
    
    print(f"\nSummary:")
    print(f"  Total experiments: {total_exp}")
    print(f"  Fully integrated (COMPLETE): {total_complete} ({total_complete/total_exp*100:.1f}%)")
    print(f"  Partially integrated (PARTIAL): {total_partial} ({total_partial/total_exp*100:.1f}%)")
    print(f"  Minimally integrated (MINIMAL): {total_minimal} ({total_minimal/total_exp*100:.1f}%)")

if __name__ == '__main__':
    main()
