# Contributing to Catalyst Knowledge Expert Kit

Thank you for your interest in contributing! This document provides guidelines for both domain experts (catalysis researchers) and framework engineers.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [How Can I Contribute?](#how-can-i-contribute)
3. [For Domain Experts](#for-domain-experts)
4. [For Framework Engineers](#for-framework-engineers)
5. [Pull Request Process](#pull-request-process)
6. [Style Guidelines](#style-guidelines)
7. [Community](#community)

---

## Code of Conduct

- Be respectful and inclusive
- Focus on what is best for the project
- Accept constructive criticism gracefully
- Prioritize scientific accuracy over speed
- Protect the framework integrity

---

## How Can I Contribute?

### Reporting Bugs

**Before creating an issue, please check:**
- Has this been reported before? (search existing issues)
- Can you reproduce it reliably?
- Is it a framework bug or a domain-specific issue?

**Framework Bugs:**
- Use label: `framework-bug`
- Include: file path, line number, error message, steps to reproduce
- Do NOT attempt to fix directly

**Domain/Extraction Bugs:**
- Use label: `extraction-bug`
- Include: document ID, expected vs. actual extraction, prompt version
- May propose fix via PR (if in allowed modification list)

### Suggesting Enhancements

**Framework Enhancements:**
- Use label: `framework-enhancement`
- Describe the use case and why current framework is insufficient
- Wait for PI approval before implementation

**Domain Enhancements:**
- Use label: `enhancement`
- If in allowed modification list (see AGENTS.md), submit PR directly
- If uncertain, ask in Issue first

### Contributing Code

**Allowed Modifications (No PI Approval Required):**
- `config/prompts/**` — LLM extraction prompts
- `config/audit_anchors.yaml` — Physical plausibility ranges
- `config/quantity_definitions.yaml` — Unit conversions
- `proposed_schemas/**` — Candidate schema extensions
- `docs/**` — Documentation
- `examples/` — New examples (do not modify F02 without permission)

**Forbidden Modifications (Framework Code):**
- `src/**` — Core pipeline logic
- `scripts/**` — Execution scripts (except HTML generator with approval)
- `tests/**` — Test suite
- `config/pipeline*.yaml` — Pipeline configuration

See [AGENTS.md](AGENTS.md) for complete rules.

---

## For Domain Experts

### What You Can Do

1. **Refine Extraction Prompts**
   - Modify `config/prompts/science_extraction_v2.yaml`
   - Add domain-specific guidance for catalyst terminology
   - Adjust the six extraction dimensions

2. **Adjust Physical Plausibility Checks**
   - Edit `config/audit_anchors.yaml`
   - Update realistic ranges for catalysis quantities
   - Add new quantity types

3. **Extend Quantity Definitions**
   - Modify `config/quantity_definitions.yaml`
   - Add new unit conversions or validation rules

4. **Propose Schema Extensions**
   - Refine proposed schemas in `proposed_schemas/`
   - These are candidates for future production use

5. **Review HTML Reports**
   - Open `examples/F02/F02_knowledge_report_v3.html`
   - Verify scientific accuracy
   - Report discrepancies via GitHub Issues

### What You Cannot Modify

The following are **framework code** and must not be modified:
- `src/**` — Core pipeline logic, adapters, schema validation
- `scripts/**` — Pipeline execution scripts (except HTML generator)
- `tests/**` — Test suite
- `config/pipeline*.yaml` — Pipeline configuration and DAG

**If you discover a bug in framework code**, please submit a GitHub Issue with the label `framework-bug`. Do NOT attempt to modify these files directly.

### Workflow for Domain Experts

1. **Fork the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Catalyst-Knowledge-Expert-Kit.git
   cd Catalyst-Knowledge-Expert-Kit
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/improve-catalyst-design-prompt
   ```

3. **Make your changes**
   - Edit the relevant files (e.g., `config/prompts/science_extraction_v2.yaml`)
   - Follow the style guidelines below

4. **Validate your changes**
   ```bash
   # Syntax check
   python -c "import yaml; yaml.safe_load(open('config/prompts/science_extraction_v2.yaml'))"
   
   # Run tests
   pytest tests/ -v
   ```

5. **Test on a real document** (if modifying prompts)
   ```bash
   # Re-run F02 extraction with new prompts
   python scripts/run_pipeline.py --config config/pipeline_014_real_e2e_gate.yaml --document-id F02
   python scripts/generate_html_knowledge_report_v3.py
   # Open examples/F02/F02_knowledge_report_v3.html in browser
   ```

6. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(prompts): Improve catalyst design extraction guidance"
   ```

7. **Push to your fork**
   ```bash
   git push origin feature/improve-catalyst-design-prompt
   ```

8. **Submit a pull request**
   - Go to https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit/pulls
   - Click "New pull request"
   - Select your branch
   - Fill in the PR template
   - Request review from `@domain-expert-assistant`

---

## For Framework Engineers

### Your Responsibilities

1. **Protect the framework**
   - Validate that PRs do not modify framework code without approval
   - Run regression tests after any change
   - Report framework bugs as Issues

2. **Maintain test coverage**
   - Add tests for new features
   - Ensure coverage ≥ 80%
   - Run full test suite before merging

3. **Support domain experts**
   - Help them understand prompt/schema structure
   - Validate their changes don't break extraction
   - Generate before/after comparisons

4. **Keep documentation current**
   - Update README.md, docs/, and inline comments
   - Validate examples still work
   - Update PROMPT_SCHEMA_CATALOG.md if needed

### Workflow for Framework Engineers

1. **Review incoming PRs**
   - Check that no framework files are modified (unless PI-approved)
   - Validate syntax and tests
   - Provide constructive feedback

2. **Run regression tests**
   ```bash
   pytest tests/ --cov=src/catalyst_knowledge --cov-report=html
   ```

3. **Validate examples**
   ```bash
   python scripts/generate_html_knowledge_report_v3.py
   # Open examples/F02/F02_knowledge_report_v3.html
   ```

4. **Merge approved PRs**
   - Ensure all CI checks pass
   - At least 1 human review approval
   - No unresolved comments

5. **Handle framework bugs**
   - Create GitHub Issue with label `framework-bug`
   - Assign to PI or framework owner
   - Do NOT fix directly without approval

---

## Pull Request Process

### Before Submitting

1. **Check the modification rules**
   - See [AGENTS.md](AGENTS.md) for what you can/cannot modify
   - If modifying framework code, get PI approval first

2. **Validate your changes**
   - Syntax check all YAML files
   - Run test suite: `pytest tests/`
   - Check coverage: `pytest tests/ --cov=src/catalyst_knowledge`

3. **Update documentation**
   - If behavior changed, update relevant docs
   - Update PROMPT_SCHEMA_CATALOG.md if prompts/schemas changed

4. **Test on real data** (if applicable)
   - Re-run F02 example
   - Validate HTML report
   - Compare before/after

### PR Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Files Modified
- `path/to/file1` — Description of change
- `path/to/file2` — Description of change

## Testing
- [ ] Syntax validation passed
- [ ] Test suite passed: `pytest tests/`
- [ ] Coverage ≥ 80% (if src/ modified)
- [ ] Example validated (if prompts modified)

## Checklist
- [ ] My code follows the style guidelines
- [ ] I have commented my code (if complex)
- [ ] I have updated the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective (if applicable)

## Screenshots (if applicable)
Add screenshots to help explain your changes.

## Additional Notes
Any additional information for reviewers.
```

### Review Process

1. **Automated CI checks**
   - Lint: `flake8 src/ scripts/ tests/`
   - Type check: `mypy src/`
   - Tests: `pytest tests/`
   - Coverage: Must not drop below 80%

2. **Human review**
   - Framework Guardian validates no framework files modified
   - Domain Expert validates scientific accuracy (if prompts changed)
   - Test Engineer validates test coverage

3. **Merge criteria**
   - All CI checks pass
   - At least 1 human review approval
   - No unresolved comments
   - Documentation updated (if applicable)

---

## Style Guidelines

### Python Code

- Follow PEP 8
- Use type hints for function signatures
- Write docstrings for all public functions/classes
- Maximum line length: 100 characters
- Use `black` for formatting: `black src/ scripts/ tests/`
- Use `flake8` for linting: `flake8 src/ scripts/ tests/`
- Use `mypy` for type checking: `mypy src/`

### YAML Files

- Use 2-space indentation
- Quote strings that contain special characters
- Use descriptive keys (snake_case)
- Add comments for complex sections
- Validate syntax: `python -c "import yaml; yaml.safe_load(open('file.yaml'))"`

### Documentation

- Use Markdown (.md) format
- Write in clear, concise English
- Include code examples where helpful
- Update table of contents if adding sections
- Proofread before submitting

### Commit Messages

Format:
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation
- `style` — Formatting (no code change)
- `refactor` — Code restructuring
- `test` — Adding tests
- `chore` — Maintenance

Examples:
```
feat(prompts): Add selectivity extraction guidance

Include specific instructions for extracting selectivity values
with units and conditions. Addresses Issue #42.
```

```
fix(schema): Correct unit conversion for activation energy

Was using kJ/mol but schema expects J/mol. Added conversion
factor in quantity_definitions.yaml.
```

---

## Community

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and ideas
- **GitHub Pull Requests**: Code contributions

### Getting Help

- Check the documentation first (README.md, docs/)
- Search existing Issues and Discussions
- Ask in GitHub Discussions
- Tag relevant maintainers: `@JinhZhao`

### Recognition

Contributors will be acknowledged in:
- README.md (Contributors section)
- Release notes
- Academic publications (if applicable)

---

## Thank You!

Your contributions help make this project better for everyone in the catalysis research community. Whether you're fixing a typo in the documentation, refining extraction prompts, or proposing schema extensions, your work is valued and appreciated.

---

**Last Updated**: 2026-11-07  
**Version**: 1.0.0
