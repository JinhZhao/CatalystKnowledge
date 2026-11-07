#!/usr/bin/env python3
"""
Part B: Experiment与Observation真实关联审计
审计每个文档的Experiment数据链完整性
"""
import json
from pathlib import Path
from datetime import datetime

def audit_experiment_chain(doc_id):
    """审计单个文档的Experiment数据链"""
    report_path = Path(f'runs/single_doc_reports/{doc_id}/{doc_id}_knowledge_report.json')
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # 提取scientific_objects中的Experiment
    sci_objects = report.get('scientific_objects', {}).get('objects', {})
    experiment = sci_objects.get('Experiment', {})
    sample = sci_objects.get('CatalystSample', {})
    reaction = sci_objects.get('Reaction', {})
    observations = sci_objects.get('Observation', [])
    
    # 提取knowledge_objects中的experiment_proposals
    knowledge_objects = report.get('knowledge_objects', {})
    experiment_proposals = knowledge_objects.get('experiment_proposals', [])
    
    # 提取表格数据
    tables = report.get('tables', [])
    
    # 提取数量记录
    quantity_records_data = report.get('quantity_records', {})
    quantity_records = quantity_records_data.get('records', [])
    
    # 审计Experiment对象
    experiment_audit = {
        'has_experiment_object': bool(experiment),
        'has_experiment_conditions': False,
        'has_observation': len(observations) > 0,
        'has_quantity_records': len(quantity_records) > 0,
        'has_table_data': len(tables) > 0,
        'has_source_anchor': False,
        'observation_count': len(observations),
        'quantity_record_count': len(quantity_records),
        'table_count': len(tables)
    }
    
    # 检查实验条件
    if experiment:
        # 兼容document_id和doc_id
        exp_doc_id = experiment.get('document_id', '') or experiment.get('doc_id', '')
        
        # 检查reaction_conditions
        reaction_conditions = experiment.get('reaction_conditions', '')
        if reaction_conditions and len(reaction_conditions) > 10:
            experiment_audit['has_experiment_conditions'] = True
        
        # 检查metrics
        metrics = experiment.get('metrics', [])
        if metrics and len(metrics) > 0:
            experiment_audit['has_experiment_conditions'] = True
        
        # 检查source_anchor
        source_anchor = experiment.get('source_anchor')
        if source_anchor:
            experiment_audit['has_source_anchor'] = True
    
    # 判断数据链完整性
    chain_completeness = {
        'CatalystSample': bool(sample),
        'Reaction': bool(reaction),
        'Experiment': experiment_audit['has_experiment_object'],
        'ExperimentConditions': experiment_audit['has_experiment_conditions'],
        'Observation': experiment_audit['has_observation'],
        'QuantityRecord': experiment_audit['has_quantity_records'],
        'TableData': experiment_audit['has_table_data'],
        'SourceAnchor': experiment_audit['has_source_anchor']
    }
    
    # 判断整合状态
    core_chain = (chain_completeness['CatalystSample'] and 
                  chain_completeness['Reaction'] and 
                  chain_completeness['Experiment'] and
                  chain_completeness['ExperimentConditions'])
    
    if core_chain and chain_completeness['QuantityRecord'] and chain_completeness['Observation']:
        integration_status = 'COMPLETE'
    elif core_chain and chain_completeness['QuantityRecord']:
        integration_status = 'PARTIAL_WITH_QUANTITIES'
    elif core_chain:
        integration_status = 'PARTIAL_MINIMAL'
    else:
        integration_status = 'INCOMPLETE'
    
    return {
        'doc_id': doc_id,
        'experiment_audit': experiment_audit,
        'chain_completeness': chain_completeness,
        'integration_status': integration_status,
        'experiment_details': experiment if experiment else None,
        'sample_details': sample if sample else None,
        'reaction_details': reaction if reaction else None
    }

def main():
    docs = ['F02', 'F07', 'P01', 'PAT01']
    all_audits = {}
    
    print("=" * 70)
    print("Part B: Experiment与Observation真实关联审计")
    print("=" * 70)
    
    for doc in docs:
        print(f"\n审计 {doc}...")
        audit = audit_experiment_chain(doc)
        all_audits[doc] = audit
        
        print(f"  Experiment对象: {'YES' if audit['experiment_audit']['has_experiment_object'] else 'NO'}")
        print(f"  实验条件: {'YES' if audit['experiment_audit']['has_experiment_conditions'] else 'NO'}")
        print(f"  Observation: {audit['experiment_audit']['observation_count']}个")
        print(f"  QuantityRecord: {audit['experiment_audit']['quantity_record_count']}个")
        print(f"  表格: {audit['experiment_audit']['table_count']}个")
        print(f"  SourceAnchor: {'YES' if audit['experiment_audit']['has_source_anchor'] else 'NO'}")
        print(f"  整合状态: {audit['integration_status']}")
    
    # 保存结果
    output_path = Path('runs/v11_007/part_b_experiment_chain_audit.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result = {
        'audit_timestamp': datetime.now().isoformat(),
        'documents': all_audits,
        'summary': {
            'total_experiments': sum(1 for a in all_audits.values() if a['experiment_audit']['has_experiment_object']),
            'complete_chains': sum(1 for a in all_audits.values() if a['integration_status'] == 'COMPLETE'),
            'partial_with_quantities': sum(1 for a in all_audits.values() if a['integration_status'] == 'PARTIAL_WITH_QUANTITIES'),
            'partial_minimal': sum(1 for a in all_audits.values() if a['integration_status'] == 'PARTIAL_MINIMAL'),
            'incomplete': sum(1 for a in all_audits.values() if a['integration_status'] == 'INCOMPLETE')
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*70}")
    print(f"Part B审计完成。结果保存到: {output_path}")
    print(f"\n总摘要:")
    print(f"  Experiment对象总数: {result['summary']['total_experiments']}/4")
    print(f"  COMPLETE链条: {result['summary']['complete_chains']}")
    print(f"  PARTIAL_WITH_QUANTITIES: {result['summary']['partial_with_quantities']}")
    print(f"  PARTIAL_MINIMAL: {result['summary']['partial_minimal']}")
    print(f"  INCOMPLETE: {result['summary']['incomplete']}")

if __name__ == '__main__':
    main()
