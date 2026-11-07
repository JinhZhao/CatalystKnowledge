"""
G3-02: ENT-001 Scientific Object Structuring

Map real LLM extraction results to scientific objects:
Document → CatalystSample → Reaction → Experiment → Observation → Evidence

Distinguish roles: catalyst, precursor, support, active component, substrate, product.
Keep uncertain objects/relations as candidates.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


def load_extraction_results(doc_id: str) -> Dict[str, Any]:
    """Load extraction results for a document."""
    extraction_dir = Path(f'data/test_corpus/g3_output/{doc_id}')
    
    dimensions = {}
    for dim_file in extraction_dir.glob('*_extracted.json'):
        dim_name = dim_file.stem.replace('_extracted', '')
        with open(dim_file, 'r', encoding='utf-8') as f:
            dimensions[dim_name] = json.load(f)
    
    return dimensions


def create_catalyst_sample(doc_id: str, dimensions: Dict) -> Dict[str, Any]:
    """Create CatalystSample object from extraction results."""
    
    catalyst_design = dimensions.get('catalyst_design', {})
    characterization = dimensions.get('characterization', {})
    
    # Extract catalyst system components
    catalyst_system = catalyst_design.get('catalyst_system', '')
    active_component = catalyst_design.get('active_component', '')
    support = catalyst_design.get('support', '')
    
    # Determine roles
    roles = {}
    if active_component:
        roles['active_component'] = active_component
    if support:
        roles['support'] = support
    
    # Parse catalyst system for additional components
    if catalyst_system:
        # Simple heuristic: look for common patterns
        if '/' in catalyst_system:
            parts = catalyst_system.split('/')
            if len(parts) >= 2:
                if not roles.get('active_component'):
                    roles['active_component'] = parts[0].strip()
                if not roles.get('support'):
                    roles['support'] = parts[1].strip()
    
    sample = {
        'object_type': 'CatalystSample',
        'object_id': f'{doc_id}_sample_001',
        'document_id': doc_id,
        'name': catalyst_system if catalyst_system else f'{doc_id} catalyst',
        'roles': roles,
        'synthesis_method': catalyst_design.get('synthesis_method'),
        'characterization_evidence': {
            'techniques': characterization.get('techniques_used', []),
            'findings': characterization.get('key_findings', []),
            'morphological': characterization.get('morphological_evidence'),
            'electronic': characterization.get('electronic_evidence')
        },
        'confidence': 'candidate',  # All objects start as candidates
        'source_anchor': {
            'document_id': doc_id,
            'element_type': 'TEXT',
            'location': 'catalyst_design + characterization dimensions'
        }
    }
    
    return sample


def create_reaction(doc_id: str, dimensions: Dict) -> Dict[str, Any]:
    """Create Reaction object from extraction results."""
    
    catalyst_design = dimensions.get('catalyst_design', {})
    mechanism = dimensions.get('mechanism', {})
    
    reaction_type = catalyst_design.get('reaction_type', '')
    proposed_pathway = mechanism.get('proposed_pathway', '')
    intermediates = mechanism.get('intermediates', [])
    
    reaction = {
        'object_type': 'Reaction',
        'object_id': f'{doc_id}_reaction_001',
        'document_id': doc_id,
        'reaction_type': reaction_type if reaction_type else 'unknown',
        'proposed_pathway': proposed_pathway,
        'intermediates': intermediates,
        'computational_support': mechanism.get('computational_support'),
        'experimental_support': mechanism.get('experimental_support'),
        'confidence': 'candidate',
        'source_anchor': {
            'document_id': doc_id,
            'element_type': 'TEXT',
            'location': 'catalyst_design + mechanism dimensions'
        }
    }
    
    return reaction


def create_experiment(doc_id: str, dimensions: Dict) -> Dict[str, Any]:
    """Create Experiment object from extraction results."""
    
    performance = dimensions.get('performance', {})
    reliability = dimensions.get('reliability', {})
    
    reaction_conditions = performance.get('reaction_conditions', '')
    key_metrics = performance.get('key_metrics', [])
    
    experiment = {
        'object_type': 'Experiment',
        'object_id': f'{doc_id}_experiment_001',
        'document_id': doc_id,
        'reaction_conditions': reaction_conditions,
        'metrics': key_metrics,
        'time_on_stream': reliability.get('time_on_stream'),
        'time_on_stream_note': reliability.get('time_on_stream_note'),
        'cycle_count': reliability.get('cycle_count'),
        'confidence': 'candidate',
        'source_anchor': {
            'document_id': doc_id,
            'element_type': 'TEXT',
            'location': 'performance + reliability dimensions'
        }
    }
    
    return experiment


def create_observations(doc_id: str, dimensions: Dict) -> List[Dict[str, Any]]:
    """Create Observation objects from performance metrics."""
    
    performance = dimensions.get('performance', {})
    key_metrics = performance.get('key_metrics', [])
    
    observations = []
    for i, metric in enumerate(key_metrics):
        obs = {
            'object_type': 'Observation',
            'object_id': f'{doc_id}_obs_{i+1:03d}',
            'document_id': doc_id,
            'metric_name': metric.get('metric_name'),
            'value': metric.get('value'),
            'conditions': metric.get('conditions'),
            'unit': metric.get('unit'),  # May be embedded in value
            'confidence': 'candidate',
            'source_anchor': {
                'document_id': doc_id,
                'element_type': 'TEXT',
                'location': f'performance dimension, metric {i+1}'
            }
        }
        observations.append(obs)
    
    return observations


def create_evidence(doc_id: str, dimensions: Dict) -> List[Dict[str, Any]]:
    """Create Evidence objects from characterization and mechanism."""
    
    characterization = dimensions.get('characterization', {})
    mechanism = dimensions.get('mechanism', {})
    reliability = dimensions.get('reliability', {})
    
    evidence_list = []
    
    # Characterization evidence
    findings = characterization.get('key_findings', [])
    for i, finding in enumerate(findings):
        ev = {
            'object_type': 'Evidence',
            'object_id': f'{doc_id}_evidence_char_{i+1:03d}',
            'document_id': doc_id,
            'evidence_type': 'characterization',
            'content': finding,
            'techniques': characterization.get('techniques_used', []),
            'confidence': 'candidate',
            'source_anchor': {
                'document_id': doc_id,
                'element_type': 'TEXT',
                'location': f'characterization dimension, finding {i+1}'
            }
        }
        evidence_list.append(ev)
    
    # Mechanism evidence
    if mechanism.get('computational_support'):
        ev = {
            'object_type': 'Evidence',
            'object_id': f'{doc_id}_evidence_mech_comp',
            'document_id': doc_id,
            'evidence_type': 'mechanism_computational',
            'content': mechanism.get('computational_support'),
            'confidence': 'candidate',
            'source_anchor': {
                'document_id': doc_id,
                'element_type': 'TEXT',
                'location': 'mechanism dimension, computational support'
            }
        }
        evidence_list.append(ev)
    
    if mechanism.get('experimental_support'):
        ev = {
            'object_type': 'Evidence',
            'object_id': f'{doc_id}_evidence_mech_exp',
            'document_id': doc_id,
            'evidence_type': 'mechanism_experimental',
            'content': mechanism.get('experimental_support'),
            'confidence': 'candidate',
            'source_anchor': {
                'document_id': doc_id,
                'element_type': 'TEXT',
                'location': 'mechanism dimension, experimental support'
            }
        }
        evidence_list.append(ev)
    
    # Reliability evidence
    stability_evidence = reliability.get('stability_evidence', [])
    for i, stab in enumerate(stability_evidence):
        ev = {
            'object_type': 'Evidence',
            'object_id': f'{doc_id}_evidence_rel_{i+1:03d}',
            'document_id': doc_id,
            'evidence_type': 'reliability',
            'content': stab,
            'confidence': 'candidate',
            'source_anchor': {
                'document_id': doc_id,
                'element_type': 'TEXT',
                'location': f'reliability dimension, stability evidence {i+1}'
            }
        }
        evidence_list.append(ev)
    
    return evidence_list


def establish_relationships(doc_id: str, objects: Dict) -> List[Dict[str, Any]]:
    """Establish relationships between scientific objects."""
    
    relationships = []
    
    sample = objects.get('CatalystSample')
    reaction = objects.get('Reaction')
    experiment = objects.get('Experiment')
    observations = objects.get('Observation', [])
    evidence = objects.get('Evidence', [])
    
    # Sample -> Reaction (catalyzes)
    if sample and reaction:
        relationships.append({
            'relationship_type': 'catalyzes',
            'source_id': sample['object_id'],
            'target_id': reaction['object_id'],
            'confidence': 'candidate'
        })
    
    # Reaction -> Experiment (performed_in)
    if reaction and experiment:
        relationships.append({
            'relationship_type': 'performed_in',
            'source_id': reaction['object_id'],
            'target_id': experiment['object_id'],
            'confidence': 'candidate'
        })
    
    # Experiment -> Observations (produced)
    if experiment and observations:
        for obs in observations:
            relationships.append({
                'relationship_type': 'produced',
                'source_id': experiment['object_id'],
                'target_id': obs['object_id'],
                'confidence': 'candidate'
            })
    
    # Observations -> Evidence (supported_by)
    if observations and evidence:
        for obs in observations:
            for ev in evidence[:2]:  # Link to first 2 evidence items
                relationships.append({
                    'relationship_type': 'supported_by',
                    'source_id': obs['object_id'],
                    'target_id': ev['object_id'],
                    'confidence': 'candidate'
                })
    
    return relationships


def structure_document(doc_id: str) -> Dict[str, Any]:
    """Create complete scientific object structure for a document."""
    
    print(f"\nStructuring document: {doc_id}")
    
    # Load extraction results
    dimensions = load_extraction_results(doc_id)
    
    # Create objects
    sample = create_catalyst_sample(doc_id, dimensions)
    reaction = create_reaction(doc_id, dimensions)
    experiment = create_experiment(doc_id, dimensions)
    observations = create_observations(doc_id, dimensions)
    evidence = create_evidence(doc_id, dimensions)
    
    # Organize objects
    objects = {
        'Document': {
            'object_type': 'Document',
            'object_id': doc_id,
            'document_type': 'research_article' if doc_id.startswith('F') else 'patent',
            'title': dimensions.get('catalyst_design', {}).get('catalyst_system', f'{doc_id} document')
        },
        'CatalystSample': sample,
        'Reaction': reaction,
        'Experiment': experiment,
        'Observation': observations,
        'Evidence': evidence
    }
    
    # Establish relationships
    relationships = establish_relationships(doc_id, objects)
    
    # Calculate statistics
    stats = {
        'total_objects': 1 + 1 + 1 + 1 + len(observations) + len(evidence),
        'objects_by_type': {
            'Document': 1,
            'CatalystSample': 1,
            'Reaction': 1,
            'Experiment': 1,
            'Observation': len(observations),
            'Evidence': len(evidence)
        },
        'total_relationships': len(relationships),
        'all_confidence': 'candidate'
    }
    
    result = {
        'doc_id': doc_id,
        'timestamp': datetime.now().isoformat(),
        'objects': objects,
        'relationships': relationships,
        'statistics': stats
    }
    
    # Save result
    output_dir = Path(f'data/test_corpus/g3_output/{doc_id}')
    output_file = output_dir / 'scientific_objects.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"  Objects created: {stats['total_objects']}")
    print(f"  Relationships: {stats['total_relationships']}")
    print(f"  Saved: {output_file}")
    
    return result


def main():
    """Run scientific object structuring for all documents."""
    
    print("="*60)
    print("G3-02: ENT-001 Scientific Object Structuring")
    print("="*60)
    
    doc_ids = ['F02', 'F07', 'PAT01']
    
    all_results = {}
    
    for doc_id in doc_ids:
        result = structure_document(doc_id)
        all_results[doc_id] = result
    
    # Summary
    print("\n" + "="*60)
    print("STRUCTURING SUMMARY")
    print("="*60)
    
    total_objects = sum(r['statistics']['total_objects'] for r in all_results.values())
    total_relationships = sum(r['statistics']['total_relationships'] for r in all_results.values())
    
    print(f"Total documents: {len(all_results)}")
    print(f"Total objects: {total_objects}")
    print(f"Total relationships: {total_relationships}")
    print(f"All objects confidence: candidate")
    print()
    
    for doc_id, result in all_results.items():
        stats = result['statistics']
        print(f"{doc_id}:")
        print(f"  Objects: {stats['total_objects']}")
        print(f"  Relationships: {stats['total_relationships']}")
        print(f"  By type: {stats['objects_by_type']}")
    
    # Save overall summary
    output_dir = Path('data/test_corpus/g3_output')
    summary_file = output_dir / 'scientific_objects_summary.json'
    
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_documents': len(all_results),
        'total_objects': total_objects,
        'total_relationships': total_relationships,
        'all_confidence': 'candidate',
        'documents': {
            doc_id: {
                'statistics': r['statistics'],
                'output_file': f'data/test_corpus/g3_output/{doc_id}/scientific_objects.json'
            }
            for doc_id, r in all_results.items()
        }
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nSummary saved: {summary_file}")
    
    return all_results


if __name__ == '__main__':
    main()
