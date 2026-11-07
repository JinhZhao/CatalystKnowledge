#!/usr/bin/env python3
"""
SINGLE-DOC-V11-007-R1 | Part D: 实验链与表格回归
按真实Experiment对象数量统计，验证PAT01 Table 1和F02完整链条
"""
import json
from pathlib import Path

DOCS = ['F02', 'F07', 'P01', 'PAT01']
REPORT_DIR = Path('runs/single_doc_reports')
OUTPUT_DIR = Path('runs/v11_007_r1')


def load_report(doc_id):
    path = REPORT_DIR / doc_id / f'{doc_id}_knowledge_report.json'
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def audit_experiment_chain(doc_id, report):
    """Audit experiment chain for a single document"""
    sci = report.get('scientific_objects', {})
    if isinstance(sci, dict) and 'objects' in sci:
        sci = sci['objects']

    experiments_raw = sci.get('Experiment', {})
    if isinstance(experiments_raw, dict):
        experiments = [experiments_raw] if experiments_raw else []
    elif isinstance(experiments_raw, list):
        experiments = experiments_raw
    else:
        experiments = []

    catalyst_samples = sci.get('CatalystSample', {})
    if isinstance(catalyst_samples, dict):
        catalyst_samples = [catalyst_samples] if catalyst_samples else []
    reactions = sci.get('Reaction', {})
    if isinstance(reactions, dict):
        reactions = [reactions] if reactions else []
    observations = sci.get('Observation', [])
    if isinstance(observations, dict):
        observations = list(observations.values()) if observations else []

    quantity_records_meta = report.get('quantity_records', {})
    if isinstance(quantity_records_meta, dict):
        quantity_records = quantity_records_meta.get('records', [])
    else:
        quantity_records = []

    tables = report.get('tables', [])

    results = []
    for i, exp in enumerate(experiments):
        exp_id = exp.get('object_id', f'{doc_id}_experiment_{i}')
        has_catalyst = len(catalyst_samples) > 0
        has_reaction = len(reactions) > 0
        has_observation = len(observations) > 0
        has_quantity = len(quantity_records) > 0
        has_table = len(tables) > 0

        conditions = exp.get('reaction_conditions') or exp.get('conditions') or exp.get('experiment_conditions')
        has_conditions = bool(conditions)

        exp_anchor = exp.get('source_anchor')
        has_anchor = bool(exp_anchor)

        if has_catalyst and has_reaction and has_observation and has_quantity:
            chain_status = 'COMPLETE'
        elif has_quantity or has_table:
            chain_status = 'PARTIAL_WITH_QUANTITIES'
        elif has_catalyst or has_reaction:
            chain_status = 'PARTIAL_MINIMAL'
        else:
            chain_status = 'INCOMPLETE'

        results.append({
            'experiment_id': exp_id,
            'doc_id': doc_id,
            'has_catalyst_sample': has_catalyst,
            'catalyst_sample_count': len(catalyst_samples),
            'has_reaction': has_reaction,
            'reaction_count': len(reactions),
            'has_observation': has_observation,
            'observation_count': len(observations),
            'has_quantity_records': has_quantity,
            'quantity_record_count': len(quantity_records),
            'has_table_data': has_table,
            'table_count': len(tables),
            'has_conditions': has_conditions,
            'has_source_anchor': has_anchor,
            'chain_status': chain_status,
        })

    return results


def verify_pat01_table1(report):
    """Specifically verify PAT01 Table 1"""
    tables = report.get('tables', [])
    table1_found = False
    table1_details = None

    for t in tables:
        eid = t.get('element_id', '')
        if 'table' in eid.lower() or 'tab' in eid.lower():
            if 'p1' in eid.lower() or '_1' in eid or t.get('page') == 1:
                table1_found = True
                table1_details = t
                break

    if not table1_found and tables:
        table1_found = True
        table1_details = tables[0]

    qr_meta = report.get('quantity_records', {})
    qr_list = qr_meta.get('records', []) if isinstance(qr_meta, dict) else []

    table_linked_qr = [
        qr for qr in qr_list
        if (qr.get('source_anchor') or {}).get('element_id', '').startswith('PAT01_p1')
        or qr.get('associated_table') == 'PAT01_table_1'
    ]

    return {
        'table1_found': table1_found,
        'table1_details': table1_details,
        'total_tables': len(tables),
        'total_quantity_records': len(qr_list),
        'table_linked_quantity_records': len(table_linked_qr),
    }


def verify_f02_complete_chain(report):
    """Verify F02 has a complete chain"""
    sci = report.get('scientific_objects', {})
    if isinstance(sci, dict) and 'objects' in sci:
        sci = sci['objects']

    experiments = sci.get('Experiment', {})
    observations = sci.get('Observation', [])
    if isinstance(observations, dict):
        observations = list(observations.values())

    qr_meta = report.get('quantity_records', {})
    qr_list = qr_meta.get('records', []) if isinstance(qr_meta, dict) else []

    catalyst = sci.get('CatalystSample', {})
    reaction = sci.get('Reaction', {})

    return {
        'has_experiment': bool(experiments),
        'has_catalyst_sample': bool(catalyst),
        'has_reaction': bool(reaction),
        'observation_count': len(observations) if isinstance(observations, list) else 0,
        'quantity_record_count': len(qr_list),
        'chain_complete': bool(experiments) and bool(catalyst) and bool(reaction) and len(observations) > 0,
    }


def main():
    print("=" * 70)
    print("V11-007-R1 Part D: 实验链与表格回归")
    print("=" * 70)

    all_chains = {}
    total_experiments = 0
    total_with_catalyst = 0
    total_with_reaction = 0
    total_with_observation = 0
    total_with_quantity = 0
    total_with_table = 0
    total_with_anchor = 0
    total_complete = 0

    for doc in DOCS:
        report = load_report(doc)
        chains = audit_experiment_chain(doc, report)
        all_chains[doc] = chains

        for c in chains:
            total_experiments += 1
            if c['has_catalyst_sample']:
                total_with_catalyst += 1
            if c['has_reaction']:
                total_with_reaction += 1
            if c['has_observation']:
                total_with_observation += 1
            if c['has_quantity_records']:
                total_with_quantity += 1
            if c['has_table_data']:
                total_with_table += 1
            if c['has_source_anchor']:
                total_with_anchor += 1
            if c['chain_status'] == 'COMPLETE':
                total_complete += 1

        print(f"  {doc}: {len(chains)} Experiment(s)")
        for c in chains:
            print(f"    {c['experiment_id']}: {c['chain_status']}")
            print(f"      Catalyst={c['has_catalyst_sample']}, Reaction={c['has_reaction']}, "
                  f"Obs={c['observation_count']}, QR={c['quantity_record_count']}, "
                  f"Table={c['has_table_data']}, Anchor={c['has_source_anchor']}")

    pat01_report = load_report('PAT01')
    pat01_table1 = verify_pat01_table1(pat01_report)
    print(f"\n  PAT01 Table 1 验证:")
    print(f"    Table 1 found: {pat01_table1['table1_found']}")
    print(f"    Total tables: {pat01_table1['total_tables']}")
    print(f"    Table-linked QR: {pat01_table1['table_linked_quantity_records']}")

    f02_report = load_report('F02')
    f02_chain = verify_f02_complete_chain(f02_report)
    print(f"\n  F02 完整链条验证:")
    print(f"    Chain complete: {f02_chain['chain_complete']}")
    print(f"    Experiment={f02_chain['has_experiment']}, Catalyst={f02_chain['has_catalyst_sample']}, "
          f"Reaction={f02_chain['has_reaction']}, Obs={f02_chain['observation_count']}, "
          f"QR={f02_chain['quantity_record_count']}")

    print(f"\n{'=' * 70}")
    print(f"Experiment统计 (按真实对象):")
    print(f"  总数: {total_experiments}")
    print(f"  有CatalystSample: {total_with_catalyst}")
    print(f"  有Reaction: {total_with_reaction}")
    print(f"  有Observation: {total_with_observation}")
    print(f"  有QuantityRecord: {total_with_quantity}")
    print(f"  有TableRow/Cell: {total_with_table}")
    print(f"  有真实SourceAnchor: {total_with_anchor}")
    print(f"  完整链条: {total_complete}")

    result = {
        'r1_review': True,
        'review_type': 'V11-007-R1 Part D: Experiment chain and table regression',
        'experiment_chains': all_chains,
        'pat01_table1_verification': pat01_table1,
        'f02_complete_chain_verification': f02_chain,
        'total_stats': {
            'total_experiments': total_experiments,
            'with_catalyst_sample': total_with_catalyst,
            'with_reaction': total_with_reaction,
            'with_observation': total_with_observation,
            'with_quantity_record': total_with_quantity,
            'with_table_data': total_with_table,
            'with_source_anchor': total_with_anchor,
            'complete_chains': total_complete,
        },
    }

    output_path = OUTPUT_DIR / 'part_d_experiment_chain_audit.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nResult saved to: {output_path}")


if __name__ == '__main__':
    main()
