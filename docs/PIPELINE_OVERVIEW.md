# Pipeline Architecture Overview

> Version: 1.0.0  
> Last Updated: 2026-11-07

---

## Overview

The Catalyst Knowledge Expert Kit processes scientific literature through a **14-stage pipeline** organized as a directed acyclic graph (DAG). Each stage is implemented as a `StageAdapter` that consumes upstream outputs and produces structured data for downstream stages.

**Key Design Principles:**
- **Stage isolation**: Each stage can be run independently
- **Cache reuse**: Stages can skip if output already exists
- **Failure propagation**: Errors in one stage block dependent stages
- **Evidence tracking**: All data includes provenance and source anchors

---

## Pipeline Stages

```
┌─────────────────────────────────────────────────────────────┐
│                    INPUT: PDF Document                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: PDF Parse (MinerU)                                 │
│ - Extract text, figures, tables from PDF                    │
│ - Output: content_list.json, images/                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Document IR                                        │
│ - Build intermediate representation                         │
│ - Assign element IDs, track page numbers                    │
│ - Output: document_ir.json                                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Figure Parser                                      │
│ - Detect and extract figures                                │
│ - Generate captions, bounding boxes                         │
│ - Output: figure_parser.json                                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: VLM Figure Science                                 │
│ - Analyze figures with Qwen3-VL-32B                         │
│ - Extract scientific observations                           │
│ - Output: vlm_science_records.json                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: Table Parser                                       │
│ - Detect and extract tables                                 │
│ - Parse structure (headers, rows)                           │
│ - Output: table_parser.json                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 6: Table Science                                      │
│ - Convert table cells to science records                    │
│ - Add SourceAnchor, evidence_type                           │
│ - Output: table_science_records.json                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 7: Figure-Text Association                            │
│ - Link figures/tables to text mentions                      │
│ - Build association graph                                   │
│ - Output: figure_associations.json                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 8: Six-Dimension Extraction (V1 - DEPRECATED)         │
│ - Original extraction with hardcoded prompts                │
│ - 6000-char truncation                                      │
│ - Status: DISABLED                                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 9: Science Extraction V2                              │
│ - LLM-based 6-dimension extraction (DeepSeek-V3)            │
│ - Section-aware chunking                                    │
│ - Multi-chunk merging with deduplication                    │
│ - Output: {dimension}_v2_extracted.json (6 files)           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 10: Num-Unit Normalization                            │
│ - Normalize quantities to SI units                          │
│ - Validate physical plausibility                            │
│ - Output: quantity_records.json                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 11: Evidence Verification                             │
│ - Cross-validate extracted data against source              │
│ - Check source quotes, numeric values, origins              │
│ - Output: evidence_verification.json                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 12: Quality Gate                                      │
│ - Compute QA status (PASS/CONDITIONAL_PASS/PARTIAL/FAILED)  │
│ - Calculate EV coverage                                     │
│ - Output: quality_gate.json                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 13: Canonical Store                                   │
│ - Store all records in canonical format                     │
│ - Build knowledge graph                                     │
│ - Output: canonical_store/                                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 14: Report Generation                                 │
│ - Generate HTML report                                      │
│ - Embed images, VLM records, evidence                       │
│ - Output: {document_id}_knowledge_report_v3.html            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   OUTPUT: HTML Report                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Stage Details

### Stage 1: PDF Parse (MinerU)

**Purpose**: Extract raw content from PDF

**Input**: PDF file

**Output**:
- `content_list.json` — Structured text, figures, tables
- `images/` — Extracted figure images
- Metadata (page count, element count)

**Adapter**: `pdf_parse_adapter.py`

**Notes**:
- Requires MinerU installation (external tool)
- Not part of the Python pipeline
- Can be skipped if MinerU output already exists

---

### Stage 2: Document IR

**Purpose**: Build intermediate representation

**Input**: MinerU `content_list.json`

**Output**: `document_ir.json`

**Key Operations**:
- Assign unique element IDs (e.g., `F02_p3_b42`)
- Track page numbers and positions
- Classify elements (text, figure, table, formula)

**Adapter**: `document_ir_adapter.py`

---

### Stage 3: Figure Parser

**Purpose**: Detect and extract figures

**Input**: Document IR

**Output**: `figure_parser.json`

**Key Operations**:
- Identify figure elements
- Extract captions
- Generate bounding boxes
- Compute SHA256 hashes for image integrity

**Adapter**: `figure_parser_adapter.py`

**Output Schema**:
```json
{
  "figure_id": "F02_fig_01",
  "document_id": "F02",
  "namespace": "F02",
  "figure_number": 1,
  "caption": "FIGURE 1 XRD patterns of...",
  "page_idx": 2,
  "image_path": "path/to/image.jpg",
  "image_sha256": "abc123...",
  "bbox": [49, 376, 546, 498],
  "source_anchor": {...}
}
```

---

### Stage 4: VLM Figure Science

**Purpose**: Analyze figures with vision-language model

**Input**: Figure images + captions

**Output**: `vlm_science_records.json`

**Model**: `Qwen/Qwen3-VL-32B-Instruct` via SiliconFlow API

**Key Operations**:
- Send image + caption to VLM
- Extract scientific observations
- Classify evidence type (IMAGE_ONLY_OBSERVATION, TEXT_SUPPORTED_STATEMENT, MODEL_INFERENCE)
- Assign confidence levels (HIGH, MEDIUM, LOW)
- Generate SourceAnchor with bbox and image hash

**Adapter**: `vlm_figure_science_adapter.py`

**Output Schema**:
```json
{
  "record_id": "VLM-F02_fig_01-001",
  "figure_id": "F02_fig_01",
  "statement": "The XRD pattern shows...",
  "evidence_type": "IMAGE_ONLY_OBSERVATION",
  "confidence": "HIGH",
  "quality_state": "CANDIDATE",
  "source_anchor": {
    "page_idx": 2,
    "bbox": [49, 376, 546, 498],
    "image_sha256": "abc123..."
  }
}
```

**Cost**: ~$0.15 per figure (9 figures = ~$1.35)

---

### Stage 5: Table Parser

**Purpose**: Detect and extract tables

**Input**: Document IR

**Output**: `table_parser.json`

**Key Operations**:
- Identify table elements
- Extract captions
- Parse structure (headers, rows) — **if OCR enabled**
- Generate bounding boxes

**Adapter**: `table_parser_adapter.py`

**Current Limitation**: Table OCR not executed in baseline run (status: `OCR_PENDING`)

---

### Stage 6: Table Science

**Purpose**: Convert table cells to science records

**Input**: Table parser output

**Output**: `table_science_records.json`

**Key Operations**:
- Iterate over table cells
- Generate statements from cell content
- Add SourceAnchor with table bbox
- Classify evidence type (TEXT_SUPPORTED_STATEMENT)

**Adapter**: `table_science_adapter.py`

**Output Schema**:
```json
{
  "record_id": "TABLE-F02_table_01-R2C3",
  "table_id": "F02_table_01",
  "statement": "The surface area is 1380 m2/g",
  "evidence_type": "TEXT_SUPPORTED_STATEMENT",
  "row_idx": 2,
  "col_idx": 3,
  "unit": "m2/g",
  "source_anchor": {...}
}
```

---

### Stage 7: Figure-Text Association

**Purpose**: Link figures/tables to text mentions

**Input**: Figure parser, table parser, document IR

**Output**: `figure_associations.json`

**Key Operations**:
- Search text for figure/table references (e.g., "Figure 1", "Table 2")
- Build association graph
- Compute confidence scores

**Adapter**: `figure_text_adapter.py`

**Version**: 2.1.0 (FIX-003: depends on figure_parser and table_parser)

---

### Stage 8: Six-Dimension Extraction (V1) — DEPRECATED

**Status**: DISABLED

**Reason**: Replaced by Stage 9 (V2) with better chunking and merging

---

### Stage 9: Science Extraction V2

**Purpose**: Extract 6 dimensions of scientific knowledge from text

**Input**: Document text (section-aware chunks)

**Output**: 6 files: `{dimension}_v2_extracted.json`

**Model**: `deepseek-ai/DeepSeek-V3` via SiliconFlow API

**Key Operations**:
- Split document into section-aware chunks
- Extract each dimension with LLM
- Merge multi-chunk results with deduplication
- Track data origin (ORIGINAL_EXPERIMENT, LITERATURE_REFERENCE, etc.)
- Track status (REPORTED, NOT_REPORTED, NOT_EXTRACTED, UNRESOLVED)

**Adapter**: `science_extraction_v2_adapter.py`

**Six Dimensions**:
1. **catalyst_design** — Catalyst system, type, active component, support, synthesis, reaction type
2. **characterization** — Techniques, morphology, structure, properties
3. **performance** — Metrics, claims, benchmarks, conditions
4. **mechanism** — Pathway, rate-determining step, intermediates, active sites
5. **structure_activity** — Descriptors, relationships, evidence strength
6. **reliability** — Stability, cycles, reproducibility, deactivation

**Output Schema** (per dimension):
```json
{
  "dimension": "performance",
  "fields": {
    "key_metrics": {
      "value": [...],
      "status": "REPORTED",
      "origin": "ORIGINAL_EXPERIMENT",
      "source_quote": "..."
    },
    "key_claim": {
      "value": "...",
      "status": "REPORTED",
      "origin": "ORIGINAL_EXPERIMENT",
      "source_quote": "..."
    }
  },
  "validation_warnings": [],
  "merge_notes": "Merged from 3 chunks"
}
```

**Cost**: ~$0.50 per document

---

### Stage 10: Num-Unit Normalization

**Purpose**: Normalize quantities to SI units

**Input**: Science extraction output

**Output**: `quantity_records.json`

**Key Operations**:
- Parse numeric values and units
- Convert to SI units (e.g., kJ/mol → J/mol)
- Validate physical plausibility (using `audit_anchors.yaml`)
- Track conversion metadata

**Adapter**: `num_unit_adapter.py`

**Configuration**: `config/quantity_definitions.yaml`

**Output Schema**:
```json
{
  "record_id": "F02_qty_conversion_F02_104_0p8",
  "quantity_type": "conversion",
  "three_layer_values": {
    "raw": {"value": "0.8", "unit": "%"},
    "si": {"value": "0.008", "unit": "decimal"},
    "domain": {"value": "0.8", "unit": "%"}
  },
  "experimental_context": {...},
  "source_anchor": {...}
}
```

---

### Stage 11: Evidence Verification

**Purpose**: Cross-validate extracted data against source

**Input**: All extraction outputs

**Output**: `evidence_verification.json`

**Key Operations**:
- Verify source quotes match source text
- Check numeric values against source
- Detect origin contamination (literature in ORIGINAL_EXPERIMENT)
- Validate figure/table anchors
- Check cross-record consistency

**Adapter**: `evidence_verifier_adapter.py`

**Verification Checks**:

**Text Extraction:**
1. SOURCE_QUOTE_MATCH
2. SOURCE_QUOTE_PRESENT
3. NUMERIC_ZERO_CHECK
4. NUMERIC_SOURCE_MATCH
5. ORIGIN_CONTAMINATION
6. STATUS_VALUE_CONSISTENCY
7. FIGURE_DATA_CROSSREF
8. CROSS_DIMENSION_CONTRADICTION

**VLM Figures:**
1. SOURCE_ANCHOR_PRESENT
2. SOURCE_ANCHOR_BBOX_VALID
3. BODY_TEXT_CROSSREF
4. NUMERICAL_ANCHOR
5. IMAGE_INTEGRITY
6. CROSS_RECORD_CONSISTENCY

**Tables:**
1. TABLE_DOCUMENT_ID
2. TABLE_ROW_IDX / TABLE_COL_IDX
3. TABLE_HEADER_ASSOCIATION
4. TABLE_ANCHOR_ELEMENT_TYPE
5. TABLE_NUMERICAL_FIDELITY
6. TABLE_UNIT_FIDELITY

---

### Stage 12: Quality Gate

**Purpose**: Compute QA status and coverage

**Input**: Evidence verification, all extraction outputs

**Output**: `quality_gate.json`

**Key Operations**:
- Calculate EV coverage (% of records verified)
- Determine overall QA status
- Generate summary report

**Adapter**: `quality_gate_adapter.py`

**QA Status Logic**:
- **PASS**: All extractions valid, EV present with 100% coverage, no rejected records
- **CONDITIONAL_PASS**: All pass but EV explicitly disabled
- **PARTIAL**: EV coverage < 100%, or some extraction failures, or rejected records
- **FAILED**: No VLM+Table+extraction results, or EV missing entirely, or all extractions failed

**Version**: 2.0.0

---

### Stage 13: Canonical Store

**Purpose**: Store all records in canonical format

**Input**: All extraction outputs

**Output**: `canonical_store/` directory

**Key Operations**:
- Consolidate all records
- Build knowledge graph (objects + relationships)
- Generate unique IDs
- Track provenance

**Adapter**: `store_adapter.py`

**Output Structure**:
```
canonical_store/
├── knowledge_objects.json
├── knowledge_relationships.json
├── vlm_records.json
├── table_records.json
└── quantity_records.json
```

---

### Stage 14: Report Generation

**Purpose**: Generate interactive HTML report

**Input**: Canonical store, all extraction outputs

**Output**: `{document_id}_knowledge_report_v3.html`

**Key Operations**:
- Load all data sources
- Generate HTML with embedded images (base64)
- Create interactive navigation
- Format six-dimension tables
- Display VLM records (expandable)
- Show QA status and evidence

**Adapter**: `report_adapter.py` + `scripts/generate_html_knowledge_report_v3.py`

**Output Size**: ~2.77 MB (for F02 example)

---

## Pipeline Configuration

### Production Config

**File**: `config/pipeline_014_real_e2e_gate.yaml`

**Key Settings**:
```yaml
llm:
  api_key_env: "LLM_API_KEY"
  api_base_env: "LLM_API_BASE"
  model_env: "LLM_MODEL"
  default_model: "deepseek-ai/DeepSeek-V3"
  default_api_base: "https://api.siliconflow.cn/v1"
  temperature: 0.1
  max_tokens: 4096

stages:
  vlm_figure_science:
    enabled: true
    model_id: "Qwen/Qwen3-VL-32B-Instruct"
    timeout_seconds: 2000
  
  science_extraction_v2:
    enabled: true
    skip_if_output_exists: false
  
  evidence_verification:
    enabled: true
```

### Test Config

**File**: `config/pipeline_012_e2e_test.yaml`

**Key Differences**:
- VLM disabled (no API calls)
- Evidence verification disabled
- Uses cached outputs where possible

---

## Data Flow

### Input → Output

```
PDF → MinerU → content_list.json
                    ↓
              document_ir.json
                    ↓
         ┌──────────┴──────────┐
         ↓                     ↓
   figure_parser.json    table_parser.json
         ↓                     ↓
   vlm_science_records   table_science_records
         └──────────┬──────────┘
                    ↓
        figure_associations.json
                    ↓
        science_extraction_v2 (6 dimensions)
                    ↓
        quantity_records.json
                    ↓
        evidence_verification.json
                    ↓
        quality_gate.json
                    ↓
        canonical_store/
                    ↓
        HTML Report
```

### Record Types

1. **VLM Records** — Figure observations (141 for F02)
2. **Table Records** — Table cell data (0 for F02 baseline)
3. **Quantity Records** — Normalized quantities (19 for F02)
4. **Knowledge Objects** — Facts, claims, evidence, limitations (44 for F02)
5. **Knowledge Relationships** — Links between objects (22 for F02)

---

## Performance Characteristics

### F02 Example

| Metric | Value |
|--------|-------|
| Total processing time | ~55 minutes |
| API cost | ~$2.00 |
| HTML report size | 2.77 MB |
| VLM records | 141 |
| Table records | 0 (OCR not executed) |
| Quantity records | 19 |
| Knowledge objects | 44 |
| Knowledge relationships | 22 |
| QA status | CONDITIONAL PASS |

### Typical Paper (20 pages, 10 figures, 5 tables)

| Metric | Value |
|--------|-------|
| Processing time | 60-90 minutes |
| API cost | $2-3 |
| HTML report size | 3-5 MB |
| VLM records | 150-200 |
| Knowledge objects | 50-100 |

---

## Error Handling

### Stage Failure

If a stage fails:
1. Error is logged with full traceback
2. Dependent stages are blocked
3. Pipeline halts with non-zero exit code
4. Partial outputs are preserved for debugging

### Cache Invalidation

To force re-run of a stage:
1. Delete the stage's output directory
2. Set `skip_if_output_exists: false` in config
3. Re-run pipeline

### Evidence Verification Failures

If EV detects issues:
1. Warnings are logged
2. QA status downgraded to PARTIAL or FAILED
3. Report highlights problematic records
4. Human review required

---

## Extensibility

### Adding a New Stage

1. Create adapter in `src/catalyst_knowledge/pipeline/adapters/`
2. Register stage in `config/pipeline_014_real_e2e_gate.yaml`
3. Define input/output contract
4. Add tests in `tests/pipeline/`

### Adding a New Extraction Dimension

1. Update `config/prompts/science_extraction_v2.yaml`
2. Add dimension to `src/catalyst_knowledge/core/six_dimension_schema.py`
3. Update `science_extraction_v2_adapter.py` to handle new dimension
4. Add tests

### Supporting a New LLM Provider

1. Add provider to `src/catalyst_knowledge/core/llm_service.py`
2. Update `config/pipeline_014_real_e2e_gate.yaml` with provider settings
3. Test with F02 example

---

## Monitoring and Observability

### Logging

All stages log to console with timestamps:
```
2026-11-07 12:00:00 [INFO] Stage 9: Science Extraction V2 starting
2026-11-07 12:00:05 [INFO] Processing chunk 1/3
2026-11-07 12:00:15 [INFO] LLM call successful (finish_reason: stop)
2026-11-07 12:00:20 [INFO] Stage 9 complete (3 chunks merged)
```

### Metrics

Each stage reports:
- Processing time
- Input/output record counts
- API call counts and costs
- Error/warning counts

### Artifacts

All outputs are saved to `runs/{run_id}/`:
```
runs/real_e2e_gate_014/
├── document_ir/
├── figure_parser/
├── vlm_figure_science/
├── table_parser/
├── table_science/
├── extraction_v2/
├── evidence_verification/
├── quality_gate/
├── canonical_store/
└── reports/
```

---

## Security Considerations

### API Keys

- Never commit API keys to Git
- Use environment variables: `LLM_API_KEY`
- `.gitignore` excludes `.env` files

### Data Privacy

- PDFs are processed locally (except API calls to SiliconFlow)
- Extracted data is stored locally
- No data is sent to third parties except LLM/VLM APIs

### Model Safety

- LLM outputs are validated against schema
- Evidence verification catches hallucinations
- Human review required for scientific claims

---

## Future Work

### Planned Enhancements

1. **Automated PDF Input**
   - Integrate MinerU as Stage 1
   - Support arbitrary PDF upload

2. **Table OCR**
   - Enable MinerU `table_enable=True`
   - Parse table rows/columns

3. **Batch Processing**
   - Process multiple documents in parallel
   - Aggregate results across papers

4. **Interactive Review**
   - Web UI for expert review
   - Real-time correction of extractions

5. **Knowledge Graph Query**
   - SPARQL endpoint
   - Cross-paper reasoning

---

## References

- **MinerU**: https://github.com/opendatalab/MinerU
- **SiliconFlow**: https://siliconflow.cn
- **DeepSeek-V3**: https://api-docs.deepseek.com
- **Qwen3-VL**: https://qwenlm.github.io

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-11-07  
**Status**: ✅ Complete
