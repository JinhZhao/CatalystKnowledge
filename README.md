# Catalyst Knowledge Expert Kit

**Version**: 0.1.0  
**Release Date**: 2026-11-07  
**Status**: Engineering Baseline — Expert Trial

---

## Overview

The Catalyst Knowledge Expert Kit is an automated pipeline for extracting structured scientific knowledge from catalysis research literature. It combines LLM-based text extraction, vision-language model (VLM) figure analysis, and rigorous evidence verification to produce machine-readable knowledge graphs from scientific papers.

**Key Capabilities:**
- Extract 6 dimensions of scientific knowledge from paper text (catalyst design, characterization, performance, mechanism, structure-activity, reliability)
- Analyze figures using VLM (Qwen3-VL-32B) to extract scientific observations
- Parse tables and associate figures/tables with textual mentions
- Verify all extracted data against source text with evidence tracking
- Generate interactive HTML reports for expert review
- Build knowledge graphs with provenance tracking

**Current Status:**
- ✅ Framework validated on F02 (Cu/BN photothermal catalysis paper)
- ✅ 141 VLM figure records extracted and verified
- ✅ 6-dimension text extraction operational
- ⚠️ Table OCR not executed in baseline run (detected but not parsed)
- ⚠️ Arbitrary PDF input requires manual MinerU pre-processing

---

## For Domain Experts (Catalysis Researchers)

### What You Can Do

1. **Refine Extraction Prompts**
   - Modify `config/prompts/science_extraction_v2.yaml` to improve how scientific content is extracted
   - Add domain-specific guidance for catalyst terminology, reaction conditions, etc.
   - Adjust the six extraction dimensions to better match your research area

2. **Adjust Physical Plausibility Checks**
   - Edit `config/audit_anchors.yaml` to update realistic ranges for catalysis quantities
   - Add new quantity types relevant to your domain

3. **Extend Quantity Definitions**
   - Modify `config/quantity_definitions.yaml` to add new unit conversions or validation rules
   - Define domain-specific quantities not in the baseline

4. **Propose Schema Extensions**
   - Refine proposed schemas in `proposed_schemas/` for figures, tables, and evidence
   - These are candidates for future production use

5. **Review HTML Reports**
   - Open `examples/F02/F02_knowledge_report_v3.html` to see extracted knowledge
   - Verify scientific accuracy of extracted data
   - Report discrepancies via GitHub Issues

### What You Cannot Modify

The following are **framework code** and must not be modified by domain experts:
- `src/**` — Core pipeline logic, adapters, schema validation
- `scripts/**` — Pipeline execution scripts (except HTML generator)
- `tests/**` — Test suite
- `config/pipeline*.yaml` — Pipeline configuration and DAG
- HTML report generator logic

**If you discover a bug in framework code**, please submit a GitHub Issue with the label `framework-bug`. Do NOT attempt to modify these files directly.

---

## Quick Start

### Prerequisites

- Python 3.11+
- SiliconFlow API key (for LLM and VLM access)
- MinerU installed separately (for PDF pre-processing)

### Installation

```bash
# Clone the repository
git clone https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit.git
cd Catalyst-Knowledge-Expert-Kit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up API credentials
export LLM_API_KEY="your-siliconflow-api-key"
export LLM_API_BASE="https://api.siliconflow.cn/v1"
export LLM_MODEL="deepseek-ai/DeepSeek-V3"
```

### Running the Pipeline

**Note**: The current pipeline requires MinerU pre-processing. Arbitrary PDF input is not fully automated.

#### Option 1: Use F02 Example (Already Processed)

The F02 example is pre-processed and ready for demonstration:

```bash
# Generate HTML report from existing F02 data
python scripts/generate_html_knowledge_report_v3.py

# Open the report
# On Windows: start examples/F02/F02_knowledge_report_v3.html
# On Mac/Linux: open examples/F02/F02_knowledge_report_v3.html
```

#### Option 2: Process a New PDF (Requires MinerU)

```bash
# Step 1: Pre-process PDF with MinerU (external tool)
# See docs/LOCAL_TESTING_GUIDE.md for MinerU setup

# Step 2: Run the pipeline
python scripts/run_pipeline.py \
  --config config/pipeline_014_real_e2e_gate.yaml \
  --document-id YOUR_DOC_ID \
  --mineru-output path/to/mineru/output

# Step 3: Generate HTML report
python scripts/generate_html_knowledge_report_v3.py
```

---

## Project Structure

```
Catalyst-Knowledge-Expert-Kit/
├── src/                          # Core framework (DO NOT MODIFY)
│   └── catalyst_knowledge/
│       ├── core/                 # Schema definitions
│       ├── pipeline/             # Pipeline orchestration
│       │   └── adapters/         # Stage adapters
│       └── schema/               # Data contracts
├── config/                       # Configuration files
│   ├── prompts/                  # LLM prompts (EDITABLE)
│   │   └── science_extraction_v2.yaml
│   ├── pipeline*.yaml            # Pipeline configs (DO NOT MODIFY)
│   ├── audit_anchors.yaml        # Plausibility ranges (EDITABLE)
│   └── quantity_definitions.yaml # Unit conversions (EDITABLE)
├── scripts/                      # Execution scripts (DO NOT MODIFY)
├── tests/                        # Test suite (DO NOT MODIFY)
├── proposed_schemas/             # Candidate schemas (EDITABLE)
├── docs/                         # Documentation
│   ├── PROMPT_SCHEMA_CATALOG.md  # Complete prompt/schema inventory
│   ├── LOCAL_TESTING_GUIDE.md    # How to run locally
│   └── PIPELINE_OVERVIEW.md      # Pipeline architecture
├── examples/                     # Example outputs
│   └── F02/                      # F02 paper example
│       └── F02_knowledge_report_v3.html
├── requirements.txt              # Python dependencies
├── FRAMEWORK_BASELINE_MANIFEST.json  # Baseline state
└── README.md                     # This file
```

---

## Pipeline Architecture

The pipeline consists of **14 stages** organized as a directed acyclic graph (DAG):

1. **pdf_parse** — MinerU PDF parsing (pre-processing)
2. **document_ir** — Document intermediate representation
3. **figure_parser** — Figure detection and extraction
4. **vlm_figure_science** — VLM-based figure analysis (Qwen3-VL-32B)
5. **table_parser** — Table detection and extraction
6. **table_science** — Table science record generation
7. **figure_text_association** — Link figures/tables to text mentions
8. **six_dimension_extraction** — (Deprecated V1)
9. **science_extraction_v2** — LLM-based 6-dimension text extraction (DeepSeek-V3)
10. **num_unit_normalization** — Quantity and unit normalization
11. **evidence_verification** — Cross-validate extracted data against source
12. **quality_gate** — Compute QA status and coverage
13. **canonical_store** — Store all records in canonical format
14. **report_generation** — Generate HTML report

**Production Config**: `config/pipeline_014_real_e2e_gate.yaml`

See `docs/PIPELINE_OVERVIEW.md` for detailed architecture.

---

## Six Extraction Dimensions

The pipeline extracts scientific knowledge across 6 dimensions:

1. **Catalyst Design** — Catalyst system, type, active component, support, synthesis method, reaction type, design rationale
2. **Characterization** — Techniques used (XRD, BET, TEM, XPS, etc.), morphology, structure, electronic/optical/surface properties
3. **Performance** — Key metrics (conversion, selectivity, yield), key claims, benchmark comparisons, reaction conditions
4. **Mechanism** — Proposed pathway, rate-determining step, intermediates, active sites, role of light, computational/experimental support
5. **Structure-Activity** — Descriptors, relationship summary, evidence strength, data points, morphology-activity link
6. **Reliability** — Time on stream, cycle count, mass transfer verification, reproducibility, deactivation mechanism, stability summary

Each dimension is extracted with:
- **Data origin** classification (ORIGINAL_EXPERIMENT, LITERATURE_REFERENCE, SYSTEM_INFERRED, etc.)
- **Status** tracking (REPORTED, NOT_REPORTED, NOT_EXTRACTED, UNRESOLVED)
- **Source quotes** for traceability
- **Evidence verification** against source text

See `docs/PROMPT_SCHEMA_CATALOG.md` for complete schema details.

---

## Evidence Verification

All extracted data undergoes rigorous verification:

**Text Extraction Checks:**
- SOURCE_QUOTE_MATCH — Quoted text found in source
- NUMERIC_SOURCE_MATCH — Numeric values verified in source
- ORIGIN_CONTAMINATION — Literature keywords in ORIGINAL_EXPERIMENT
- CROSS_DIMENSION_CONTRADICTION — Conflicting values across chunks

**VLM Figure Checks:**
- SOURCE_ANCHOR_EXISTENCE — Figure anchor present
- IMAGE_INTEGRITY — SHA256 verification of source images
- BODY_TEXT_CROSSREF — Phrases found in paper text
- NUMERICAL_ANCHOR — Numeric values verified

**Table Checks:**
- TABLE_NUMERICAL_FIDELITY — Numeric values match source
- TABLE_UNIT_FIDELITY — Units consistent with source

**QA Status:**
- PASS — All checks pass, 100% EV coverage
- CONDITIONAL_PASS — All pass but EV disabled
- PARTIAL — Some failures or <100% coverage
- FAILED — Critical failures

---

## Example Output: F02 Paper

The `examples/F02/` directory contains a complete example from a real catalysis paper:

**Paper**: "Photothermal oxidative dehydrogenation of propane to propylene over Cu/BN catalysts"  
**DOI**: 10.3389/fchem.2024.1439185

**Extracted Data:**
- 9 figures analyzed with VLM → 141 scientific observations
- 2 tables detected (OCR not executed in baseline)
- 6-dimension text extraction complete
- 44 knowledge objects (facts, claims, evidence, limitations, hypotheses)
- 22 knowledge relationships
- QA status: CONDITIONAL PASS (table OCR gap)

**Interactive Report**: `examples/F02/F02_knowledge_report_v3.html`
- Left sidebar navigation
- 9 embedded figure images (base64, offline-viewable)
- 141 expandable VLM records
- 6-dimension tables with status/origin badges
- Evidence provenance tracking

---

## Contributing

### For Domain Experts

1. **Prompt Refinement**: Edit `config/prompts/science_extraction_v2.yaml`
2. **Plausibility Ranges**: Edit `config/audit_anchors.yaml`
3. **Quantity Definitions**: Edit `config/quantity_definitions.yaml`
4. **Schema Proposals**: Edit files in `proposed_schemas/`

**Workflow:**
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improve-extraction-prompt`)
3. Make your changes
4. Test locally (see `docs/LOCAL_TESTING_GUIDE.md`)
5. Submit a pull request

### For Framework Engineers

Framework code (`src/`, `scripts/`, `tests/`, `config/pipeline*.yaml`) is managed by the engineering team. Domain experts should submit GitHub Issues for framework bugs rather than attempting direct modifications.

See `CONTRIBUTING.md` for detailed guidelines.

---

## Testing

### Run Test Suite

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/catalyst_knowledge

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/pipeline/
```

### Validate Framework Integrity

```bash
# Check that all key files are present
python -c "import json; m=json.load(open('FRAMEWORK_BASELINE_MANIFEST.json')); print(f'Components: {len(m[\"framework_components\"])}')"

# Verify prompt loading
python -c "from src.catalyst_knowledge.pipeline.prompt_loader import load_prompt_config; cfg=load_prompt_config(); print(f'Prompt version: {cfg.prompt_version}')"
```

See `docs/LOCAL_TESTING_GUIDE.md` for comprehensive testing procedures.

---

## Known Limitations

### 1. Table OCR Not Executed

**Status**: Tables are detected but not parsed into structured rows/columns.

**Affected**: F02_table_01, F02_table_02

**Workaround**: Use historical 004-B table recognition results if needed (not integrated into 014 pipeline).

**Future Work**: Enable MinerU `table_enable=True` parameter and re-run pipeline.

### 2. Arbitrary PDF Input Requires Manual Pre-processing

**Status**: Pipeline requires MinerU output as input. Arbitrary PDF → MinerU → Pipeline is not fully automated.

**Workaround**: Manually run MinerU on PDF before pipeline execution.

**Future Work**: Integrate MinerU as Stage 1 of pipeline with automatic PDF detection.

### 3. SiliconFlow API Dependency

**Status**: Pipeline requires SiliconFlow API key for LLM (DeepSeek-V3) and VLM (Qwen3-VL-32B).

**Workaround**: None — API access is required.

**Note**: API costs apply. F02 example uses ~$2 in API calls.

---

## Documentation

- **[PROMPT_SCHEMA_CATALOG.md](docs/PROMPT_SCHEMA_CATALOG.md)** — Complete inventory of all prompts, schemas, and configs
- **[LOCAL_TESTING_GUIDE.md](docs/LOCAL_TESTING_GUIDE.md)** — How to set up and test locally
- **[PIPELINE_OVERVIEW.md](docs/PIPELINE_OVERVIEW.md)** — Detailed pipeline architecture
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Contribution guidelines
- **[AGENTS.md](AGENTS.md)** — AI agent collaboration protocol

---

## Citation

If you use this toolkit in your research, please cite:

```bibtex
@software{catalyst_knowledge_expert_kit_2026,
  title = {Catalyst Knowledge Expert Kit: Automated Scientific Knowledge Extraction from Catalysis Literature},
  author = {Zhao, Jinhui},
  year = {2026},
  version = {0.1.0},
  url = {https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit}
}
```

---

## License

This project is licensed under the MIT License — see the LICENSE file for details.

---

## Contact

- **Project Lead**: Jinhui Zhao
- **Repository**: https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit
- **Issues**: https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit/issues

---

## Acknowledgments

- **MinerU** — PDF parsing and document structure extraction
- **SiliconFlow** — LLM and VLM API services (DeepSeek-V3, Qwen3-VL-32B)
- **F02 Paper Authors** — "Photothermal oxidative dehydrogenation of propane to propylene over Cu/BN catalysts" (Frontiers in Chemistry, 2024)

---

**Last Updated**: 2026-11-07  
**Status**: ✅ Engineering Baseline Complete — Ready for Expert Trial
