# Local Testing Guide

> Version: 1.0.0  
> Last Updated: 2026-11-07

---

## Overview

This guide explains how to set up and test the Catalyst Knowledge Expert Kit locally. It covers:

1. Environment setup
2. Running the F02 example
3. Processing a new PDF
4. Validating changes
5. Troubleshooting

---

## Prerequisites

### Required Software

- **Python 3.11+**
  ```bash
  python --version  # Should show 3.11.x or higher
  ```

- **Git**
  ```bash
  git --version
  ```

- **MinerU** (for PDF pre-processing)
  - Install separately: https://github.com/opendatalab/MinerU
  - Note: MinerU is a large installation with model weights

### Required Accounts

- **SiliconFlow API Key**
  - Sign up at: https://siliconflow.cn
  - Get API key from dashboard
  - Models used:
    - Text: `deepseek-ai/DeepSeek-V3`
    - Vision: `Qwen/Qwen3-VL-32B-Instruct`

---

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit.git
cd Catalyst-Knowledge-Expert-Kit
```

### Step 2: Create Virtual Environment

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Set Environment Variables

**On Windows (PowerShell):**
```powershell
$env:LLM_API_KEY="your-siliconflow-api-key"
$env:LLM_API_BASE="https://api.siliconflow.cn/v1"
$env:LLM_MODEL="deepseek-ai/DeepSeek-V3"
```

**On Windows (Command Prompt):**
```cmd
set LLM_API_KEY=your-siliconflow-api-key
set LLM_API_BASE=https://api.siliconflow.cn/v1
set LLM_MODEL=deepseek-ai/DeepSeek-V3
```

**On macOS/Linux:**
```bash
export LLM_API_KEY="your-siliconflow-api-key"
export LLM_API_BASE="https://api.siliconflow.cn/v1"
export LLM_MODEL="deepseek-ai/DeepSeek-V3"
```

### Step 5: Verify Installation

```bash
# Check that all dependencies are installed
python -c "import pydantic, yaml, openai, requests; print('Dependencies OK')"

# Check that src is importable
python -c "import sys; sys.path.insert(0, 'src'); from catalyst_knowledge.pipeline.prompt_loader import load_prompt_config; print('Import OK')"
```

---

## Running the F02 Example

The F02 example is pre-processed and ready for demonstration. This is the fastest way to see the system in action.

### Step 1: Generate HTML Report

```bash
python scripts/generate_html_knowledge_report_v3.py
```

Expected output:
```
[INFO] Loading data sources...
[INFO] Generating HTML...
[INFO] Writing to examples/F02/F02_knowledge_report_v3.html
[INFO] [DONE] Generated F02_knowledge_report_v3.html (2774209 bytes)
```

### Step 2: Open the Report

**On Windows:**
```bash
start examples/F02/F02_knowledge_report_v3.html
```

**On macOS:**
```bash
open examples/F02/F02_knowledge_report_v3.html
```

**On Linux:**
```bash
xdg-open examples/F02/F02_knowledge_report_v3.html
```

### Step 3: Explore the Report

The HTML report contains:
- **Left sidebar**: Navigation to 7 main sections
- **Literature Overview**: Title, DOI, catalyst system, reaction type
- **Six Dimensions**: Tables showing extracted data with status/origin badges
- **Figure Gallery**: 9 embedded images with 141 VLM records (expandable)
- **Table Explorer**: 2 tables (note: OCR not executed in baseline)
- **QA Verification**: 22 checks (13 PASS, 2 FAIL, 5 WARN)
- **Knowledge Objects**: 44 objects, 22 relationships
- **Evidence & Provenance**: Source tracking and distribution

### Expected Results

| Metric | Value |
|--------|-------|
| File size | ~2.77 MB |
| Embedded images | 9/9 |
| VLM records | 141/141 |
| Dimensions | 6/6 |
| Knowledge objects | 44 |
| Knowledge relationships | 22 |
| QA status | CONDITIONAL PASS |

---

## Processing a New PDF

**Note**: This requires MinerU pre-processing and is not fully automated.

### Step 1: Pre-process PDF with MinerU

```bash
# Install MinerU (if not already installed)
# See: https://github.com/opendatalab/MinerU

# Run MinerU on your PDF
mineru parse --input your_paper.pdf --output mineru_output/
```

### Step 2: Run the Pipeline

```bash
python scripts/run_pipeline.py \
  --config config/pipeline_014_real_e2e_gate.yaml \
  --document-id YOUR_DOC_ID \
  --mineru-output mineru_output/
```

**Warning**: This will make API calls to SiliconFlow and incur costs (~$2 for a typical paper).

### Step 3: Generate HTML Report

```bash
python scripts/generate_html_knowledge_report_v3.py
```

### Step 4: Open the Report

```bash
# On Windows
start runs/YOUR_RUN_ID/reports/YOUR_DOC_ID_knowledge_report_v3.html
```

### Current Limitations

1. **MinerU is required**: The pipeline cannot directly process arbitrary PDFs
2. **API costs**: Each run costs ~$2 in SiliconFlow API calls
3. **Table OCR**: Not executed by default (requires `table_enable=True` in MinerU)
4. **No batch processing**: One document at a time

---

## Validating Changes

### If You Modified Prompts

**Step 1: Syntax Validation**
```bash
python -c "import yaml; yaml.safe_load(open('config/prompts/science_extraction_v2.yaml'))"
echo "Syntax OK"
```

**Step 2: Run Test Suite**
```bash
pytest tests/ -v
```

**Step 3: Re-run F02 Extraction**
```bash
# Clear cache to force re-extraction
rm -rf runs/real_e2e_gate_014/extraction_v2/F02/

# Re-run pipeline
python scripts/run_pipeline.py \
  --config config/pipeline_014_real_e2e_gate.yaml \
  --document-id F02

# Regenerate HTML
python scripts/generate_html_knowledge_report_v3.py
```

**Step 4: Compare Before/After**
- Open the HTML report
- Check the six dimension tables
- Verify that extraction quality improved
- Look for any regressions

### If You Modified Audit Anchors

**Step 1: Syntax Validation**
```bash
python -c "import yaml; yaml.safe_load(open('config/audit_anchors.yaml'))"
echo "Syntax OK"
```

**Step 2: Run Test Suite**
```bash
pytest tests/ -v
```

**Step 3: Check Quantity Normalization**
```bash
# Re-run num_unit_normalization stage
python scripts/run_pipeline.py \
  --config config/pipeline_014_real_e2e_gate.yaml \
  --document-id F02 \
  --stage num_unit_normalization
```

### If You Modified Quantity Definitions

**Step 1: Syntax Validation**
```bash
python -c "import yaml; yaml.safe_load(open('config/quantity_definitions.yaml'))"
echo "Syntax OK"
```

**Step 2: Run Test Suite**
```bash
pytest tests/ -v
```

**Step 3: Validate Unit Conversions**
```bash
# Write a small test script
python -c "
from src.catalyst_knowledge.core.num_unit_normalizer import normalize_quantity
result = normalize_quantity('100 kJ/mol', 'activation_energy')
print(f'Normalized: {result}')
"
```

### If You Modified Proposed Schemas

**Step 1: Syntax Validation**
```bash
python -c "import yaml; yaml.safe_load(open('proposed_schemas/figure_schema_v1.yaml'))"
echo "Syntax OK"
```

**Step 2: Validate Schema Structure**
```bash
# Write a small validation script
python -c "
import yaml
from pathlib import Path
schema = yaml.safe_load(Path('proposed_schemas/figure_schema_v1.yaml').read_text())
print(f'Schema keys: {list(schema.keys())}')
"
```

---

## Running Tests

### Full Test Suite

```bash
pytest tests/ -v
```

### With Coverage

```bash
pytest tests/ --cov=src/catalyst_knowledge --cov-report=html
# Open htmlcov/index.html in browser
```

### Specific Test Categories

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Pipeline tests only
pytest tests/pipeline/ -v

# Fixture validation
pytest tests/test_fixture_validation.py -v
```

### Expected Test Results

| Test Category | Count | Status |
|---------------|-------|--------|
| Unit tests | ~100 | PASS |
| Integration tests | ~30 | PASS |
| Pipeline tests | ~26 | PASS |
| Fixture validation | 1 | PASS |
| **Total** | **~156** | **PASS** |

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'catalyst_knowledge'"

**Solution**: Add `src/` to Python path
```bash
# On Windows
set PYTHONPATH=%CD%\src;%PYTHONPATH%

# On macOS/Linux
export PYTHONPATH=$PWD/src:$PYTHONPATH
```

### Issue: "LLM_API_KEY not set"

**Solution**: Set environment variables (see Installation Step 4)

### Issue: "MinerU not found"

**Solution**: Install MinerU separately
- GitHub: https://github.com/opendatalab/MinerU
- Note: Large installation with model weights

### Issue: "API call failed: 401 Unauthorized"

**Solution**: Check your SiliconFlow API key
- Verify key is correct
- Check account balance
- Ensure API base URL is correct

### Issue: "Tests fail after modifying prompts"

**Solution**: This is expected if you changed extraction behavior
- Review the failing tests
- Update test expectations if the change is intentional
- Re-run tests to confirm

### Issue: "HTML report is blank or missing data"

**Solution**: Check that pipeline ran successfully
```bash
# Look for error messages in the console output
# Check that output files exist
ls runs/*/reports/*.json
```

### Issue: "Coverage dropped below 80%"

**Solution**: Add tests for new code
```bash
# See what's not covered
pytest tests/ --cov=src/catalyst_knowledge --cov-report=term-missing

# Add tests for uncovered lines
```

---

## Performance Benchmarks

### F02 Example

| Stage | Time | Cost |
|-------|------|------|
| PDF parsing (MinerU) | ~2 min | Free |
| Document IR | ~10 sec | Free |
| Figure parsing | ~30 sec | Free |
| VLM figure science (9 figures) | ~30 min | ~$1.50 |
| Table parsing | ~20 sec | Free |
| Table science | ~10 sec | Free |
| Science extraction V2 (6 dimensions) | ~15 min | ~$0.50 |
| Evidence verification | ~5 min | Free |
| HTML generation | ~5 sec | Free |
| **Total** | **~55 min** | **~$2.00** |

### Typical Paper (20 pages, 10 figures, 5 tables)

| Metric | Value |
|--------|-------|
| Processing time | 60-90 minutes |
| API cost | $2-3 |
| HTML report size | 3-5 MB |
| VLM records | 150-200 |
| Knowledge objects | 50-100 |

---

## Advanced Usage

### Custom Pipeline Configuration

Create a custom config file:
```yaml
# config/my_custom_pipeline.yaml
extends: pipeline_014_real_e2e_gate.yaml

stages:
  vlm_figure_science:
    enabled: false  # Skip VLM to save cost
  
  science_extraction_v2:
    prompt_config: config/prompts/my_custom_prompt.yaml
```

Run with custom config:
```bash
python scripts/run_pipeline.py --config config/my_custom_pipeline.yaml
```

### Batch Processing

Process multiple documents:
```bash
for doc in doc1 doc2 doc3; do
  python scripts/run_pipeline.py \
    --config config/pipeline_014_real_e2e_gate.yaml \
    --document-id $doc \
    --mineru-output mineru_output/$doc/
done
```

### Debug Mode

Enable verbose logging:
```bash
python scripts/run_pipeline.py \
  --config config/pipeline_014_real_e2e_gate.yaml \
  --document-id F02 \
  --log-level DEBUG
```

---

## Support

### Documentation

- [README.md](README.md) — Project overview
- [AGENTS.md](AGENTS.md) — AI agent protocol
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines
- [docs/PROMPT_SCHEMA_CATALOG.md](docs/PROMPT_SCHEMA_CATALOG.md) — Prompt/schema inventory
- [docs/PIPELINE_OVERVIEW.md](docs/PIPELINE_OVERVIEW.md) — Pipeline architecture

### Getting Help

1. Check this guide first
2. Search existing GitHub Issues
3. Ask in GitHub Discussions
4. Create a new Issue if needed

---

**Last Updated**: 2026-11-07  
**Version**: 1.0.0
