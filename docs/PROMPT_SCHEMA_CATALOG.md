# Prompt & Schema Catalog — Catalyst Knowledge Expert Kit v0.1

> Generated: 2026-11-07
> Source: D:\Knowledge_World (production run 014)
> Status: ENGINEERING BASELINE

## Overview

This catalog documents all Prompt, Schema, and Configuration files that control the scientific extraction behavior of the Catalyst Knowledge pipeline. It is intended for catalysis domain experts who need to understand or modify the extraction logic.

**Key Principle**: Framework code (src/**, scripts/**, tests/**) is NOT modifiable by domain experts. Only Prompt and Schema files marked as EDITABLE may be changed.

---

## 1. Six-Dimension Text Extraction

### 1.1 Prompt Template

| Property | Value |
|----------|-------|
| **File** | `config/prompts/science_extraction_v2.yaml` |
| **Size** | 19,589 bytes |
| **Purpose** | Config-driven prompt templates for LLM-based six-dimension extraction |
| **Schema Version** | 2.0.0 |
| **Pipeline Stage** | `science_extraction_v2` (Stage 9 of 14) |
| **Active?** | Yes (pipeline_014_real_e2e_gate.yaml) |
| **Editable?** | **YES** — Domain experts may refine extraction instructions |

**Six Dimensions Defined:**

1. **catalyst_design** (8 fields)
   - catalyst_system, catalyst_type, active_component, support
   - synthesis_method, synthesis_conditions, reaction_type, design_rationale

2. **characterization** (6 fields)
   - techniques_used (array), morphology, structure
   - electronic_properties, optical_properties, surface_properties

3. **performance** (5 fields)
   - key_metrics (array of {metric_name, value, unit, conditions, catalyst})
   - key_claim, benchmark_comparison (array), reaction_conditions, experiment_matrix (array)

4. **mechanism** (7 fields)
   - proposed_pathway, rate_determining_step, intermediates (array)
   - active_sites, role_of_light, computational_support, experimental_support (array)

5. **structure_activity** (5 fields)
   - descriptors (array of {descriptor_name, descriptor_values, correlated_property, correlation_type})
   - relationship_summary, evidence_strength, data_points_count, morphology_activity_link

6. **reliability** (6 fields)
   - time_on_stream, cycle_count, mass_transfer_verification
   - reproducibility, deactivation_mechanism, stability_summary

**Common Instructions (injected into ALL dimension prompts):**
- Data origin classification: ORIGINAL_EXPERIMENT, CONTROL_EXPERIMENT, LITERATURE_REFERENCE, THEORETICAL_CALCULATION, PATENT_EXAMPLE, SYSTEM_INFERRED, UNKNOWN_ORIGIN
- Missing data status: REPORTED, NOT_REPORTED, NOT_EXTRACTED, UNRESOLVED, NOT_APPLICABLE
- Specificity requirements: no generic descriptions, no zero for missing values
- Literature vs original work distinction
- Cross-chunk awareness for multi-section documents
- Source text quoting for traceability

**Extraction Control Parameters:**
```yaml
max_content_chars_per_chunk: 8000
max_retries: 2
temperature: 0.1
max_tokens: 4096
response_format: json_object
```

### 1.2 Schema (Python Pydantic Model)

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/core/six_dimension_schema.py` |
| **Size** | 17,884 bytes |
| **Purpose** | Pydantic v2 unified data model with cross-validation for six extraction dimensions |
| **Pipeline Stage** | `science_extraction_v2` (output validation) |
| **Active?** | Yes |
| **Editable?** | **NO** — Framework code |

**Key Features:**
- 6 cross-validation rules (CV-SYNTH-CHAR-001, CV-TYPE-CHAR-001, CV-PERF-REL-001, CV-MECH-CHAR-001, CV-SA-PERF-001, CV-REL-001)
- Completeness analysis
- Weighted reliability scoring
- HypothesisSet with Voc4Cat ontology tags

### 1.3 Adapter (Pipeline Stage)

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/science_extraction_v2_adapter.py` |
| **Size** | 29,814 bytes |
| **Purpose** | Section-aware, config-driven LLM extraction adapter with adaptive chunking, multi-chunk merging, deduplication, and token budget protection |
| **Pipeline Stage** | `science_extraction_v2` |
| **Active?** | Yes |
| **Editable?** | **NO** — Framework code |

### 1.4 Supporting Infrastructure

| File | Size | Purpose | Editable? |
|------|------|---------|-----------|
| `src/catalyst_knowledge/pipeline/prompt_loader.py` | 3,394 bytes | Loads prompt templates from YAML, renders with dimension-specific variables | **NO** |
| `src/catalyst_knowledge/pipeline/data_origin_classifier.py` | 7,652 bytes | DataOrigin/DataStatus enums, default value anchor checks, chunk merge logic | **NO** |
| `src/catalyst_knowledge/pipeline/section_aware_extractor.py` | 37,706 bytes | Section-aware content loading, adaptive chunking, token budget management | **NO** |

### 1.5 Deprecated V1 Adapter (Reference Only)

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/extraction_adapter.py` |
| **Size** | 12,941 bytes |
| **Purpose** | Original V1 six-dimension extraction with hardcoded prompts and 6000-char truncation |
| **Pipeline Stage** | `six_dimension_extraction` |
| **Active?** | **DISABLED** in all pipeline configs (marked v1_deprecated) |
| **Editable?** | **NO** — Deprecated, do not modify |

---

## 2. Figure VLM Science Extraction

### 2.1 Adapter (Pipeline Stage)

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/vlm_figure_science_adapter.py` |
| **Size** | 5,061 bytes |
| **Purpose** | Pipeline-stage wrapper for VLM figure science; loads VLM adapter module, calls VLM for each figure with optional body-text context, outputs structured science records |
| **Pipeline Stage** | `vlm_figure_science` (Stage 4 of 14) |
| **Active?** | Yes (pipeline_014_real_e2e_gate.yaml) |
| **Model** | `Qwen/Qwen3-VL-32B-Instruct` via SiliconFlow API |
| **Editable?** | **NO** — Framework code |

**Output Record Schema:**
```json
{
  "record_id": "string",
  "figure_id": "string",
  "document_id": "string",
  "namespace": "string",
  "round": "integer",
  "model_id": "string",
  "run_id": "string",
  "statement": "string",
  "evidence_type": "IMAGE_ONLY_OBSERVATION | TEXT_SUPPORTED_STATEMENT | MODEL_INFERENCE",
  "source_reference": "string",
  "confidence": "HIGH | MEDIUM | LOW",
  "quality_state": "CANDIDATE | VERIFIED | NEEDS_REVIEW | REJECTED",
  "image_region": {
    "panels": [],
    "axis_labels": [],
    "colors": [],
    "markers": []
  },
  "source_anchor": {
    "document_id": "string",
    "namespace": "string",
    "element_type": "figure",
    "page_idx": "integer",
    "page_number": "integer",
    "bbox": {"x0": 0, "y0": 0, "x1": 0, "y1": 0},
    "coordinate_system": "pixel",
    "page_size": {"width": 0, "height": 0},
    "image_file": {
      "path": "string",
      "filename": "string",
      "sha256": "string"
    },
    "anchor_version": "1.0.0"
  },
  "verification_status": "string",
  "uncertainty_note": "string",
  "timestamp": "ISO-8601",
  "adapter_version": "string"
}
```

### 2.2 Figure Schema (Proposed, Not in Production)

| Property | Value |
|----------|-------|
| **File** | `proposed_schemas/figure_schema_v1.yaml` |
| **Size** | 7,458 bytes |
| **Purpose** | Candidate schema for structured Figure records with panels, visual observations, axes, extraction status |
| **Status** | ENGINEERING_CANDIDATE / NOT_IMPLEMENTED |
| **Editable?** | **YES** — Proposed schema, open for refinement |

---

## 3. Table Parser / Table Science

### 3.1 Table Parser Adapter

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/table_parser_adapter.py` |
| **Size** | 2,172 bytes |
| **Purpose** | Wraps the TableParser into a pipeline stage; parses table images from MinerU output |
| **Pipeline Stage** | `table_parser` (Stage 5 of 14) |
| **Active?** | Yes (all pipeline configs) |
| **Editable?** | **NO** — Framework code |

### 3.2 Table Science Adapter

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/table_science_adapter.py` |
| **Size** | 6,845 bytes |
| **Purpose** | Converts TableParser cell data into structured science records with SourceAnchor, evidence_type, and quality_state |
| **Pipeline Stage** | `table_science` (Stage 6 of 14) |
| **Active?** | Yes (pipeline_012 and pipeline_014) |
| **Editable?** | **NO** — Framework code |

**Output Record Schema:**
```json
{
  "record_id": "TABLE-{table_id}-R{row}C{col}",
  "table_id": "string",
  "document_id": "string",
  "namespace": "string",
  "statement": "string",
  "evidence_type": "TEXT_SUPPORTED_STATEMENT",
  "quality_state": "CANDIDATE",
  "confidence": "HIGH | MEDIUM | LOW",
  "source_anchor": {
    "element_type": "table",
    "page_idx": "integer",
    "bbox": [0, 0, 0, 0],
    "image_sha256": "string"
  },
  "raw_text": "string",
  "header": "string",
  "row_idx": "integer",
  "col_idx": "integer",
  "unit": "string",
  "verification_status": "string"
}
```

### 3.3 Table Schema (Proposed, Not in Production)

| Property | Value |
|----------|-------|
| **File** | `proposed_schemas/table_schema_v1.yaml` |
| **Size** | 9,048 bytes |
| **Purpose** | Candidate schema for structured Table records with CellRecord, ColumnHeader, TableRowRecord; includes RapidTable integration rules |
| **Status** | ENGINEERING_CANDIDATE / NOT_IMPLEMENTED |
| **Editable?** | **YES** — Proposed schema, open for refinement |

---

## 4. Figure-Text Association

### 4.1 Adapter

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/figure_text_adapter.py` |
| **Size** | 7,531 bytes |
| **Purpose** | Associates figures/tables with their textual mentions in the paper body; integrates MinerU content_list with FigureParser and TableParser outputs |
| **Pipeline Stage** | `figure_text_association` (Stage 7 of 14) |
| **Active?** | Yes (all pipeline configs) |
| **Version** | 2.1.0 (FIX-003: depends on figure_parser and table_parser stages) |
| **Editable?** | **NO** — Framework code |

**Output:** `{document_id}_figure_associations.json` containing associations array, data_sources list, and parser integration flags.

---

## 5. Evidence Verification

### 5.1 Adapter

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/evidence_verifier_adapter.py` |
| **Size** | 72,044 bytes (largest adapter) |
| **Purpose** | Cross-validates extracted scientific data against source text; contains three verifier classes: EvidenceVerifier (text extraction), VLMRecordVerifier (figure VLM records), and TableRecordVerifier (table records) |
| **Pipeline Stage** | `evidence_verification` (Stage 11 of 14) |
| **Active?** | Yes (pipeline_014_real_e2e_gate.yaml) |
| **Editable?** | **NO** — Framework code |

**Verification Checks:**

**EvidenceVerifier (Text Extraction):**
1. SOURCE_QUOTE_MATCH — Quoted text found in source
2. SOURCE_QUOTE_PRESENT — REPORTED fields have quotes
3. NUMERIC_ZERO_CHECK — False zero detection
4. NUMERIC_SOURCE_MATCH — Numeric values verified in source
5. ORIGIN_CONTAMINATION — Literature keywords in ORIGINAL_EXPERIMENT
6. STATUS_VALUE_CONSISTENCY — Status/value coherence
7. FIGURE_DATA_CROSSREF — Figure caption numbers in text
8. CROSS_DIMENSION_CONTRADICTION — Conflicting values across chunks

**VLMRecordVerifier (Figure VLM):**
1. SOURCE_ANCHOR_PRESENT / SOURCE_ANCHOR_EXISTENCE
2. SOURCE_ANCHOR_BBOX_VALID
3. BODY_TEXT_CROSSREF (phrases/fragments)
4. NUMERICAL_ANCHOR
5. IMAGE_INTEGRITY (sha256 verification)
6. CROSS_RECORD_CONSISTENCY

**TableRecordVerifier (Table Science):**
1. TABLE_DOCUMENT_ID / TABLE_ID_PRESENT
2. TABLE_ROW_IDX / TABLE_COL_IDX
3. TABLE_HEADER_ASSOCIATION
4. TABLE_ANCHOR_ELEMENT_TYPE / TABLE_ANCHOR_PAGE / TABLE_ANCHOR_BBOX_VALID
5. TABLE_NUMERICAL_FIDELITY / TABLE_UNIT_FIDELITY

### 5.2 Evidence Context Schema (Proposed, Not in Production)

| Property | Value |
|----------|-------|
| **File** | `proposed_schemas/evidence_context_schema_v1.yaml` |
| **Size** | 8,485 bytes |
| **Purpose** | Extended evidence model binding evidence to claims with polarity (SUPPORTS/CONTRADICTS/QUALIFIES/NEUTRAL), dual assessment (confidence vs evidence_strength), and anti-pattern rules |
| **Status** | ENGINEERING_CANDIDATE / NOT_IMPLEMENTED |
| **Editable?** | **YES** — Proposed schema, open for refinement |

---

## 6. Quality Assurance (QA)

### 6.1 Quality Gate Adapter

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/pipeline/adapters/quality_gate_adapter.py` |
| **Size** | 20,313 bytes |
| **Purpose** | Unified QA gate consuming VLM figure records, table science records, evidence verification results, and extraction outputs; computes EV coverage and determines overall QA status |
| **Pipeline Stage** | `quality_gate` (Stage 12 of 14) |
| **Active?** | Yes (all pipeline configs) |
| **Version** | 2.0.0 |
| **Editable?** | **NO** — Framework code |

**QA Status Logic:**
- **PASS**: All extractions valid, EV present with 100% coverage, no rejected records
- **CONDITIONAL_PASS**: All pass but EV explicitly disabled in config
- **PARTIAL**: EV coverage < 100%, or some extraction failures, or rejected records
- **FAILED**: No VLM+Table+extraction results, or EV missing entirely (when enabled), or all extractions failed

**Dependencies:** six_dimension_extraction, science_extraction_v2, num_unit_normalization, vlm_figure_science, table_science, evidence_verification

---

## 7. Pipeline Configuration Files

### 7.1 Base Pipeline Config

| Property | Value |
|----------|-------|
| **File** | `config/pipeline.yaml` |
| **Size** | 4,900 bytes |
| **Purpose** | Default pipeline configuration defining all 14 stages, paths, LLM settings (deepseek-chat), and execution parameters |
| **Pipeline Version** | 1.0.0 |
| **Schema Version** | 1.0.0 (SINGLE-DOC-V11-007-R1) |
| **Active?** | Base reference; not directly used for production runs |
| **Editable?** | **NO** — Framework config |

### 7.2 Test Pipeline Config (012)

| Property | Value |
|----------|-------|
| **File** | `config/pipeline_012_e2e_test.yaml` |
| **Size** | 4,012 bytes |
| **Purpose** | Mock/engineering E2E test config; enables science_extraction_v2 and table_science; disables VLM and evidence verification (no paid LLM) |
| **Active?** | Engineering testing only |
| **Editable?** | **NO** — Framework config |

### 7.3 Production Pipeline Config (014)

| Property | Value |
|----------|-------|
| **File** | `config/pipeline_014_real_e2e_gate.yaml` |
| **Size** | 4,915 bytes |
| **Purpose** | **Current production config** for real LLM E2E runs; ALL stages enabled; uses SiliconFlow API (DeepSeek-V3 for text, Qwen3-VL-32B for vision); requires PI authorization |
| **Active?** | **Yes — this is the production config** |
| **Editable?** | **NO** — Framework config (requires PI approval to modify) |

**Stage Enablement in pipeline_014:**

| Stage | Enabled | skip_if_output_exists | Notes |
|-------|---------|----------------------|-------|
| pdf_parse | true | true | Reuse from 012 |
| document_ir | true | true | Reuse from 012 |
| figure_parser | true | true | Reuse from 012 |
| vlm_figure_science | **true** | true | Qwen3-VL-32B-Instruct via SiliconFlow |
| table_parser | true | true | Reuse from 012 |
| table_science | **true** | true | Reuse from 012 |
| figure_text_association | true | true | Reuse from 012 |
| six_dimension_extraction (V1) | **false** | — | Deprecated |
| science_extraction_v2 | **true** | false | Force re-run with real LLM |
| num_unit_normalization | true | false | Re-run after new extraction |
| evidence_verification | **true** | false | Real verification |
| quality_gate | true | false | |
| canonical_store | true | false | |
| report_generation | true | false | |

---

## 8. Core Schema Definitions

### 8.1 Catalysis Schema V1

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/schema/catalysis_schema_v1.py` |
| **Size** | 20,226 bytes |
| **Purpose** | Core data contract defining 18 Pydantic models: DataStatus enum, SourceAnchor, ValueWithSource, Document, DocumentElement, Attachment, TaxonomyAssignment, OntologyMapping, ChemicalEntity, CatalystSample, Reaction, Experiment, Observation, Assertion, Evidence, PatentClaim, PatentExample, SchemaMetadata |
| **Schema Version** | 1.0.0 (SCHEMA_VERSION) |
| **Active?** | Yes — used by all pipeline stages for data contracts |
| **Editable?** | **NO** — Framework code |

### 8.2 Catalysis Schema V1 Extensions

| Property | Value |
|----------|-------|
| **File** | `src/catalyst_knowledge/schema/catalysis_schema_v1_extensions.py` |
| **Size** | 13,380 bytes |
| **Purpose** | Single-paper knowledge extensions: adds Limitation, OpenQuestion, Feasibility, ValidationPlan models plus extended versions of Assertion, Evidence, Observation, Experiment; all backward-compatible (Optional fields) |
| **Active?** | Yes — used for meta-science modeling |
| **Editable?** | **NO** — Framework code |

---

## 9. Supporting Configuration Files

### 9.1 Audit Anchors

| Property | Value |
|----------|-------|
| **File** | `config/audit_anchors.yaml` |
| **Size** | 2,538 bytes |
| **Purpose** | Physical plausibility ranges for 17 catalysis quantities (activation_energy, adsorption_energy, reaction_temperature, TOF, faradaic_efficiency, selectivity, conversion, current_density, overpotential, binding_energy, particle_size, surface_area, pore_size, stability_hours, yield, space_time_yield) used by ClaimValidator to flag suspicious values |
| **Pipeline Stage** | Referenced by `num_unit_normalization` and `quality_gate` |
| **Active?** | Yes |
| **Editable?** | **YES** — Domain experts may refine plausibility ranges |

### 9.2 Quantity Definitions (NUM-UNIT-001)

| Property | Value |
|----------|-------|
| **File** | `config/quantity_definitions.yaml` |
| **Size** | 27,398 bytes |
| **Purpose** | Comprehensive quantity registry defining 17 quantity types (temperature, pressure, time, TOS, specific_surface_area, conversion, selectivity, yield, current_density, overpotential, activation_energy, TOF, TON, reaction_rate, catalytic_activity, concentration, mass, volumetric_flow_rate) with SI units, domain units, conversion formulas, validation rules, and QA checks |
| **Version** | 1.0 (engineering_candidate) |
| **Pipeline Stage** | `num_unit_normalization` (Stage 10 of 14) |
| **Active?** | Yes |
| **Editable?** | **YES** — Domain experts may add new quantity types or refine conversion rules |

---

## 10. Proposed Schemas (Candidate / Not in Production)

| File | Size | Purpose | Status | Editable? |
|------|------|---------|--------|-----------|
| `proposed_schemas/figure_schema_v1.yaml` | 7,458 bytes | Structured Figure records with panels, visual observations, axes | ENGINEERING_CANDIDATE | **YES** |
| `proposed_schemas/table_schema_v1.yaml` | 9,048 bytes | Structured Table records with CellRecord, ColumnHeader, TableRowRecord; RapidTable integration | ENGINEERING_CANDIDATE | **YES** |
| `proposed_schemas/evidence_context_schema_v1.yaml` | 8,485 bytes | Extended evidence model with polarity, dual assessment, anti-pattern rules | ENGINEERING_CANDIDATE | **YES** |
| `proposed_schemas/catalysis_knowledge_theme_registry_v1.yaml` | 11,583 bytes | Theme registry for knowledge organization | Reference | **YES** |
| `proposed_schemas/catalysis_node_registry_v1.yaml` | 28,213 bytes | Node registry for knowledge graph construction | Reference | **YES** |
| `proposed_schemas/catalysis_relationship_registry_v1.yaml` | 21,156 bytes | Relationship registry for knowledge graph edges | Reference | **YES** |

---

## 11. Active Production Path

```
pipeline.yaml (base) --> pipeline_014_real_e2e_gate.yaml (production override)
                              |
                              v
science_extraction_v2.yaml (prompt) --> prompt_loader.py --> science_extraction_v2_adapter.py
                                                                        |
                                                                        v
                                                          six_dimension_schema.py (validation)
                                                                        |
                                                          data_origin_classifier.py (normalization)
                                                          section_aware_extractor.py (chunking)
                                                                        |
                                                                        v
                                              evidence_verifier_adapter.py --> quality_gate_adapter.py
                                              vlm_figure_science_adapter.py
                                              table_science_adapter.py
                                              figure_text_adapter.py
                                                                        |
                                                                        v
                                              catalysis_schema_v1.py + extensions.py (data contracts)
```

---

## 12. Summary Statistics

| Category | Count | Total Size |
|----------|-------|------------|
| Prompt YAML files | 1 | 19,589 bytes |
| Pipeline YAML configs | 3 | 13,827 bytes |
| Supporting YAML configs | 2 | 29,936 bytes |
| Python schema files | 3 | 51,610 bytes |
| Python adapter files | 17 | ~246,000 bytes |
| Python pipeline infrastructure | 5+ | ~70,000 bytes |
| Proposed schema YAML files | 6 | 85,943 bytes |
| **Grand Total** | **37+ files** | **~517 KB** |

---

## 13. Editable vs Non-Editable Summary

### EDITABLE by Domain Experts

| File | What Can Be Changed |
|------|---------------------|
| `config/prompts/science_extraction_v2.yaml` | Refine extraction instructions, add domain-specific guidance, adjust common instructions |
| `config/audit_anchors.yaml` | Adjust physical plausibility ranges for catalysis quantities |
| `config/quantity_definitions.yaml` | Add new quantity types, refine conversion formulas, update validation rules |
| `proposed_schemas/*.yaml` | All proposed schemas are open for refinement |

### NOT EDITABLE (Framework Code)

| Directory/File | Reason |
|----------------|--------|
| `src/**` | Core framework code — requires engineering team to modify |
| `scripts/**` | Pipeline execution scripts — framework integrity |
| `tests/**` | Test suite — validates framework behavior |
| `config/pipeline*.yaml` | Pipeline configuration — controls execution flow |
| HTML report generator | Report rendering logic — framework component |

**Framework Bug Reporting**: If you discover a bug in non-editable files, please submit a GitHub Issue with the label `framework-bug`. Do NOT attempt to modify these files directly.

---

## 14. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-11-07 | Initial catalog based on D:\Knowledge_World production run 014 |

---

**Document Status**: COMPLETE
**Next Review**: After first domain expert feedback cycle
